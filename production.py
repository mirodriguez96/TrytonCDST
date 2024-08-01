from trytond.wizard import (Wizard, StateReport, StateView, Button,
                            StateTransition)
from trytond.modules.company import CompanyReport
from trytond.transaction import Transaction
from trytond.model import fields, ModelView
from trytond.exceptions import UserError
from trytond.pool import Pool, PoolMeta
from trytond.report import Report

from decimal import Decimal
from itertools import chain
from sql import Table
import datetime
import calendar


# Heredamos del modelo sale.sale para agregar el campo id_tecno
class Production(metaclass=PoolMeta):
    'Production'
    __name__ = 'production'
    id_tecno = fields.Char('Id Tabla Sqlserver', required=False)
    move = fields.Many2One('account.move',
                           'Account Move',
                           states={'readonly': True})

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

    @classmethod
    def delete_productions_account(cls, production):
        Actualizacion = Pool().get('conector.actualizacion')
        actualizacion = Actualizacion.create_or_update('PRODUCCION')
        Production = Pool().get('production')
        stock_move = Table('stock_move')
        account_move = Table('account_move')
        Period = Pool().get('stock.period')
        cursor = Transaction().connection.cursor()

        logs = {}
        exceptions = []
        to_save = []
        to_delete = []

        for prod in production:
            dat = str(prod.effective_date).split()[0].split('-')
            year = int(dat[0])
            month = int(dat[1])
            _, day = calendar.monthrange(year, month)
            date = f"{year}-{month}-{day}"
            validate_period = Period.search([('date', '=', date)])
            if validate_period:
                period = validate_period[0].state
                if period == 'closed':
                    print("periodo cerrado")
                    exceptions.append(prod.id_tecno)
                    logs[prod.
                         id_tecno] = "EL PERIODO DEL DOCUMENTO SE ENCUENTRA \
                    CERRADO Y NO ES POSIBLE MODIFICAR LA PRODUCCION"

                    actualizacion.add_logs(logs)
                    return False

            if prod.state == 'draft':
                continue

            if prod.move:
                # Se agrega a la lista el asiento que debe ser eliminado
                to_delete.append(prod.move.id)
            inputs = [mv.id for mv in prod.inputs]
            outputs = [mv.id for mv in prod.outputs]
            moves = inputs + outputs
            if moves:
                cursor.execute(
                    *stock_move.update(columns=[stock_move.state],
                                       values=['draft'],
                                       where=stock_move.id.in_(moves)))
            prod.state = 'draft'
            to_save.append(prod)

        if to_delete:
            cursor.execute(
                *account_move.update(columns=[account_move.state],
                                     values=['draft'],
                                     where=account_move.id.in_(to_delete)))
            cursor.execute(*account_move.delete(
                where=account_move.id.in_(to_delete)))

        if to_save:
            Production.save(to_save)

        cls.delete_productions(production)
        return True

    @classmethod
    def delete_productions(cls, productions):
        pool = Pool()
        Move = pool.get('stock.move')
        Product = Pool().get('product.product')

        to_draft, to_delete = [], []
        id_products = []

        cursor = Transaction().connection.cursor()
        sql_table = cls.__table__()
        _today = datetime.date.today()

        for production in productions:
            # Save data of move stock to delete it
            for move in chain(production.inputs, production.outputs):
                id_products.append(move.product.id)
                if move.state != 'cancelled':
                    to_draft.append(move)
                else:
                    to_delete.append(move)

            # Delete data from table production
            try:
                ids = [production.id]
                cursor.execute(*sql_table.delete(
                    where=sql_table.id.in_(ids or [None])))
                print("produccion eliminada")
            except Exception as error:
                print(error)
                return False
        Move.draft(to_draft)
        Move.delete(to_delete)

        products = Product.search([('id', 'in', id_products)])
        Product.recompute_cost_price(products, start=_today)

    # Función encargada de importar las producciones de TecnoCarnes a Tryton
    @classmethod
    def import_data_production(cls):
        print('RUN PRODUCTION')
        try:
            pool = Pool()
            Config = pool.get('conector.configuration')
            Actualizacion = pool.get('conector.actualizacion')
            Period = pool.get('account.period')
            Production = pool.get('production')
            Location = pool.get('stock.location')
            Product = pool.get('product.product')
            Template = pool.get('product.template')

            logs = {}
            to_created = []
            to_exception = []
            not_import = []
            data = []
            _today = datetime.date.today()
            actualizacion = Actualizacion.create_or_update('PRODUCCION')
            parametro = Config.get_data_parametros('177')
            valor_parametro = parametro[0].Valor.split(',')
            for tipo in valor_parametro:
                result = Config.get_documentos_tipo(None, tipo)
                if result:
                    data += result

            if not data:
                actualizacion.save()
                print("FINISH PRODUCTION")
                return

            for transformacion in data:
                data_products = []
                try:
                    sw = transformacion.sw
                    numero_doc = transformacion.Numero_documento
                    tipo_doc = transformacion.tipo
                    id_tecno = str(sw) + '-' + tipo_doc + '-' + str(numero_doc)
                    print(id_tecno)

                    if transformacion.anulado == 'S':
                        logs[id_tecno] = "Documento anulado en TecnoCarnes"
                        not_import.append(id_tecno)
                        continue

                    if transformacion.exportado == 'N':
                        already_production = Production.search([('id_tecno', '=',
                                                                id_tecno)])
                        if already_production:
                            delete_production = Production.delete_productions_account(
                                already_production)
                            if not delete_production:
                                continue
                            logs[id_tecno] = "La producción fue eliminada y "\
                                "se creara de nuevo"
                    fecha = str(
                        transformacion.Fecha_Hora_Factura).split()[0].split('-')
                    name = f"{fecha[0]}-{fecha[1]}"
                    fecha = datetime.date(int(fecha[0]), int(fecha[1]),
                                          int(fecha[2]))
                    validate_period = Period.search([('name', '=', name)])
                    if validate_period[0].state == 'close':
                        to_exception.append(id_tecno)
                        logs[id_tecno] = "EXCEPCION: EL PERIODO DEL DOCUMENTO \
                        SE ENCUENTRA CERRADO Y NO ES POSIBLE SU CREACION"

                        continue

                    reference = tipo_doc + '-' + str(numero_doc)
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
                        bodega = Location.search([('id_tecno', '=', line.IdBodega)
                                                  ])
                        if not bodega:
                            msg = f"EXCEPCION: No se encontro la bodega {line.IdBodega}"
                            logs[id_tecno] = msg
                            to_exception.append(id_tecno)
                            break
                        bodega, = bodega
                        producto = Product.search([
                            'OR', ('id_tecno', '=', line.IdProducto),
                            ('code', '=', line.IdProducto)
                        ])
                        if not producto:
                            msg = f"EXCEPCION: No se encontro el producto {line.IdProducto}"
                            logs[id_tecno] = msg
                            to_exception.append(id_tecno)
                            break

                        producto, = producto
                        if not producto.account_category.account_stock:
                            raise UserError('msg_missing_account_stock',
                                            producto.rec_name)
                        # Se valida si el producto esta creado en unidades para eliminar sus decimales
                        if producto.default_uom.symbol.upper() == 'U':
                            cantidad = float(int(cantidad))
                        data_products.append(producto.id)
                        transf = {
                            'product': producto.id,
                            'quantity': abs(cantidad),
                            'uom': producto.default_uom.id,
                            'planned_date': fecha,
                            'effective_date': fecha,
                        }
                        # Entrada (-1)
                        if cantidad < 0:
                            transf['from_location'] = bodega.storage_location.id
                            transf['to_location'] = bodega.production_location.id
                            if first:
                                first = False
                                # Se actualiza el producto para que sea producible
                                if not producto.template.producible:
                                    Template.write([producto.template],
                                                   {'producible': True})
                                production['product'] = producto.id
                                production['quantity'] = abs(cantidad)
                                production['uom'] = producto.default_uom.id
                            entradas.append(transf)
                        # Salida (+1)
                        elif cantidad > 0:
                            transf['from_location'] = bodega.production_location.id
                            transf['to_location'] = bodega.storage_location.id
                            valor_unitario = Decimal(0)
                            if line.Valor_Unitario:
                                valor_unitario = Decimal(
                                    round(line.Valor_Unitario, 2))
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
                    # Se crea y procesa las producciones
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

                    if data_products:
                        products_to_recalcule = Product.search([('id', 'in',
                                                                data_products)])
                        Product.recompute_cost_price(products_to_recalcule,
                                                     start=_today)
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
        except Exception as error:
            print(f'ERROR PRODUCCIONES: {error}')
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
        journal = account_configuration.get_multivalue('stock_journal',
                                                       company=rec.company.id)
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
        account_move.lines = account_move_lines
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
        assert type_.startswith('in_') or type_.startswith(
            'out_'), 'wrong type'
        # se comienza a crear la línea de asiento
        if not smove.product.account_category.account_stock:
            raise UserError('msg_missing_account_stock',
                            smove.product.rec_name)
        move_line = AccountMoveLine(
            account=smove.product.account_category.account_stock,
            party=smove.company.party)
        if ((type_ in {'in_production', 'in_warehouse'})
                and smove.product.cost_price_method != 'fixed'):
            unit_price = smove.unit_price
        else:
            unit_price = smove.cost_price or smove.product.cost_price
        unit_price = Uom.compute_price(smove.product.default_uom, unit_price,
                                       smove.uom)
        # amount = Decimal(str(smove.quantity)) * unit_price
        amount = smove.company.currency.round(
            Decimal(str(smove.quantity)) * unit_price)
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
            party=rec.company.party)
        if not amount:
            return
        if amount > Decimal('0.0'):
            move_line.debit = Decimal('0.0')
            move_line.credit = amount
        else:
            move_line.debit = -amount
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

    @classmethod
    def set_cost_from_moves(cls):
        pool = Pool()
        Move = pool.get('stock.move')
        try:
            productions = set()
            moves = Move.search([
                ('production_cost_price_updated', '=', True),
                ('production_input', '!=', None),
            ],
                order=[('effective_date', 'ASC')])
            for move in moves:
                if move.production_input not in productions:
                    cls.__queue__.set_cost([move.production_input])
                    productions.add(move.production_input)
            Move.write(moves, {'production_cost_price_updated': False})
        except Exception as error:
            print(f'ERROR PRODUCTION: {error}')


