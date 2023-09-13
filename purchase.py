import datetime
from trytond.model import fields
from trytond.pool import Pool, PoolMeta
from trytond.exceptions import UserError
from trytond.transaction import Transaction
from decimal import Decimal
from sql import Table
from trytond.pyson import Eval

class Configuration(metaclass=PoolMeta):
    'Configuration'
    __name__ = 'purchase.configuration'
    type_order_tecno = fields.Char('Type order TecnoCarnes')

#Heredamos del modelo purchase.purchase para agregar el campo id_tecno
class Purchase(metaclass=PoolMeta):
    'Purchase'
    __name__ = 'purchase.purchase'
    id_tecno = fields.Char('Id Tabla Sqlserver', required=False)
    order_tecno = fields.Selection([('yes', 'Yes'), ('no', 'No')],
                                   'Order TecnoCarnes',
                                    states={
                                        'readonly': Eval('state').in_(['processing', 'done']),
                                        'required': Eval('state') == 'processing'
                                        }
                                    )
    order_tecno_sent = fields.Boolean('Order TecnoCarnes sent', readonly=True)

    @classmethod
    def copy(cls, purchases, default=None):
        if default is None:
            default = {}
        else:
            default = default.copy()
        # default.setdefault('order_tecno', 'no')
        default.setdefault('order_tecno_sent', False)
        return super(Purchase, cls).copy(purchases, default=default)

    @classmethod
    def import_data_purchase(cls):
        print('RUN COMPRAS')
        cls.import_tecnocarnes('3')

    @classmethod
    def import_data_purchase_return(cls):
        print('RUN DEVOLUCIONES DE COMPRAS')
        cls.import_tecnocarnes('4')

    # Función encargada de importar de SqlServer (TecnoCarnes) las compras y devoluciones de las compras
    @classmethod
    def import_tecnocarnes(cls, swt):
        pool = Pool()
        Config = pool.get('conector.configuration')
        configuration = Config.get_configuration()
        if not configuration:
            return
        Actualizacion = pool.get('conector.actualizacion')
        data = Config.get_documentos_tecno(swt)
        #Se crea o actualiza la fecha de importación
        actualizacion = Actualizacion.create_or_update('COMPRAS')
        if not data:
            actualizacion.save()
            print('FINISH COMPRAS')
            return
        Invoice = pool.get('account.invoice')
        Purchase = pool.get('purchase.purchase')
        PurchaseLine = pool.get('purchase.line')
        Product = pool.get('product.product')
        Location = pool.get('stock.location')
        payment_term = pool.get('account.invoice.payment_term')
        PaymentLine = pool.get('account.invoice-account.move.line')
        Party = pool.get('party.party')
        Address = pool.get('party.address')
        Tax = pool.get('account.tax')
        Module = pool.get('ir.module')
        company_operation = Module.search([('name', '=', 'company_operation'), ('state', '=', 'activated')])
        if company_operation:
            CompanyOperation = pool.get('company.operation_center')
            operation_center = CompanyOperation.search([], order=[('id', 'DESC')], limit=1)
        logs = [] # lista utilizada para almacenar los mensajes (logs) en el proceso de la importación
        to_created = [] # lista utilizada para almacenar los documentos que se importaron correctamente
        to_exception = [] # lista utilizada para almacenar los documentos que tuvieron alguna excepcion en el proceso de la importación
        not_import = [] # lista utilizada para almacenar los documentos que NO se deben importar (anulados)
        parties = Party._get_party_documentos(data, 'nit_Cedula')
        # Procedemos a realizar la compra
        for compra in data:
            sw = compra.sw
            numero_doc = compra.Numero_documento
            tipo_doc = compra.tipo
            id_compra = str(sw)+'-'+tipo_doc+'-'+str(numero_doc)
            try:
                existe = Purchase.search([('id_tecno', '=', id_compra)])
                if existe:
                    if compra.anulado == 'S':
                        msg =  f"El documento {id_compra} fue eliminado de tryton porque fue anulado en TecnoCarnes"
                        logs.append(msg)
                        cls.delete_imported_purchases(existe)
                        not_import.append(id_compra)
                        continue
                    to_created.append(id_compra)
                    continue
                if compra.anulado == 'S':
                    msg = f"{id_compra} Documento anulado en TecnoCarnes"
                    logs.append(msg)
                    not_import.append(id_compra)
                    continue
                print(id_compra)
                if company_operation and not operation_center:
                    msg = f"{id_compra} Falta el centro de operación"
                    logs.append(msg)
                    to_exception.append(id_compra)
                    continue
                purchase = Purchase()
                purchase.number = tipo_doc+'-'+str(numero_doc)
                purchase.id_tecno = id_compra
                purchase.description = compra.notas.replace('\n', ' ').replace('\r', '')
                purchase.order_tecno = 'no'
                #Se trae la fecha de la compra y se adapta al formato correcto para Tryton
                fecha = str(compra.fecha_hora).split()[0].split('-')
                fecha_date = datetime.date(int(fecha[0]), int(fecha[1]), int(fecha[2]))
                purchase.purchase_date = fecha_date
                nit_cedula = compra.nit_Cedula.replace('\n',"")
                party = None
                if nit_cedula in parties['active']:
                    party = parties['active'][nit_cedula]
                if not party:
                    if nit_cedula not in parties['inactive']:
                        msg = f"EXCEPCION {id_compra} - No se encontró el tercero con id {nit_cedula}"
                        logs.append(msg)
                        to_exception.append(id_compra)
                    continue
                purchase.party = party
                #Se busca una dirección del tercero para agregar en la factura y envio
                address = Address.search([('party', '=', party.id)], limit=1)
                if address:
                    purchase.invoice_address = address[0].id
                #Se indica a que bodega pertenece
                bodega = Location.search([('id_tecno', '=', compra.bodega)])
                if not bodega:
                    msg = f"EXCEPCION {id_compra} - No se econtro la bodega {compra.bodega}"
                    logs.append(msg)
                    to_exception.append(id_compra)
                    continue
                bodega = bodega[0]
                purchase.warehouse = bodega
                #Se le asigna el plazo de pago correspondiente
                plazo_pago = payment_term.search([('id_tecno', '=', compra.condicion)])
                if not plazo_pago:
                    msg = f"EXCEPCION {id_compra} - No se econtro el plazo de pago {compra.condicion}"
                    logs.append(msg)
                    to_exception.append(id_compra)
                    continue
                purchase.payment_term = plazo_pago[0]
                lineas_tecno = Config.get_lineasd_tecno(id_compra)
                if not lineas_tecno:
                    msg = f"EXCEPCION {id_compra} - No se encontraron líneas para la compra"
                    logs.append(msg)
                    to_exception.append(id_compra)
                    continue
                retencion_iva = False
                if compra.retencion_iva and compra.retencion_iva > 0:
                    retencion_iva = True
                retencion_ica = False
                if compra.retencion_ica and compra.retencion_ica > 0:
                    retencion_ica = True
                retencion_rete = False
                if compra.retencion_causada and compra.retencion_causada > 0:
                    if not retencion_iva and not retencion_ica:
                        retencion_rete = True
                    elif (compra.retencion_iva + compra.retencion_ica) != compra.retencion_causada:
                        retencion_rete = True
                #Ahora traemos las lineas de producto para la compra a procesar
                #_lines = []
                for lin in lineas_tecno:
                    #print(id_producto)
                    producto = Product.search([('id_tecno', '=', str(lin.IdProducto))])
                    if not producto:
                        msg = f"{id_compra} No se encontro el producto {str(lin.IdProducto)} - Revisar si tiene variante o esta inactivo"
                        logs.append(msg)
                        to_exception.append(id_compra)
                        break
                    #mensaje si la busqueda de "Product" trae mas de un producto
                    elif len(producto) > 1:
                      msg = f"REVISAR {id_compra} - Hay mas de un producto que tienen el mismo código o id_tecno."
                      logs.append(msg)
                      to_exception.append(id_compra)
                      break
                    producto, = producto
                    cantidad_facturada = abs(round(lin.Cantidad_Facturada, 3))
                    if cantidad_facturada < 0: # negativo = devolucion (TecnoCarnes)
                        cant = cantidad_facturada
                        for line in compra.lines:
                            line_quantity = line.quantity
                            if sw == 2:
                                line_quantity = (line_quantity * -1)
                                cant = (cantidad_facturada * -1)
                            if line.product == producto and line_quantity > 0: # Mejorar
                                total_quantity = round((line.quantity + cant), 3)
                                line.quantity = total_quantity
                                line.save()
                                break
                        continue
                    line = PurchaseLine()
                    line.product = producto
                    line.purchase = purchase
                    line.type = 'line'
                    line.unit = producto.template.default_uom
                    #Se verifica si es una devolución
                    if sw == 4:
                        line.quantity = cantidad_facturada * -1
                        #Se indica a que documento hace referencia la devolucion
                        purchase.reference = compra.Tipo_Docto_Base.strip()+'-'+str(compra.Numero_Docto_Base)
                    else:
                        line.quantity = cantidad_facturada
                        purchase.reference = tipo_doc+'-'+str(numero_doc)
                    if company_operation:
                        line.operation_center = operation_center[0]
                    #Comprueba los cambios y trae los impuestos del producto
                    line.on_change_product()
                    #Se verifica si el impuesto al consumo fue aplicado
                    impuesto_consumo = lin.Impuesto_Consumo
                    #A continuación se verifica las retenciones e impuesto al consumo
                    impuestos_linea = []
                    for impuestol in line.taxes:
                        clase_impuesto = impuestol.classification_tax_tecno
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
                            tax = Tax.search([('consumo', '=', True), ('type', '=', 'fixed'), ('amount', '=', impuesto_consumo), ['OR', ('group.kind', '=', 'purchase'), ('group.kind', '=', 'both')]])
                            if tax:
                                if len(tax) > 1:
                                    msg = f"EXCEPCION: {id_compra} - Se encontro mas de un impuesto de tipo consumo con el importe igual a {impuesto_consumo} del grupo compras, recuerde que se debe manejar un unico impuesto con esta configuracion"
                                    logs.append(msg)
                                    to_exception.append(id_compra)
                                    break
                                tax, = tax
                                impuestos_linea.append(tax)
                            else:
                                msg = f"EXCEPCION: {id_compra} No se encontró el impuesto fijo al consumo con valor {str(impuesto_consumo)}"
                                logs.append(msg)
                                to_exception.append(id_compra)
                                break
                        elif clase_impuesto != '05' and clase_impuesto != '06' and clase_impuesto != '07' and not impuestol.consumo:
                            if impuestol not in impuestos_linea:
                                impuestos_linea.append(impuestol)
                    if id_compra in to_exception:
                        break
                    line.taxes = impuestos_linea
                    # line.gross_unit_price = lin.Valor_Unitario
                    line.unit_price = lin.Valor_Unitario
                    #Verificamos si hay descuento para la linea de producto y se agrega su respectivo descuento
                    if lin.Porcentaje_Descuento_1 > 0:
                        porcentaje = round((lin.Porcentaje_Descuento_1/100), 4)
                        line.gross_unit_price = lin.Valor_Unitario
                        line.discount = Decimal(str(porcentaje))
                        line.on_change_discount()
                    line.save()
                if id_compra in to_exception:
                    continue
                #Procesamos la compra para generar la factura y procedemos a rellenar los campos de la factura
                purchase.quote([purchase])
                purchase.confirm([purchase])
                #Se requiere procesar de forma 'manual' la compra para que genere la factura
                purchase.process([purchase])
                #Se hace uso del asistente para crear el envio del proveedor
                if compra.sw == 3:
                    Purchase.generate_shipment([purchase])
                for shipment in purchase.shipments:
                    shipment.reference = purchase.number
                    shipment.planned_date = fecha_date
                    shipment.effective_date = fecha_date
                    shipment.save()
                    shipment.receive([shipment])
                    shipment.done([shipment])
                for shipment in purchase.shipment_returns:
                    shipment.reference = purchase.number
                    shipment.planned_date = fecha_date 
                    shipment.effective_date = fecha_date
                    shipment.save()
                    shipment.wait([shipment])
                    shipment.assign([shipment])
                    shipment.done([shipment])
                if not purchase.invoices:
                    purchase.create_invoice()
                    if not purchase.invoices:
                        msg = f"EXCEPCION {id_compra} sin factura"
                        logs.append(msg)
                        to_exception.append(id_compra)
                        continue
                for invoice in purchase.invoices:
                    invoice.number = purchase.number
                    invoice.invoice_date = fecha_date
                    #Se agrega en la descripcion el nombre del tipo de documento de la tabla en sqlserver
                    # desc = Config.get_tbltipodoctos(tipo_doc)
                    # if desc:
                    #     invoice.description = desc[0].TipoDoctos.replace('\n', ' ').replace('\r', '')
                    original_invoice = None
                    if compra.sw == 4:
                        dcto_base = str(compra.Tipo_Docto_Base)+'-'+str(compra.Numero_Docto_Base)
                        invoice.reference = dcto_base
                        invoice.comment = f"DEVOLUCION DE LA FACTURA {dcto_base}"
                        original_invoice = Invoice.search([('number', '=', dcto_base)])
                        if original_invoice:
                            original_invoice = original_invoice[0]
                        else:
                            msg = f"NO SE ENCONTRO LA FACTURA {dcto_base} PARA CRUZAR CON LA DEVOLUCION {invoice.number}"
                            logs.append(msg)
                    invoice.save()
                    #Verificamos que el total de la tabla en sqlserver coincidan o tengan una diferencia menor a 4 decimales, para contabilizar la factura
                    ttecno = {
                        'retencion_causada': compra.retencion_causada,
                        'valor_total': compra.valor_total,
                    }
                    result = Invoice._validate_total_tecno(invoice.total_amount, ttecno)
                    if not result['value']:
                        msg = f"REVISAR: ({id_compra}) "\
                        f"El total de Tryton {invoice.total_amount} "\
                        f"es diferente al total de TecnoCarnes {result['total_tecno']} "\
                        f"La diferencia es de {result['diferencia']}"
                        logs.append(msg)
                        to_exception.append(id_compra)
                        continue
                    with Transaction().set_context(_skip_warnings=True):
                        Invoice.validate_invoice([invoice])
                        Invoice.post_batch([invoice])
                        Invoice.post([invoice])
                        if original_invoice:
                            # payment_lines = invoice.payment_lines + (invoice.lines_to_pay[0])
                            # original_invoice.payment_lines = payment_lines
                            paymentline = PaymentLine()
                            paymentline.invoice = original_invoice
                            paymentline.invoice_account = invoice.account
                            paymentline.invoice_party = invoice.party
                            paymentline.line = invoice.lines_to_pay[0]
                            paymentline.save()
                            Invoice.process([original_invoice])
                to_created.append(id_compra)
            except Exception as e:
                msg = f"EXCEPCION {id_compra} - {str(e)}"
                logs.append(msg)
                to_exception.append(id_compra)
                continue
        Actualizacion.add_logs(actualizacion, logs)
        for idt in to_created:
            #print('creado...', idt) #TEST
            Config.update_exportado(idt, 'T')
        for idt in to_exception:
            #print('excepcion...', idt) #TEST
            Config.update_exportado(idt, 'E')
        for idt in not_import:
            #print('not_import...', idt) #TEST
            Config.update_exportado(idt, 'X')
        print('FINISH COMPRAS')


    # Se elimina vía base de datos las compras y pagos relacionados
    @classmethod
    def delete_imported_purchases(cls, purchases):
        pool = Pool()
        #Purchase = pool.get('purchase.purchase')
        purchase_table = Table('purchase_purchase')
        invoice_table = Table('account_invoice')
        move_table = Table('account_move')
        stock_move_table = Table('stock_move')
        shipment_table = Table('stock_shipment_in')
        shipment_return_table = Table('stock_shipment_in_return')
        cursor = Transaction().connection.cursor()
        Conexion = pool.get('conector.configuration')
        ids_tecno = []
        for purchase in purchases:
            if purchase.id_tecno:
                ids_tecno.append(purchase.id_tecno)
            else:
                raise UserError("Error: ", f"No se encontró el id_tecno de {purchase}")
            for invoice in purchase.invoices:
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

            if purchase.id:
                cursor.execute(*purchase_table.update(
                    columns=[purchase_table.state, purchase_table.shipment_state, purchase_table.invoice_state],
                    values=['draft', 'none', 'none'],
                    where=purchase_table.id == purchase.id)
                )
            # The stock moves must be delete
            stock_moves = [m.id for line in purchase.lines for m in line.moves]
            shipments = []
            for shipment in purchase.shipments:
                shipments.append(shipment.id)
                for inventory_move in shipment.inventory_moves:
                    stock_moves.append(inventory_move.id)
            shipment_returns = []
            for shipment in purchase.shipment_returns:
                shipment_returns.append(shipment.id)
            if stock_moves:
                cursor.execute(*stock_move_table.update(
                    columns=[stock_move_table.state],
                    values=['draft'],
                    where=stock_move_table.id.in_(stock_moves)
                ))

                cursor.execute(*stock_move_table.delete(
                    where=stock_move_table.id.in_(stock_moves))
                )

            if shipments:
                cursor.execute(*shipment_table.update(
                    columns=[shipment_table.state],
                    values=['draft'],
                    where=shipment_table.id.in_(shipments)
                ))
                #Eliminación de los envíos
                cursor.execute(*shipment_table.delete(
                    where=shipment_table.id.in_(shipments))
                )

            if shipment_returns:
                cursor.execute(*shipment_return_table.update(
                    columns=[shipment_return_table.state],
                    values=['draft'],
                    where=shipment_return_table.id.in_(shipment_returns)
                ))
                #Eliminación de las devoluciones de envíos
                cursor.execute(*shipment_return_table.delete(
                    where=shipment_return_table.id.in_(shipment_returns))
                )

            # Se elimina la compra
            cursor.execute(*purchase_table.delete(
                where=purchase_table.id == purchase.id)
            )
        for idt in ids_tecno:
            Conexion.update_exportado(idt, 'N')


    @classmethod
    def unreconcile_move(self, move):
        Reconciliation = Pool().get('account.move.reconciliation')
        reconciliations = [l.reconciliation for l in move.lines if l.reconciliation]
        if reconciliations:
            Reconciliation.delete(reconciliations)

    @classmethod
    def process(cls, purchases):
        super().process(purchases)
        pool = Pool()
        configuration = pool.get('purchase.configuration')(1)
        for purchase in purchases:
            if purchase.order_tecno == 'yes' and not purchase.order_tecno_sent:
                if configuration.type_order_tecno:
                    cls._send_order(purchase, configuration.type_order_tecno)
                else:
                    raise UserError('Order TecnoCarnes', 'missing type_order_tecno')
                
    
    @classmethod
    def _send_order(cls, purchase, type_order):
        """
        Insert into Documentos_Ped 
        (NUMERO_PEDIDO,NIT,DIRECCION_ENTREGA,DIRECCION_FACTURA,VENDEDOR,FECHA_HORA_PEDIDO,FECHA_HORA_LIMITE_ENTREGA,
        FECHA_HORA_ENTREGA,NUMERO_ENTREGAS,CONDICION,DIAS_VALIDEZ,DESCUENTO_PIE,
        VALOR_TOTAL,ANULADO,NOTAS,USUARIO,PC,DURACION,CONCEPTO,MONEDA,DESPACHO,
        NIT_DESTINO,ABONO,PRIORIDAD,SW,BODEGA,NROOCTERCERO,TELEFONO1,PORC_PENDIENTE,
        IDFORMAENVIO,IDTRANSPORTADOR,COMISION_VENDEDOR,TASA_MONEDA_EXT,CONTACTO_COMPRAS,
        CONTACTO_PAGOS,CERTIFICADO_COMPLETACION,PUNTO_FOB,COD_MOTIVO_ANULACIONES,
        TELEFONO2,EXPORTADO,TIPO_DESTINO,RETENCION_1,USUARIO_APROBACION,FECHA_APROBACION,
        IdAlistador,Ultimo_Cambio_Registro,IdCanal,IdFormaPago) values 
        (3,'98642443',1,1,0,{ ts '2022-12-31 10:46:29' },{ ts '2022-12-31 10:46:29' },
        { ts '2022-12-31 10:46:29' },1,0,0,0,
        0,1,'','Cad_Lan4','CAD',0,0,1,'F',
        '98642443',0,'0',9,1,'0','0',
        100,1,1,0,1,'Desconocido','Desconocido',
        0,'0',0,'0','N',' ',0,' ',
        { ts '2023-02-17 11:35:45' },0,{ ts '2023-02-17 11:35:45' },0,0)

        Insert into Documentos_Lin_Ped 
        (numero_pedido,IdProducto,cantidad,cantidad_despachada,
        valor_unitario,porcentaje_iva,porcentaje_descuento,
        und,cantidad_und,nota,despacho_virtual,porc_dcto_2,
        porc_dcto_3,sw,bodega,fecha_hora_entrega,MaxCantidad,
        MinCantidad,DireccionEnvio,IdVendedor,IdCliente,DireccionFactura,
        Producto,Linea,Exportado,Numero_Lote,Tipo_Destino,Envase,
        Porcentaje_ReteFuente,Serial,Cantidad_Orden) values 
        (3,30,10,0,14000,0,0,'1',0,
        'NOTA ',
        0,0,0,9,1,{ ts '2022-01-03 14:38:10' },
        0,0,1,1,'98642443',1,'PIERNA',1,' ','',' ',0,0,' ',0)
        """

        address = 1
        if purchase.invoice_address.id_tecno:
            address = int(purchase.invoice_address.id_tecno.split('-')[1])

        date_created = purchase.create_date.strftime('%Y-%m-%d %H:%M:%S')
        date_created = f"CAST('{date_created}' AS datetime)"

        warehouse = 1
        if purchase.warehouse.id_tecno:
            warehouse = purchase.warehouse.id_tecno

        pedido = f"SET DATEFORMAT ymd Insert into Documentos_Ped \
            (NUMERO_PEDIDO, NIT, DIRECCION_ENTREGA, DIRECCION_FACTURA, VENDEDOR, \
            FECHA_HORA_PEDIDO, FECHA_HORA_LIMITE_ENTREGA, FECHA_HORA_ENTREGA, \
            NUMERO_ENTREGAS, CONDICION, DIAS_VALIDEZ, DESCUENTO_PIE, VALOR_TOTAL, \
            ANULADO, NOTAS, USUARIO, PC, DURACION, CONCEPTO, MONEDA, DESPACHO, \
            NIT_DESTINO, ABONO, PRIORIDAD, SW, BODEGA, NROOCTERCERO, TELEFONO1, \
            PORC_PENDIENTE, IDFORMAENVIO, IDTRANSPORTADOR, COMISION_VENDEDOR, \
            TASA_MONEDA_EXT, CONTACTO_COMPRAS, CONTACTO_PAGOS, CERTIFICADO_COMPLETACION, \
            PUNTO_FOB, COD_MOTIVO_ANULACIONES, TELEFONO2, EXPORTADO, TIPO_DESTINO, RETENCION_1, \
            USUARIO_APROBACION, FECHA_APROBACION, IdAlistador, Ultimo_Cambio_Registro, \
            IdCanal, IdFormaPago) values \
            ({purchase.number},'{purchase.party.id_number}', {address}, {address}, 0, \
            {date_created}, {date_created}, {date_created}, \
            1, 0, 0, 0, {purchase.total_amount}, \
            1, '{purchase.comment}', 'Cad_Lan4', 'CAD', 0, 0, 1, 'N', \
            '{purchase.party.id_number}', 0, 'A', {type_order}, {warehouse}, 'T-{purchase.number}', '0', \
            100, 1, 2, 0, \
            1, 'Desconocido', 'Desconocido', 0, \
            ' ', 0, ' ', 'N', ' ', 0,\
            ' ', {date_created}, 0, {date_created}, \
            0, 1)"
        # breakpoint()
        linea = f"SET DATEFORMAT ymd Insert into Documentos_Lin_Ped\
            (numero_pedido, IdProducto, cantidad, cantidad_despachada,\
            valor_unitario, porcentaje_iva, porcentaje_descuento,\
            und, cantidad_und, nota, despacho_virtual, porc_dcto_2,\
            porc_dcto_3, sw, bodega, fecha_hora_entrega, MaxCantidad,\
            MinCantidad, DireccionEnvio, IdVendedor, IdCliente, DireccionFactura,\
            Producto, Linea, Exportado, Numero_Lote, Tipo_Destino, Envase,\
            Porcentaje_ReteFuente, Serial, Cantidad_Orden) values "
        
        lineas = ""
        cont = 1
        for line in purchase.lines:
            quantity = line.quantity
            uom = 1
            if line.product.purchase_uom.symbol == 'u':
                uom = 2
            lineas += f"({purchase.number}, {line.product.code}, {quantity}, 0,\
                {line.unit_price}, 0, 0,\
                '{uom}', 1, '{line.note}', 0, 0,\
                0, {type_order}, {warehouse}, {date_created}, {quantity},\
                {quantity}, 1, 1, '{purchase.party.id_number}', 1,\
                '{line.product.name}', {cont}, 'N', ' ', ' ', 0,\
                0, ' ', {quantity})"
            if cont < len(purchase.lines):
                lineas +=", "
            cont += 1
        linea += lineas

        consecutivo = f"UPDATE consecutivos SET siguiente = {purchase.number} WHERE tipo = {type_order}"

        cnx = Pool().get('conector.configuration')
        cnx.set_data_rollback([pedido, linea, consecutivo])
        purchase.order_tecno_sent = True
        purchase.save()


    @classmethod
    def _create_shipment(cls, data):
        if not data:
            return
        pool = Pool()
        Shipment = pool.get('stock.shipment.in')
        # Se procede a crear los envíos segun la compra
        to_create = []
        for number in data:
            purchase  = data[number]['purchase']
            if purchase.shipments:
                continue
            shipment = {
                'reference': purchase.reference,
                'warehouse': purchase.warehouse.id,
                'supplier': purchase.party.id,
                'company': purchase.company.id,
                'effective_date': data[number]['date'],
                'planned_date': data[number]['date'],
            }
            moves = []
            for move in data[number]['lines']:
                move['to_location'] = purchase.warehouse.input_location.id
                move['currency'] = purchase.company.currency.id
                # move = {
                #     'from_location': dict['from_location'].id,
                #     'to_location': purchase.warehouse.input_location.id,
                #     'product': dict['product'].id,
                #     'uom': dict['uom'].id,
                #     'quantity': dict['quantity'],
                #     'unit_price': dict['unit_price'],
                #     'currency': purchase.company.currency.id,
                # }
                for pl in purchase.lines:
                    if pl.product.id == move['product']:
                        move['origin'] = pl
                moves.append(move)
            if moves:
                shipment['incoming_moves'] = [('create', moves)]
            to_create.append(shipment)
        with Transaction().set_context(_skip_warnings=True):
            shipments = Shipment.create(to_create)
            Shipment.receive(shipments)
            Shipment.done(shipments)


    @classmethod
    def _validate_order(cls, lineas):
        pool = Pool()
        Purchase = pool.get('purchase.purchase')
        Product = pool.get('product.product')
        Location = pool.get('stock.location')
        result = {
            'tryton': {},
            'logs': [],
            'exportado': {}
        }
        excepcion = []
        # Se trae las ubicaciones existentes en Tryton
        _locations = Location.search([
            'OR',
            ('type', '=', 'warehouse'), 
            ('type', '=', 'supplier')
        ])
        locations = {}
        for location in _locations:
            if 'supplier' not in locations and location.type == 'supplier':
                locations['supplier'] = location
                continue
            id_tecno = location.id_tecno
            if id_tecno not in locations:
                locations[id_tecno] = location
        # Se procede a validar las líneas
        products = {}
        tecno = {}
        for linea in lineas:
            id_tecno = f"{linea.sw}-{linea.tipo}-{linea.Numero_Documento}" 
            if id_tecno in excepcion:
                continue
            # Se valida la existencia del producto
            idproducto = str(linea.IdProducto)
            if idproducto not in products:
                product = Product.search([('code', '=', idproducto)])
                if not product:
                    msg = f"EXCEPCION - {id_tecno} el producto con codigo {idproducto} no fue encontrado"
                    result['logs'].append(msg)
                    excepcion.append(id_tecno)
                    result['exportado'][id_tecno] = 'E'
                    continue
                products[idproducto], = product
            # Se valida la existencia de la bodega
            # bodega = str(linea.Bodega)
            # if bodega not in locations:
            #     msg = f"EXCEPCION - {id_tecno} la bodega con id {bodega} no fue encontrada"
            #     result['logs'].append(msg)
            #     excepcion.append(id_tecno)
            #     result['exportado'][id_tecno] = 'E'
            #     continue
            # Se valida el precio del producto
            valor_unitario = Decimal(linea.Valor_Unitario)
            if valor_unitario <= 0:
                msg = f"EXCEPCION - {id_tecno} el valor unitario no puede ser menor o igual a cero. Su valor es: {valor_unitario} "
                result['logs'].append(msg)
                excepcion.append(id_tecno)
                result['exportado'][id_tecno] = 'E'
                continue
            # Se valida la cantidad del producto
            cantidad = float(linea.Cantidad_Facturada)
            if cantidad <= 0:
                msg = f"EXCEPCION - {id_tecno} la cantidad no puede ser menor o igual a cero. Su valor es: {cantidad} "
                result['logs'].append(msg)
                excepcion.append(id_tecno)
                result['exportado'][id_tecno] = 'E'
                continue
            if products[idproducto].purchase_uom.symbol == 'u':
                cantidad = int(cantidad)
            else:
                cantidad = round(cantidad, 3)
            # Se procede a almacenar los datos validados
            line = {
                'from_location': locations['supplier'].id,
                # 'to_location': locations[bodega].input_location,
                'product': products[idproducto].id,
                'uom': products[idproducto].purchase_uom.id,
                'quantity': cantidad,
                'unit_price': round(valor_unitario, 2)
            }
            number = linea.DescuentoOrdenVenta.split('-')[1]
            if number not in tecno:
                fecha = str(linea.Fecha_Documento).split()[0].split('-')
                _date = datetime.date(int(fecha[0]), int(fecha[1]), int(fecha[2]))
                tecno[number] = {
                    'id_tecno': id_tecno,
                    'date': _date,
                    'lines': []
                }
            tecno[number]['lines'].append(line)

        # Se trae todas las ordenes de compra que tecno nos indica faltan por entrar la mercancia
        purchases = Purchase.search([
            ('order_tecno', '=', 'yes'),
            ('order_tecno_sent', '=', True),
            ('number', 'in', tecno.keys())
        ])
        # Se valida las ordenes de compra según su estado de envío 
        # y se agregan las líneas que van a ser creadas a la variable result
        for purchase in purchases:
            number = purchase.number
            if purchase.shipments:
                id_tecno = tecno[number]['id_tecno']
                msg = f"EXCEPCION - {id_tecno} el envío de la orden de compra ya se encuentra creado"
                result['logs'].append(msg)
                excepcion.append(id_tecno)
                result['exportado'][id_tecno] = 'E'
                continue
            # Se almacena la compra y las líneas
            if number not in result['tryton']:
                result['tryton'][number] = {
                    'purchase': purchase,
                    'date': tecno[number]['date'],
                    'lines': tecno[number]['lines'],
                }
                result['exportado'][tecno[number]['id_tecno']] = 'T'
        # Se valida si la orden de compra no existe en Tryton
        for number in tecno.keys():
            id_tecno = tecno[number]['id_tecno']
            if number not in result['tryton'] and id_tecno not in excepcion:
                msg = f"EXCEPCION - {id_tecno} no se encontro la orden de compra"
                result['logs'].append(msg)
                excepcion.append(id_tecno)
                result['exportado'][id_tecno] = 'E'
            
        return result
    

    @classmethod
    def import_order_tecno(cls):
        pool = Pool()
        Config = pool.get('conector.configuration')
        Actualizacion = pool.get('conector.actualizacion')
        actualizacion = Actualizacion.create_or_update('ENTRADA DE MERCANCIA')
        lineas = Config.get_documentos_orden()
        result = cls._validate_order(lineas)
        cls._create_shipment(result['tryton'])
        Actualizacion.add_logs(actualizacion, result['logs'])
        for idt, exportado in result['exportado'].items():
            Config.update_exportado(idt, exportado)

        
class PurchaseLine(metaclass=PoolMeta):
    __name__ = 'purchase.line'

    @classmethod
    def __setup__(cls):
        super(PurchaseLine, cls).__setup__()

    # Se hereda la funcion 'compute_taxes' para posteriormente quitar el impuesto (IVA) a los terceros 'regimen_no_responsable'
    # def compute_taxes(self, party):
    #     taxes_id = super(PurchaseLine, self).compute_taxes(party)
    #     Tax = Pool().get('account.tax')
    #     if party.regime_tax == 'regimen_no_responsable':
    #         taxes_result = set()
    #         for tax_id in taxes_id:
    #             tax = Tax(tax_id)
    #             # El impuesto de IVA equivale al codigo 01
    #             if tax.classification_tax_tecno == '01':
    #                 continue
    #             taxes_result.add(tax_id)
    #         taxes_id = list(taxes_result)
    #     return taxes_id