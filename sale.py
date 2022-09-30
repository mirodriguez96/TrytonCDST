import datetime
from trytond.model import fields
from trytond.pool import Pool, PoolMeta
from trytond.exceptions import UserError
from trytond.transaction import Transaction
from decimal import Decimal
from sql import Table



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
        print('RUN VENTAS')
        pool = Pool()
        Config = pool.get('conector.configuration')
        Actualizacion = pool.get('conector.actualizacion')
        data = []
        ventas_tecno = Config.get_documentos_tecno('1')
        if ventas_tecno:
            data = ventas_tecno
        devoluciones_tecno = Config.get_documentos_tecno('2')
        if devoluciones_tecno:
            data += devoluciones_tecno

        #Se crea o actualiza la fecha de importación
        actualizacion = Actualizacion.create_or_update('VENTAS')
        if not data:
            actualizacion.save()
            print('FINISH VENTAS')
            return
        Sale = pool.get('sale.sale')
        SaleLine = pool.get('sale.line')
        Product = pool.get('product.product')
        SaleDevice = pool.get('sale.device')
        Location = pool.get('stock.location')
        payment_term = pool.get('account.invoice.payment_term')
        Party = pool.get('party.party')
        Address = pool.get('party.address')
        Shop = pool.get('sale.shop')
        Tax = pool.get('account.tax')
        User = pool.get('res.user')
        Module = pool.get('ir.module')
        
        # Se consulta si el módulo company_operation esta activado
        company_operation = Module.search([('name', '=', 'company_operation'), ('state', '=', 'activated')])
        if company_operation:
            CompanyOperation = pool.get('company.operation_center')
            operation_center = CompanyOperation.search([], order=[('id', 'DESC')], limit=1)
        venta_pos = []
        pdevoluciones_pos = Config.get_data_parametros('10')
        if pdevoluciones_pos:
            pdevoluciones_pos = (pdevoluciones_pos[0].Valor).strip().split(',')
            venta_pos += pdevoluciones_pos
        pventa_pos = Config.get_data_parametros('8')
        if pventa_pos:
            pventa_pos = (pventa_pos[0].Valor).strip().split(',')
            venta_pos += pventa_pos
        venta_electronica = Config.get_data_parametros('9')
        if venta_electronica:
            venta_electronica = (venta_electronica[0].Valor).strip().split(',')
        logs = []
        to_created = []
        to_exception = []
        #Procedemos a realizar una venta
        for venta in data:
            try:
                sw = venta.sw
                numero_doc = venta.Numero_documento
                tipo_doc = venta.tipo
                id_venta = str(sw)+'-'+tipo_doc+'-'+str(numero_doc)
                existe = Sale.search([('id_tecno', '=', id_venta)])
                if existe:
                    to_created.append(id_venta)
                    continue
                print(id_venta)
                if company_operation and not operation_center:
                    msg = f"{id_venta} Falta el centro de operación"
                    logs.append(msg)
                    to_exception.append(id_venta)
                    continue
                analytic_account = None
                if hasattr(SaleLine, 'analytic_accounts'):
                    tbltipodocto = Config.get_tbltipodoctos(tipo_doc)
                    if tbltipodocto and tbltipodocto[0].Encabezado != '0':
                        AnalyticAccount = pool.get('analytic_account.account')
                        analytic_account = AnalyticAccount.search([('code', '=', str(tbltipodocto[0].Encabezado))])
                        if not analytic_account:
                            msg = f'EXCEPCION {id_venta} - No se encontro la asignacion de la cuenta analitica en TecnoCarnes {str(tbltipodocto[0].Encabezado)}'
                            logs.append(msg)
                            to_exception.append(id_venta)
                            continue
                        analytic_account = analytic_account[0]
                #Se trae la fecha de la venta y se adapta al formato correcto para Tryton
                fecha = str(venta.fecha_hora).split()[0].split('-')
                fecha_date = datetime.date(int(fecha[0]), int(fecha[1]), int(fecha[2]))
                nit_cedula = venta.nit_Cedula
                party = Party.search([('id_number', '=', nit_cedula)])
                if not party:
                    msg2 = f'EXCEPCION {id_venta} - No se encontro el tercero {nit_cedula}'
                    logs.append(msg2)
                    actualizacion.reset_writedate('TERCEROS')
                    to_exception.append(id_venta)
                    continue
                party = party[0]
                #Se indica a que bodega pertenece
                id_tecno_bodega = venta.bodega
                bodega = Location.search([('id_tecno', '=', id_tecno_bodega)])
                if not bodega:
                    msg2 = f'EXCEPCION {id_venta} - Bodega {id_tecno_bodega} no existe'
                    logs.append(msg2)
                    to_exception.append(id_venta)
                    continue
                bodega = bodega[0]
                shop = Shop.search([('warehouse', '=', bodega.id)])
                if not shop:
                    msg2 = f'EXCEPCION {id_venta} - Tienda (bodega) {id_tecno_bodega} no existe'
                    logs.append(msg2)
                    to_exception.append(id_venta)
                    continue
                shop = shop[0]
                #Se le asigna el plazo de pago correspondiente
                condicion = venta.condicion
                plazo_pago = payment_term.search([('id_tecno', '=', condicion)])
                if not plazo_pago:
                    msg2 = f'EXCEPCION {id_venta} - Plazo de pago {condicion} no existe'
                    logs.append(msg2)
                    to_exception.append(id_venta)
                    continue
                plazo_pago = plazo_pago[0]
                #Ahora traemos las lineas (productos) para la venta
                documentos_linea = Config.get_lineasd_tecno(id_venta)
                if not documentos_linea:
                    msg = f"EXCEPCION {id_venta} - No se encontraron líneas para la venta"
                    logs.append(msg)
                    to_exception.append(id_venta)
                    continue
                with Transaction().set_user(1):
                    User.shop = shop
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
                sale.payment_term = plazo_pago
                sale.self_pick_up = False
                #Se revisa si la venta es clasificada como electronica o pos y se cambia el tipo
                if tipo_doc in venta_electronica:
                    #continue #TEST
                    sale.invoice_type = '1'
                elif tipo_doc in venta_pos:
                    sale.shop = shop
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
                #Ahora se procede a crear las líneas para la venta
                not_product = False
                #_lines = []
                for lin in documentos_linea:
                    producto = Product.search(['OR', ('id_tecno', '=', str(lin.IdProducto)), ('code', '=', str(lin.IdProducto))])
                    if not producto:
                        msg = f"{id_venta} No se encontro el producto {str(lin.IdProducto)}"
                        logs.append(msg)
                        not_product = True
                        break
                    producto, = producto
                    linea = SaleLine()
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
                        linea.operation_center = operation_center[0]
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
                    # Se guarda la linea para la venta
                    # linea.on_change_quantity()
                    if analytic_account:
                        AnalyticEntry = pool.get('analytic.account.entry')
                        root, = AnalyticAccount.search([('type', '=', 'root')])
                        analytic_entry = AnalyticEntry()
                        analytic_entry.root = root
                        analytic_entry.account = analytic_account
                        linea.analytic_accounts = [analytic_entry]
                    # _lines.append(linea)
                    linea.save()
                if not_product:
                    to_exception.append(id_venta)
                    continue
                #Se procesa los registros creados
                with Transaction().set_user(1):
                    context = User.get_preferences()
                with Transaction().set_context(context, _skip_warnings=True):
                    Sale.quote([sale])
                    Sale.confirm([sale])
                    Sale.process([sale])
                    cls.finish_shipment_process(sale)
                    if sale.invoice_type == 'P':
                        Sale.post_invoices(sale)
                        if sale.payment_term.id_tecno == '0':
                            cls.set_payment_pos(sale, logs, to_exception)
                            Sale.update_state([sale])
                    else:
                        cls.finish_invoice_process(sale, venta, logs, to_exception)
                to_created.append(id_venta)
            except Exception as e:
                msg = f"EXCEPCION {id_venta} - {str(e)}"
                logs.append(msg)
                to_exception.append(id_venta)
        Actualizacion.add_logs(actualizacion, logs)
        for idt in to_created:
            if idt not in to_exception:
                Config.update_exportado(idt, 'T')
                # print('creado...', idt) #TEST
        for idt in to_exception:
            Config.update_exportado(idt, 'E')
            # print('excepcion...', idt) #TEST
        print('FINISH VENTAS')


    # Funcion encargada de finalizar el proceso de envío de la venta
    @classmethod
    def finish_shipment_process(cls, sale):
        for shipment in sale.shipments:
            shipment.number = sale.number
            shipment.reference = sale.reference
            shipment.effective_date = sale.sale_date
            shipment.wait([shipment])
            shipment.pick([shipment])
            shipment.pack([shipment])
            shipment.done([shipment])
        for shipment in sale.shipment_returns:
            shipment.number = sale.number
            shipment.reference = sale.reference
            shipment.effective_date = sale.sale_date
            shipment.receive([shipment])
            shipment.done([shipment])

    #Se actualiza las facturas y envios con la información de la venta
    @classmethod
    def finish_invoice_process(cls, sale, venta, logs, to_exception):
        pool = Pool()
        Invoice = pool.get('account.invoice')
        PaymentLine = pool.get('account.invoice-account.move.line')
        Config = pool.get('conector.configuration')
        #Procesamos la venta para generar la factura y procedemos a rellenar los campos de la factura
        if not sale.invoices:
            sale._process_invoice([sale])
            if not sale.invoices:
                msg1 = f"EXCEPTION {sale.id_tecno} VENTA SIN FACTURA"
                logs.append(msg1)
                to_exception.append(sale.id_tecno)
        for invoice in sale.invoices:
            invoice.accounting_date = sale.sale_date
            invoice.number = sale.number
            invoice.reference = sale.reference
            invoice.invoice_date = sale.sale_date
            invoice.invoice_type = 'C'
            tipo_numero = sale.number.split('-')
            #Se agrega en la descripcion el nombre del tipo de documento de la tabla en sqlserver
            tbltipodocto = Config.get_tbltipodoctos(tipo_numero[0])
            if tbltipodocto:
                invoice.description = tbltipodocto[0].TipoDoctos.replace('\n', ' ').replace('\r', '')
            invoice.save()
            Invoice.validate_invoice([invoice])
            total_tryton = abs(invoice.untaxed_amount)
            #Se almacena el total de la venta traida de TecnoCarnes
            total_tecno = 0
            valor_total = Decimal(abs(venta.valor_total))
            valor_impuesto = Decimal(abs(venta.Valor_impuesto) + abs(venta.Impuesto_Consumo))
            if valor_impuesto > 0:
                total_tecno = valor_total - valor_impuesto
            else:
                total_tecno = valor_total
            diferencia_total = abs(total_tryton - total_tecno)
            if venta.sw == 2:
                dcto_base = str(venta.Tipo_Docto_Base)+'-'+str(venta.Numero_Docto_Base)
                original_invoice = Invoice.search([('number', '=', dcto_base)])
                if original_invoice:
                    invoice.original_invoice = original_invoice[0]
                else:
                    msg = f"NO SE ENCONTRO LA FACTURA {dcto_base} PARA CRUZAR CON LA DEVOLUCION {invoice.number}"
                    logs.append(msg)
                    to_exception.append(sale.id_tecno)
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
                msg1 = f'FACTURA {sale.id_tecno}'
                msg2 = f'No contabilizada diferencia total mayor al rango permitido'
                full_msg = ' - '.join([msg1, msg2])
                logs.append(full_msg)
                invoice.comment = msg2
                invoice.save()

    #Función encargada de buscar recibos de caja pagados en TecnoCarnes y pagarlos en Tryton
    @classmethod
    def set_payment_pos(cls, sale, logs, to_exception):
        Config = Pool().get('conector.configuration')
        pagos = Config.get_tipos_pago(sale.id_tecno)
        if not pagos:
            msg = f"EXCEPCION {sale.id_tecno} - No se encontraron pagos asociados en tecnocarnes (documentos_che)"
            logs.append(msg)
            to_exception.append(sale.id_tecno)
            return
        #si existe pagos pos...
        pool = Pool()
        Journal = pool.get('account.statement.journal')
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
            valor = pago.valor
            if pago.sw == 2 and valor > 0:
                valor = valor*-1
            data_payment = {
                'sales': {
                    sale: valor
                },
                'statement': statement.id,
                'date': fecha_date
            }
            result_payment = cls.multipayment_invoices_statement(data_payment, logs, to_exception)
            if result_payment != 'ok':
                msg = f"ERROR AL PROCESAR EL PAGO DE LA VENTA POS {sale.number}"
                logs.append(msg)

    
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
    def multipayment_invoices_statement(cls, args, logs, to_exception):
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
            user = User(1)
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
            total_paid = Decimal(0.0)
            if sale.payments:
                total_paid = sum([p.amount for p in sale.payments])
                if total_paid >= sale.total_amount:
                    if total_paid == sale.total_amount:
                        Sale.do_reconcile([sale])
                    else:
                        msg = f"{sale.id_tecno} sale_pos.msg_total_paid_>_total_amount"
                        logs.append(msg)
                        to_exception.append(sale.id_tecno)
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
                    msg = f"sale_pos.msg_party_without_account_receivable"
                    logs.append(msg)
                    to_exception.append(sale.id_tecno)
                    continue
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
