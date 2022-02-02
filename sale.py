import datetime
from trytond.model import fields
from trytond.pool import Pool, PoolMeta
from trytond.exceptions import UserError
from trytond.transaction import Transaction
from decimal import Decimal
import logging
from sql import Table


__all__ = [
    'Sale',
    'Cron',
    ]


#Config = configuration.Configuration()


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
        data = cls.last_update()
        cls.add_sale(data)

    @classmethod
    def add_sale(cls, ventas_tecno):
        #Se crea o actualiza la fecha de importación
        actualizacion = cls.create_or_update()
        logs = []
        #now = datetime.datetime.now()
        if ventas_tecno:
            pool = Pool()
            Sale = pool.get('sale.sale')
            SaleLine = pool.get('sale.line')
            SaleDevice = pool.get('sale.device')
            location = pool.get('stock.location')
            payment_term = pool.get('account.invoice.payment_term')
            Party = pool.get('party.party')
            Address = pool.get('party.address')
            coluns_doc = cls.get_columns_db_tecno('Documentos')
            columns_tipodoc = cls.get_columns_db_tecno('TblTipoDoctos')
            Invoice = pool.get('account.invoice')
            Shop = pool.get('sale.shop')
            Tax = pool.get('account.tax')
            #LineTax = pool.get('sale.line-account.tax')
            User = pool.get('res.user')
            
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
                sale = None
                if not existe:
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
                            sale.reference = venta[coluns_doc.index('Tipo_Docto_Base')].strip()+'-'+str(venta[coluns_doc.index('Numero_Docto_Base')])
                        else:
                            linea.quantity = cantidad_facturada
                            sale.reference = tipo_doc+'-'+str(numero_doc)
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
                else:
                    cls.importado(id_venta)
                if sale:
                    to_create.append(sale)
            #Sale.save(to_create)
            #SaleLine.save(create_line)
            #_sale almacena los registros creados
            #_sale = Sale.create(to_create)
            with Transaction().set_user(1):
                context = User.get_preferences()
            with Transaction().set_context(context, _skip_warnings=True):
                Sale.quote(to_create)
                Sale.confirm(to_create)#Revisar
                Sale.process(to_create)
            #Procesamos la venta para generar la factura y procedemos a rellenar los campos de la factura
            for sale in to_create:
                #print('INICIO VENTA: '+str(sale.id_tecno))
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
                    msg1 = f'Venta sin envio: {sale.id_tecno}'
                    logging.warning(msg1)
                    #logs += '\n' + msg1
                if sale.invoices:
                    #try:
                    invoice, = sale.invoices
                    invoice.accounting_date = sale.sale_date
                    invoice.number = sale.number
                    invoice.reference = sale.reference
                    invoice.invoice_date = sale.sale_date
                    tipo_numero = sale.number.split('-')
                    #Se agrega en la descripcion el nombre del tipo de documento de la tabla en sqlserver
                    desc = cls.get_tipo_dcto(tipo_numero[0])
                    if desc:
                        invoice.description = desc[0][columns_tipodoc.index('TipoDoctos')].replace('\n', ' ').replace('\r', '')
                    invoice.save()
                    invoice.validate_invoice([invoice])
                    total_tryton = abs(invoice.untaxed_amount)
                    #Se almacena el total de la venta traida de TecnoCarnes
                    total_tecno = 0
                    for venta in ventas_tecno:
                        tipo_numero_tecno = venta[coluns_doc.index('tipo')].strip()+'-'+str(venta[coluns_doc.index('Numero_documento')])
                        if tipo_numero_tecno == sale.number:
                            valor_total = Decimal(abs(venta.valor_total))
                            valor_impuesto = Decimal(abs(venta.Valor_impuesto) + abs(venta.Impuesto_Consumo))
                            if valor_impuesto > 0:
                                total_tecno = valor_total - valor_impuesto
                            else:
                                total_tecno = valor_total
                    diferencia_total = abs(total_tryton - total_tecno)
                    if diferencia_total <= 1.0:
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
                    if invoice.invoice_type == 'P':
                        cls.set_payment(invoice, sale)
                else:
                    msg1 = f'Venta sin factura: {sale.id_tecno}'
                    logging.error(msg1)
                    logs.append(msg1)
                #Marcar como importado
                cls.importado(sale.id_tecno)
        actualizacion.add_logs(actualizacion, logs)
        logging.warning('FINISH VENTAS')


    #Función encargada de buscar recibos de caja pagados en TecnoCarnes y pagarlos en Tryton
    @classmethod
    def set_payment(cls, invoice, sale):
        """
        data_statement = {
            'device': sale.sale_device,
            'total_money': 0,
            'date': sale.sale_date
        }

        result = cls.vm_open_statement(data_statement)
        print(result)
        if result['result']:
            print('ESTADO DE CUENTA CREADO', sale.sale_date)

            data_payment = {
                'sale_id': sale.id,
                'journal_id': 1,
                'cash_received': 0,
            }
        """
        
        pool = Pool()
        #Statement = pool.get('account.statement')
        #StatementLine = pool.get('account.statement.line')
        Invoice = pool.get('account.invoice')
        Voucher = pool.get('account.voucher')
        PaymentMode = pool.get('account.voucher.paymode')
        #StatementJournal = pool.get('account.statement.journal')
        columns_tip = cls.get_columns_db_tecno('Documentos_Che')
        #columns_rec = cls.get_columns_db_tecno('Documentos_Cruce')
        
        tipo_numero = invoice.number.split('-')
        #print('INICIO VOUCHER '+invoice.number)
        tipo = tipo_numero[0]
        nro = tipo_numero[1]
        recibos = cls.get_recibos(tipo, nro)
        
        #Si hay recibos para pagar
        if recibos:
            voucher, = Invoice.create_voucher([invoice])
            recibo = recibos[0] #

            #Se trae la fecha de la venta y se adapta al formato correcto para Tryton
            fecha = str(recibo[columns_tip.index('fecha')]).split()[0].split('-')
            fecha = datetime.date(int(fecha[0]), int(fecha[1]), int(fecha[2]))

            idt = recibo[columns_tip.index('forma_pago')]
            payment_mode, = PaymentMode.search([('id_tecno', '=', idt)])
            valor_pagado = recibo[columns_tip.index('valor')]
            #for voucher in vouchers:
            voucher.date = fecha
            voucher.payment_mode = payment_mode
            voucher.reference = invoice.number
            voucher.description = 'VENTA POS'
            voucher.save()
            Voucher.process([voucher])
            diferencia_total = abs(Decimal(valor_pagado) - Decimal(voucher.amount_to_pay))
            #print(diferencia_total)
            if diferencia_total <= 1.0:
                Voucher.post([voucher])

            """
            #REVISAR PROCESOS Y FALTA QUE APAREZCAN VENTAS EN ESTADO DE CUENTA
            journal, = StatementJournal.search([('id_tecno', '=', str(idt))])
            payment_amount = abs(sale.total_amount - sale.paid_amount)
            statements = Statement.search([('date', '=', fecha),('journal', '=', journal)])
            #Se procede a crear el estado de cuenta
            if not statements:
                statements = {
                    'name': sale.sale_device.name+' - '+journal.name,
                    'date': fecha,
                    'turn': 0,
                    'sale_device': sale.sale_device.id,
                    'journal': journal.id,
                    'start_balance': 0,
                    'end_balance': 0,
                    'state': 'draft'
                }
                statements = Statement.create([statements])
            if not sale.party.account_receivable:  
                raise UserError('sale_pos.msg_party_without_account_receivable', s=sale.party.name)
            account = sale.party.account_receivable.id
            if payment_amount:
                amount = payment_amount
                if sale.total_amount < 0:
                    amount = amount * -1
                payment = StatementLine(
                    statement=statements[0].id,
                    date=fecha,
                    amount=amount,
                    party=sale.party.id,
                    account=account,
                    description='VENTA POS',
                    sale=sale.id,
                    # number=self.start.voucher,
                    # voucher=self.start.voucher,
                )
                payment.save()
                payment.create_move()
            """
        else:
            logging.warning('NO HAY RECIBO POS: '+invoice.number)
        
        
    @classmethod
    def vm_open_statement(cls, args):
        if not args.get('device'):
            return {'result': False}
        pool = Pool()
        Statement = pool.get('account.statement')
        Device = pool.get('sale.device')
        device = Device(args['device'])
        money = args['total_money']
        date = args['date']
        journals = [j.id for j in device.journals]
        statements = Statement.search([
                ('journal', 'in', journals),
                ('sale_device', '=', device.id),
                ('date', '=', date)
            ])
        journals_of_draft_statements = [s.journal for s in statements
                                        if s.state == 'draft']
        
        vlist = []
        for journal in device.journals:
            statements_date = Statement.search([
                ('journal', '=', journal.id),
                ('date', '=', date),
                ('sale_device', '=', device.id),
            ])
            turn = len(statements_date) + 1
            if journal not in journals_of_draft_statements:
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
                if journal.kind == 'cash' and money:
                    values['start_balance'] = Decimal(money)
                vlist.append(values)
        Statement.create(vlist)
        return {'result': True}

    #Metodo encargado de obtener la forma en que se pago el comprobante (recibos)
    @classmethod
    def get_tipo_pago(cls, tipo, nro):
        Config = Pool().get('conector.configuration')
        consult = "SELECT * FROM dbo.Documentos_Che WHERE sw = 5 AND tipo = "+tipo+" AND numero ="+nro
        result = Config.get_data(consult)
        return result
    
    #Metodo encargado de obtener el recibo pagado a una venta cuando es POS
    @classmethod
    def get_recibos(cls, tipo, nro):
        data = []
        try:
            Config = Pool().get('conector.configuration')
            conexion = Config.conexion()
            with conexion.cursor() as cursor:
                #Se realiza una consulta con sw = 1 para el caso de las ventas POS que son aquellas con condicion 1 (efectivo)
                query = cursor.execute("SELECT * FROM dbo.Documentos_Che WHERE sw = 1 AND tipo = "+tipo+" AND numero ="+nro)
                data = list(query.fetchall())
        except Exception as e:
            print("ERROR QUERY get_recibos: ", e)
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
        #consult = "SELECT TOP (10) * FROM dbo.Documentos WHERE fecha_hora >= CAST('"+date+"' AS datetime) AND (sw = 1 OR sw = 2)" #TEST
        consult = "SET DATEFORMAT ymd SELECT TOP(50) * FROM dbo.Documentos WHERE fecha_hora >= CAST('"+date+"' AS datetime) AND (sw = 1 OR sw = 2) AND exportado != 'T'"
        result = Config.get_data(consult)
        return result

    @classmethod
    def importado(cls, id):
        lista = id.split('-')
        try:
            Config = Pool().get('conector.configuration')
            conexion = Config.conexion()
            with conexion.cursor() as cursor:
                cursor.execute("UPDATE dbo.Documentos SET exportado = 'T' WHERE sw ="+lista[0]+" and tipo = "+lista[1]+" and Numero_documento = "+lista[2])
        except Exception as e:
            print(e)
            raise UserError('Error al actualizar como importado: ', e)

    #Función encargada de convertir una fecha dada, al formato y orden para consultas sql server
    #@classmethod
    #def convert_date(cls, fecha):
    #    result = fecha.strftime('%Y-%m-%d %H:%M:%S')
    #    return result

    #Función encargada de consultar si existe un producto dado de la bd
    @classmethod
    def buscar_producto(cls, id_producto):
        Product = Pool().get('product.product')
        producto = Product.search([('id_tecno', '=', id_producto), ('salable', '=', True)])
        if producto:
            return producto[0]
        else:
            msg1 = f'Error al buscar producto con id: {id_producto}'
            logging.error(msg1)
            raise UserError(msg1)
            

    #Función encargada de traer los datos de la bd con una fecha dada.
    @classmethod
    def last_update(cls):
        #Actualizacion = Pool().get('conector.actualizacion')
        #Se consulta la ultima actualización realizada para los terceros
        #ultima_actualizacion = Actualizacion.search([('name', '=','VENTAS')])
        #if ultima_actualizacion:
        #    #Se calcula la fecha restando la diferencia de horas que tiene el servidor con respecto al clienete
        #    if ultima_actualizacion[0].write_date:
        #        fecha = (ultima_actualizacion[0].write_date - datetime.timedelta(hours=5))
        #    else:
        #        fecha = (ultima_actualizacion[0].create_date - datetime.timedelta(hours=5))
        #else:
        #    fecha = datetime.date(1,1,1)
        #    pass
        Config = Pool().get('conector.configuration')
        config, = Config.search([], order=[('id', 'DESC')], limit=1)
        fecha = config.date
        fecha = fecha.strftime('%Y-%m-%d %H:%M:%S')
        data = cls.get_data_tecno(fecha)
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
    def delete_imported_sales(cls, sales):
        sale_table = Table('sale_sale')
        invoice_table = Table('account_invoice')
        move_table = Table('account_move')
        stock_move_table = Table('stock_move')
        cursor = Transaction().connection.cursor()
        #Sale = Pool().get('sale.sale')
        Conexion = Pool().get('conector.configuration')
        for sale in sales:            
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
            
            if sale.id and sale.id_tecno:
                lista = sale.id_tecno.split('-')
                consult = "UPDATE dbo.Documentos SET exportado = 'N' WHERE sw ="+lista[0]+" and tipo = "+lista[1]+" and Numero_documento = "+lista[2]
                Conexion.set_data(consult)
                cursor.execute(*sale_table.delete(
                    where=sale_table.id == sale.id)
                )


    @classmethod
    def unreconcile_move(self, move):
        Reconciliation = Pool().get('account.move.reconciliation')
        reconciliations = [l.reconciliation for l in move.lines if l.reconciliation]
        if reconciliations:
            Reconciliation.delete(reconciliations)