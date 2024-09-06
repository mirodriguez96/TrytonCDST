from trytond.wizard import Wizard, StateView, Button, StateReport
from trytond.transaction import Transaction
from trytond.model import fields, ModelView
from trytond.exceptions import UserError
from trytond.pool import Pool, PoolMeta
from trytond.report import Report
from trytond.pyson import Eval, If


from sql.operators import Like, Between
from collections import OrderedDict
from sql.aggregate import Sum
from decimal import Decimal
from datetime import date
from sql import Table


STATES = [("", ""), ("draft", "Borrador"), ("done", "Finalizado")]
TYPE_DOCUMENT = [("", "")]


class Sale(metaclass=PoolMeta):
    'Sale inheritance Model'
    __name__ = 'sale.sale'
    id_tecno = fields.Char('Id Tabla Sqlserver', required=False, select=True)
    invoice_amount_tecno = fields.Numeric('Value_Tecno',
                                          digits=(16, 2),
                                          required=False)
    tax_amount_tecno = fields.Numeric('Value_Tax_Tecno',
                                      digits=(16, 2),
                                      required=False)

    @classmethod
    def import_data_sale(cls):
        print('RUN VENTAS')
        cls.import_tecnocarnes('1')

    @classmethod
    def import_data_sale_return(cls):
        print('RUN DEVOLUCIONES DE VENTAS')
        cls.import_tecnocarnes('2')

    @classmethod
    def import_tecnocarnes(cls, swt):
        """Function to import Sales and Sale returns to tecnocarnes"""

        pool = Pool()
        Sale = pool.get('sale.sale')
        SaleLine = pool.get('sale.line')
        Period = pool.get('account.period')
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
        Config = pool.get('conector.configuration')
        configuration = Config.get_configuration()
        Actualizacion = pool.get('conector.actualizacion')

        logs = {}
        logs_che = {}
        to_created = []
        to_exception = []
        not_import = []
        venta_pos = []

        data = Config.get_documentos_tecno(swt)

        if not configuration or not data:
            return

        actualizacion = Actualizacion.create_or_update('VENTAS')
        actualizacion_che = Actualizacion.create_or_update('SIN DOCUMENTO CHE')

        parties = Party._get_party_documentos(data, 'nit_Cedula')

        # validate if operation center is active
        company_operation = Module.search([('name', '=', 'company_operation'),
                                           ('state', '=', 'activated')])
        if company_operation:
            CompanyOperation = pool.get('company.operation_center')
            operation_center = CompanyOperation.search([],
                                                       order=[('id', 'DESC')],
                                                       limit=1)

        # Save the sale types of tecnocarnes
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

        # Build the SALE
        for venta in data:
            try:
                analytic_account = None
                party = None
                retencion_iva = False
                retencion_ica = False
                retencion_rete = False

                sw = venta.sw
                numero_doc = venta.Numero_documento
                tipo_doc = venta.tipo
                id_venta = str(sw) + '-' + tipo_doc + '-' + str(numero_doc)

                value_total = Decimal(str(round(venta.valor_total,
                                                2)))
                caused_retention = Decimal(str(round(venta.retencion_causada,
                                                     2)))
                tax_consumption = Decimal(str(round(venta.Impuesto_Consumo,
                                                    2)))
                invoice_amount_tecno = value_total - caused_retention

                if venta.Valor_impuesto:
                    tax_amount_tecno = Decimal(
                        str(round(venta.Impuesto_Consumo, 2)))
                else:
                    tax_amount_tecno = Decimal(0)

                already_sale = Sale.search([('id_tecno', '=', id_venta)])
                if already_sale:
                    if venta.anulado == 'S':
                        dat = str(venta.fecha_hora).split()[0].split('-')
                        name = f"{dat[0]}-{dat[1]}"
                        validate_period = Period.search([('name', '=', name)])
                        if validate_period[0].state == 'close':
                            to_exception.append(id_venta)
                            logs[id_venta] = "EXCEPCION: EL PERIODO DEL \
                                    DOCUMENTO SE ENCUENTRA CERRADO Y NO ES \
                                    POSIBLE SU ELIMINACION O MODIFICACION"

                            continue

                        cls.delete_imported_sales(already_sale)
                        logs[id_venta] = "El documento fue eliminado de tryton\
                                porque fue anulado en TecnoCarnes"

                        not_import.append(id_venta)
                        continue

                    to_created.append(id_venta)
                    continue

                if venta.anulado == 'S':
                    logs[id_venta] = "Documento anulado en TecnoCarnes"
                    not_import.append(id_venta)
                    continue

                if venta.sw == 2:
                    dcto_base = str(venta.Tipo_Docto_Base) + '-' + str(
                        venta.Numero_Docto_Base)
                    original_invoice = Sale.search([('number', '=', dcto_base)
                                                    ])
                    if not original_invoice:
                        msg = f"EXCEPCION: El documento (devolucion) \
                            {id_venta} no encuentra el documento de \
                            referencia {dcto_base} para ser cruzado"

                        logs[id_venta] = msg
                        to_exception.append(id_venta)
                        continue

                if company_operation and not operation_center:
                    msg = f"EXCEPCION {id_venta} - Falta centro de operación"
                    logs[id_venta] = msg
                    to_exception.append(id_venta)
                    continue

                date_ = str(venta.fecha_hora).split()[0].split('-')
                name = f"{date_[0]}-{date_[1]}"
                validate_period = Period.search([('name', '=', name)])
                if validate_period[0].state == 'close':
                    to_exception.append(id_venta)
                    logs[id_venta] = "EXCEPCION: EL PERIODO DEL DOCUMENTO SE "
                    "ENCUENTRA CERRADO Y NO ES POSIBLE SU CREACION"
                    continue

                if hasattr(SaleLine, 'analytic_accounts'):
                    tbltipodocto = Config.get_tbltipodoctos(tipo_doc)
                    if tbltipodocto and tbltipodocto[0].Encabezado != '0':
                        AnalyticAccount = pool.get('analytic_account.account')
                        analytic_account = AnalyticAccount.search([
                            ('code', '=', str(tbltipodocto[0].Encabezado))
                        ])
                        if not analytic_account:
                            msg = f'EXCEPCION {id_venta} - No se encontro \
                                la asignacion de la cuenta analitica en \
                                TecnoCarnes {str(tbltipodocto[0].Encabezado)}'

                            logs[id_venta] = msg
                            to_exception.append(id_venta)
                            continue
                        analytic_account = analytic_account[0]

                # build data_sale from tecnocarnes
                fecha = str(venta.fecha_hora).split()[0].split('-')
                fecha_date = date(int(fecha[0]), int(fecha[1]),
                                  int(fecha[2]))

                nit_cedula = venta.nit_Cedula.replace('\n', "")
                if nit_cedula in parties['active']:
                    party = parties['active'][nit_cedula]
                if not party:
                    if nit_cedula not in parties['inactive']:
                        logs[id_venta] = f"EXCEPCION: No se encontro \
                                el tercero {nit_cedula}"

                        to_exception.append(id_venta)
                    continue

                # asgined the location
                id_tecno_bodega = venta.bodega
                bodega = Location.search([('id_tecno', '=', id_tecno_bodega)])
                if not bodega:
                    logs[id_venta] = f"EXCEPCION: Bodega {id_tecno_bodega} \
                            no existe"

                    to_exception.append(id_venta)
                    continue
                bodega = bodega[0]

                # asigned the warehouse
                shop = Shop.search([('warehouse', '=', bodega.id)])
                if not shop:
                    logs[id_venta] = f"EXCEPCION: Tienda (bodega) \
                            {id_tecno_bodega} no existe"

                    to_exception.append(id_venta)
                    continue
                shop = shop[0]

                # asigned payment condition
                condicion = venta.condicion
                plazo_pago = payment_term.search([('id_tecno', '=', condicion)
                                                  ])
                if not plazo_pago:
                    logs[id_venta] = f"EXCEPCION: \
                            Plazo de pago {condicion} no existe"

                    to_exception.append(id_venta)
                    continue
                plazo_pago = plazo_pago[0]

                # get product lines for sale
                documentos_linea = Config.get_lineasd_tecno(id_venta)
                if not documentos_linea:
                    logs[id_venta] = "EXCEPCION: No se encontraron \
                            líneas para la venta"

                    to_exception.append(id_venta)
                    continue

                # asigned sale (terminal)
                id_tecno_device = venta.pc + '-' + str(venta.bodega)
                sale_device = SaleDevice.search([
                    'OR', ('id_tecno', '=', id_tecno_device),
                    [
                        'AND', ('id_tecno', '=', venta.pc),
                        ('shop.warehouse.id_tecno', '=', venta.bodega)
                    ]
                ])
                if not sale_device:
                    logs[id_venta] = f"EXCEPCION: Terminal \
                            de venta {id_tecno_device} no existe"

                    to_exception.append(id_venta)
                    continue
                elif len(sale_device) > 1:
                    logs[id_venta] = "EXCEPCION: Hay mas de una \
                            terminal que concuerdan con el mismo \
                            equipo de venta y bodega"

                    to_exception.append(id_venta)
                    continue
                sale_device = sale_device[0]

                # Finished process to build SALE
                with Transaction().set_user(1):
                    User.shop = shop
                    context = User.get_preferences()
                with Transaction().set_context(context,
                                               shop=shop.id,
                                               _skip_warnings=True):
                    sale = Sale()

                sale.number = tipo_doc + '-' + str(numero_doc)
                sale.reference = tipo_doc + '-' + str(numero_doc)
                sale.id_tecno = id_venta
                sale.description = (venta.notas).replace('\n', ' ').replace(
                    '\r', '').replace('\t', ' ')
                sale.invoice_type = 'C'
                sale.sale_date = fecha_date
                sale.party = party.id
                sale.invoice_party = party.id
                sale.shipment_party = party.id
                sale.warehouse = bodega
                sale.payment_term = plazo_pago
                sale.self_pick_up = False
                sale.invoice_number = sale.number
                sale.invoice_date = fecha_date
                sale.invoice_amount_tecno = Decimal(
                    str(round(invoice_amount_tecno, 2)))
                sale.tax_amount_tecno = Decimal(str(round(tax_amount_tecno,
                                                          2)))
                """ Se revisa si la venta es clasificada como electronica o
                pos y se cambia el tipo"""
                if tipo_doc in venta_electronica:
                    sale.invoice_type = '1'
                elif tipo_doc in venta_pos:
                    sale.shop = shop
                    sale.invoice_type = 'P'
                    sale.pos_create_date = fecha_date
                    sale.sale_device = sale_device
                """ Se busca una dirección del tercero para agregar en la
                factura y envio"""
                address = Address.search([('party', '=', party.id)], limit=1)
                if address:
                    sale.invoice_address = address[0].id
                    sale.shipment_address = address[0].id
                sale.save()
                """Se revisa si se aplico alguno de
                los 3 impuestos en la venta"""
                if venta.retencion_iva > 0:
                    retencion_iva = True

                if venta.retencion_ica > 0:
                    retencion_ica = True

                if venta.retencion_causada > 0:
                    if not retencion_iva and not retencion_ica:
                        retencion_rete = True
                    elif (venta.retencion_iva +
                          venta.retencion_ica) != venta.retencion_causada:
                        retencion_rete = True

                for lin in documentos_linea:
                    impuestos_linea = []

                    producto = Product.search([
                        'OR', ('id_tecno', '=', str(lin.IdProducto)),
                        ('code', '=', str(lin.IdProducto))
                    ])

                    if not producto:
                        msg = f"EXCEPCION: No se encontro el producto \
                            {str(lin.IdProducto)} - \
                            Revisar si tiene variante o esta inactivo"

                        logs[id_venta] = msg
                        to_exception.append(id_venta)
                        break

                    if len(producto) > 1:
                        logs[id_venta] = "EXCEPCION: Hay mas de un \
                                producto que tienen el mismo código o id_tecno"

                        to_exception.append(id_venta)
                        break

                    producto, = producto
                    """Validate if product is not salable"""
                    if not producto.template.salable:
                        msg = f"EXCEPCION: El producto \
                            {str(lin.IdProducto)} \
                            no esta marcado como vendible"

                        logs[id_venta] = msg
                        to_exception.append(id_venta)
                        break
                    cantidad_facturada = round(float(lin.Cantidad_Facturada),
                                               3)

                    if producto.template.default_uom.id == 1:
                        cantidad_facturada = int(cantidad_facturada)
                    if cantidad_facturada < 0:  # negativo = devolucion (Tecno)
                        cant = cantidad_facturada
                        for line in sale.lines:
                            line_quantity = line.quantity
                            if sw == 2:
                                line_quantity = (line_quantity * -1)
                                cant = (cantidad_facturada * -1)
                            if line.product == producto and line_quantity > 0:
                                total_quantity = round((line.quantity + cant),
                                                       3)
                                line.quantity = total_quantity
                                line.save()
                                break
                        continue

                    linea = SaleLine()
                    linea.sale = sale
                    linea.product = producto
                    linea.type = 'line'
                    linea.unit = producto.sale_uom

                    # Validate if is sale return
                    if sw == 2:
                        linea.quantity = cantidad_facturada * -1
                        dcto_base = str(venta.Tipo_Docto_Base) + '-' + str(
                            venta.Numero_Docto_Base)

                        # asigned document reference
                        sale.reference = dcto_base
                        sale.comment = f"DEVOLUCIÓN DE LA FACTURA {dcto_base}"
                    else:
                        linea.quantity = cantidad_facturada

                    if company_operation:
                        linea.operation_center = operation_center[0]

                    # validate changes and get taxes from product
                    linea.on_change_product()

                    # validate if tax consumption was appyl
                    impuesto_consumo = lin.Impuesto_Consumo

                    # validate withholdings and tax consumption
                    for impuestol in linea.taxes:
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
                            # validate tax consumption for apply
                            tax = Tax.search([('consumo', '=', True),
                                              ('type', '=', 'fixed'),
                                              ('amount', '=',
                                               impuesto_consumo),
                                              [
                                                  'OR',
                                                  ('group.kind', '=', 'sale'),
                                                  ('group.kind', '=', 'both')
                            ]])
                            if tax:
                                if len(tax) > 1:
                                    msg = f"EXCEPCION: ({id_venta})\
                                        Se encontro mas de un impuesto\
                                        de tipo consumo con el importe igual\
                                        a {impuesto_consumo} del grupo\
                                        venta, recuerde que se debe manejar\
                                        un unico impuesto con esta\
                                        configuracion"

                                    logs[id_venta] = msg
                                    to_exception.append(id_venta)
                                    break
                                tax, = tax
                                impuestos_linea.append(tax)
                            else:
                                msg = f"EXCEPCION: No se encontró el impuesto \
                                    al consumo con el importe igual a \
                                    {impuesto_consumo}"

                                logs[id_venta] = msg
                                to_exception.append(id_venta)
                                break

                        elif clase_impuesto != '05' \
                            and clase_impuesto != '06' \
                            and clase_impuesto != '07' \
                                and not impuestol.consumo:
                            if impuestol not in impuestos_linea:
                                impuestos_linea.append(impuestol)

                    linea.taxes = impuestos_linea
                    linea.base_price = lin.Valor_Unitario
                    linea.unit_price = lin.Valor_Unitario

                    # validate if product line have a discount to add it
                    if lin.Porcentaje_Descuento_1 > 0:
                        porcentaje = lin.Porcentaje_Descuento_1 / 100
                        linea.base_price = lin.Valor_Unitario
                        linea.discount_rate = Decimal(str(porcentaje))
                        linea.on_change_discount_rate()

                    # save the line for the SALE
                    if analytic_account:
                        AnalyticEntry = pool.get('analytic.account.entry')
                        root, = AnalyticAccount.search([('type', '=', 'root')])
                        analytic_entry = AnalyticEntry()
                        analytic_entry.root = root
                        analytic_entry.account = analytic_account
                        linea.analytic_accounts = [analytic_entry]
                    linea.save()

                if id_venta in to_exception:
                    sale.number = None
                    sale.invoice_number = None
                    sale.save()
                    Sale.delete([sale])
                    continue

                # process created registry
                with Transaction().set_user(1):
                    context = User.get_preferences()

                with Transaction().set_context(context, _skip_warnings=True):
                    Sale.quote([sale])
                    Sale.confirm([sale])
                    Sale.process([sale])
                    cls.finish_shipment_process(sale, numero_doc, Config,
                                                tipo_doc)
                    cls._post_invoices(sale, venta, logs, to_exception)
                    if id_venta in to_exception:
                        continue
                    pagos = Config.get_tipos_pago(id_venta)
                    if pagos:
                        args_statement = {
                            'device': sale_device,
                            'usuario': venta.usuario,
                        }
                        cls.set_payment_pos(pagos, sale, args_statement, logs,
                                            to_exception)
                        Sale.update_state([sale])
                    elif sale.payment_term.id_tecno == '0':
                        logs_che[
                            id_venta] = "EXCEPCION: No se encontraron pagos asociados en tecnocarnes (documentos_che)"
                        cls.delete_imported_sales([sale], cod='E')
                        continue
                to_created.append(id_venta)
            except Exception as e:
                # logs[id_venta] = f"EXCEPCION: ERROR AL IMPORTAR LA VENTA"
                logs[id_venta] = f"EXCEPCION: {str(e)}"
                to_exception.append(id_venta)

        actualizacion.add_logs(logs)
        actualizacion_che.add_logs(logs_che)
        for idt in to_created:
            if idt not in to_exception:
                Config.update_exportado(idt, 'T')
        for idt in to_exception:
            Config.update_exportado(idt, 'E')
        for idt in not_import:
            Config.update_exportado(idt, 'X')
        print('FINISH VENTAS')

    # Funcion encargada de finalizar el proceso de envío de la venta
    @classmethod
    def finish_shipment_process(cls, sale, numero_doc, Config, tipo_doc):
        pool = Pool()
        Product = pool.get('product.product')

        dictprodut = {}
        select = f"SELECT tr.IdProducto, tr.IdResponsable\
                FROM TblProducto tr \
                join Documentos_Lin dl  \
                on tr.IdProducto = dl.IdProducto \
                WHERE dl.Numero_Documento = {numero_doc} and dl.tipo = {tipo_doc};"

        result = Config.get_data(select)

        for item in result:

            dictprodut[item[0]] = {
                'idresponsable': str(item[1]),
            }

        for shipment in sale.shipments:
            shipment.reference = sale.number
            shipment.effective_date = sale.sale_date
            shipment.save()
            for productmove in shipment.outgoing_moves:
                idTecno = int(productmove.product.id_tecno)
                if idTecno in dictprodut.keys():
                    id_ = dictprodut[idTecno]['idresponsable']
                    producto = Product.search(
                        ['OR', ('id_tecno', '=', id_), ('code', '=', id_)])
                    if producto:
                        product, = producto
                        if productmove.product.default_uom.symbol == product.default_uom.symbol:
                            productmove.product = product

                    productmove.save()
            shipment.wait([shipment])
            shipment.pick([shipment])
            shipment.pack([shipment])
            shipment.done([shipment])
        for shipment in sale.shipment_returns:
            shipment.reference = sale.number
            shipment.effective_date = sale.sale_date
            for productmove in shipment.incoming_moves:
                idTecno = int(productmove.product.id_tecno)
                if idTecno in dictprodut.keys():
                    id_ = dictprodut[idTecno]['idresponsable']
                    producto = Product.search(
                        ['OR', ('id_tecno', '=', id_), ('code', '=', id_)])
                    if producto:
                        product, = producto
                        if productmove.product.default_uom.symbol == product.default_uom.symbol:
                            productmove.product = product

                    productmove.save()
            shipment.save()
            shipment.receive([shipment])
            shipment.done([shipment])

    @classmethod
    def _post_invoices(cls, sale, venta, logs, to_exception):
        """Function to update invoices and sends with sale info"""

        pool = Pool()
        Invoice = pool.get('account.invoice')
        PaymentLine = pool.get('account.invoice-account.move.line')
        Config = pool.get('conector.configuration')

        # process sale to build invoice
        if not sale.invoices:
            logs[sale.id_tecno] = "REVISAR: VENTA SIN FACTURA"
            to_exception.append(sale.id_tecno)

        for invoice in sale.invoices:
            invoice.accounting_date = sale.sale_date
            invoice.number = sale.number
            invoice.invoice_date = sale.sale_date
            invoice.invoice_type = 'C'
            tipo_numero = sale.number.split('-')

            if sale.description:
                invoice.description = sale.description
            else:
                # Fill description with the type document from tecno
                tbltipodocto = Config.get_tbltipodoctos(tipo_numero[0])
                if tbltipodocto:
                    invoice.description = tbltipodocto[0].TipoDoctos.replace(
                        '\n', ' ').replace('\r', '')

            invoice.save()
            if venta.sw == 2:
                dcto_base = str(venta.Tipo_Docto_Base) + '-' + str(
                    venta.Numero_Docto_Base)
                invoice.reference = dcto_base
                original_invoice = Invoice.search([('number', '=', dcto_base)])
                if original_invoice:
                    invoice.original_invoice = original_invoice[0]
                else:
                    msg = f"REVISAR: NO SE ENCONTRO LA FACTURA {dcto_base} \
                        PARA CRUZAR CON LA DEVOLUCION {invoice.number}"

                    logs[sale.id_tecno] = msg
                    to_exception.append(sale.id_tecno)
            Invoice.validate_invoice([invoice], sw=venta.sw)
            result = cls._validate_total(invoice.total_amount, venta)
            if not result['value']:
                msg = f"REVISAR: ({sale.id_tecno})\
                El total de Tryton {invoice.total_amount}\
                es diferente al total de TecnoCarnes {result['total_tecno']}\
                La diferencia es de {result['diferencia']}"

                logs[sale.id_tecno] = msg
                to_exception.append(sale.id_tecno)
                continue

            try:
                Invoice.post_batch([invoice])
                Invoice.post([invoice])
            except Exception as e:
                if invoice.state == 'posted':
                    # Revert invoice state to validated
                    account_invoice = Table('account_invoice')
                    cursor = Transaction().connection.cursor()
                    cursor.execute(*account_invoice.update(
                        columns=[
                            account_invoice.state,
                        ],
                        values=["validated"],
                        where=account_invoice.id == invoice.id))
                msg = f"REVISAR FACTURA: {sale.id_tecno} - {str(e)}"
                logs[sale.id_tecno] = msg
                to_exception.append(sale.id_tecno)
                continue
            if invoice.original_invoice:
                paymentline = PaymentLine()
                paymentline.invoice = invoice.original_invoice
                paymentline.invoice_account = invoice.account
                paymentline.invoice_party = invoice.party
                paymentline.line = invoice.lines_to_pay[0]
                paymentline.save()
                Invoice.reconcile_invoice(invoice)

    @classmethod
    def _validate_total(cls, total_tryton, venta):
        """ Function to validate difference from tecno and tryton"""

        result = {
            'value': False,
        }
        retencion_causada = abs(venta.retencion_causada)
        total_tecno = abs(venta.valor_total)
        total_tryton = abs(total_tryton)
        total_tecno = total_tecno - retencion_causada
        diferencia = abs(total_tryton - total_tecno)

        if diferencia < Decimal('6.0'):
            result['value'] = True
        result['total_tecno'] = total_tecno
        result['diferencia'] = diferencia
        return result

    @classmethod
    def set_payment_pos(cls, pagos, sale, args_statement, logs, to_exception):
        """Function to seach paid cash receipts in tecno
            to pay in tryton"""

        pool = Pool()
        Journal = pool.get('account.statement.journal')

        for pago in pagos:
            valor = pago.valor
            if valor == 0:
                msg = f"REVISAR {sale.id_tecno} - Revisar \
                    el valor del pago, su valor es de {valor}"

                logs[sale.id_tecno] = msg
                to_exception.append(sale.id_tecno)
                return

            fecha = str(pago.fecha).split()[0].split('-')
            fecha_date = date(int(fecha[0]), int(fecha[1]),
                              int(fecha[2]))
            args_statement['date'] = fecha_date
            journal, = Journal.search([('id_tecno', '=', pago.forma_pago)])
            args_statement['journal'] = journal
            statement, = cls.search_or_create_statement(args_statement)

            if pago.sw == 2 and valor > 0:
                valor = valor * -1

            data_payment = {
                'sales': {
                    sale: valor
                },
                'statement': statement.id,
                'date': fecha_date,
            }
            result_payment = cls.multipayment_invoices_statement(
                data_payment, logs, to_exception)
            if result_payment != 'ok':
                msg = f"REVISAR: ERROR AL PROCESAR \
                    EL PAGO DE LA VENTA POS {sale.number}"

                logs[sale.id_tecno] = msg

    @classmethod
    def search_or_create_statement(cls, args):
        """Function to search account statement by a sale device
            if it doest not exist, create it"""

        pool = Pool()
        Statement = pool.get('account.statement')
        Device = pool.get('sale.device')

        device = Device(args['device'])
        date = args['date']
        journal = args['journal']
        usuario = args['usuario']
        name_statement = '%s - %s - %s' % (device.rec_name,
                                           journal.rec_name.strip(), usuario)
        statement = Statement.search([('name', '=', name_statement),
                                      ('journal', '=', journal.id),
                                      ('sale_device', '=', device.id),
                                      ('date', '=', date),
                                      ('state', '=', 'draft')])
        if not statement:
            statements_date = Statement.search([
                ('journal', '=', journal.id),
                ('date', '=', date),
                ('sale_device', '=', device.id),
            ])
            turn = len(statements_date) + 1
            values = {
                'name': name_statement,
                'date': date,
                'journal': journal.id,
                'company': device.shop.company.id,
                'start_balance': journal.default_start_balance
                or Decimal('0.0'),
                'end_balance': Decimal('0.0'),
                'turn': turn,
                'sale_device': device.id,
            }
            statement = Statement.create([values])
        return statement

    @classmethod
    def multipayment_invoices_statement(cls, args, logs, to_exception):
        """Function to pay multiple invoice with
            multiple payment types"""

        pool = Pool()
        Sale = pool.get('sale.sale')
        Configuration = pool.get('account.configuration')
        StatementLine = pool.get('account.statement.line')

        sales = args.get('sales', None)
        statement_id = args.get('statement', None)
        date = args.get('date', None)

        # Build the payment line with the account statement line
        for sale in sales.keys():
            total_paid = Decimal(0.0)
            if sale.payments:
                total_paid = sum([p.amount for p in sale.payments])
                if abs(total_paid) >= abs(sale.total_amount):
                    if total_paid == sale.total_amount:
                        Sale.do_reconcile([sale])
                    else:
                        msg = f"REVISAR: venta pos con un total pagado: \
                            {total_paid} mayor al total de la venta: \
                            {sale.total_amount}"

                        logs[sale.id_tecno] = msg
                    continue

            total_pay = args.get('sales')[sale]
            if not total_pay:
                total_pay = sale.total_amount
            else:
                remainder = sale.residual_amount - total_pay
                if abs(remainder) < Decimal(600.0) and remainder != 0:
                    total_pay = sale.residual_amount

            if not sale.invoice or (sale.invoice.state != 'posted'
                                    and sale.invoice.state != 'paid'):
                Sale.post_invoices(sale)

            if not sale.party.account_receivable:
                Party = pool.get('party.party')
                config = Configuration(1)
                if config.default_account_receivable:
                    Party.write([sale.party], {
                        'account_receivable':
                        config.default_account_receivable.id
                    })
                else:
                    logs[sale.id_tecno] = "EXCEPCION: \
                            sale_pos.msg_party_without_account_receivable"

                    to_exception.append(sale.id_tecno)
                    continue

            account_id = sale.party.account_receivable.id
            total_pay = Decimal(str(round(total_pay, 2)))
            to_create = {
                'sale': sale.id,
                'date': date,
                'statement': statement_id,
                'amount': total_pay,
                'party': sale.party.id,
                'account': account_id,
                'description': sale.invoice_number or sale.invoice.number
                or '',
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

    # Función encargada de obtener los ids de los registros a eliminar
    @classmethod
    def _get_delete_sales(cls, sales):
        pool = Pool()
        LineStatement = pool.get('account.statement.line')
        AccountMove = pool.get('account.move')

        ids_tecno = []
        to_delete = {
            'sale': [],
            'reconciliation': [],
            'move': [],
            'invoice': [],
            'stock_move': [],
            'shipment': [],
            'shipment_return': [],
            'statement_line': []
        }
        for sale in sales:
            if sale.id_tecno:
                ids_tecno.append(sale.id_tecno)
            else:
                raise UserError("Error Conector",
                                f"No se encontró el id_tecno para {sale}")
            # Se procede a seleccionar las facturas de la venta
            for invoice in sale.invoices:
                if hasattr(invoice, 'electronic_state') and \
                        invoice.electronic_state == 'submitted':
                    raise UserError('account_col.msg_with_electronic_invoice')
                if invoice.state == 'paid':
                    for line in invoice.move.lines:
                        if line.reconciliation and line.reconciliation.id not in to_delete[
                                'reconciliation']:
                            to_delete['reconciliation'].append(
                                line.reconciliation.id)
                if invoice.move:
                    if invoice.move.id not in to_delete['move']:
                        to_delete['move'].append(invoice.move.id)
                if invoice.id not in to_delete['invoice']:
                    to_delete['invoice'].append(invoice.id)
                    line_statement = LineStatement.search([("invoice", "=",
                                                            invoice.id)])
                    if line_statement:
                        account_moves = AccountMove.search([
                            ("id", "=", line_statement[0].move.id)
                        ])
                        if account_moves:
                            to_delete['move'].append(account_moves[0].id)
                            AccountMove.delete_lines(account_moves)

            # Se procede a seleccionar los envíos y movimientos de inventario de la venta
            for line in sale.lines:
                for move in line.moves:
                    if move.id not in to_delete['stock_move']:
                        to_delete['stock_move'].append(move.id)

            for shipment in sale.shipments:
                if shipment.id not in to_delete['shipment']:
                    to_delete['shipment'].append(shipment.id)
                for move in shipment.inventory_moves:
                    if move.id not in to_delete['stock_move']:
                        to_delete['stock_move'].append(move.id)

            for shipment in sale.shipment_returns:
                if shipment.id not in to_delete['shipment_return']:
                    to_delete['shipment_return'].append(shipment.id)
                for move in shipment.inventory_moves:
                    if move.id not in to_delete['stock_move']:
                        to_delete['stock_move'].append(move.id)

            # Se procede a seleccionar las lineas de pago (POS)
            for line in sale.payments:
                if line.id not in to_delete['statement_line']:
                    to_delete['statement_line'].append(line.id)

            if sale.id not in to_delete['sale']:
                to_delete['sale'].append(sale.id)
        return ids_tecno, to_delete

    # Función creada con base al asistente force_draft del módulo sale_pos de presik
    # Esta función se encarga de eliminar los registros mediante cursor
    @classmethod
    def _delete_sales(cls, to_delete):
        sale_table = Table('sale_sale')
        invoice_table = Table('account_invoice')
        move_table = Table('account_move')
        stock_move_table = Table('stock_move')
        statement_line = Table('account_statement_line')
        shipment_table = Table('stock_shipment_out')
        shipment_return_table = Table('stock_shipment_out_return')
        reconciliation_table = Table('account_move_reconciliation')
        cursor = Transaction().connection.cursor()
        # Se procede a realizar la eliminación de todos los registros
        print(to_delete)
        if to_delete['reconciliation']:
            cursor.execute(*reconciliation_table.delete(
                where=reconciliation_table.id.in_(
                    to_delete['reconciliation'])))

        if to_delete['move']:
            cursor.execute(
                *move_table.update(columns=[move_table.state],
                                   values=['draft'],
                                   where=move_table.id.in_(to_delete['move'])))
            cursor.execute(*move_table.delete(
                where=move_table.id.in_(to_delete['move'])))

        if to_delete['invoice']:
            cursor.execute(*invoice_table.update(
                columns=[invoice_table.state, invoice_table.number],
                values=['validate', None],
                where=invoice_table.id.in_(to_delete['invoice'])))
            cursor.execute(*invoice_table.delete(
                where=invoice_table.id.in_(to_delete['invoice'])))

        if to_delete['stock_move']:
            cursor.execute(*stock_move_table.update(
                columns=[stock_move_table.state],
                values=['draft'],
                where=stock_move_table.id.in_(to_delete['stock_move'])))
            cursor.execute(*stock_move_table.delete(
                where=stock_move_table.id.in_(to_delete['stock_move'])))

        if to_delete['shipment']:
            cursor.execute(*shipment_table.update(
                columns=[shipment_table.state],
                values=['draft'],
                where=shipment_table.id.in_(to_delete['shipment'])))
            cursor.execute(*shipment_table.delete(
                where=shipment_table.id.in_(to_delete['shipment'])))

        if to_delete['shipment_return']:
            cursor.execute(*shipment_return_table.update(
                columns=[shipment_return_table.state],
                values=['draft'],
                where=shipment_return_table.id.in_(
                    to_delete['shipment_return'])))
            cursor.execute(*shipment_return_table.delete(
                where=shipment_return_table.id.in_(
                    to_delete['shipment_return'])))

        if to_delete['statement_line']:
            cursor.execute(*statement_line.delete(
                where=statement_line.id.in_(to_delete['statement_line'])))

        if to_delete['sale']:
            cursor.execute(
                *sale_table.update(columns=[
                    sale_table.state, sale_table.shipment_state,
                    sale_table.invoice_state
                ],
                    values=['draft', 'none', 'none'],
                    where=sale_table.id.in_(to_delete['sale'])))
            cursor.execute(*sale_table.delete(
                where=sale_table.id.in_(to_delete['sale'])))

    # Función encargada de eliminar y marcar para importar ventas de importadas de TecnoCarnes
    @classmethod
    def delete_imported_sales(cls, sales, cod='N'):
        Cnxn = Pool().get('conector.configuration')
        ids_tecno, to_delete = cls._get_delete_sales(sales)
        cls._delete_sales(to_delete)
        for idt in ids_tecno:
            Cnxn.update_exportado(idt, cod)


class SaleLine(metaclass=PoolMeta):
    __name__ = 'sale.line'

    @classmethod
    def __setup__(cls):
        super(SaleLine, cls).__setup__()

    # Se hereda la funcion 'compute_taxes' para posteriormente quitar el impuesto (IVA) a los terceros 'regimen_no_responsable'
    # def compute_taxes(self, party):
    #     taxes_id = super(SaleLine, self).compute_taxes(party)
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


class Statement(metaclass=PoolMeta):
    __name__ = 'account.statement'

    @fields.depends('end_balance')
    def on_change_with_end_balance(self):
        amount = (self.start_balance + sum(l.amount for l in self.lines))
        return amount


# reporte costo de ventas
class SaleShopDetailedCDSStart(ModelView):
    'Sale Shop Detailed Start'
    __name__ = 'sale_shop.sale_detailed_cds.start'
    start_date = fields.Date("From Date",
                             domain=[
                                 If(
                                     Eval('end_date') & Eval('start_date'),
                                     ('start_date', '<=', Eval('end_date')),
                                     ()),
                             ],
                             depends=['end_date'],
                             required=True)
    end_date = fields.Date("To Date",
                           domain=[
                               If(
                                   Eval('start_date') & Eval('end_date'),
                                   ('end_date', '>=', Eval('start_date')), ()),
                               (('end_date', '<=', date.today()))
                           ],
                           depends=['start_date'],
                           required=True)
    company = fields.Many2One('company.company', 'Company', required=True)
    # salesman = fields.Many2One('company.employee', 'Salesman')
    # party = fields.Many2One('party.party', 'Party')
    # product = fields.Many2One('product.product', 'Product')
    # shop = fields.Many2One('sale.shop', 'Shop')

    @staticmethod
    def default_company():
        return Transaction().context.get('company')


class SaleShopDetailedCDS(Wizard):
    'Sale Shop Detailed'
    __name__ = 'sale_shop.sale_detailed_cds'
    start = StateView('sale_shop.sale_detailed_cds.start',
                      'conector.sale_shop_detailed_start_cds_form', [
                          Button('Cancel', 'end', 'tryton-cancel'),
                          Button('Print', 'print_', 'tryton-ok', default=True),
                      ])

    print_ = StateReport('sale_shop.report_sale_detailed_cds')

    def do_print_(self, action):
        salesman_id = None
        party_id = None
        product_id = None
        shop_id = None
        # if self.start.salesman:
        #     salesman_id = self.start.salesman.id
        # if self.start.shop:
        #     shop_id = self.start.shop.id
        # if self.start.party:
        #     party_id = self.start.party.id
        # if self.start.product:
        #     product_id = self.start.product.id
        data = {
            'company': self.start.company.id,
            'start_date': self.start.start_date,
            'end_date': self.start.end_date,
            'salesman': salesman_id,
            'party': party_id,
            'product': product_id,
            'shop': shop_id,
        }

        return action, data

    def transition_print_(self):
        return 'end'


class SaleShopDetailedCDSReport(Report):
    'Sale Shop Detailed Report'
    __name__ = 'sale_shop.report_sale_detailed_cds'

    @classmethod
    def get_context(cls, records, header, data):
        report_context = super().get_context(records, header, data)
        pool = Pool()
        cursor = Transaction().connection.cursor()
        InvoiceLine = pool.get('account.invoice.line')
        Company = pool.get('company.company')
        MoveLine = pool.get('account.move.line')
        Account = pool.get('account.account')
        Product_uom = pool.get('product.uom')
        Product = pool.get('product.product')
        ProductTemplate = pool.get('product.template')
        Invoice = pool.get('account.invoice')
        Move = pool.get('account.move')
        Party = pool.get('party.party')
        Shop = pool.get('sale.shop')

        product_uom = Product_uom.__table__()
        moveLine = MoveLine.__table__()
        account = Account.__table__()
        invoiceLine = InvoiceLine.__table__()
        party = Party.__table__()
        invoice = Invoice.__table__()
        moves = Move.__table__()
        product = Product.__table__()
        productTemplate = ProductTemplate.__table__()
        shop = Shop.__table__()

        lines = {}

        # Columnas donde se grabaran la consulta que se realiza a las lineas de los movimientos
        columnsMove = {
            'id': moveLine.id,
            'move': moveLine.move,
            'cost': Sum(moveLine.debit - moveLine.credit),
            'reference': moveLine.reference,
            'description': moveLine.description,
            'date': moves.date,
            'party': party.name,
        }

        # Columnas donde se grabaran la consulta que se realiza a las lineas de las facturas
        columnsLine = {
            'move': invoice.move,
            'total_quantity': Sum(invoiceLine.quantity),
            'unit_price': invoiceLine.unit_price,
            'reference': invoice.reference,
            'product_name': invoiceLine.description,
            'invoice_date': invoice.invoice_date,
            'shop': shop.name,
            'unit': product_uom.symbol,
            'state': invoice.state
        }

        # Filtros de busquedas para las lineas de los movimientos
        where = Like(account.code, ('6%'))
        where &= Between(moves.date, data['start_date'], data['end_date'])

        # Consulta que retorna los valores de las lineas de los movimientos
        selectMove = account.join(
            moveLine, 'LEFT', condition=moveLine.account == account.id).join(
                moves, 'LEFT', condition=moveLine.move == moves.id).join(
                    party, 'LEFT',
                    condition=moveLine.party == party.id).select(
                        *columnsMove.values(),
                        where=where,
                        group_by=[
                            moveLine.move,
                            moveLine.id,
                            moveLine.account,
                            moveLine.description,
                            moveLine.reference,
                            moves.date,
                            party.name,
                        ])
        # Ejecucion de la consulta
        cursor.execute(*selectMove)

        resultMove = cursor.fetchall()

        fila_dict_move = {}

        # Verificamos que la consulta traiga informacion
        if resultMove:

            for index, record in enumerate(resultMove):
                fila_dict_move = OrderedDict(
                )  # Le damos la extructura de diccionario
                fila_dict_move = dict(zip(columnsMove.keys(), record))

                move = fila_dict_move['move']
                reference = fila_dict_move['reference']
                description = fila_dict_move['description']
                cost = fila_dict_move['cost']
                date = fila_dict_move['date']
                party = fila_dict_move['party']

                if move not in lines:
                    lines[move] = {'lines': {}}

                if description not in lines[move]['lines']:
                    lines[move]['lines'][description] = {
                        'party': party,
                        'unit_price': 0,
                        'total_quantity': 0,
                        'cost': 0,
                        'reference': reference,
                        'date': date,
                        'shop': '',
                        'total_cost': 0,
                        'state': '',
                        'unit': ''
                    }

                lines[move]['lines'][description]['cost'] += cost

        # FIltros para la consulta a las lineas de las facturas
        where = Between(invoice.invoice_date, data['start_date'],
                        data['end_date'])
        where &= invoice.state.in_(['paid', 'validated', 'posted'])
        where &= invoice.type.in_(['out'])

        # Consulta que retorna la informacion de las lineas de las facturas
        selectLine = invoice.join(
            invoiceLine, 'LEFT',
            condition=invoiceLine.invoice == invoice.id).join(
                product, 'LEFT',
                condition=invoiceLine.product == product.id).join(
                    productTemplate,
                    'LEFT',
                    condition=product.template == productTemplate.id).join(
                        shop, 'LEFT', condition=invoice.shop == shop.id).join(
                            product_uom,
                            'LEFT',
                            condition=invoiceLine.unit ==
                            product_uom.id).select(
                                *columnsLine.values(),
                                where=where,
                                group_by=[
                                    invoice.move, invoice.description,
                                    invoice.reference, invoiceLine.unit_price,
                                    invoiceLine.description,
                                    invoice.invoice_date, shop.name,
                                    product_uom.symbol, invoice.state
                                ])

        cursor.execute(*selectLine)

        resultLine = cursor.fetchall()

        fila_dict_line = {}

        # Verificamos que la consulta halla traifo informacion
        if resultLine:

            for record in resultLine:

                fila_dict_line = OrderedDict(
                )  # Le damos la extructura de diccionario
                fila_dict_line = dict(zip(columnsLine.keys(), record))

                move = fila_dict_line['move']
                reference = fila_dict_line['reference']
                description = fila_dict_line['product_name']
                unit_price = fila_dict_line['unit_price']
                total_quantity = fila_dict_line['total_quantity']
                shop = fila_dict_line['shop']
                unit = fila_dict_line['unit']
                state = fila_dict_line['state']

                if move in lines:
                    if description in lines[move]['lines']:

                        lines[move]['lines'][description]['shop'] = shop
                        lines[move]['lines'][description][
                            'unit_price'] = unit_price
                        lines[move]['lines'][description][
                            'total_quantity'] += Decimal(total_quantity)
                        lines[move]['lines'][description]['unit'] = unit
                        lines[move]['lines'][description]['state'] = state

            # For que recorreo las lineas creadas con las lineas de movimiento y factura y realiza la operacion
            # para dar el costo unitario, si este es 0 aplica un 0
            for key, record in lines.items():
                for description, line in lines[key]['lines'].items():
                    line['total_cost'] = round(
                        line['cost'] / line['total_quantity'],
                        2) if line['cost'] != 0 and line[
                            'total_quantity'] != 0 else line['cost']

        report_context['records'] = lines
        report_context['start_date'] = data['start_date']
        report_context['end_date'] = data['end_date']
        report_context['company'] = Company(data['company'])
        return report_context


class SaleInvoiceValueCdstStart(ModelView):
    'Sale Invoice Values View Report'
    __name__ = 'sale.invoice_values_cdst.start'
    company = fields.Many2One('company.company', 'Company', required=True)
    from_date = fields.Date('From Date', required=True)
    to_date = fields.Date('To Date', required=True)
    document_type = fields.Selection('get_document_type', 'Type Document')
    # state = fields.Selection(STATES, 'State')

    @staticmethod
    def default_company():
        return Transaction().context.get('company')

    def get_document_type():
        pool = Pool()
        Config = pool.get('conector.configuration')
        condition = "(tipo=1 OR tipo=2)"
        consultc = "SET DATEFORMAT ymd "\
            "SELECT idTipoDoctos FROM TblTipoDoctos "\
            f"WHERE {condition} "
        result_tecno = Config.get_data(consultc)
        list_document = [row[0] for row in result_tecno]
        TYPE_DOCUMENT = [(val, val) for val in list_document]
        return TYPE_DOCUMENT


class SaleInvoiceValueCdst(Wizard):
    'Sale Invoice Values Wizard'
    __name__ = 'sale.invoice_values_cdst'
    start = StateView('sale.invoice_values_cdst.start',
                      'conector.form_view_invoice_values_cdst_start', [
                          Button('Cancel', 'end', 'tryton-cancel'),
                          Button('Print', 'print_', 'tryton-ok', default=True),
                      ])
    print_ = StateReport('sale.invoice_values_cdst.report')

    def do_print_(self, action):
        """Function to save form values and return to build report"""

        from_date = self.start.from_date
        to_date = self.start.to_date
        if (to_date - from_date).days > 31:
            raise UserError(
                'El rango de fecha no puede exceder mas de 31 dias.')

        data = {
            'company': self.start.company.id,
            'from_date': from_date,
            'to_date': to_date,
            'type_document': self.start.document_type,
            # 'state': self.start.state,
        }
        return action, data


class SaleInvoiceValueCdstReport(Report):
    'Sale Invoice Values Report'
    __name__ = 'sale.invoice_values_cdst.report'

    @classmethod
    def get_context(cls, records, header, data):
        """Function that take context of report and import it"""
        report_context = super().get_context(records, header, data)

        pool = Pool()
        Company = pool.get('company.company')
        Sale = pool.get('sale.sale')

        info_invoices = []
        type_document = ""
        state = ""
        total_amount_tecno = Decimal(0)
        total_amount_tryton = Decimal(0)
        total_amount_tax_tecno = Decimal(0)
        init_date = data["from_date"]
        end_date = data["to_date"]

        # build init domain
        domain_sales = [("sale_date", ">=", init_date),
                        ("sale_date", "<=", end_date),
                        ("state", "!=", "draft")]

        # validate if type document was selected and add to domain
        if data["type_document"]:
            type_document = data["type_document"]
            domain_sales.append(("number", "ilike", f"{type_document}-%"))

        sales = Sale.search(domain_sales)

        if sales:
            for sale in sales:
                invoices = {}
                invoice_difference = 0
                if sale.invoice:
                    invoice_amount_tecno = sale.invoice_amount_tecno
                    tax_amount_tecno = sale.tax_amount_tecno
                    invoice_value_tryton = sale.invoice.total_amount
                    total_amount_tax_tecno += tax_amount_tecno
                    if invoice_amount_tecno is not None\
                            and invoice_value_tryton is not None:

                        invoice_amount_tecno = Decimal(
                            abs(invoice_amount_tecno))
                        invoice_value_tryton = Decimal(
                            abs(invoice_value_tryton))
                        tax_amount_tecno = Decimal(abs(tax_amount_tecno))

                        invoice_difference = invoice_amount_tecno \
                            - invoice_value_tryton

                        invoice_difference = Decimal(abs(invoice_difference))
                        total_amount_tecno += invoice_amount_tecno
                        total_amount_tryton += invoice_value_tryton

                        if invoice_difference > 5:
                            invoices = {
                                "date": sale.sale_date,
                                "reference": sale.reference,
                                "description": sale.invoice.description,
                                "value_tecno": invoice_amount_tecno,
                                "value_tryton": invoice_value_tryton,
                                "difference": invoice_difference,
                                "tax_amount": tax_amount_tecno,
                            }
                            info_invoices.append(invoices)
            total_difference = abs(total_amount_tecno - total_amount_tryton)

        if not sales:
            raise UserError(
                message="SIN INFORMACION",
                description="No hay documentos en el rango de fecha"
                "con inconsistencias.")

        report_context['info_report'] = info_invoices
        report_context['company'] = Company(data['company'])
        report_context['type'] = type_document
        report_context['total_tecno'] = total_amount_tecno
        report_context['total_tryton'] = total_amount_tryton
        report_context['state'] = state
        report_context['total_difference'] = total_difference
        report_context['total_amount_tax_tecno'] = total_amount_tax_tecno
        return report_context