class ProductionReport(CompanyReport):
    'Production Report'
    __name__ = 'production.report'


class ProductionDetailedStart(ModelView):
    'Production Detailed Start'
    __name__ = 'production.detailed.start'
    company = fields.Many2One('company.company', 'Company', required=True)
    start_date = fields.Date('Start Date', required=True)
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
    start = StateView('production.detailed.start',
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
        }
        return action, data

    def transition_print_(self):
        return 'end'


class ProductionDetailedReport(Report):
    'Production Detailed Report'
    __name__ = 'production.detailed_report'

    @classmethod
    def get_context(cls, records, header, data):
        """Function to build data to report"""

        report_context = super().get_context(records, header, data)
        Production = Pool().get('production')
        production_data = {}

        domain = [
            ('company', '=', data['company']),
            ('effective_date', '>=', data['start_date']),
            ('effective_date', '<=', data['end_date']),
            ('state', '!=', 'draft'),
        ]
        productions = Production.search(domain)
        cls.set_outputs(productions, production_data)
        cls.set_inputs(productions, production_data)

        for production, data in production_data.items():
            total_sell_price = data['totals']['total_sell_price']
            total_prod_price = data['totals']['_total_cost_production']
            total_input_amount = data['totals']['total_estimated_amount']
            total_output_amount = data['totals']['total_production_amount']

            if total_prod_price != 0:
                margin = (total_sell_price - total_prod_price) / \
                    total_prod_price
                production_data[production]['totals']['margin'] = margin

            if total_input_amount != 0:
                performance = (total_output_amount/total_input_amount)
                production_data[production]['totals']['performance'] = performance

        report_context['records'] = production_data
        report_context['Decimal'] = Decimal
        return report_context

    @classmethod
    def set_outputs(cls, productions, production):
        """Function to save outputs and totals data"""

        for record in productions:
            estimated_amount = round(Decimal(record.quantity), 2)

            if record.number not in production:
                production[record.number] = {
                    'werehouse':
                    record.warehouse.name,
                    'location':
                    record.location.name,
                    'date':
                    record.effective_date,
                    'refference':
                    record.reference,
                    'not_production_amount_total': estimated_amount,
                    'outputs': {},
                    'inputs': {},
                    'totals': {},
                }

            if production[record.number]['totals'] == {}:
                production[record.number]['totals'] = {
                    'total_estimated_amount': 0,
                    'total_production_amount': 0,
                    'total_cost_production': 0,
                    '_total_cost_production': 0,
                    'total_sell_price': 0,
                    'margin': 0,
                    'performance': 0,
                }

            for pro in record.outputs:
                if pro.product.name not in production[
                        record.number]['outputs']:
                    production[record.number]['outputs'][pro.product.name] = {
                        'id_product': pro.product.code,
                        'udm': pro.product.template.default_uom.symbol,
                        'production_amount': 0,
                        'production_cost': 0,
                        'output_unit_cost': 0,
                        'sale_price': 0,
                        'sell_price': 0
                    }
                sale_price = 0
                if pro.product.list_price:
                    sale_price = pro.product.list_price
                    production[record.number]['outputs'][
                        pro.product.name]['sale_price'] = sale_price

                production_amount = round(Decimal(pro.quantity), 2)
                sell_price = production_amount * sale_price
                output_unit_cost = round(pro.unit_price, 2)
                production_cost = round(production_amount * output_unit_cost)

                production[record.number]['outputs'][
                    pro.product.name]['production_amount'] += production_amount
                production[record.number]['outputs'][
                    pro.product.name]['sell_price'] += sell_price
                production[record.number]['outputs'][pro.product.name][
                    'output_unit_cost'] += output_unit_cost
                production[record.number]['outputs'][pro.product.name][
                    'production_cost'] += production_cost
                production[record.number][
                    'not_production_amount_total'] -= production_amount

                # create total values
                production[record.number]['totals']['total_sell_price'] += sell_price
                production[record.number][
                    'totals']['total_production_amount'] += production_amount
                production[record.number][
                    'totals']['total_cost_production'] += production_cost

    @classmethod
    def set_inputs(cls, productions, production):
        """Function to save inputs data"""

        for record in productions:

            for pro in record.inputs:
                unit_cost_estimated_prod = 0
                production_cost = 0

                inputs_amount = round(Decimal(pro.quantity),
                                      2) if pro.quantity else 0
                if pro.cost_price:
                    unit_cost_estimated_prod = pro.cost_price
                    _production_cost = round(
                        (unit_cost_estimated_prod * inputs_amount), 2)
                    production_cost = (_production_cost * -1)
                if pro.product.name not in production[
                        record.number]['inputs']:
                    production[record.number]['inputs'][pro.product.name] = {
                        'id_product': pro.product.code,
                        'udm': pro.product.template.default_uom.symbol,
                        'inputs_amount': inputs_amount,
                        'estimated_unit_cost': unit_cost_estimated_prod,
                        'production_cost': production_cost,
                    }
                else:
                    production[record.number]['inputs'][
                        pro.product.name]['inputs_amount'] += inputs_amount
                    production[record.number]['inputs'][
                        pro.product.name]['production_cost'] += production_cost

                production[record.number][
                    'totals']['total_cost_production'] += production_cost
                production[record.number][
                    'totals']['_total_cost_production'] += _production_cost
                production[record.number][
                    'totals']['total_estimated_amount'] += inputs_amount


