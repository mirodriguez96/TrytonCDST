import datetime
from trytond.model import fields
from trytond.pool import Pool, PoolMeta
from trytond.exceptions import UserError, UserWarning
from trytond.transaction import Transaction
from decimal import Decimal
import logging
from sql import Table


__all__ = [
    'Sale',
    'Cron',
    ]


class Cron(metaclass=PoolMeta):
    'Cron'
    __name__ = 'ir.cron'

    @classmethod
    def __setup__(cls):
        super().__setup__()
        cls.method.selection.append(
            ('sale.sale|import_data_sale', "Importar ventas"),
            )
        cls.method.selection.append(
            ('sale.sale|update_pos_tecno', "Actualizar ventas POS"),
            )
        cls.method.selection.append(
            ('sale.sale|process_payment_pos', "Procesar pagos POS"),
            )


#Heredamos del modelo sale.sale para agregar el campo id_tecno
class Sale(metaclass=PoolMeta):
    'Sale'
    __name__ = 'sale.sale'
    id_tecno = fields.Char('Id Tabla Sqlserver', required=False)

    @classmethod
    def import_data_sale(cls):
        logging.warning('RUN VENTAS')
        data = cls.get_data_tecno()
        cls.add_sale(data)

    @classmethod
    def add_sale(cls, ventas_tecno):
        #Se crea o actualiza la fecha de importación
        actualizacion = cls.create_or_update()
        logs = []
        if not ventas_tecno:
            actualizacion.add_logs(actualizacion, logs)
            logging.warning('FINISH VENTAS')
            return
        pool = Pool()
        Sale = pool.get('sale.sale')
        SaleLine = pool.get('sale.line')
        SaleDevice = pool.get('sale.device')
        location = pool.get('stock.location')
        payment_term = pool.get('account.invoice.payment_term')
        Party = pool.get('party.party')
        Address = pool.get('party.address')
        coluns_doc = cls.get_columns_db_tecno('Documentos')
        Shop = pool.get('sale.shop')
        Tax = pool.get('account.tax')
        User = pool.get('res.user')
        Module = pool.get('ir.module')
        conector_actualizacion = Table('conector_actualizacion')
        cursor = Transaction().connection.cursor()
        
        company_operation = Module.search([('name', '=', 'company_operation'), ('state', '=', 'activated')])
        if company_operation:
            CompanyOperation = pool.get('company.operation_center')
            company_operation = CompanyOperation(1)
        col_param = cls.get_columns_db_tecno('TblParametro')
        venta_pos = cls.get_data_parametros('8')
        venta_electronica = cls.get_data_parametros('9')
        if venta_pos:
            venta_pos = venta_pos[0][col_param.index('Valor')].strip().split(',')
        if venta_electronica:
            venta_electronica = venta_electronica[0][col_param.index('Valor')].strip().split(',')
        to_create = []
        #Procedemos a realizar una venta
        for venta in ventas_tecno:
            sw = venta[coluns_doc.index('sw')]
            numero_doc = venta[coluns_doc.index('Numero_documento')]
            tipo_doc = venta[coluns_doc.index('tipo')].strip()
            id_venta = str(sw)+'-'+tipo_doc+'-'+str(numero_doc)
            existe = cls.buscar_venta(id_venta)
            if existe:
                cls.importado(id_venta)
                continue
            #print(id_venta)
            #Se trae la fecha de la venta y se adapta al formato correcto para Tryton
            fecha = str(venta[coluns_doc.index('Fecha_Orden_Venta')]).split()[0].split('-')
            fecha_date = datetime.date(int(fecha[0]), int(fecha[1]), int(fecha[2]))
            nit_cedula = venta[coluns_doc.index('nit_Cedula')]
            party = Party.search([('id_number', '=', nit_cedula)])
            if not party:
                msg2 = f' No se encontro el tercero {nit_cedula} de la venta {id_venta}'
                logging.error(msg2)
                logs.append(msg2)
                #Se elimina la fecha de última modificación para que se actualicen los terceros desde (primer importe) una fecha mayor rango
                cursor.execute(*conector_actualizacion.update(
                        columns=[conector_actualizacion.write_date],
                        values=[None],
                        where=conector_actualizacion.name == 'TERCEROS')
                    )
                continue
            party = party[0]
            #Se indica a que bodega pertenece
            id_tecno_bodega = venta[coluns_doc.index('bodega')]
            bodega = location.search([('id_tecno', '=', id_tecno_bodega)])
            if not bodega:
                msg2 = f' Bodega {id_tecno_bodega} no existe de la venta {id_venta}'
                logging.error(msg2)
                logs.append(msg2)
                continue
            bodega = bodega[0]
            shop = Shop.search([('warehouse', '=', bodega)])
            if not shop:
                msg2 = f' Bodega (shop) {id_tecno_bodega} no existe de la venta {id_venta}'
                logging.error(msg2)
                logs.append(msg2)
                continue
            shop = shop[0]
            #Se le asigna el plazo de pago correspondiente
            condicion = venta[coluns_doc.index('condicion')]
            plazo_pago = payment_term.search([('id_tecno', '=', condicion)])
            if not plazo_pago:
                msg2 = f'Plazo de pago {condicion} no existe de la venta {id_venta}'
                logging.error(msg2)
                logs.append(msg2)
                continue
            plazo_pago = plazo_pago[0]
            with Transaction().set_user(1):
                context = User.get_preferences()
            with Transaction().set_context(context, shop=shop.id, _skip_warnings=True):
                sale = Sale()
            sale.number = tipo_doc+'-'+str(numero_doc)
            sale.reference = tipo_doc+'-'+str(numero_doc)
            sale.id_tecno = id_venta
            sale.description = venta[coluns_doc.index('notas')].replace('\n', ' ').replace('\r', '')
            sale.invoice_type = 'C'
            sale.sale_date = fecha_date
            sale.party = party.id
            sale.invoice_party = party.id
            sale.shipment_party = party.id
            sale.warehouse = bodega
            sale.shop = shop
            sale.payment_term = plazo_pago
            #Se revisa si la venta es clasificada como electronica o pos y se cambia el tipo
            if tipo_doc in venta_electronica:
                sale.invoice_type = '1'
            elif tipo_doc in venta_pos:
                sale.invoice_type = 'P'
                sale.pos_create_date = fecha_date
                sale.self_pick_up = True
                #Busco la terminal y se la asigno
                sale_device, = SaleDevice.search([('id_tecno', '=', venta[coluns_doc.index('pc')])])
                sale.sale_device = sale_device
            #Se busca una dirección del tercero para agregar en la factura y envio
            address = Address.search([('party', '=', party.id)], limit=1)
            if address:
                sale.invoice_address = address[0].id
                sale.shipment_address = address[0].id
            
            #SE CREA LA VENTA
            sale.save()

            retencion_iva = False
            if venta.retencion_iva and venta.retencion_iva > 0:
                retencion_iva = True
            retencion_ica = False
            if venta.retencion_ica and venta.retencion_ica > 0:
                retencion_ica = True
            retencion_rete = False
            if venta.retencion_causada and venta.retencion_causada > 0:
                retencion_rete = True
            
            #Ahora traemos las lineas de producto para la venta a procesar
            documentos_linea = cls.get_line_where(str(sw), str(numero_doc), str(tipo_doc))
            col_line = cls.get_columns_db_tecno('Documentos_Lin')
            #create_line = []
            for lin in documentos_linea:
                linea = SaleLine()
                id_producto = str(lin[col_line.index('IdProducto')])
                producto = cls.buscar_producto(id_producto)
                linea.sale = sale
                linea.product = producto
                linea.type = 'line'
                linea.unit = producto.template.default_uom
                #Se verifica si es una devolución
                cant = float(lin[col_line.index('Cantidad_Facturada')])
                cantidad_facturada = abs(round(cant, 3))
                if linea.unit.id == 1:
                    cantidad_facturada = int(cantidad_facturada)
                #print(cant, cantidad_facturada)
                if sw == 2:
                    linea.quantity = cantidad_facturada * -1
                    #Se indica a que documento hace referencia la devolucion
                    sale.comment = f"DEVOLUCIÓN DE LA FACTURA {venta.Tipo_Docto_Base}-{str(venta.Numero_Docto_Base)}"
                else:
                    linea.quantity = cantidad_facturada
                #Se verifica si tiene activo el módulo centro de operaciones y se añade 1 por defecto
                if company_operation:
                    linea.operation_center = company_operation
                #Comprueba los cambios y trae los impuestos del producto
                linea.on_change_product()
                #Se verifica si el impuesto al consumo fue aplicado
                impuesto_consumo = lin[col_line.index('Impuesto_Consumo')]
                #A continuación se verifica las retenciones e impuesto al consumo
                impuestos_linea = []
                for impuestol in linea.taxes:
                    clase_impuesto = impuestol.classification_tax
                    if clase_impuesto == '05' and retencion_iva:
                        impuestos_linea.append(impuestol)
                    elif clase_impuesto == '06' and retencion_rete:
                        impuestos_linea.append(impuestol)
                    elif clase_impuesto == '07' and retencion_ica:
                        impuestos_linea.append(impuestol)
                    elif impuestol.consumo and impuesto_consumo > 0:
                        #Se busca el impuesto al consumo con el mismo valor para aplicarlo
                        tax = Tax.search([('consumo', '=', True), ('type', '=', 'fixed'), ('amount', '=', impuesto_consumo)])
                        if tax:
                            tax, = tax
                            impuestos_linea.append(tax)
                        else:
                            raise UserError('ERROR IMPUESTO', 'No se encontró el impuesto al consumo: '+id_venta)
                    elif clase_impuesto != '05' and clase_impuesto != '06' and clase_impuesto != '07' and not impuestol.consumo:
                        impuestos_linea.append(impuestol)
                linea.taxes = impuestos_linea
                linea.unit_price = lin[col_line.index('Valor_Unitario')]
                #Verificamos si hay descuento para la linea de producto y se agrega su respectivo descuento
                if lin[col_line.index('Porcentaje_Descuento_1')] > 0:
                    porcentaje = lin[col_line.index('Porcentaje_Descuento_1')]/100
                    linea.base_price = lin[col_line.index('Valor_Unitario')]
                    linea.discount_rate = Decimal(str(porcentaje))
                    linea.on_change_discount_rate()
                #Se guarda la linea para la venta
                linea.save()
            if sale.invoice_type == 'P':
                with Transaction().set_user(1):
                    context = User.get_preferences()
                with Transaction().set_context(context, shop=shop.id, _skip_warnings=True):
                    cls.venta_mostrador(sale)   
            #Se almacena en una lista las ventas creadas
            to_create.append(sale)
        #Se procesa los registros creados
        with Transaction().set_user(1):
            context = User.get_preferences()
        with Transaction().set_context(context, _skip_warnings=True):
            Sale.quote(to_create)
            Sale.confirm(to_create)
            Sale.process(to_create)
        log = cls.update_invoices_shipments(to_create, ventas_tecno, logs)
        actualizacion.add_logs(actualizacion, log)
        for sale in to_create:
            cls.importado(sale.id_tecno)
            #print('creado...', sale.id_tecno) #TEST
        logging.warning('FINISH VENTAS')


    #Se actualiza las facturas y envios con la información de la venta
    @classmethod
    def update_invoices_shipments(cls, sales, ventas_tecno, logs):
        Invoice = Pool().get('account.invoice')
        #Procesamos la venta para generar la factura y procedemos a rellenar los campos de la factura
        for sale in sales:
            #print(f"PROCESS: {sale.id_tecno}")
            if sale.shipments:
                shipment_out, = sale.shipments
                shipment_out.number = sale.number
                shipment_out.reference = sale.reference
                shipment_out.effective_date = sale.sale_date
                shipment_out.wait([shipment_out])
                shipment_out.pick([shipment_out])#Revvisar
                shipment_out.pack([shipment_out])#Revvisar
                shipment_out.done([shipment_out])
                #logging.error(str(e))
                #logs = logs+"\n"+"Error venta (envio): "+str(sale.id_tecno)+" - "+str(e)
            else:
                if sale.invoice_type != 'P':
                    msg1 = f'Venta sin envio: {sale.id_tecno}'
                    logging.warning(msg1)
                    logs += '\n' + msg1
            if sale.invoices:
                #print(sale.id_tecno)
                invoice, = sale.invoices
                invoice.accounting_date = sale.sale_date
                invoice.number = sale.number
                invoice.reference = sale.reference
                invoice.invoice_date = sale.sale_date
                tipo_numero = sale.number.split('-')
                #Se agrega en la descripcion el nombre del tipo de documento de la tabla en sqlserver
                desc = cls.get_tipo_dcto(tipo_numero[0])
                if desc:
                    invoice.description = desc[0].TipoDoctos.replace('\n', ' ').replace('\r', '')
                invoice.save()
                if invoice.invoice_type != 'P':
                    Invoice.validate_invoice([invoice])
                total_tryton = abs(invoice.untaxed_amount)
                #Se almacena el total de la venta traida de TecnoCarnes
                total_tecno = 0
                for venta in ventas_tecno:
                    tipo_numero_tecno = venta.tipo.strip()+'-'+str(venta.Numero_documento)
                    if tipo_numero_tecno == sale.number:
                        valor_total = Decimal(abs(venta.valor_total))
                        valor_impuesto = Decimal(abs(venta.Valor_impuesto) + abs(venta.Impuesto_Consumo))
                        if valor_impuesto > 0:
                            total_tecno = valor_total - valor_impuesto
                        else:
                            total_tecno = valor_total
                diferencia_total = abs(total_tryton - total_tecno)
                if diferencia_total < Decimal(6.0) and invoice.invoice_type != 'P':
                    Invoice.post_batch([invoice])
                    Invoice.post([invoice])
                else:
                    msg1 = f'Factura: {sale.id_tecno}'
                    msg2 = f'No contabilizada diferencia total mayor al rango permitido'
                    full_msg = ' - '.join([msg1, msg2])
                    logging.error(msg2)
                    logs.append(full_msg)
                    invoice.comment = 'No contabilizada diferencia total mayor al rango permitido'
                    invoice.save()
            else:
                msg1 = f'Venta sin factura: {sale.id_tecno}'
                logging.error(msg1)
                logs.append(msg1)
        return logs

    #Función encargada de buscar recibos de caja pagados en TecnoCarnes y pagarlos en Tryton
    @classmethod
    def set_payment_pos(cls, sale):
        tipo_numero = sale.number.split('-')
        tipo = tipo_numero[0]
        nro = tipo_numero[1]
        pago = cls.get_payment_tecno(tipo, nro)
        if not pago:
            return
        #si existe pago pos...
        pool = Pool()
        Journal = pool.get('account.statement.journal')
        Statement = pool.get('account.statement')
        Actualizacion = pool.get('conector.actualizacion')
        pago, = pago
        fecha = str(pago.fecha).split()[0].split('-')
        fecha_date = datetime.date(int(fecha[0]), int(fecha[1]), int(fecha[2]))
        journal, = Journal.search([('id_tecno', '=', pago.forma_pago)])
        args_statement = {
            'device': sale.sale_device,
            'date': fecha_date,
            'journal': journal,
        }
        statement, = cls.search_or_create_statement(args_statement)
        valor_pagado = pago.valor
        data_payment = {
            'sales': {
                sale: valor_pagado
            },
            'statement': statement.id,
            'date': fecha_date
        }
        result_payment = cls.multipayment_invoices_statement(data_payment)
        if result_payment['msg'] != 'ok':
            actualizacion, = Actualizacion.search([('name', '=','VENTAS')])
            Actualizacion.add_logs(actualizacion, [result_payment['msg']])
            logging.error(result_payment)
        sale.workflow_to_end([sale])

    
    #Metodo encargado de buscar el estado de cuenta de una terminal y en caso de no existir, se crea.
    @classmethod
    def search_or_create_statement(cls, args):
        pool = Pool()
        Statement = pool.get('account.statement')
        Device = pool.get('sale.device')
        device = Device(args['device'])
        date = args['date']
        journal = args['journal']
        statement = Statement.search([
                ('journal', '=', journal.id),
                ('sale_device', '=', device.id),
                ('date', '=', date),
                ('state', '=', 'draft')
            ])
        if not statement:
            statements_date = Statement.search([
                    ('journal', '=', journal.id),
                    ('date', '=', date),
                    ('sale_device', '=', device.id),
                ])
            turn = len(statements_date) + 1
            values = {
                'name': '%s - %s' % (device.rec_name, journal.rec_name),
                'date': date,
                'journal': journal.id,
                'company': device.shop.company.id,
                'start_balance': journal.default_start_balance or Decimal('0.0'),
                'end_balance': Decimal('0.0'),
                'turn': turn,
                'sale_device': device.id,
            }
            statement = Statement.create([values])
        return statement


    @classmethod
    def multipayment_invoices_statement(cls, args, context=None):
        pool = Pool()
        Date = pool.get('ir.date')
        Sale = pool.get('sale.sale')
        Configuration = pool.get('account.configuration')
        User = pool.get('res.user')
        StatementLine = pool.get('account.statement.line')
        sales = args.get('sales', None)
        if not sales:
            sales_ids = args.get('sales_ids', None)
            sales = Sale.browse(sales_ids)
        statement_id = args.get('statement', None)
        if not statement_id:
            journal_id = args.get('journal_id', None)
            user_id = context.get('user')
            user = User(user_id)
            statements = cls.search([
                ('journal', '=', journal_id),
                ('state', '=', 'draft'),
                ('sale_device', '=', user.sale_device.id),
            ])
            if statements:
                statement_id = statements[0].id
            else:
                return
        date = args.get('date', None)
        if not date:
            date = Date.today()

        for sale in sales.keys():
            if not sale.number:
                continue
            if sale.payments:
                total_paid = sum([p.amount for p in sale.payments])
                if total_paid >= sale.total_amount:
                    continue
            total_amount = args.get('sales')[sale]
            if not total_amount:
                total_amount = sale.total_amount
            if not sale.invoice or (sale.invoice.state != 'posted' and sale.invoice.state != 'paid'):
                Sale.post_invoice(sale)
            if not sale.party.account_receivable:
                Party = pool.get('party.party')
                config = Configuration(1)
                if config.default_account_receivable:
                    Party.write([sale.party], {
                        'account_receivable': config.default_account_receivable.id
                    })
                else:
                    raise UserError('sale_pos.msg_party_without_account_receivable', sale.party.name)
            account_id = sale.party.account_receivable.id
            to_create = {
                'sale': sale.id,
                'date': date,
                'statement': statement_id,
                'amount': total_amount,
                'party': sale.party.id,
                'account': account_id,
                'description': sale.invoice_number or sale.invoice.number or '',
            }
            line, = StatementLine.create([to_create])
            write_sale = {
                'turn': line.statement.turn,
            }
            if hasattr(sale, 'order_status'):
                write_sale['order_status'] = 'delivered'
            Sale.write([sale], write_sale)
            if sale.payments:
                total_paid = sum([p.amount for p in sale.payments])
                if total_paid == sale.total_amount:
                    Sale.do_reconcile([sale])
        return 'ok'


    @classmethod
    def venta_mostrador(cls, sale):
        pool = Pool()
        Sale = pool.get('sale.sale')
        #Procesar ventas pos
        Sale.faster_process({'sale_id':sale.id}, {})
        Sale.process_pos(sale)
        if sale.payment_term.id_tecno == '0':
            cls.set_payment_pos(sale)

    @classmethod
    def process_payment_pos(cls):
        logging.warning('RUN PROCESS POS')
        pool = Pool()
        User = pool.get('res.user')
        Sale = pool.get('sale.sale')
        Warning = pool.get('res.user.warning')
        warning_name = 'process_payment_pos'
        if Warning.check(warning_name):
            raise UserWarning(warning_name, "Recuerde que primero debe ejecutar 'actualizador ventas POS'.")
        ventas = cls.get_date_type()
        for venta in ventas:
            id_tecno = str(venta.sw)+'-'+venta.tipo+'-'+str(venta.Numero_documento)
            sale = Sale.search([('id_tecno', '=', id_tecno),('invoice_state', '!=', 'paid')])
            if sale:
                sale, = sale
                with Transaction().set_user(1):
                    context = User.get_preferences()
                with Transaction().set_context(context, shop=sale.shop.id, _skip_warnings=True):
                    Sale.quote([sale])
                    Sale.confirm([sale])
                    Sale.process([sale])
                    cls.update_invoices_shipments([sale], [venta], [])
                    if sale.payment_term.id_tecno == '0':
                        #print(id_tecno)
                        cls.set_payment_pos(sale)
        logging.warning('FINISH PROCESS POS')

    
    @classmethod
    def update_pos_tecno(cls):
        logging.warning('RUN UPDATE POS')
        pool = Pool()
        Sale = pool.get('sale.sale')
        Device = pool.get('sale.device')
        Module = pool.get('ir.module')
        sale_table = Table('sale_sale')
        line_table = Table('sale_line')
        cursor = Transaction().connection.cursor()
        
        ventas = cls.get_date_type()
        for venta in ventas:
            id_tecno = str(venta.sw)+'-'+venta.tipo+'-'+str(venta.Numero_documento)
            sale = Sale.search([('id_tecno', '=', id_tecno),('invoice_state', '!=', 'paid')])
            #Se valida que haya encontrado una venta y tenga valores para actualizar
            if sale and hasattr(sale[0], 'sale_device') and venta.pc:
                sale, = sale
                cls.force_draft([sale])
                if not sale.sale_device:
                    #print(id_tecno, venta.pc)
                    sale_device = Device.search([('id_tecno', '=', venta.pc)])
                    if not sale_device:
                        continue
                    sale_device, = sale_device
                    cursor.execute(*sale_table.update(
                        columns=[sale_table.sale_device, sale_table.invoice_type],
                        values=[sale_device.id, 'P'],
                        where=sale_table.id == sale.id)
                    )
                company_operation = Module.search([('name', '=', 'company_operation'), ('state', '=', 'activated')])
                if company_operation:
                    CompanyOperation = pool.get('company.operation_center')
                    company_operation = CompanyOperation(1)
                    for line in sale.lines:
                        if not line.operation_center:
                            cursor.execute(*line_table.update(
                                columns=[line_table.operation_center],
                                values=[company_operation.id],
                                where=line_table.id == line.id)
                            )
            else:
                logging.warning(f'NO SE ENCONTRO VENTAS O EQUIPOS PARA REALIZAR LA ACTUALIZACION DE VENTA POS {id_tecno}')
        logging.warning('FINISH UPDATE POS')

    #Metodo encargado de obtener la forma en que se pago el comprobante (recibos)
    @classmethod
    def get_tipo_pago(cls, tipo, nro):
        Config = Pool().get('conector.configuration')
        consult = "SELECT * FROM dbo.Documentos_Che WHERE sw = 5 AND tipo = "+tipo+" AND numero ="+nro
        result = Config.get_data(consult)
        return result
    
    #Metodo encargado de obtener el pago de una venta cuando es POS
    @classmethod
    def get_payment_tecno(cls, tipo, nro):
        Config = Pool().get('conector.configuration')
        consult = "SELECT * FROM dbo.Documentos_Che WHERE sw = 1 AND tipo = "+tipo+" AND numero ="+nro
        data = Config.get_data(consult)
        return data

    @classmethod
    def get_data_table(cls, table):
        data = []
        try:
            Config = Pool().get('conector.configuration')
            conexion = Config.conexion()
            with conexion.cursor() as cursor:
                query = cursor.execute("SELECT * FROM dbo."+table+"")
                data = list(query.fetchall())
        except Exception as e:
            print("ERROR QUERY get_data_table: ", e)
            raise UserError('ERROR QUERY get_data_table: ', str(e))
        return data

    @classmethod
    def get_data_parametros(cls, id):
        data = []
        try:
            Config = Pool().get('conector.configuration')
            conexion = Config.conexion()
            with conexion.cursor() as cursor:
                query = cursor.execute("SELECT * FROM dbo.TblParametro WHERE IdParametro = "+id+"")
                data = list(query.fetchall())
        except Exception as e:
            print("ERROR QUERY get_data_parametros: ", e)
            raise UserError('ERROR QUERY get_data_parametros: ', str(e))
        return data

    #Metodo encargado de traer el tipo de documento de la bd
    @classmethod
    def get_tipo_dcto(cls, id):
        data = []
        try:
            Config = Pool().get('conector.configuration')
            conexion = Config.conexion()
            with conexion.cursor() as cursor:
                query = cursor.execute("SELECT * FROM dbo.TblTipoDoctos WHERE idTipoDoctos = '"+id+"'")
                data = list(query.fetchall())
        except Exception as e:
            print("ERROR QUERY TblTipoDoctos: ", e)
        return data

    #Esta función se encarga de traer todos los datos de una tabla dada de la bd
    @classmethod
    def get_line_where(cls, sw, nro, tipo):
        data = []
        try:
            Config = Pool().get('conector.configuration')
            conexion = Config.conexion()
            with conexion.cursor() as cursor:
                query = cursor.execute("SELECT * FROM dbo.Documentos_Lin WHERE sw = "+sw+" AND Numero_Documento = "+nro+" AND tipo = "+tipo+" order by seq")
                data = list(query.fetchall())
        except Exception as e:
            print("ERROR QUERY Documentos_Lin: ", e)
        return data

    #Función encargada de consultar las columnas pertenecientes a 'x' tabla de la bd
    @classmethod
    def get_columns_db_tecno(cls, table):
        columns = []
        try:
            Config = Pool().get('conector.configuration')
            conexion = Config.conexion()
            with conexion.cursor() as cursor:
                query = cursor.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = '"+table+"' ORDER BY ORDINAL_POSITION")
                for q in query.fetchall():
                    columns.append(q[0])
        except Exception as e:
            print("ERROR QUERY "+table+": ", e)
        return columns

    #Esta función se encarga de traer todos los datos de una tabla dada de acuerdo al rango de fecha dada de la bd
    @classmethod
    def get_data_tecno(cls, date):
        Config = Pool().get('conector.configuration')
        config, = Config.search([], order=[('id', 'DESC')], limit=1)
        fecha = config.date.strftime('%Y-%m-%d %H:%M:%S')
        #consult = "SELECT * FROM dbo.Documentos WHERE (sw = 1 OR sw = 2) AND tipo = 147 AND fecha_hora >= CAST('"+fecha+"' AS datetime) AND exportado != 'T'" #TEST
        consult = "SET DATEFORMAT ymd SELECT TOP(50) * FROM dbo.Documentos WHERE fecha_hora >= CAST('"+fecha+"' AS datetime) AND (sw = 1 OR sw = 2) AND exportado != 'T'"
        result = Config.get_data(consult)
        return result

    @classmethod
    def importado(cls, id):
        lista = id.split('-')
        Config = Pool().get('conector.configuration')
        query = "UPDATE dbo.Documentos SET exportado = 'T' WHERE sw ="+lista[0]+" and tipo = "+lista[1]+" and Numero_documento = "+lista[2]
        Config.set_data(query)
    
    @classmethod
    def get_datapos_tecno(cls, date, tipo):
        Config = Pool().get('conector.configuration')
        #consult = "SELECT * FROM dbo.Documentos WHERE (sw = 1 OR sw = 2) AND tipo = 140 AND Numero_documento > 49 AND Numero_documento < 236" #TEST
        consult = "SET DATEFORMAT ymd SELECT * FROM dbo.Documentos WHERE fecha_hora >= CAST('"+date+"' AS datetime) AND sw = 1 AND condicion = 0 AND (tipo = 152 OR tipo = 145)"
        result = Config.get_data(consult)
        return result


    #Función encargada de consultar si existe un producto y es vendible
    @classmethod
    def buscar_producto(cls, id_producto):
        Product = Pool().get('product.product')
        producto = Product.search([('id_tecno', '=', id_producto)])
        conector_actualizacion = Table('conector_actualizacion')
        cursor = Transaction().connection.cursor()
        
        if producto:
            producto, = producto
            if not producto.salable:
                producto.salable = True
                producto.save()
            return producto
        else:
            cursor.execute(*conector_actualizacion.update(
                columns=[conector_actualizacion.write_date],
                values=[None],
                where=conector_actualizacion.name == 'PRODUCTOS')
            )
            msg1 = f'Error al buscar el producto con id: {id_producto}'
            logging.error(msg1)
            raise UserError('Error product search', msg1)
            
    
    @classmethod
    def get_date_type(cls):
        Config = Pool().get('conector.configuration')
        config, = Config.search([], order=[('id', 'DESC')], limit=1)
        fecha = config.date
        fecha = fecha.strftime('%Y-%m-%d %H:%M:%S')
        data = cls.get_datapos_tecno(fecha, '145')
        return data

    #Crea o actualiza un registro de la tabla actualización en caso de ser necesario
    @classmethod
    def create_or_update(cls):
        Actualizacion = Pool().get('conector.actualizacion')
        actualizacion = Actualizacion.search([('name', '=','VENTAS')])
        if actualizacion:
            #Se busca un registro con la actualización
            actualizacion, = actualizacion
        else:
            #Se crea un registro con la actualización
            actualizacion = Actualizacion()
            actualizacion.name = 'VENTAS'
            actualizacion.logs = 'logs...'
            actualizacion.save()
        return actualizacion

    #Metodo encargado de buscar si exste una venta
    @classmethod
    def buscar_venta(cls, id):
        Sale = Pool().get('sale.sale')
        sale = Sale.search([('id_tecno', '=', id)])
        if sale:
            return sale[0]
        else:
            return False

    @classmethod
    def force_draft(cls, sales):
        sale_table = Table('sale_sale')
        invoice_table = Table('account_invoice')
        move_table = Table('account_move')
        stock_move_table = Table('stock_move')
        cursor = Transaction().connection.cursor()

        for sale in sales:
            for invoice in sale.invoices:
                if (hasattr(invoice, 'cufe') and invoice.cufe) or \
                    hasattr(invoice, 'electronic_state') and \
                    invoice.electronic_state == 'submitted':
                        raise UserError('account_col.msg_with_electronic_invoice')
                if invoice.state == 'paid':
                    cls.unreconcile_move(invoice.move)
                if invoice.move:
                    cursor.execute(*move_table.update(
                        columns=[move_table.state],
                        values=['draft'],
                        where=move_table.id == invoice.move.id)
                    )
                    cursor.execute(*move_table.delete(
                        where=move_table.id == invoice.move.id)
                    )
                cursor.execute(*invoice_table.update(
                    columns=[invoice_table.state, invoice_table.number],
                    values=['validate', None],
                    where=invoice_table.id == invoice.id)
                )
                cursor.execute(*invoice_table.delete(
                    where=invoice_table.id == invoice.id)
                )

            if sale.id:
                cursor.execute(*sale_table.update(
                    columns=[sale_table.state, sale_table.shipment_state, sale_table.invoice_state],
                    values=['draft', 'none', 'none'],
                    where=sale_table.id == sale.id)
                )
            # The stock moves must be delete
            stock_moves = [m.id for line in sale.lines for m in line.moves]
            if stock_moves:
                cursor.execute(*stock_move_table.update(
                    columns=[stock_move_table.state],
                    values=['draft'],
                    where=stock_move_table.id.in_(stock_moves)
                ))

                cursor.execute(*stock_move_table.delete(
                    where=stock_move_table.id.in_(stock_moves))
                )


    @classmethod
    def delete_imported_sales(cls, sales):
        sale_table = Table('sale_sale')
        invoice_table = Table('account_invoice')
        move_table = Table('account_move')
        stock_move_table = Table('stock_move')
        cursor = Transaction().connection.cursor()
        #Sale = Pool().get('sale.sale')
        Conexion = Pool().get('conector.configuration')
        for sale in sales:
            if sale.id_tecno:
                lista = sale.id_tecno.split('-')
                consult = "UPDATE dbo.Documentos SET exportado = 'S' WHERE sw ="+lista[0]+" and tipo = "+lista[1]+" and Numero_documento = "+lista[2]
                Conexion.set_data(consult)
            else:
                raise UserError("Error: ", f"No se encontró el id_tecno de {sale}")

            for invoice in sale.invoices:
                if invoice.state == 'paid':
                    cls.unreconcile_move(invoice.move)
                if invoice.move:
                    cursor.execute(*move_table.update(
                        columns=[move_table.state],
                        values=['draft'],
                        where=move_table.id == invoice.move.id)
                    )
                    cursor.execute(*move_table.delete(
                        where=move_table.id == invoice.move.id)
                    )
                cursor.execute(*invoice_table.update(
                    columns=[invoice_table.state, invoice_table.number],
                    values=['validate', None],
                    where=invoice_table.id == invoice.id)
                )
                cursor.execute(*invoice_table.delete(
                    where=invoice_table.id == invoice.id)
                )

            if sale.id:
                cursor.execute(*sale_table.update(
                    columns=[sale_table.state, sale_table.shipment_state, sale_table.invoice_state],
                    values=['draft', 'none', 'none'],
                    where=sale_table.id == sale.id)
                )
            # The stock moves must be delete
            stock_moves = [m.id for line in sale.lines for m in line.moves]
            if stock_moves:
                cursor.execute(*stock_move_table.update(
                    columns=[stock_move_table.state],
                    values=['draft'],
                    where=stock_move_table.id.in_(stock_moves)
                ))

                cursor.execute(*stock_move_table.delete(
                    where=stock_move_table.id.in_(stock_moves))
                )
            #Se elimina la venta
            cursor.execute(*sale_table.delete(
                    where=sale_table.id == sale.id)
                )


    @classmethod
    def unreconcile_move(self, move):
        Reconciliation = Pool().get('account.move.reconciliation')
        reconciliations = [l.reconciliation for l in move.lines if l.reconciliation]
        if reconciliations:
            Reconciliation.delete(reconciliations)