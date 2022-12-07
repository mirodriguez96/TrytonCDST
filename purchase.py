import datetime
from trytond.model import fields
from trytond.pool import Pool, PoolMeta
from trytond.exceptions import UserError
from trytond.transaction import Transaction
from decimal import Decimal
from sql import Table


#Heredamos del modelo purchase.purchase para agregar el campo id_tecno
class Purchase(metaclass=PoolMeta):
    'Purchase'
    __name__ = 'purchase.purchase'
    id_tecno = fields.Char('Id Tabla Sqlserver', required=False)


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
        #Procedemos a realizar la compra
        for compra in data:
            sw = compra.sw
            numero_doc = compra.Numero_documento
            tipo_doc = compra.tipo
            id_compra = str(sw)+'-'+tipo_doc+'-'+str(numero_doc)
            try:
                if compra.anulado == 'S':
                    msg = f"{id_compra} Documento anulado en TecnoCarnes"
                    logs.append(msg)
                    not_import.append(id_compra)
                    continue
                existe = Purchase.search([('id_tecno', '=', id_compra)])
                if existe:
                    to_created.append(id_compra)
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
                #Se trae la fecha de la compra y se adapta al formato correcto para Tryton
                fecha = str(compra.fecha_hora).split()[0].split('-')
                fecha_date = datetime.date(int(fecha[0]), int(fecha[1]), int(fecha[2]))
                purchase.purchase_date = fecha_date
                party = Party.search([('id_number', '=', compra.nit_Cedula.replace('\n',""))])
                if not party:
                    msg = f"EXCEPCION {id_compra} - No se encontró el tercero con id {compra.nit_Cedula}"
                    logs.append(msg)
                    to_exception.append(id_compra)
                    continue
                party = party[0]
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
                not_product = False
                for lin in lineas_tecno:
                    #print(id_producto)
                    producto = Product.search([('id_tecno', '=', str(lin.IdProducto))])
                    if not producto:
                        msg = f"{id_compra} No se encontro el producto {str(lin.IdProducto)}"
                        logs.append(msg)
                        not_product = True
                        break
                    producto, = producto
                    line = PurchaseLine()
                    line.product = producto
                    line.purchase = purchase
                    line.type = 'line'
                    line.unit = producto.template.default_uom
                    #Se verifica si es una devolución
                    cantidad_facturada = abs(round(lin.Cantidad_Facturada, 3))
                    # if line.unit.id == 1:
                    #     cantidad_facturada = int(cantidad_facturada)
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
                    not_impoconsumo = False
                    impuestos_linea = []
                    for impuestol in line.taxes:
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
                                msg = f"{id_compra} No se encontró el impuesto fijo al consumo con valor {str(impuesto_consumo)}"
                                logs.append(msg)
                                not_impoconsumo = True
                                break
                        elif clase_impuesto != '05' and clase_impuesto != '06' and clase_impuesto != '07' and not impuestol.consumo:
                            if impuestol not in impuestos_linea:
                                impuestos_linea.append(impuestol)
                    if not_impoconsumo:
                        not_product = True
                        break
                    line.taxes = impuestos_linea
                    line.unit_price = lin.Valor_Unitario
                    line.save()
                if not_product:
                    to_exception.append(id_compra)
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
                    invoice.reference = purchase.number
                    invoice.invoice_date = fecha_date
                    #Se agrega en la descripcion el nombre del tipo de documento de la tabla en sqlserver
                    desc = Config.get_tbltipodoctos(tipo_doc)
                    if desc:
                        invoice.description = desc[0].TipoDoctos.replace('\n', ' ').replace('\r', '')
                    invoice.validate_invoice([invoice])
                    original_invoice = None
                    if compra.sw == 4:
                        dcto_base = str(compra.Tipo_Docto_Base)+'-'+str(compra.Numero_Docto_Base)
                        invoice.comment = f"DEVOLUCION DE LA FACTURA {dcto_base}"
                        original_invoice = Invoice.search([('number', '=', dcto_base)])
                        if original_invoice:
                            original_invoice = original_invoice[0]
                        else:
                            msg = f"NO SE ENCONTRO LA FACTURA {dcto_base} PARA CRUZAR CON LA DEVOLUCION {invoice.number}"
                            logs.append(msg)
                    #Verificamos que el total de la tabla en sqlserver coincidan o tengan una diferencia menor a 4 decimales, para contabilizar la factura
                    total_tryton = Decimal(abs(invoice.total_amount))
                    total_tecno = Decimal(abs(compra.valor_total))
                    # retencion_causada = Decimal(abs(compra.retencion_causada))
                    # total_tecno = total_tecno - retencion_causada
                    diferencia_total = abs(total_tryton - total_tecno)
                    if diferencia_total < Decimal(6.0):
                        with Transaction().set_context(_skip_warnings=True):
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
                    invoice.save()
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
                for inventory_move in shipment.inventory_moves:
                    stock_moves.append(inventory_move.id)
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
            Conexion.update_exportado(idt, 'S')


    @classmethod
    def unreconcile_move(self, move):
        Reconciliation = Pool().get('account.move.reconciliation')
        reconciliations = [l.reconciliation for l in move.lines if l.reconciliation]
        if reconciliations:
            Reconciliation.delete(reconciliations)