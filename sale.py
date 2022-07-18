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
        Shop = pool.get('sale.shop')
        Tax = pool.get('account.tax')
        User = pool.get('res.user')
        Module = pool.get('ir.module')
        
        company_operation = Module.search([('name', '=', 'company_operation'), ('state', '=', 'activated')])
        if company_operation:
            CompanyOperation = pool.get('company.operation_center')
            company_operation = CompanyOperation(1)
        venta_pos = []
        pdevoluciones_pos = cls.get_data_parametros('10')
        if pdevoluciones_pos:
            pdevoluciones_pos = (pdevoluciones_pos[0].Valor).strip().split(',')
            venta_pos += pdevoluciones_pos
        pventa_pos = cls.get_data_parametros('8')
        if pventa_pos:
            pventa_pos = (pventa_pos[0].Valor).strip().split(',')
            venta_pos += pventa_pos
        venta_electronica = cls.get_data_parametros('9')
        if venta_electronica:
            venta_electronica = (venta_electronica[0].Valor).strip().split(',')
        to_created = []
        to_process = []
        #Procedemos a realizar una venta
        for venta in ventas_tecno:
            sw = venta.sw
            numero_doc = venta.Numero_documento
            tipo_doc = venta.tipo
            id_venta = str(sw)+'-'+tipo_doc+'-'+str(numero_doc)
            existe = cls.buscar_venta(id_venta)
            if existe:
                cls.importado(id_venta)
                continue
            print(id_venta)
            #Se trae la fecha de la venta y se adapta al formato correcto para Tryton
            fecha = str(venta.fecha_hora).split()[0].split('-')
            fecha_date = datetime.date(int(fecha[0]), int(fecha[1]), int(fecha[2]))
            nit_cedula = venta.nit_Cedula
            party = Party.search([('id_number', '=', nit_cedula)])
            if not party:
                msg2 = f' No se encontro el tercero {nit_cedula} de la venta {id_venta}'
                logging.error(msg2)
                logs.append(msg2)
                actualizacion.reset_writedate('TERCEROS')
                continue
            party = party[0]
            #Se indica a que bodega pertenece
            id_tecno_bodega = venta.bodega
            bodega = location.search([('id_tecno', '=', id_tecno_bodega)])
            if not bodega:
                msg2 = f'Bodega {id_tecno_bodega} no existe de la venta {id_venta}'
                logging.error(msg2)
                logs.append(msg2)
                continue
            bodega = bodega[0]
            shop = Shop.search([('warehouse', '=', bodega.id)])
            if not shop:
                msg2 = f'Bodega (shop) {id_tecno_bodega} no existe de la venta {id_venta}'
                logging.error(msg2)
                logs.append(msg2)
                continue
            shop = shop[0]
            #Se le asigna el plazo de pago correspondiente
            condicion = venta.condicion
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
            sale.description = (venta.notas).replace('\n', ' ').replace('\r', '')
            sale.invoice_type = 'C'
            sale.sale_date = fecha_date
            sale.party = party.id
            sale.invoice_party = party.id
            sale.shipment_party = party.id
            sale.warehouse = bodega
            sale.shop = shop
            sale.payment_term = plazo_pago
            sale.self_pick_up = False
            #Se revisa si la venta es clasificada como electronica o pos y se cambia el tipo
            if tipo_doc in venta_electronica:
                #continue #TEST
                sale.invoice_type = '1'
            elif tipo_doc in venta_pos:
                sale.invoice_type = 'P'
                sale.invoice_date = fecha_date
                sale.pos_create_date = fecha_date
                #sale.self_pick_up = True
                #Busco la terminal y se la asigno
                sale_device, = SaleDevice.search([('id_tecno', '=', venta.pc)])
                sale.sale_device = sale_device
                sale.invoice_number = sale.number
            #Se busca una dirección del tercero para agregar en la factura y envio
            address = Address.search([('party', '=', party.id)], limit=1)
            if address:
                sale.invoice_address = address[0].id
                sale.shipment_address = address[0].id
            
            #SE CREA LA VENTA
            sale.save()
            #Se revisa si se aplico alguno de los 3 impuestos en la venta
            retencion_iva = False
            if venta.retencion_iva > 0:
                retencion_iva = True
            retencion_ica = False
            if venta.retencion_ica > 0:
                retencion_ica = True
            retencion_rete = False
            if venta.retencion_causada > 0:
                if not retencion_iva and not retencion_ica:
                    retencion_rete = True
                elif (venta.retencion_iva + venta.retencion_ica) != venta.retencion_causada:
                    retencion_rete = True
            
            #Ahora traemos las lineas de producto para la venta a procesar
            documentos_linea = cls.get_line_where(str(sw), str(numero_doc), str(tipo_doc))
            #col_line = cls.get_columns_db_tecno('Documentos_Lin')
            #create_line = []
            for lin in documentos_linea:
                linea = SaleLine()
                id_producto = str(lin.IdProducto)
                producto = cls.buscar_producto(id_producto)
                linea.sale = sale
                linea.product = producto
                linea.type = 'line'
                linea.unit = producto.template.default_uom
                #Se verifica si es una devolución
                cant = float(lin.Cantidad_Facturada)
                cantidad_facturada = abs(round(cant, 3))
                if linea.unit.id == 1:
                    cantidad_facturada = int(cantidad_facturada)
                #print(cant, cantidad_facturada)
                if sw == 2:
                    linea.quantity = cantidad_facturada * -1
                    dcto_base = str(venta.Tipo_Docto_Base)+'-'+str(venta.Numero_Docto_Base)
                    #Se indica a que documento hace referencia la devolucion
                    sale.reference = dcto_base
                    sale.comment = f"DEVOLUCIÓN DE LA FACTURA {dcto_base}"
                else:
                    linea.quantity = cantidad_facturada
                #Se verifica si tiene activo el módulo centro de operaciones y se añade 1 por defecto
                if company_operation:
                    linea.operation_center = company_operation
                #Comprueba los cambios y trae los impuestos del producto
                linea.on_change_product()
                #Se verifica si el impuesto al consumo fue aplicado
                impuesto_consumo = lin.Impuesto_Consumo
                #A continuación se verifica las retenciones e impuesto al consumo
                impuestos_linea = []
                for impuestol in linea.taxes:
                    clase_impuesto = impuestol.classification_tax
                    if clase_impuesto == '05' and retencion_iva:
                        if impuestol not in impuestos_linea:
                            impuestos_linea.append(impuestol)
                    elif clase_impuesto == '06' and retencion_rete:
                        if impuestol not in impuestos_linea:
                            impuestos_linea.append(impuestol)
                    elif clase_impuesto == '07' and retencion_ica:
                        if impuestol not in impuestos_linea:
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
                        if impuestol not in impuestos_linea:
                            impuestos_linea.append(impuestol)
                linea.taxes = impuestos_linea
                linea.unit_price = lin.Valor_Unitario
                #Verificamos si hay descuento para la linea de producto y se agrega su respectivo descuento
                if lin.Porcentaje_Descuento_1 > 0:
                    porcentaje = lin.Porcentaje_Descuento_1/100
                    linea.base_price = lin.Valor_Unitario
                    linea.discount_rate = Decimal(str(porcentaje))
                    linea.on_change_discount_rate()
                #Se guarda la linea para la venta
                #linea.on_change_quantity()
                linea.save()
            if sale.invoice_type == 'P':
                with Transaction().set_user(1):
                    context = User.get_preferences()
                with Transaction().set_context(context, shop=shop.id, _skip_warnings=True):
                    cls.venta_mostrador(sale)
                    cls.finish_shipment_process([sale])
            else:
                #Se almacena en una lista las ventas creadas para ser procesadas
                to_process.append(sale)
            to_created.append(sale.id_tecno)
        #Se procesa los registros creados
        with Transaction().set_user(1):
            context = User.get_preferences()
        with Transaction().set_context(context, _skip_warnings=True):
            Sale.quote(to_process)
            Sale.confirm(to_process)
            Sale.process(to_process)
        log = cls.update_invoices_shipments(to_process, ventas_tecno, logs)
        actualizacion.add_logs(actualizacion, log)
        for id_tecno in to_created:
            cls.importado(id_tecno)
            #print('creado...', id_tecno) #TEST 
        logging.warning('FINISH VENTAS')


    # Funcion encargada de finalizar el proceso de envío de la venta
    @classmethod
    def finish_shipment_process(cls, sales):
        for sale in sales:
            for shipment in sale.shipments:
                shipment.number = sale.number
                shipment.reference = sale.reference
                shipment.effective_date = sale.sale_date
                shipment.wait([shipment])
                shipment.pick([shipment])
                shipment.pack([shipment])
                shipment.done([shipment])

    #Se actualiza las facturas y envios con la información de la venta
    @classmethod
    def update_invoices_shipments(cls, sales, ventas_tecno, logs):
        Invoice = Pool().get('account.invoice')
        PaymentLine = Pool().get('account.invoice-account.move.line')
        cls.finish_shipment_process(sales)
        #Procesamos la venta para generar la factura y procedemos a rellenar los campos de la factura
        for sale in sales:
            for invoice in sale.invoices:
                invoice.accounting_date = sale.sale_date
                invoice.number = sale.number
                invoice.reference = sale.reference
                invoice.invoice_date = sale.sale_date
                invoice.invoice_type = 'C'
                tipo_numero = sale.number.split('-')
                #Se agrega en la descripcion el nombre del tipo de documento de la tabla en sqlserver
                desc = cls.get_tipo_dcto(tipo_numero[0])
                if desc:
                    invoice.description = desc[0].TipoDoctos.replace('\n', ' ').replace('\r', '')
                invoice.save()
                Invoice.validate_invoice([invoice])
                total_tryton = abs(invoice.untaxed_amount)
                #Se almacena el total de la venta traida de TecnoCarnes
                total_tecno = 0
                devolucion = False
                dcto_base = None
                for venta in ventas_tecno:
                    tipo_numero_tecno = venta.tipo.strip()+'-'+str(venta.Numero_documento)
                    if tipo_numero_tecno == sale.number:
                        if venta.sw == 2:
                            devolucion = True
                            dcto_base = str(venta.Tipo_Docto_Base)+'-'+str(venta.Numero_Docto_Base)
                        valor_total = Decimal(abs(venta.valor_total))
                        valor_impuesto = Decimal(abs(venta.Valor_impuesto) + abs(venta.Impuesto_Consumo))
                        if valor_impuesto > 0:
                            total_tecno = valor_total - valor_impuesto
                        else:
                            total_tecno = valor_total
                diferencia_total = abs(total_tryton - total_tecno)
                if devolucion:
                    original_invoice = Invoice.search([('number', '=', dcto_base)])
                    if original_invoice:
                        invoice.original_invoice = original_invoice[0]
                    else:
                        msg = f"NO SE ENCONTRO LA FACTURA {dcto_base} PARA CRUZAR CON LA DEVOLUCION {invoice.number}"
                        logs.append(msg)
                        logging.error(msg)
                if diferencia_total < Decimal(6.0):
                    Invoice.post_batch([invoice])
                    Invoice.post([invoice])
                    if invoice.original_invoice:
                        if invoice.original_invoice.amount_to_pay + invoice.amount_to_pay != 0:
                            paymentline = PaymentLine()
                            paymentline.invoice = invoice.original_invoice
                            paymentline.invoice_account = invoice.account
                            paymentline.invoice_party = invoice.party
                            for ml in invoice.move.lines:
                                if ml.account.type.receivable:
                                    paymentline.line = ml
                            paymentline.save()
                        Invoice.reconcile_invoice(invoice)
                else:
                    msg1 = f'Factura: {sale.id_tecno}'
                    msg2 = f'No contabilizada diferencia total mayor al rango permitido'
                    full_msg = ' - '.join([msg1, msg2])
                    logging.error(full_msg)
                    logs.append(full_msg)
                    invoice.comment = msg2
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
        pagos = cls.get_payment_tecno(tipo, nro)
        if not pagos:
            return
        #si existe pagos pos...
        pool = Pool()
        Journal = pool.get('account.statement.journal')
        #Statement = pool.get('account.statement')
        Actualizacion = pool.get('conector.actualizacion')
        for pago in pagos:
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
            if result_payment != 'ok':
                msg = 'ERROR AL PROCESAR EL PAGO DE LA VENTA POS {tipo_numero}'
                actualizacion, = Actualizacion.search([('name', '=','VENTAS')])
                Actualizacion.add_logs(actualizacion, [msg])
                logging.error(msg)
        #sale.workflow_to_end([sale]) #REVISAR

    
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


    # Metodo encargado de pagar multiples facturas con multiples formas de pago
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
            total_paid = Decimal(0.0)
            if sale.payments:
                total_paid = sum([p.amount for p in sale.payments])
                if total_paid >= sale.total_amount:
                    if total_paid == sale.total_amount:
                        Sale.do_reconcile([sale])
                    continue
            total_pay = args.get('sales')[sale]
            if not total_pay:
                total_pay = sale.total_amount
            else:
                dif = Decimal(total_paid + total_pay) - sale.total_amount
                dif = Decimal(abs(dif))
                if dif < Decimal(600.0) and dif != 0:
                    total_pay = sale.total_amount
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
                'amount': total_pay,
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
            if (total_pay + total_paid) == sale.total_amount:
                Sale.do_reconcile([sale])
        return 'ok'


    @classmethod
    def venta_mostrador(cls, sale):
        pool = Pool()
        Sale = pool.get('sale.sale')
        #Procesar ventas pos
        Sale.quote([sale])
        Sale.confirm([sale])
        Sale.process([sale])
        Sale.post_invoices(sale)
        Sale.do_stock_moves([sale])
        if sale.payment_term.id_tecno == '0':
            cls.set_payment_pos(sale)
            Sale.update_state([sale])

    @classmethod
    def process_payment_pos(cls):
        logging.warning('RUN PROCESS POS')
        pool = Pool()
        User = pool.get('res.user')
        Sale = pool.get('sale.sale')
        cursor = Transaction().connection.cursor()
        cursor.execute("SELECT id, id_tecno FROM sale_sale WHERE (number LIKE '152-%' or number LIKE '145-%') and state != 'done' and state != 'draft'")
        result = cursor.fetchall()
        if not result:
            return
        for sale_id in result:
            print(sale_id[0])
            sale = Sale(sale_id[0])
            if not sale.sale_device:
                print(sale_id[0], 'NO SALE_DEVICE')
                continue
            with Transaction().set_user(1):
                context = User.get_preferences()
            with Transaction().set_context(context, shop=sale.shop.id, _skip_warnings=True):
                cls.set_payment_pos(sale)
                Sale.update_state([sale])
        logging.warning('FINISH PROCESS POS')
    
    @classmethod
    def update_pos_tecno(cls):
        logging.warning('RUN UPDATE POS')
        pool = Pool()
        Sale = pool.get('sale.sale')
        cursor = Transaction().connection.cursor()
        cursor.execute("SELECT id, id_tecno FROM sale_sale WHERE (number LIKE '152-%' or number LIKE '145-%') and sale_device is null")
        result = cursor.fetchall()
        if not result:
            return
        for sale_id in result:
            print(sale_id[0])
            sale = Sale(sale_id[0])
            if not sale.sale_device:
                doc = cls.get_datapos_tecno(sale_id[1])
                cursor.execute("SELECT id FROM sale_device WHERE id_tecno = '"+doc[0].pc+"'")
                resultd = cursor.fetchone()
                print(resultd[0])
                cursor.execute("UPDATE sale_sale SET sale_device = "+str(resultd[0])+" WHERE id = "+str(sale_id[0]))
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
        Config = Pool().get('conector.configuration')(1)
        consult = "SELECT * FROM dbo.Documentos_Lin WHERE sw = "+sw+" AND Numero_Documento = "+nro+" AND tipo = "+tipo+" order by seq"
        result = Config.get_data(consult)
        return result

    #Esta función se encarga de traer todos los datos de una tabla dada de acuerdo al rango de fecha dada de la bd
    @classmethod
    def get_data_tecno(cls):
        Config = Pool().get('conector.configuration')(1)
        fecha = Config.date.strftime('%Y-%m-%d %H:%M:%S')
        #consult = "SELECT * FROM dbo.Documentos WHERE tipo = 146 AND Numero_documento = 25" #TEST
        consult = "SET DATEFORMAT ymd SELECT TOP(50) * FROM dbo.Documentos WHERE fecha_hora >= CAST('"+fecha+"' AS datetime) AND (sw = 1 OR sw = 2) AND exportado != 'T' ORDER BY fecha_hora ASC"
        result = Config.get_data(consult)
        return result

    @classmethod
    def importado(cls, id):
        lista = id.split('-')
        Config = Pool().get('conector.configuration')
        query = "UPDATE dbo.Documentos SET exportado = 'T' WHERE sw ="+lista[0]+" and tipo = "+lista[1]+" and Numero_documento = "+lista[2]
        Config.set_data(query)
    
    @classmethod
    def get_datapos_tecno(cls, id):
        Config = Pool().get('conector.configuration')
        lista = id.split('-')
        consult = "SELECT pc FROM dbo.Documentos WHERE sw ="+lista[0]+" and tipo = "+lista[1]+" and Numero_documento = "+lista[2]
        result = Config.get_data(consult)
        return result


    #Función encargada de consultar si existe un producto y es vendible
    @classmethod
    def buscar_producto(cls, id_producto):
        Product = Pool().get('product.product')
        producto = Product.search(['OR', ('id_tecno', '=', id_producto), ('code', '=', id_producto)])
        #conector_actualizacion = Table('conector_actualizacion')
        #cursor = Transaction().connection.cursor()
        
        if producto:
            producto, = producto
            if not producto.salable:
                producto.salable = True
                producto.sale_uom = producto.default_uom
                producto.save()
                msg1 = f'Error el producto con id: {id_producto} aparecia NO vendible'
                logging.error(msg1)
                raise UserError('Error product', msg1)
                return False
            return producto
        else:
            #cursor.execute(*conector_actualizacion.update(
            #    columns=[conector_actualizacion.write_date],
            #    values=[None],
            #    where=conector_actualizacion.name == 'PRODUCTOS')
            #)
            msg1 = f'Error al buscar el producto con id: {id_producto}'
            logging.error(msg1)
            #Product.update_products()
            raise UserError('Error product', msg1)
            return False
            

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
        statement_line = Table('account_statement_line')
        cursor = Transaction().connection.cursor()

        for sale in sales:
            for invoice in sale.invoices:
                if (hasattr(invoice, 'cufe') and invoice.cufe) or \
                    hasattr(invoice, 'electronic_state') and \
                    invoice.electronic_state == 'submitted':
                        raise UserError('account_col.msg_with_electronic_invoice')
                if invoice.state == 'paid':
                    invoice.unreconcile_move(invoice.move)
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
            #Se pasa a estado borrador la venta
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
                #Eliminación de los movimientos
                cursor.execute(*stock_move_table.delete(
                    where=stock_move_table.id.in_(stock_moves))
                )
            #Se verifica si tiene lineas de pago y se eliminan
            if sale.payments:
                for payment in sale.payments:
                    cursor.execute(*statement_line.delete(
                            where=statement_line.id == payment.id)
                        )


    @classmethod
    def delete_imported_sales(cls, sales):
        sale_table = Table('sale_sale')
        cursor = Transaction().connection.cursor()
        Conexion = Pool().get('conector.configuration')
        ids_tecno = []
        for sale in sales:
            if sale.id_tecno:
                ids_tecno.append(sale.id_tecno)
            else:
                raise UserError("Error: ", f"No se encontró el id_tecno de {sale}")
            cls.force_draft([sale])
            #Se elimina la venta
            cursor.execute(*sale_table.delete(where=sale_table.id == sale.id))
        for id in ids_tecno:
            Conexion.update_exportado(id, 'S')
