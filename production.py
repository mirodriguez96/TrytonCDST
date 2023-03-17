from trytond.model import fields
from trytond.pool import Pool, PoolMeta
from decimal import Decimal
import datetime


#Heredamos del modelo sale.sale para agregar el campo id_tecno
class Production(metaclass=PoolMeta):
    'Production'
    __name__ = 'production'
    id_tecno = fields.Char('Id Tabla Sqlserver', required=False)
    move = fields.Many2One('account.move', 'Account Move', states={'readonly': True})

    @classmethod
    def done(cls, records):
        super(Production, cls).done(records)
        for rec in records:
            cls.create_account_move(rec)

    # Función encargada de importar las producciones de TecnoCarnes a Tryton
    @classmethod
    def import_data_production(cls):
        print('RUN PRODUCTION')
        pool = Pool()
        Config = pool.get('conector.configuration')
        Actualizacion = pool.get('conector.actualizacion')
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
        logs = []
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
                    msg = f"{id_tecno} Documento anulado en TecnoCarnes"
                    logs.append(msg)
                    not_import.append(id_tecno)
                    continue
                existe = Production.search([('id_tecno', '=', id_tecno)])
                if existe:
                    msg = f"La producción {id_tecno} ya existe en Tryton"
                    logs.append(msg)
                    to_created.append(id_tecno)
                    continue
                fecha = str(transformacion.Fecha_Hora_Factura).split()[0].split('-')
                fecha = datetime.date(int(fecha[0]), int(fecha[1]), int(fecha[2]))
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
                        msg = f"EXCEPCION {id_tecno} - No se encontro la bodega {line.IdBodega}"
                        logs.append(msg)
                        to_exception.append(id_tecno)
                        break
                    bodega, = bodega
                    producto = Product.search(['OR', ('id_tecno', '=', line.IdProducto), ('code', '=', line.IdProducto)])
                    if not producto:
                        msg = f"EXCEPCION {id_tecno} - No se encontro el producto {line.IdProducto}"
                        logs.append(msg)
                        to_exception.append(id_tecno)
                        break
                    producto, = producto
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
                                msg = f"EXCEPCION {id_tecno} - Valor de venta en 0 en tryton y tecnoCarnes del producto {line.IdProducto}"
                                logs.append(msg)
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
                    msg = f"EXCEPCION {id_tecno} - No se encontraron líneas de entrada para la producción"
                    logs.append(msg)
                    to_exception.append(id_tecno)
                    continue
                if not salidas:
                    msg = f"EXCEPCION {id_tecno} - No se encontraron líneas de salida para la producción"
                    logs.append(msg)
                    to_exception.append(id_tecno)
                    continue
                production['inputs'] = [('create', entradas)]
                production['outputs'] = [('create', salidas)]
                #Se crea y procesa las producciones
                producciones = Production.create([production])
                Production.wait(producciones)
                Production.assign(producciones)
                Production.run(producciones)
                Production.done(producciones)
                to_created.append(id_tecno)
            except Exception as e:
                msg = f"EXCEPCION {id_tecno}: {str(e)}"
                logs.append(msg)
                to_exception.append(id_tecno)
        Actualizacion.add_logs(actualizacion, logs)
        for idt in not_import:
            Config.update_exportado(idt, 'X')
        for idt in to_exception:
            Config.update_exportado(idt, 'E')
        for idt in to_created:
            Config.update_exportado(idt, 'T')
        print('FINISH PRODUCTION')


    #Función encargada de revertir las producciones hechas
    @classmethod
    def reverse_production(cls, productions):
        pool = Pool()
        Production = pool.get('production')
        Move = pool.get('stock.move')
        reverse = Production.copy(productions)
        to_reverse = []
        for production in reverse:
            to_inputs = []
            for output in production.outputs:
                inp = Move()
                inp.product = output.product
                inp.quantity = output.quantity
                inp.uom = output.uom
                inp.from_location = output.to_location
                inp.to_location = output.from_location
                to_inputs.append(inp)
            to_outputs = []
            for input in production.inputs:
                out = Move()
                out.product = input.product
                out.quantity = input.quantity
                out.uom = input.uom
                out.from_location = input.to_location
                out.to_location = input.from_location
                out.unit_price = input.product.template.list_price
                to_outputs.append(out)
            production.inputs = to_inputs
            production.outputs = to_outputs
            to_reverse.append(production)
        #print(to_reverse)
        Production.save(to_reverse)

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
        account_move_lines = []
        for move in rec.inputs:
            move_line = cls._get_account_stock_move(move)
            if move_line:
                account_move_lines.append(move_line)
        for move in rec.outputs:
            move_line = cls._get_account_stock_move(move)
            if move_line:
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
