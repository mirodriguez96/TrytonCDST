import datetime
from decimal import Decimal
import unicodedata

from sql import Table
from trytond.exceptions import UserError
from trytond.model import fields
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Eval
from trytond.transaction import Transaction


def normalize_text(text):
    return unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('ASCII')

class Configuration(metaclass=PoolMeta):
    'Configuration'
    __name__ = 'purchase.configuration'
    type_order_tecno = fields.Char('Type order TecnoCarnes')


class Purchase(metaclass=PoolMeta):
    'Purchase Model inheritance'

    __name__ = 'purchase.purchase'
    id_tecno = fields.Char('Id Tabla Sqlserver', required=False)
    order_tecno = fields.Selection(
        [('yes', 'Yes'), ('no', 'No')],
        'Order TecnoCarnes',
        states={
            'readonly': Eval('state').in_(['processing', 'done']),
            'required': Eval('state') == 'processing'
        })
    order_tecno_sent = fields.Boolean('Order TecnoCarnes sent', readonly=True)

    @staticmethod
    def default_order_tecno():
        return 'no'

    @classmethod
    def copy(cls, purchases, default=None):
        if default is None:
            default = {}
        else:
            default = default.copy()
        default.setdefault('order_tecno_sent', False)
        return super(Purchase, cls).copy(purchases, default=default)

    @classmethod
    def import_data_purchase(cls):
        import_name = "COMPRAS"
        print(f"---------------RUN {import_name}---------------")
        cls.import_tecnocarnes('3', import_name)
        print(f"---------------FINISH {import_name}---------------")

    @classmethod
    def import_data_purchase_return(cls):
        import_name = "DEVOLUCIONES DE COMPRAS"
        print(f"---------------RUN {import_name}---------------")
        cls.import_tecnocarnes('4', import_name)
        print(f"---------------FINISH {import_name}---------------")

    @classmethod
    def import_tecnocarnes(cls, swt, import_name):
        """Importa datos de compras desde TecnoCarnes a Tryton

        Args:
            swt (int): Identificador del tipo de documento
            import_name (str): Nombre del proceso de importación para logging

        Returns:
            None
        """
        pool = Pool()
        Transaction().set_context(active_test=False)  # Para incluir registros inactivos en búsquedas

        # Modelos Tryton - agrupados por funcionalidad
        payment_models = {
            'PaymentLine': pool.get('account.invoice-account.move.line'),
            'PaymentTerm': pool.get('account.invoice.payment_term'),
        }

        purchase_models = {
            'Purchase': pool.get('purchase.purchase'),
            'PurchaseLine': pool.get('purchase.line'),
        }

        invoice_models = {
            'Invoice': pool.get('account.invoice'),
            'Tax': pool.get('account.tax'),
            'Period': pool.get('account.period'),
        }

        product_models = {
            'Product': pool.get('product.product'),
            'Location': pool.get('stock.location'),
        }

        party_models = {
            'Party': pool.get('party.party'),
            'Address': pool.get('party.address'),
        }

        other_models = {
            'Actualizacion': pool.get('conector.actualizacion'),
            'Config': pool.get('conector.configuration'),
            'Module': pool.get('ir.module'),
        }

        # Verificar si el módulo company_operation está activo
        company_operation = other_models['Module'].search([
            ('name', '=', 'company_operation'),
            ('state', '=', 'activated')
        ])

        if company_operation:
            operation_models = {
                'CompanyOperation': pool.get('company.operation_center'),
            }
            operation_center = operation_models['CompanyOperation'].search(
                [], order=[('id', 'ASC')], limit=1
            )

        # Inicialización de variables de estado
        logs = {}
        to_exception = []
        to_created = []
        not_import = []

        data = other_models['Config'].get_documentos_tecno(swt)
        actualizacion = other_models['Actualizacion'].create_or_update('COMPRAS')

        if not data:
            print(f"---------------NO DATA {import_name}---------------")
            actualizacion.save()
            print(f"---------------FINISH {import_name}---------------")
            return

        # Obtener partes (parties) una sola vez para optimización
        parties = party_models['Party']._get_party_documentos(data, 'nit_Cedula')

        print('compras a importar :', len(data))
        # Procesar cada compra
        for compra in data:
            configuration = other_models['Config'].get_configuration()
            if not configuration:
                return
            sw = compra.sw
            numero_doc = compra.Numero_documento
            tipo_doc = compra.tipo
            id_compra = f"{sw}-{tipo_doc}-{numero_doc}"
            print('Procesando compra:', id_compra)
            dcto_referencia = str(compra.Numero_Docto_Base)
            number_ = f"{tipo_doc}-{numero_doc}"

            try:
                # Verificar si el documento ya existe
                existe = purchase_models['Purchase'].search([('id_tecno', '=', id_compra)])

                if existe:
                    if compra.anulado == 'S':
                        if cls._is_period_closed(compra.fecha_hora):
                            to_exception.append(id_compra)
                            logs[id_compra] = (
                                "EXCEPCION: EL PERIODO DEL DOCUMENTO SE ENCUENTRA CERRADO "
                                "Y NO ES POSIBLE SU ELIMINACION O MODIFICACION"
                            )
                            continue

                        logs[id_compra] = (
                            "El documento fue eliminado de tryton porque fue anulado en TecnoCarnes"
                        )
                        cls.delete_imported_purchases(existe)
                        not_import.append(id_compra)
                        continue

                    logs[id_compra] = "Documento ya existe en Tryton"
                    to_created.append(id_compra)
                    continue

                if compra.anulado == 'S':
                    logs[id_compra] = "Documento anulado en TecnoCarnes"
                    not_import.append(id_compra)
                    continue

                if company_operation and not operation_center:
                    logs[id_compra] = "Falta el centro de operación"
                    to_exception.append(id_compra)
                    continue

                if cls._is_period_closed(compra.fecha_hora):
                    to_exception.append(id_compra)
                    logs[id_compra] = (
                        "EXCEPCION: EL PERIODO DEL DOCUMENTO SE ENCUENTRA CERRADO "
                        "Y NO ES POSIBLE SU CREACION"
                    )
                    continue

                # Crear la compra
                purchase = cls._create_purchase(
                    purchase_models['Purchase'],
                    compra,
                    id_compra,
                    number_,
                    party_models['Party'],
                    parties,
                    party_models['Address'],
                    payment_models['PaymentTerm'],
                    product_models['Location'],
                    company_operation,
                    operation_center if company_operation else None,
                    logs
                )

                if not purchase or id_compra in to_exception:
                    to_exception.append(id_compra)
                    continue

                # Procesar líneas de compra
                lineas_tecno = other_models['Config'].get_lineasd_tecno(id_compra)
                if not lineas_tecno:
                    logs[id_compra] = "EXCEPCION: No se encontraron líneas para la compra"
                    to_exception.append(id_compra)
                    continue

                retencion_iva = compra.retencion_iva and compra.retencion_iva > 0
                retencion_ica = compra.retencion_ica and compra.retencion_ica > 0
                retencion_rete = False

                if compra.retencion_causada and compra.retencion_causada > 0:
                    if not retencion_iva and not retencion_ica:
                        retencion_rete = True
                    elif (compra.retencion_iva + compra.retencion_ica) != compra.retencion_causada:
                        retencion_rete = True

                if not cls._process_purchase_lines(
                    purchase,
                    lineas_tecno,
                    product_models['Product'],
                    invoice_models['Tax'],
                    retencion_iva,
                    retencion_ica,
                    retencion_rete,
                    compra,
                    sw,
                    logs,
                    to_exception,
                    company_operation,
                    operation_center if company_operation else None
                ):
                    continue

                # Procesar la compra completa
                if not cls._complete_purchase_processing(
                    purchase,
                    purchase_models['Purchase'],
                    invoice_models['Invoice'],
                    payment_models['PaymentLine'],
                    compra,
                    sw,
                    id_compra,
                    dcto_referencia,
                    logs,
                    to_exception,
                    to_created
                ):
                    continue
                Transaction().commit()
            except Exception as error:
                Transaction().rollback()
                if id_compra in to_created:
                    to_created.remove(id_compra)
                logs[id_compra] = f"EXCEPCION: {str(error)}"
                print(f"ROLLBACK-{import_name}: {error}")
                to_exception.append(id_compra)
                continue

        # Guardar resultados
        actualizacion.add_logs(logs)
        cls._update_import_status(
            other_models['Config'],
            to_created,
            to_exception,
            not_import
        )

        print(f"---------------FINISH {import_name}---------------")

    @classmethod
    def _is_period_closed(cls, fecha_hora):
        """Verifica si el período contable está cerrado"""
        fecha = str(fecha_hora).split()[0].split('-')
        name = f"{fecha[0]}-{fecha[1]}"
        period = Pool().get('account.period').search([('name', '=', name)])
        return period and period[0].state == 'close'

    @classmethod
    def _create_purchase(cls, Purchase, compra, id_compra, number_, Party, parties,
                        Address, PaymentTerm, Location, company_operation,
                        operation_center, logs):
        """Crea una nueva compra con los datos básicos"""
        try:
            purchase = Purchase()
            purchase.number = number_
            purchase.id_tecno = id_compra
            purchase.description = compra.notas.replace('\n', ' ').replace('\r', '')
            purchase.order_tecno = 'no'

            # Fecha de la compra
            fecha = str(compra.fecha_hora).split()[0].split('-')
            fecha_date = datetime.date(int(fecha[0]), int(fecha[1]), int(fecha[2]))
            purchase.purchase_date = fecha_date

            # Tercero (party)
            nit_cedula = compra.nit_Cedula.replace('\n', "")
            party = parties['active'].get(nit_cedula)

            if not party:
                if nit_cedula not in parties['inactive']:
                    logs[id_compra] = f"EXCEPCION: No se encontró el tercero con id {nit_cedula}"
                    return None
                return None

            purchase.party = party

            # Dirección
            address = Address.search([('party', '=', party.id)], limit=1)
            if address:
                purchase.invoice_address = address[0].id

            # Bodega
            bodega = Location.search([('id_tecno', '=', compra.bodega)])
            if not bodega:
                logs[id_compra] = f"EXCEPCION: No se econtró la bodega {compra.bodega}"
                return None

            bodega = bodega[0]
            if hasattr(bodega, 'operation_center') and bodega.operation_center:
                operation_center = [bodega.operation_center]

            purchase.warehouse = bodega

            # Plazo de pago
            plazo_pago = PaymentTerm.search([('id_tecno', '=', compra.condicion)])
            if not plazo_pago:
                logs[id_compra] = f"EXCEPCION: No se encontró el plazo de pago {compra.condicion}"
                return None

            purchase.payment_term = plazo_pago[0]
            return purchase

        except Exception as e:
            logs[id_compra] = f"EXCEPCION al crear compra: {str(e)}"
            return None

    @classmethod
    def _process_purchase_lines(cls, purchase, lineas_tecno, Product, Tax,
                            retencion_iva, retencion_ica, retencion_rete,
                            compra, sw, logs, to_exception, company_operation,
                            operation_center):
        """Procesa las líneas de la compra"""
        for lin in lineas_tecno:
            try:
                producto = Product.search([('id_tecno', '=', str(lin.IdProducto))])

                if not producto:
                    logs[purchase.id_tecno] = (
                        f"EXCEPCION: No se encontró el producto {str(lin.IdProducto)} - "
                        "Revisar si tiene variante o está inactivo"
                    )
                    return False

                if len(producto) > 1:
                    logs[purchase.id_tecno] = (
                        f"EXCEPCION: Hay más de un producto con el mismo id_tecno: {lin.IdProducto}"
                    )
                    return False

                producto = producto[0]
                cantidad_facturada = abs(round(lin.Cantidad_Facturada, 3))

                if cantidad_facturada < 0:
                    # Manejo de cantidades negativas
                    if not cls._handle_negative_quantity(compra, producto, cantidad_facturada, sw):
                        logs[purchase.id_tecno] = (
                            f"EXCEPCION: Hay cantidades negativas: {lin.IdProducto}")
                        return False
                    continue

                # Crear línea de compra
                line = cls._create_purchase_line(
                    purchase,
                    producto,
                    lin,
                    cantidad_facturada,
                    compra,
                    sw,
                    Tax,
                    retencion_iva,
                    retencion_ica,
                    retencion_rete,
                    company_operation,
                    operation_center,
                    logs
                )

                if not line:
                    logs[purchase.id_tecno] = (
                            f"EXCEPCION: No se pudo crear las lineas de compra: {lin.IdProducto}")
                    return False

            except Exception as e:
                Transaction().rollback()
                logs[purchase.id_tecno] = f"EXCEPCION al procesar línea: {str(e)}"
                print(f"ROLLBACK-{purchase.id_tecno}: {str(e)}")
                return False

        return True

    @classmethod
    def _handle_negative_quantity(cls, compra, producto, cantidad_facturada, sw):
        """Maneja cantidades negativas en las líneas de compra"""
        cant = cantidad_facturada
        for line in compra.lines:
            line_quantity = line.quantity
            if sw == 2:
                line_quantity = (line_quantity * -1)
                cant = (cantidad_facturada * -1)

            if line.product == producto and line_quantity > 0:
                total_quantity = round((line.quantity + cant), 3)
                line.quantity = total_quantity
                line.save()
                return True
        return False

    @classmethod
    def _create_purchase_line(cls, purchase, producto, lin, cantidad_facturada,
                            compra, sw, Tax, retencion_iva, retencion_ica,
                            retencion_rete, company_operation, operation_center,
                            logs):
        """Crea una línea de compra individual"""
        try:
            line = Pool().get('purchase.line')()
            line.product = producto
            line.purchase = purchase
            line.type = 'line'
            line.unit = producto.template.default_uom

            # Cantidad (manejo de devoluciones)
            if sw == 4:
                line.quantity = cantidad_facturada * -1
                purchase.reference = f"{compra.Tipo_Docto_Base.strip()}-{compra.Numero_Docto_Base}"
            else:
                line.quantity = cantidad_facturada
                purchase.reference = str(compra.Numero_Docto_Base)

            if company_operation and operation_center:
                line.operation_center = operation_center[0]

            line.on_change_product()

            # Manejo de impuestos
            impuestos_linea, data = cls._calculate_taxes(
                line,
                Tax,
                lin.Impuesto_Consumo,
                retencion_iva,
                retencion_ica,
                retencion_rete,
                logs,
                purchase.id_tecno
            )

            if data and data['error']:
                return None

            line.taxes = impuestos_linea
            line.unit_price = lin.Valor_Unitario

            # Manejo de descuentos
            if lin.Porcentaje_Descuento_1 > 0:
                porcentaje = round((lin.Porcentaje_Descuento_1 / 100), 4)
                line.gross_unit_price = lin.Valor_Unitario
                line.discount = Decimal(str(porcentaje))
                line.on_change_discount()

            line.save()
            return line

        except Exception as e:
            logs[purchase.id_tecno] = f"EXCEPCION al crear línea: {str(e)}"
            return None

    @classmethod
    def _calculate_taxes(cls, line, Tax, impuesto_consumo, retencion_iva,
                        retencion_ica, retencion_rete, logs, id_compra):
        """Calcula los impuestos para una línea de compra"""
        impuestos_linea = []
        data = {}
        for impuestol in line.taxes:
            clase_impuesto = impuestol.classification_tax_tecno

            if clase_impuesto == '05' and retencion_iva:
                impuestos_linea.append(impuestol)
            elif clase_impuesto == '06' and retencion_rete:
                impuestos_linea.append(impuestol)
            elif clase_impuesto == '07' and (retencion_ica or not retencion_ica):
                impuestos_linea.append(impuestol)
            elif impuestol.consumo and impuesto_consumo > 0:
                data = cls._find_consumption_tax(Tax, impuesto_consumo, logs, id_compra)
                if not data['error'] and data['tax']:
                    tax = data['tax']
                    impuestos_linea.append(tax)
            elif clase_impuesto not in ('05', '06', '07') and not impuestol.consumo:
                impuestos_linea.append(impuestol)

        return impuestos_linea, data

    @classmethod
    def _find_consumption_tax(cls, Tax, impuesto_consumo, logs, id_compra):
        """Busca el impuesto al consumo correspondiente"""
        data = {'error': False, 'tax': None}
        tax = Tax.search([
            ('consumo', '=', True),
            ('type', '=', 'fixed'),
            ('amount', '=', impuesto_consumo),
            ['OR',
                ('group.kind', '=', 'purchase'),
                ('group.kind', '=', 'both')
            ]
        ])

        if not tax:
            data['error'] = True
            logs[id_compra] = (
                f"EXCEPCION: No se encontró el impuesto fijo al consumo "
                f"con valor {str(impuesto_consumo)}"
            )

        if len(tax) > 1:
            data['error'] = True
            logs[id_compra] = (
                f"EXCEPCION: Se encontró más de un impuesto de tipo consumo "
                f"con el importe igual a {impuesto_consumo} del grupo compras, "
                "recuerde que se debe manejar un único impuesto con esta configuración"
            )
        data['tax'] = tax[0]
        return data

    @classmethod
    def _complete_purchase_processing(cls, purchase, Purchase, Invoice, PaymentLine,
                                    compra, sw, id_compra, dcto_referencia,
                                    logs, to_exception, to_created):
        """Completa el procesamiento de la compra (confirmación, facturación, etc.)"""
        try:
            # Confirmar y procesar la compra
            purchase.quote([purchase])
            purchase.confirm([purchase])
            purchase.process([purchase])

            # Generar envíos si corresponde
            if compra.sw == 3:
                Purchase.generate_shipment([purchase])

            # Procesar envíos
            fecha = str(compra.fecha_hora).split()[0].split('-')
            fecha_date = datetime.date(int(fecha[0]), int(fecha[1]), int(fecha[2]))

            for shipment in purchase.shipments + purchase.shipment_returns:
                shipment.reference = purchase.number
                shipment.planned_date = fecha_date
                shipment.effective_date = fecha_date
                shipment.save()

                if shipment in purchase.shipments:
                    shipment.receive([shipment])
                    shipment.done([shipment])
                else:
                    shipment.wait([shipment])
                    shipment.assign([shipment])
                    shipment.done([shipment])

            # Manejo de facturas
            if not purchase.invoices:
                purchase.create_invoice()
                if not purchase.invoices:
                    logs[id_compra] = "EXCEPCION: sin factura"
                    return False

            for invoice in purchase.invoices:
                if not cls._process_invoice(
                    invoice,
                    purchase,
                    compra,
                    sw,
                    id_compra,
                    dcto_referencia,
                    Invoice,
                    PaymentLine,
                    logs
                ):
                    to_exception.append(id_compra)
                    return False

            # Verificar que la compra se creó correctamente
            purchase = Purchase.search([('id_tecno', '=', id_compra)])
            if purchase and purchase[0].lines:
                if id_compra not in to_created:
                    to_created.append(id_compra)
            else:
                if id_compra in to_created:
                    to_created.remove(id_compra)
                to_exception.append(id_compra)
            return True
        except Exception as e:
            Transaction().rollback()
            print(f"ROLLBACK-{id_compra}: {str(e)}")
            logs[id_compra] = f"EXCEPCION al completar compra: {str(e)}"
            return False

    @classmethod
    def _process_invoice(cls, invoice, purchase, compra, sw, id_compra,
                        dcto_referencia, Invoice, PaymentLine, logs):
        """Procesa una factura generada a partir de la compra"""
        try:
            fecha = str(compra.fecha_hora).split()[0].split('-')
            fecha_date = datetime.date(int(fecha[0]), int(fecha[1]), int(fecha[2]))

            invoice.number = purchase.number
            invoice.invoice_date = fecha_date
            invoice.description = purchase.description

            if compra.sw == 4:
                id_tecno_ = f'{sw}-{invoice.number}'
                dcto_base = f"{compra.Tipo_Docto_Base}-{compra.Numero_Docto_Base}"
                invoice.reference = dcto_base
                invoice.comment = f"DEVOLUCIÓN DE LA FACTURA {dcto_base}"
                invoice.id_tecno = id_tecno_

                original_invoice = Invoice.search([('number', '=', dcto_base)])
                original_invoice = original_invoice[0] if original_invoice else None

                if not original_invoice:
                    logs[id_compra] = (
                        f"NO SE ENCONTRÓ LA FACTURA {dcto_base} "
                        f"PARA CRUZAR CON LA DEVOLUCIÓN {invoice.number}"
                    )
                    return False
            else:
                invoice.id_tecno = id_compra

            invoice.save()
            # Validar totales
            rete_ica_amount = compra.retencion_ica if compra.retencion_ica else 0
            ttecno = {
                'retencion_causada': compra.retencion_causada,
                'retencion_ica': rete_ica_amount,
                'valor_total': compra.valor_total,
            }

            result = Invoice._validate_total_tecno(invoice.total_amount, ttecno)
            if not result['value']:
                msg = f"""REVISAR: ({id_compra})
                 El total de Tryton {invoice.total_amount}
                 es diferente al total de TecnoCarnes {result['total_tecno']}
                 La diferencia es de {result['diferencia']}"""
                logs[id_compra] = (msg)
                return False

            # Validar y publicar factura
            with Transaction().set_context(_skip_warnings=True):
                Invoice.validate_invoice([invoice])
                Invoice.post_batch([invoice])
                Invoice.post([invoice])
                if compra.sw == 4 and original_invoice:
                    cls._reconcile_invoices(invoice, original_invoice, PaymentLine, Invoice)

            return True
        except Exception as e:
            if e.args and len(e.args) > 1:
                error_message = e.args[1][0]
                if "duplicada por referencia" in normalize_text(error_message).lower():
                    Transaction().rollback()
            print(f"ROLLBACK-{id_compra}: {str(e)}")
            msg = f"EXCEPCION al procesar factura: {str(e)}"
            logs[id_compra] = msg
            return False

    @classmethod
    def _reconcile_invoices(cls, invoice, original_invoice, PaymentLine, Invoice):
        """Reconcilia facturas (para devoluciones)"""
        total_amount = original_invoice.untaxed_amount
        line_amount = invoice.lines_to_pay[0].debit

        if total_amount == line_amount:
            invoice.original_invoice = original_invoice
            Invoice.reconcile_invoice(invoice)
        else:
            paymentline = PaymentLine()
            paymentline.invoice = original_invoice
            paymentline.invoice_account = invoice.account
            paymentline.invoice_party = invoice.party
            paymentline.line = invoice.lines_to_pay[0]
            paymentline.save()
            Invoice.process([original_invoice])

    @classmethod
    def _update_import_status(cls, Config, to_created, to_exception, not_import):
        """Actualiza el estado de los documentos importados"""
        for idt in to_created:
            Config.update_exportado(idt, 'T')
        for idt in to_exception:
            Config.update_exportado(idt, 'E')
        for idt in not_import:
            Config.update_exportado(idt, 'X')

    # Se elimina vía base de datos las compras y pagos relacionados
    @classmethod
    def delete_imported_purchases(cls, purchases):
        pool = Pool()
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
                raise UserError("Error: ",
                                f"No se encontró el id_tecno de {purchase}")
            for invoice in purchase.invoices:
                if invoice.state == 'paid':
                    cls.unreconcile_move(invoice.move)
                if invoice.move:
                    cursor.execute(*move_table.update(
                        columns=[move_table.state],
                        values=['draft'],
                        where=move_table.id == invoice.move.id))
                    cursor.execute(*move_table.delete(
                        where=move_table.id == invoice.move.id))
                cursor.execute(*invoice_table.update(
                    columns=[invoice_table.state, invoice_table.number],
                    values=['validate', None],
                    where=invoice_table.id == invoice.id))
                cursor.execute(*invoice_table.delete(
                    where=invoice_table.id == invoice.id))

            if purchase.id:
                cursor.execute(*purchase_table.update(
                    columns=[
                        purchase_table.state, purchase_table.shipment_state,
                        purchase_table.invoice_state
                    ],
                    values=['draft', 'none', 'none'],
                    where=purchase_table.id == purchase.id))
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
                    where=stock_move_table.id.in_(stock_moves)))

                cursor.execute(*stock_move_table.delete(
                    where=stock_move_table.id.in_(stock_moves)))

            if shipments:
                cursor.execute(*shipment_table.update(
                    columns=[shipment_table.state],
                    values=['draft'],
                    where=shipment_table.id.in_(shipments)))
                # Eliminación de los envíos
                cursor.execute(*shipment_table.delete(
                    where=shipment_table.id.in_(shipments)))

            if shipment_returns:
                cursor.execute(*shipment_return_table.update(
                    columns=[shipment_return_table.state],
                    values=['draft'],
                    where=shipment_return_table.id.in_(shipment_returns)))
                # Eliminación de las devoluciones de envíos
                cursor.execute(*shipment_return_table.delete(
                    where=shipment_return_table.id.in_(shipment_returns)))

            # Se elimina la compra
            cursor.execute(*purchase_table.delete(
                where=purchase_table.id == purchase.id))
        for idt in ids_tecno:
            Conexion.update_exportado(idt, 'N')

    @classmethod
    def unreconcile_move(self, move):
        Reconciliation = Pool().get('account.move.reconciliation')
        reconciliations = [
            l.reconciliation for l in move.lines if l.reconciliation
        ]
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
                    raise UserError('Order TecnoCarnes',
                                    'missing type_order_tecno')

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
                lineas += ", "
            cont += 1
        linea += lineas

        consecutivo = f"UPDATE consecutivos SET siguiente = {purchase.number} WHERE tipo = {type_order}"

        cnx = Pool().get('conector.configuration')
        cnx.set_data_rollback([pedido, linea, consecutivo])
        purchase.order_tecno_sent = True
        purchase.save()

    @classmethod
    def _create_shipment(cls, data):
        pool = Pool()
        Shipment = pool.get('stock.shipment.in')
        to_create = []

        if not data:
            return
        for number in data:
            purchase = data[number]['purchase']
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
        locations = {}
        products = {}
        tecno = {}
        excepcion = []

        result = {'tryton': {}, 'logs': {}, 'exportado': {}}
        # Se trae las ubicaciones existentes en Tryton
        _locations = Location.search(
            ['OR', ('type', '=', 'warehouse'), ('type', '=', 'supplier')])
        for location in _locations:
            if 'supplier' not in locations and location.type == 'supplier':
                locations['supplier'] = location
                continue
            id_tecno = location.id_tecno
            if id_tecno not in locations:
                locations[id_tecno] = location
        # Se procede a validar las líneas

        for linea in lineas:
            id_tecno = f"{linea.sw}-{linea.tipo}-{linea.Numero_Documento}"
            if id_tecno in excepcion:
                continue
            # Se valida la existencia del producto
            idproducto = str(linea.IdProducto)
            if idproducto not in products:
                product = Product.search([('code', '=', idproducto)])
                if not product:
                    msg = f"EXCEPCION: el producto con codigo {idproducto} no fue encontrado"
                    result['logs'][id_tecno] = msg
                    excepcion.append(id_tecno)
                    result['exportado'][id_tecno] = 'E'
                    continue
                products[idproducto], = product

            # Se valida el precio del producto
            valor_unitario = Decimal(linea.Valor_Unitario)
            if valor_unitario <= 0:
                msg = f"EXCEPCION: el valor unitario no puede ser menor o igual a cero. Su valor es: {valor_unitario} "
                result['logs'][id_tecno] = msg
                excepcion.append(id_tecno)
                result['exportado'][id_tecno] = 'E'
                continue
            # Se valida la cantidad del producto
            cantidad = float(linea.Cantidad_Facturada)
            if cantidad <= 0:
                msg = f"EXCEPCION: la cantidad no puede ser menor o igual a cero. Su valor es: {cantidad} "
                result['logs'][id_tecno] = msg
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
                _date = datetime.date(int(fecha[0]), int(fecha[1]),
                                      int(fecha[2]))
                tecno[number] = {
                    'id_tecno': id_tecno,
                    'date': _date,
                    'lines': []
                }
            tecno[number]['lines'].append(line)

        # Se trae todas las ordenes de compra que tecno nos indica faltan por entrar la mercancia
        purchases = Purchase.search([('order_tecno', '=', 'yes'),
                                     ('order_tecno_sent', '=', True),
                                     ('number', 'in', tecno.keys())])
        # Se valida las ordenes de compra según su estado de envío
        # y se agregan las líneas que van a ser creadas a la variable result
        for purchase in purchases:
            number = purchase.number
            if purchase.shipments:
                id_tecno = tecno[number]['id_tecno']
                result['logs'][
                    id_tecno] = "EXCEPCION: el envío de la orden de compra ya se encuentra creado"
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
                result['logs'][
                    id_tecno] = "EXCEPCION: no se encontro la orden de compra"
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
        if lineas:
            result = cls._validate_order(lineas)
            cls._create_shipment(result['tryton'])
            actualizacion.add_logs(result['logs'])
            for idt, exportado in result['exportado'].items():
                if exportado != 'E':
                    Config.update_exportado(idt, exportado)


class PurchaseLine(metaclass=PoolMeta):
    __name__ = 'purchase.line'

    @classmethod
    def __setup__(cls):
        super(PurchaseLine, cls).__setup__()
