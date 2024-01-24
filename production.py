from trytond.model import fields, ModelView
from trytond.pool import Pool, PoolMeta
from decimal import Decimal
import datetime
from trytond.exceptions import UserError
from trytond.modules.company import CompanyReport
from trytond.report import Report
from trytond.wizard import (
    Wizard, StateReport, StateView, Button, StateTransition)
from trytond.transaction import Transaction
from sql import Table


#Heredamos del modelo sale.sale para agregar el campo id_tecno
class Production(metaclass=PoolMeta):
    'Production'
    __name__ = 'production'
    id_tecno = fields.Char('Id Tabla Sqlserver', required=False)
    move = fields.Many2One('account.move', 'Account Move', states={'readonly': True})

    @classmethod
    def done(cls, records):
        super(Production, cls).done(records)
        pool = Pool()
        Revision = pool.get('product.cost_price.revision')
        AverageCost = pool.get('product.average_cost')
        to_update = {} 
        done_revision = []
        done_cost = []
        for rec in records:
            print(rec)
            for inputs in rec.inputs:
                inputs.origin = rec
                inputs.save()
            cls.create_account_move(rec)
            for move in rec.outputs:
                move.origin = rec
                move.save()
                product = move.product
                revision = {
                    "company": 1,
                    "product": product.id,
                    "template": product.template.id,
                    "cost_price": product.cost_price,
                    "date": datetime.date.today(),
                }
                done_revision.append(revision)

                data = {
                    "stock_move": move.id,
                    "product": product.id,
                    "effective_date": datetime.date.today(),
                    "cost_price": product.cost_price,
                }
                done_cost.append(data)

                if product not in to_update:
                    to_update[product.code] = product

        if done_revision:         
            Revision.create(done_revision)
        if data:
            AverageCost.create(done_cost)

        if to_update:

            # Se actualiza el costo para los productos (relacioandos) hijos
            Product = Pool().get('product.product')
            Product.update_product_parent(to_update)

    # Función encargada de importar las producciones de TecnoCarnes a Tryton
    @classmethod
    def import_data_production(cls):
        print('RUN PRODUCTION')
        pool = Pool()
        Config = pool.get('conector.configuration')
        Actualizacion = pool.get('conector.actualizacion')
        Period = pool.get('account.period')
        actualizacion = Actualizacion.create_or_update('PRODUCCION')
        parametro = Config.get_data_parametros('177')
        valor_parametro = parametro[0].Valor.split(',')
        data = []
        for tipo in valor_parametro:
            result = Config.get_documentos_tipo(None, tipo)
            if result:
                data += result
        if not data:
            actualizacion.save()
            print("FINISH PRODUCTION")
            return
        Production = pool.get('production')
        Location = pool.get('stock.location')
        Product = pool.get('product.product')
        Template = pool.get('product.template')
        logs = {}
        to_created = []
        to_exception = []
        not_import = []
        for transformacion in data:
            try:
                sw = transformacion.sw
                numero_doc = transformacion.Numero_documento
                tipo_doc = transformacion.tipo
                id_tecno = str(sw)+'-'+tipo_doc+'-'+str(numero_doc)
                print(id_tecno)
                if transformacion.anulado == 'S':
                    logs[id_tecno] = "Documento anulado en TecnoCarnes"
                    not_import.append(id_tecno)
                    continue
                existe = Production.search([('id_tecno', '=', id_tecno)])
                if existe:
                    logs[id_tecno] = "La producción ya existe en Tryton"
                    to_created.append(id_tecno)
                    continue
                fecha = str(transformacion.Fecha_Hora_Factura).split()[0].split('-')
                fecha = datetime.date(int(fecha[0]), int(fecha[1]), int(fecha[2]))
                name = f"{fecha[0]}-{fecha[1]}"                 
                validate_period = Period.search([('name', '=', name)])
                if validate_period[0].state == 'close':
                    to_exception.append(id_tecno)
                    logs[id_tecno] = "EXCEPCION: EL PERIODO DEL DOCUMENTO SE ENCUENTRA CERRADO \
                    Y NO ES POSIBLE SU CREACION"
                    continue
                reference = tipo_doc+'-'+str(numero_doc)
                id_bodega = transformacion.bodega
                bodega, = Location.search([('id_tecno', '=', id_bodega)])
                production = {
                    'id_tecno': id_tecno,
                    'reference': reference,
                    'planned_date': fecha,
                    'planned_start_date': fecha,
                    'effective_date': fecha,
                    'effective_start_date': fecha,
                    'warehouse': bodega.id,
                    'location': bodega.production_location.id,
                }
                lines = Config.get_lineasd_tecno(id_tecno)
                entradas = []
                salidas = []
                first = True
                for line in lines:
                    cantidad = float(line.Cantidad_Facturada)
                    bodega = Location.search([('id_tecno', '=', line.IdBodega)])
                    if not bodega:
                        msg = f"EXCEPCION: No se encontro la bodega {line.IdBodega}"
                        logs[id_tecno] = msg
                        to_exception.append(id_tecno)
                        break
                    bodega, = bodega
                    producto = Product.search(['OR', ('id_tecno', '=', line.IdProducto), ('code', '=', line.IdProducto)])
                    if not producto:
                        msg = f"EXCEPCION: No se encontro el producto {line.IdProducto}"
                        logs[id_tecno] = msg
                        to_exception.append(id_tecno)
                        break
                    producto, = producto
                    if not producto.account_category.account_stock:
                        raise UserError('msg_missing_account_stock', producto.rec_name)
                    # Se valida si el producto esta creado en unidades para eliminar sus decimales
                    if producto.default_uom.symbol.upper() == 'U':
                        cantidad = float(int(cantidad))
                    transf = {
                        'product': producto.id,
                        'quantity': abs(cantidad),
                        'uom': producto.default_uom.id,
                        'planned_date': fecha,
                        'effective_date': fecha,
                    }
                    #Entrada (-1)
                    if cantidad < 0:
                        transf['from_location'] = bodega.storage_location.id
                        transf['to_location'] = bodega.production_location.id
                        if first:
                            first = False
                            #Se actualiza el producto para que sea producible
                            if not producto.template.producible:
                                Template.write([producto.template], {'producible': True})
                            production['product'] = producto.id
                            production['quantity'] = abs(cantidad)
                            production['uom'] = producto.default_uom.id
                        entradas.append(transf)
                    #Salida (+1)
                    elif cantidad > 0:
                        transf['from_location'] = bodega.production_location.id
                        transf['to_location'] = bodega.storage_location.id
                        valor_unitario = Decimal(round(line.Valor_Unitario, 2))
                        transf['unit_price'] = valor_unitario
                        salidas.append(transf)
                        # Se valida que el precio de venta sea diferente de 0
                        if producto.list_price == 0:
                            if valor_unitario == 0:
                                msg = f"EXCEPCION: Valor de venta en 0 en tryton y tecnoCarnes del producto {line.IdProducto}"
                                logs[id_tecno] = msg
                                to_exception.append(id_tecno)
                                break
                            to_write = {
                                'sale_price_w_tax': valor_unitario,
                                'list_price': valor_unitario
                                }
                            Template.write([producto.template], to_write)
                if id_tecno in to_exception:
                    continue
                if not entradas:
                    msg = f"EXCEPCION: No se encontraron líneas de entrada para la producción"
                    logs[id_tecno] = msg
                    to_exception.append(id_tecno)
                    continue
                if not salidas:
                    msg = f"EXCEPCION: No se encontraron líneas de salida para la producción"
                    logs[id_tecno] = msg
                    to_exception.append(id_tecno)
                    continue
                production['inputs'] = [('create', entradas)]
                production['outputs'] = [('create', salidas)]
                #Se crea y procesa las producciones
                producciones = Production.create([production])
                for productions in producciones:
                    for inputs in productions.inputs:
                        inputs.origin = productions
                        inputs.save()
                    for outputs in productions.outputs:
                        outputs.origin = productions
                        outputs.save()
                Production.wait(producciones)
                Production.assign(producciones)
                Production.run(producciones)
                Production.done(producciones)
                to_created.append(id_tecno)
            except Exception as e:
                logs[id_tecno] = f"EXCEPCION: {str(e)}"
                to_exception.append(id_tecno)
        actualizacion.add_logs(logs)
        for idt in not_import:
            Config.update_exportado(idt, 'X')
        for idt in to_exception:
            Config.update_exportado(idt, 'E')
        for idt in to_created:
            Config.update_exportado(idt, 'T')
        print('FINISH PRODUCTION')


    # Función que recibe una producción y de acuerdo a esa información crea un asiento contable 
    @classmethod
    def create_account_move(cls, rec):
        pool = Pool()
        AccountConfiguration = pool.get('account.configuration')
        AccountMove = pool.get('account.move')
        Period = pool.get('account.period')
        period = Period(Period.find(rec.company.id, date=rec.planned_date))
        account_configuration = AccountConfiguration(1)
        journal = account_configuration.get_multivalue('stock_journal', company=rec.company.id)
        account_move = AccountMove()
        account_move.journal = journal
        account_move.period = period
        account_move.date = rec.planned_date
        account_move.description = f"Production {rec.number}"
        account_move.origin = str(rec)
        account_move_lines = []
        for move in rec.inputs:
            move_line = cls._get_account_stock_move(move)
            if move_line:
                move_line.origin = str(move)
                account_move_lines.append(move_line)
        for move in rec.outputs:
            move_line = cls._get_account_stock_move(move)
            if move_line:
                move_line.origin = str(move)
                account_move_lines.append(move_line)
        diff = 0
        for line in account_move_lines:
            if line.debit > 0:
                diff += line.debit
            else:
                diff -= line.credit
        move_line_adj = cls._get_account_stock_move_line(rec, diff)
        if move_line_adj:
            account_move_lines.append(move_line_adj)
        # Se agrega las líneas del asiento de acuerdo a las entradas y salidas de produccion
        account_move.lines=account_move_lines
        # Se crea y contabiliza el asiento
        AccountMove.save([account_move])
        AccountMove.post([account_move])
        # Se almacena el asiento en la produccion
        rec.move = account_move
        rec.save()

    # 3
    @classmethod
    def _get_account_stock_move_lines(cls, smove, type_):
        '''
        Return move lines for stock move
        '''
        pool = Pool()
        Uom = pool.get('product.uom')
        AccountMoveLine = pool.get('account.move.line')
        # instruccion que muestra error de tipo en caso que el movimiento de existencia no sea de entrada o salida
        assert type_.startswith('in_') or type_.startswith('out_'), 'wrong type'
        # se comienza a crear la línea de asiento
        if not smove.product.account_category.account_stock:
            raise UserError('msg_missing_account_stock', smove.product.rec_name)
        move_line = AccountMoveLine(account=smove.product.account_category.account_stock, party=smove.company.party)
        if ((type_ in {'in_production', 'in_warehouse'}) and smove.product.cost_price_method != 'fixed'):
            unit_price = smove.unit_price
        else:
            unit_price = smove.cost_price or smove.product.cost_price
        unit_price = Uom.compute_price(smove.product.default_uom, unit_price, smove.uom)
        # amount = Decimal(str(smove.quantity)) * unit_price
        amount = smove.company.currency.round(Decimal(str(smove.quantity)) * unit_price)
        # print(smove.product, amount)
        if type_.startswith('in_'):
            move_line.debit = amount
            move_line.credit = Decimal('0.0')
        else:
            move_line.debit = Decimal('0.0')
            move_line.credit = amount
        return move_line

    # 4
    @classmethod
    def _get_account_stock_move_line(cls, rec, amount):
        '''
        Return counterpart move line value for stock move
        '''
        pool = Pool()
        AccountMoveLine = pool.get('account.move.line')
        move_line = AccountMoveLine(
            account=rec.product.account_category.account_stock,
            party=rec.company.party
            )
        if not amount:
            return
        if amount > Decimal('0.0'):
            move_line.debit = Decimal('0.0')
            move_line.credit = amount
        else:
            move_line.debit = - amount
            move_line.credit = Decimal('0.0')
        return move_line

    # 2
    @classmethod
    def _get_account_stock_move_type(cls, smove):
        '''
        Get account move type
        '''
        type_ = (smove.from_location.type, smove.to_location.type)
        if type_ == ('storage', 'production'):
            return 'out_production'
        elif type_ == ('production', 'storage'):
            return 'in_production'

    # 1
    @classmethod
    def _get_account_stock_move(cls, smove):
        '''
        Return account move lines for stock move
        '''
        type_ = cls._get_account_stock_move_type(smove)
        if not type_:
            return
        account_move_lines = cls._get_account_stock_move_lines(smove, type_)
        return account_move_lines


