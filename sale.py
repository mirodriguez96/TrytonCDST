import datetime
from typing import Sequence
from trytond.model import fields
from trytond.pool import Pool, PoolMeta
from trytond.exceptions import UserError
from trytond.transaction import Transaction
#from trytond.tools import grouped_slice
from decimal import Decimal
import logging


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
        data = cls.last_update()
        cls.add_sale(data)

    @classmethod
    def add_sale(cls, ventas_tecno):
        actualizacion = cls.create_or_update() #Se crea o actualiza la fecha de importación
        logs = actualizacion.logs
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
            LineTax = pool.get('sale.line-account.tax')
            
            col_param = cls.get_columns_db_tecno('TblParametro')
            venta_pos = cls.get_data_parametros('8')
            venta_electronica = cls.get_data_parametros('9')
            venta_pos = venta_pos[0][col_param.index('Valor')].strip().split(',')
            venta_electronica = venta_electronica[0][col_param.index('Valor')].strip().split(',')
            to_create = []
            #Procedemos a realizar una venta
            for venta in ventas_tecno:
                sw = venta[coluns_doc.index('sw')]
                numero_doc = venta[coluns_doc.index('Numero_documento')]
                tipo_doc = venta[coluns_doc.index('tipo')].strip()
                id_venta = str(sw)+'-'+tipo_doc+'-'+str(numero_doc)
                existe = cls.buscar_venta(id_venta)
                if not existe:
                    #Se trae la fecha de la venta y se adapta al formato correcto para Tryton
                    fecha = str(venta[coluns_doc.index('Fecha_Orden_Venta')]).split()[0].split('-')
                    fecha_date = datetime.date(int(fecha[0]), int(fecha[1]), int(fecha[2]))
                    nit_cedula = venta[coluns_doc.index('nit_Cedula')]
                    party = Party.search([('id_number', '=', nit_cedula)])
                    if not party:
                        logging.warning("Error venta: "+id_venta+" - No se econtro el tercero con id: "+str(nit_cedula))
                        logs = logs+"\n"+"Error venta: "+id_venta+" - No se econtro el tercero con id: "+str(nit_cedula)
                        continue
                    party = party[0]
                    #Se indica a que bodega pertenece
                    id_tecno_bodega = venta[coluns_doc.index('bodega')]
                    bodega = location.search([('id_tecno', '=', id_tecno_bodega)])
                    if not bodega:
                        logging.warning('LA BODEGA: '+str(id_tecno_bodega)+' NO EXISTE')
                        logs = logs+"\n"+"Error venta: "+id_venta+" - NO EXISTE LA BODEGA: "+str(id_tecno_bodega)
                        continue
                    bodega = bodega[0]
                    shop = Shop.search([('warehouse', '=', bodega)])
                    if not shop:
                        logging.warning("No se econtro la bodega: ", venta[coluns_doc.index('bodega')])
                        logs = logs+"\n"+"Error venta: "+id_venta+" - No se econtro la bodega: "+venta[coluns_doc.index('bodega')]
                        continue
                    shop = shop[0]
                    #Se le asigna el plazo de pago correspondiente
                    condicion = venta[coluns_doc.index('condicion')]
                    plazo_pago = payment_term.search([('id_tecno', '=', condicion)])
                    if not plazo_pago:
                        logging.warning("No se econtro el plazo de pago: ", condicion)
                        logs = logs+"\n"+"Error venta: "+id_venta+" - No se econtro el plazo de pago: "+condicion
                        continue
                    plazo_pago = plazo_pago[0]
                    User = pool.get('res.user')
                    with Transaction().set_user(1):
                        context = User.get_preferences()
                    with Transaction().set_context(context, shop=shop.id):
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
                    """
                    sale_data = {
                        'number': tipo_doc+'-'+str(numero_doc),
                        'id_tecno': id_venta,
                        'description': venta[coluns_doc.index('notas')].replace('\n', ' ').replace('\r', ''),
                        'invoice_type': 'C',
                        'sale_date': fecha_date,
                        'party': party.id,
                        'invoice_party': party.id,
                        'shipment_party': party.id,
                        'warehouse': bodega,
                        'shop': shop,
                        'payment_term': plazo_pago
                    }
                    """
                    #Se revisa si la venta es clasificada como electronica o pos y se cambia el tipo
                    if tipo_doc in venta_electronica:
                        #sale_data['invoice_type'] = '1'
                        sale.invoice_type = '1'
                    elif tipo_doc in venta_pos:
                        #sale_data['invoice_type'] = 'P'
                        #sale_data['pos_create_date'] = fecha_date
                        #sale_data['self_pick_up'] = True
                        sale.invoice_type = 'P'
                        sale.pos_create_date = fecha_date
                        sale.self_pick_up = True
                        #Busco la terminal y se la asigno
                        sale_device, = SaleDevice.search([('id_tecno', '=', venta[coluns_doc.index('pc')])])
                        #sale_data['sale_device'] = sale_device
                        sale.sale_device = sale_device
                    #Se busca una dirección del tercero para agregar en la factura y envio
                    address = Address.search([('party', '=', party.id)], limit=1)
                    if address:
                        #sale_data['invoice_address'] = address[0].id
                        #sale_data['shipment_address'] = address[0].id
                        sale.invoice_address = address[0].id
                        sale.shipment_address = address[0].id
                    
                    #SE CREA LA VENTA
                    #sale, = Sale.create([sale_data])
                    sale.save()
                    
                    #Ahora traemos las lineas de producto para la venta a procesar
                    documentos_linea = cls.get_line_where(str(sw), str(numero_doc), str(tipo_doc))
                    col_line = cls.get_columns_db_tecno('Documentos_Lin')
                    create_line = []
                    for lin in documentos_linea:
                        linea = SaleLine()
                        id_producto = str(lin[col_line.index('IdProducto')])
                        producto = cls.buscar_producto(id_producto)
                        if not producto.template.salable:
                            logging.warning("El siguiente producto no es vendible: "+str(producto.code))
                            logs = logs+"\n"+"Error venta: "+id_venta+" - El siguiente producto no es vendible: "+str(producto.code)
                            continue
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
                        #Se verifica si el impuesto al consumo es del mismo valor
                        impuesto_consumo = float(lin[col_line.index('Impuesto_Consumo')])
                        if impuesto_consumo > 0:
                            linea.taxes = []
                            tax = Tax.search([('consumo', '=', True), ('type', '=', 'fixed'), ('amount', '=', impuesto_consumo)])
                            if tax:
                                linetax = LineTax()
                                linetax.line = linea
                                linetax.tax = tax[0]
                                linetax.save()
                            else:
                                raise UserError('ERROR IMPUESTO', 'No se encontró el impuesto al consumo: '+id_venta)
                        linea.unit_price = lin[col_line.index('Valor_Unitario')]
                        #Verificamos si hay descuento para la linea de producto y se agrega su respectivo descuento
                        if lin[col_line.index('Porcentaje_Descuento_1')] > 0:
                            porcentaje = round(Decimal(lin[col_line.index('Porcentaje_Descuento_1')]/100), 3)
                            #line.base_price = lin[col_line.index('Valor_Unitario')]
                            linea.discount = porcentaje
                            #line.on_chFormatopend(linea)
                    #sale_data['lines'] = [('create', create_line)]
                else:
                    """
                    #Se trae la fecha de la venta y se adapta al formato correcto para Tryton
                    fecha = str(venta[coluns_doc.index('Fecha_Orden_Venta')]).split()[0].split('-')
                    fecha_date = datetime.date(int(fecha[0]), int(fecha[1]), int(fecha[2]))
                    nit_cedula = venta[coluns_doc.index('nit_Cedula')]
                    party = Party.search([('id_number', '=', nit_cedula)])
                    if not party:
                        logging.warning("Error venta: "+id_venta+" - No se econtro el tercero con id: "+str(nit_cedula))
                        logs = logs+"\n"+"Error venta: "+id_venta+" - No se econtro el tercero con id: "+str(nit_cedula)
                        continue
                    party = party[0]
                    #Se indica a que bodega pertenece
                    id_tecno_bodega = venta[coluns_doc.index('bodega')]
                    bodega = location.search([('id_tecno', '=', id_tecno_bodega)])
                    if not bodega:
                        logging.warning('LA BODEGA: '+str(id_tecno_bodega)+' NO EXISTE')
                        logs = logs+"\n"+"Error venta: "+id_venta+" - NO EXISTE LA BODEGA: "+str(id_tecno_bodega)
                        continue
                    bodega = bodega[0]
                    shop = Shop.search([('warehouse', '=', bodega)])
                    if not shop:
                        logging.warning("No se econtro la bodega: ", venta[coluns_doc.index('bodega')])
                        logs = logs+"\n"+"Error venta: "+id_venta+" - No se econtro la bodega: "+venta[coluns_doc.index('bodega')]
                        continue
                    shop = shop[0]
                    #Se le asigna el plazo de pago correspondiente
                    condicion = venta[coluns_doc.index('condicion')]
                    plazo_pago = payment_term.search([('id_tecno', '=', condicion)])
                    if not plazo_pago:
                        logging.warning("No se econtro el plazo de pago: ", condicion)
                        logs = logs+"\n"+"Error venta: "+id_venta+" - No se econtro el plazo de pago: "+condicion
                        continue
                    plazo_pago = plazo_pago[0]
                    User = pool.get('res.user')
                    with Transaction().set_user(1):
                        context = User.get_preferences()
                    with Transaction().set_context(context, shop=shop.id):
                        existe = existe
                    existe.number = tipo_doc+'-'+str(numero_doc)
                    existe.description = venta[coluns_doc.index('notas')].replace('\n', ' ').replace('\r', '')
                    existe.invoice_type = 'C'
                    existe.sale_date = fecha_date
                    existe.party = party.id
                    existe.invoice_party = party.id
                    existe.shipment_party = party.id
                    existe.warehouse = bodega
                    existe.shop = shop
                    existe.payment_term = plazo_pago
                    #Se revisa si la venta es clasificada como electronica o pos y se cambia el tipo
                    if tipo_doc in venta_electronica:
                        #sale_data['invoice_type'] = '1'
                        existe.invoice_type = '1'
                    elif tipo_doc in venta_pos:
                        #sale_data['invoice_type'] = 'P'
                        #sale_data['pos_create_date'] = fecha_date
                        #sale_data['self_pick_up'] = True
                        existe.invoice_type = 'P'
                        existe.pos_create_date = fecha_date
                        existe.self_pick_up = True
                        #Busco la terminal y se la asigno
                        sale_device, = SaleDevice.search([('id_tecno', '=', venta[coluns_doc.index('pc')])])
                        #sale_data['sale_device'] = sale_device
                        existe.sale_device = sale_device
                    #Se busca una dirección del tercero para agregar en la factura y envio
                    address = Address.search([('party', '=', party.id)], limit=1)
                    if address:
                        #sale_data['invoice_address'] = address[0].id
                        #sale_data['shipment_address'] = address[0].id
                        existe.invoice_address = address[0].id
                        existe.shipment_address = address[0].id
                    
                    #SE GUARDA LA VENTA
                    existe.save()
                    existe.lines = []
                    #Ahora traemos las lineas de producto para la venta a procesar
                    documentos_linea = cls.get_line_where(str(sw), str(numero_doc), str(tipo_doc))
                    col_line = cls.get_columns_db_tecno('Documentos_Lin')
                    create_line = []
                    for lin in documentos_linea:
                        linea = SaleLine()
                        id_producto = str(lin[col_line.index('IdProducto')])
                        producto = cls.buscar_producto(id_producto)
                        if not producto.template.salable:
                            logging.warning("El siguiente producto no es vendible: "+str(producto.code))
                            logs = logs+"\n"+"Error venta: "+id_venta+" - El siguiente producto no es vendible: "+str(producto.code)
                            continue
                        linea.sale = existe
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
                            existe.reference = venta[coluns_doc.index('Tipo_Docto_Base')].strip()+'-'+str(venta[coluns_doc.index('Numero_Docto_Base')])
                        else:
                            linea.quantity = cantidad_facturada
                            existe.reference = tipo_doc+'-'+str(numero_doc)
                        #Comprueba los cambios y trae los impuestos del producto
                        linea.on_change_product()
                        #Se verifica si el impuesto al consumo es del mismo valor
                        impuesto_consumo = float(lin[col_line.index('Impuesto_Consumo')])
                        if impuesto_consumo > 0:
                            linea.taxes = []
                            tax = Tax.search([('consumo', '=', True), ('type', '=', 'fixed'), ('amount', '=', impuesto_consumo)])
                            if tax:
                                linetax = LineTax()
                                linetax.line = linea
                                linetax.tax = tax[0]
                                linetax.save()
                            else:
                                raise UserError('ERROR IMPUESTO', 'No se encontró el impuesto al consumo: '+id_venta)
                        linea.unit_price = lin[col_line.index('Valor_Unitario')]
                        #Verificamos si hay descuento para la linea de producto y se agrega su respectivo descuento
                        if lin[col_line.index('Porcentaje_Descuento_1')] > 0:
                            porcentaje = round(Decimal(lin[col_line.index('Porcentaje_Descuento_1')]/100), 3)
                            #line.base_price = lin[col_line.index('Valor_Unitario')]
                            linea.discount = porcentaje
                            #line.on_chFormatopend(linea)
                    existe.save()
                    """
                    cls.importado(id_venta)
                to_create.append(sale)
            #print('Ventas a crear: ', len(to_create))
            #Sale.save(to_create)
            #SaleLine.save(create_line)
            #_sale almacena los registros creados
            #_sale = Sale.create(to_create)
            with Transaction().set_user(1):
                context = User.get_preferences()
            with Transaction().set_context(context):
                Sale.quote(to_create)
                Sale.confirm(to_create)#Revisar
                Sale.process(to_create)
            #Procesamos la venta para generar la factura y procedemos a rellenar los campos de la factura
            for sale in to_create:
                print('INICIO VENTA: '+str(sale.id_tecno))
                if len(sale.shipments) == 1:
                    try:
                        shipment_out = sale.shipments[0]
                        shipment_out.number = sale.number
                        shipment_out.reference = sale.reference
                        shipment_out.effective_date = fecha_date
                        shipment_out.wait([shipment_out])
                        shipment_out.pick([shipment_out])#Revvisar
                        shipment_out.pack([shipment_out])#Revvisar
                        shipment_out.done([shipment_out])
                    except Exception as e:
                        logging.warning(str(e))
                        logs = logs+"\n"+"Error venta (envio): "+str(sale.id_tecno)+" - "+str(e)
                        continue
                try:
                    invoice = sale.invoice
                    invoice.accounting_date = sale.invoice_date
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
                    #Verificamos que el total de la tabla en sqlserver coincidan o tengan una diferencia menor a 4 decimales, para contabilizar la factura
                    total_amount = invoice.get_amount([invoice], 'total_amount')
                    total = abs(total_amount['total_amount'][invoice.id])
                    total_tecno = 0
                    for venta in ventas_tecno:
                        tipo_numero_tecno = venta[coluns_doc.index('tipo')].strip()+'-'+str(venta[coluns_doc.index('Numero_documento')])
                        if tipo_numero_tecno == sale.number:
                            total_tecno = Decimal(venta[coluns_doc.index('valor_total')])
                    diferencia_total = abs(total - total_tecno)
                    if diferencia_total <= 1.0:
                        Invoice.post_batch([invoice])
                        Invoice.post([invoice])
                    cls.set_payment(invoice, sale)
                    cls.importado(sale.id_tecno)
                    #Transaction().connection.commit()
                except Exception as e:
                    print('ERROR FACTURA: ', str(e))
                    logs = logs+"\n"+"Error venta (comprobante o factura): "+str(sale.id_tecno)+" - "+str(e)
        actualizacion.logs = logs
        actualizacion.save()
        logging.warning('FINISH VENTAS')


    #Función encargada de buscar recibos de caja pagados en TecnoCarnes y pagarlos en Tryton
    @classmethod
    def set_payment(cls, invoice, sale):
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
        print('INICIO VOUCHER '+invoice.number)
        tipo = tipo_numero[0]
        nro = tipo_numero[1]
        recibos = cls.get_recibos(tipo, nro)
        
        #Si hay recibos para pagar
        if recibos and invoice.invoice_type == 'P':
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
            print('NO HAY RECIBO')
        

    #Metodo encargado de obtener la forma en que se pago el comprobante (recibos)
    @classmethod
    def get_tipo_pago(cls, tipo, nro):
        data = []
        try:
            Config = Pool().get('conector.configuration')
            conexion = Config.conexion()
            with conexion.cursor() as cursor:
                query = cursor.execute("SELECT * FROM dbo.Documentos_Che WHERE sw = 5 AND tipo = "+tipo+" AND numero ="+nro)
                data = list(query.fetchall())
        except Exception as e:
            print("ERROR QUERY get_recibos: ", e)
        return data
    
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
    def get_data_where_tecno(cls, date): #REVISAR PARA OPTIMIZAR
        data = []
        Config = Pool().get('conector.configuration')
        conexion = Config.conexion()
        with conexion.cursor() as cursor:
            query = cursor.execute("SELECT TOP(10) * FROM dbo.Documentos WHERE fecha_hora >= CAST('"+date+"' AS datetime) AND (sw = 1 OR sw = 2) AND exportado != 'T'")
            data = list(query.fetchall())
            print(len(data))
            return data

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
    @classmethod
    def convert_date(cls, fecha):
        result = fecha.strftime('%Y-%d-%m %H:%M:%S')
        return result

    #Función encargada de consultar si existe un producto dado de la bd
    @classmethod
    def buscar_producto(cls, id_producto):
        Product = Pool().get('product.product')
        try:
            producto, = Product.search([('id_tecno', '=', id_producto)])
        except ValueError:
            print("Error, no existe el producto con la siguiente id: ", id_producto)
            raise UserError("Error, no existe el producto con la siguiente id: ", id_producto)
        else:
            return producto

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
        Config = Pool().get('conector.configuration')
        config, = Config.search([], order=[('id', 'DESC')], limit=1)
        fecha = config.date
        fecha = fecha.strftime('%Y-%d-%m %H:%M:%S')
        data = cls.get_data_where_tecno(fecha)
        return data

    #Crea o actualiza un registro de la tabla actualización en caso de ser necesario
    @classmethod
    def create_or_update(cls):
        Actualizacion = Pool().get('conector.actualizacion')
        actualizacion = Actualizacion.search([('name', '=','VENTAS')])
        if actualizacion:
            #Se busca un registro con la actualización
            actualizacion, = Actualizacion.search([('name', '=','VENTAS')])
            actualizacion.name = 'VENTAS'
            #actualizacion.logs = logs
            actualizacion.save()
        else:
            #Se crea un registro con la actualización
            actualizacion = Actualizacion()
            actualizacion.name = 'VENTAS'
            #actualizacion.logs = logs
            actualizacion.save()
        return actualizacion

    #Metodo encargado de buscar si exste una venta
    @classmethod
    def buscar_venta(cls, id):
        Sale = Pool().get('sale.sale')
        sale = Sale.search([('id_tecno', '=', id)])
        if not sale:
            return False
        return sale[0]