class ProductionForceDraft(Wizard):
    'Production Force Draft'
    __name__ = 'production.force_draft'
    start_state = 'force_draft'
    force_draft = StateTransition()

    def transition_force_draft(self):
        ids_ = Transaction().context['active_ids']
        if ids_:
            Actualizacion = Pool().get('conector.actualizacion')
            actualizacion = Actualizacion.create_or_update('PRODUCCION')
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

                if validate == 'close':
                    exceptions.append(prod.id)
                    logs[
                        prod.
                        id] = "EXCEPCION: EL PERIODO DEL DOCUMENTO SE ENCUENTRA CERRADO \
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
                    cursor.execute(
                        *stock_move.update(columns=[stock_move.state],
                                           values=['draft'],
                                           where=stock_move.id.in_(moves)))
                prod.state = 'draft'
                to_save.append(prod)
            if to_delete:
                cursor.execute(
                    *account_move.update(columns=[account_move.state],
                                         values=['draft'],
                                         where=account_move.id.in_(to_delete)))
                cursor.execute(*account_move.delete(
                    where=account_move.id.in_(to_delete)))
            if to_save:
                Production.save(to_save)
        if exceptions:
            actualizacion.add_logs(logs)
            raise UserError(
                'AVISO',
                f'Los documentos {exceptions} no pueden ser forzados a borrador porque su periodo se encuentra cerrado'
            )
        return 'end'