class ProductionReport(CompanyReport):
    'Production Report'
    __name__ = 'production.report'


class ProductionDetailedStart(ModelView):
    'Production Detailed Start'
    __name__ = 'production.detailed.start'
    company = fields.Many2One('company.company', 'Company', required=True)
    grouped = fields.Boolean('Grouped', help='Grouped by products')
    start_date = fields.Date('Start Date')
    end_date = fields.Date('End Date', required=True)

    @staticmethod
    def default_company():
        return Transaction().context.get('company')

    @staticmethod
    def default_start_date():
        Date = Pool().get('ir.date')
        return Date.today()

    @staticmethod
    def default_end_date():
        Date = Pool().get('ir.date')
        return Date.today()


class ProductionDetailed(Wizard):
    'Production Detailed'
    __name__ = 'production.detailed'
    start = StateView(
        'production.detailed.start',
        'conector.production_detailed_start_view_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Print', 'print_', 'tryton-ok', default=True),
        ])
    print_ = StateReport('production.detailed_report')

    def do_print_(self, action):
        data = {
            'ids': [],
            'company': self.start.company.id,
            'start_date': self.start.start_date,
            'end_date': self.start.end_date,
            'grouped': self.start.grouped,
        }
        return action, data

    def transition_print_(self):
        return 'end'


class ProductionDetailedReport(Report):
    'Production Detailed Report'
    __name__ = 'production.detailed_report'

    @classmethod
    def get_context(cls, records, header, data):
        report_context = super().get_context(records, header, data)
        Production = Pool().get('production')
        production = {}
        domain = [
            ('company', '=', data['company']),
            ('effective_date', '>=', data['start_date']),
            ('effective_date', '<=', data['end_date']),
            ('write_uid', '!=', 0),
            ('state', '!=', 'draft'),]

        productions = Production.search(domain)

        # if not data['grouped']:
        #     records = productions
        # else:
        #     records = {}
        #     for p in productions:
        #         key = str(p.product.id) + p.location.name
        #         try:
        #             records[key]['quantity'] += p['quantity']
        #             records[key]['cost'] += p['cost']
        #         except:
        #             records[key] = p
        #             records[key]['effective_date'] = None
        #             records[key]['numero'] = None
        #     records = records.values() if records else []

        for record in productions:
            for pro in record.outputs:
                if record.number not in production:
                    production[record.number] = {
                        'werehouse': record.warehouse.name,
                        'location': record.location.name,
                        'date': record.effective_date,
                        'estimated_amount': Decimal(record.quantity),
                        'not_production_amount_total':Decimal(record.quantity),
                        'cost_base': record.cost,
                        'unit_cost': Decimal(record.cost)/Decimal(record.quantity) if record.quantity > 0 else 0,
                        'percentage': 0,
                        'percentage_merma': 0,
                        'merma_cost_total': 0,
                        'outputs': {}
                    }

                if pro.product.name not in production[record.number]['outputs']:
                    production[record.number]['outputs'][pro.product.name] ={
                        'udm': pro.product.template.default_uom.symbol,
                        'production_amount': 0,
                        'unit_cost_estimated': 0,
                        'unit_cost_production': 0,
                    }


                production_amount = Decimal(pro.quantity)
                cost_estimated = Decimal(record.cost)/Decimal(record.quantity) if record.quantity > 0 else 0
                unit_cost_production = Decimal(record.cost)/Decimal(pro.quantity) if pro.quantity > 0 else 0
                unit_cost_estimated = production_amount*cost_estimated


                production[record.number]['outputs'][pro.product.name]['production_amount'] += production_amount
                production[record.number]['outputs'][pro.product.name]['unit_cost_estimated'] += unit_cost_estimated
                production[record.number]['outputs'][pro.product.name]['unit_cost_production'] += unit_cost_production
                production[record.number]['percentage'] += production_amount
                production[record.number]['percentage_merma'] += Decimal(record.quantity) - production_amount
                production[record.number]['not_production_amount_total'] -= production_amount
                production[record.number]['merma_cost_total'] = cost_estimated*production[record.number]['not_production_amount_total']



        report_context['records'] = production
        report_context['Decimal'] = Decimal
        return report_context


class ProductionForceDraft(Wizard):
    'Production Force Draft'
    __name__ = 'production.force_draft'
    start_state = 'force_draft'
    force_draft = StateTransition()

    def transition_force_draft(self):
        ids_ = Transaction().context['active_ids']
        if ids_:
            Actualizacion = Pool().get('conector.actualizacion')
            actualizacion = Actualizacion.create_or_update('FORZAR BORRADOR PRESTAMOS')
            Production = Pool().get('production')
            stock_move = Table('stock_move')
            logs = {}
            exceptions = []
            account_move = Table('account_move')
            Period = Pool().get('account.period')
            cursor = Transaction().connection.cursor()
            to_save = []
            to_delete = []
            for prod in Production.browse(ids_):

                if prod.move:
                    validate = prod.move.state
                else:
                    dat = str(prod.effective_date).split()[0].split('-')
                    name = f"{dat[0]}-{dat[1]}"                 
                    validate_period = Period.search([('name', '=', name)])
                    validate = validate_period[0].state

                if  validate == 'close':
                    exceptions.append(prod.id)
                    logs[prod.id] = "EXCEPCION: EL PERIODO DEL DOCUMENTO SE ENCUENTRA CERRADO \
                    Y NO ES POSIBLE FORZAR A BORRADOR"
                    continue

                if prod.state == 'draft':
                    continue
                if prod.move:
                    # Se agrega a la lista el asiento que debe ser eliminado
                    to_delete.append(prod.move.id)
                inputs = [mv.id for mv in prod.inputs]
                outputs = [mv.id for mv in prod.outputs]
                moves = inputs + outputs
                if moves:
                    cursor.execute(*stock_move.update(
                        columns=[stock_move.state],
                        values=['draft'],
                        where=stock_move.id.in_(moves))
                    )
                prod.state = 'draft'
                to_save.append(prod)
            if to_delete:
                cursor.execute(*account_move.update(
                    columns=[account_move.state],
                    values=['draft'],
                    where=account_move.id.in_(to_delete))
                )
                cursor.execute(*account_move.delete(
                    where=account_move.id.in_(to_delete))
                    )
            if to_save:
                Production.save(to_save)
        if exceptions:    
            actualizacion.add_logs(logs)
            raise UserError('AVISO', f'Los documentos {exceptions} no pueden ser forzados a borrador porque su periodo se encuentra cerrado')
        return 'end'