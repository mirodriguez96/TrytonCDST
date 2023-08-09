import datetime
from decimal import Decimal
from trytond.i18n import gettext
from trytond.pool import PoolMeta, Pool
from trytond.model import fields, ModelView
from trytond.pyson import Eval, Or, And
from trytond.wizard import Wizard, StateTransition
from trytond.transaction import Transaction
from trytond.exceptions import UserError, UserWarning
from sql import Table


from .it_supplier_noova import SendElectronicInvoice

_ZERO = Decimal('0.0')

ELECTRONIC_STATES = [
    ('none', 'None'),
    ('submitted', 'Submitted'),
    ('pending', 'Pending'),
    ('rejected', 'Rejected'),
    ('authorized', 'Authorized'),
    ('accepted', 'Accepted'),
]

_SW = {
    '27': {
        'name': 'NOTA CREDITO COMPRAS',
        'type': 'in',
        'type_note': 'credit',
    },
    '28': {
        'name': 'NOTA DEBITO COMPRAS',
        'type': 'in',
        'type_note': 'debit',
    },
    '31': {
        'name': 'NOTA DEBITO',
        'type': 'out',
        'type_note': 'debit',
    },
    '32': {
        'name': 'NOTA CREDITO',
        'type': 'out',
        'type_note': 'credit',
    },
}

class Invoice(metaclass=PoolMeta):
    'Invoice'
    __name__ = 'account.invoice'
    id_tecno = fields.Char('Id Tabla Sqlserver (credit note)', required=False)

    @staticmethod
    def default_electronic_state():
        return 'none'

    # @staticmethod
    # def default_cufe():
    #     return '0'

    # Funcion encargada de eliminar loas conciliaciones del asiento pasado como parametro
    @classmethod
    def unreconcile_move(self, move):
        Reconciliation = Pool().get('account.move.reconciliation')
        reconciliations = [l.reconciliation for l in move.lines if l.reconciliation]
        if reconciliations:
            Reconciliation.delete(reconciliations)


    # Metodo encargado de validar los datos (importados) requeridos para la creación de la factura
    def _validate_documentos_tecno(documentos):
        data = {
            'exportado': {},
            'logs': [],
            'tryton': {},
        }
        pool = Pool()
        Config = pool.get('conector.configuration')
        AccountConfiguration = pool.get('account.configuration')(1)
        Invoice = pool.get('account.invoice')
        Line = pool.get('account.invoice.line')
        Party = pool.get('party.party')
        PaymentTerm = pool.get('account.invoice.payment_term')
        Product = pool.get('product.product')
        id_company = Transaction().context.get('company')
        company = pool.get('company.company')(id_company)
        Tax = pool.get('account.tax')
        _type = None
        _type_note = None
        # Se valida si el módulo centro de operaciones está activo y es requerido en la línea de la factura
        operation_center = hasattr(Line, 'operation_center')
        if operation_center:
            OperationCenter = pool.get('company.operation_center')
            operation_center = OperationCenter.search([], order=[('id', 'DESC')], limit=1)
            if not operation_center:
                data['logs'].append('SE REQUIERE LA CREACION DE UN CENTRO DE OPERACION')
                return data
            data['operation_center'], = operation_center
        # Se comienza a recorrer los registros importados
        tecno = {}
        for doc in documentos:
            id_tecno = f"{doc.sw}-{doc.tipo}-{doc.Numero_documento}"
            if doc.anulado.upper() == 'S':
                msg = f"Documento {id_tecno} anulado en TecnoCarnes"
                data['logs'].append(msg)
                data['exportado'][id_tecno] = 'X'
                continue
            if id_tecno not in tecno:
                tecno[id_tecno] = doc
            if not _type:
                _type = _SW[str(doc.sw)]['type']
            if not _type_note:
                _type_note = _SW[str(doc.sw)]['type_note']
                if company.party.id_number == '900715776':
                    if str(doc.sw) == '27':
                        _type_note = _SW['28']['type_note']
                    elif str(doc.sw) == '28':
                        _type_note = _SW['27']['type_note']
        if not tecno:
            return data
        # Se trae todos los terceros necesarios para los documentos
        parties = Party._get_party_documentos(documentos, 'nit_Cedula')
        # Se consulta los plazos de pago existentes para posteriormente ser usados
        payment_term = {}
        for payment in PaymentTerm.search([('id_tecno', '!=', None)]):
            if payment.id_tecno not in payment_term:
                payment_term[payment.id_tecno] = payment
        # Se busca las facturas existentes
        invoices = Invoice.search([
            ('id_tecno', 'in', tecno.keys()),
        ])
        for inv in invoices:
            id_tecno = inv.id_tecno
            msg = f"EL DOCUMENTO {id_tecno} YA EXISTE EN TRYTON"
            data['exportado'][id_tecno] = 'T'
            anulado = tecno[id_tecno].anulado
            if anulado.upper() == 'S':
                msg = f"EL DOCUMENTO {id_tecno} FUE ANULADO EN TecnoCarnes (eliminar)"
                data['exportado'][id_tecno] = 'X'
            # Se elimina del diccionario de los documentos por validar
            del tecno[id_tecno]
            data['logs'].append(msg)
        if not tecno:
            return data
        # Se importa las lineas de los documentos
        documentos_lin = Config.get_documentos_lin(tuple(tecno.keys()))
        lineas_tecno = {}
        productos_lin = {}
        impuesto_consumo = {}
        for linea in documentos_lin:
            id_tecno = f"{linea.sw}-{linea.tipo}-{linea.Numero_Documento}"
            if id_tecno not in lineas_tecno:
                lineas_tecno[id_tecno] = [linea]
            else:
                lineas_tecno[id_tecno].append(linea)
            id_producto = str(linea.IdProducto)
            if id_producto not in productos_lin:
                productos_lin[id_producto] = None
            if linea.Impuesto_Consumo > 0:
                if linea.Impuesto_Consumo not in impuesto_consumo:
                    impuesto_consumo[linea.Impuesto_Consumo] = None
        # Se hace una consulta por todos los productos de las lineas y se guarda
        products = Product.search(
            ['OR', 
             ('id_tecno', 'in', productos_lin.keys()), 
             ('code', 'in', productos_lin.keys())
             ])
        for product in products:
            productos_lin[product.code] = product
        # Se consulta los impuestos de tipo consumo
        if impuesto_consumo:
            if _type == 'out':
                kind = 'sale'
            else:
                kind = 'purchase'
            doamin_consumo = [
                ('consumo', '=', True), 
                ('type', '=', 'fixed'), 
                ('amount', 'in', impuesto_consumo.keys()),
                ['OR',
                 ('group.kind', '=', kind),
                 ('group.kind', '=', 'both'),
                ],
            ]
            _taxes = Tax.search(doamin_consumo)
            for tax in _taxes:
                impuesto_consumo[tax.amount] = tax
            for value in impuesto_consumo:
                if not impuesto_consumo[value]:
                    msg = f"No se encontro el impuesto al consumo con valor fijo de {value} para {kind}"
                    data['logs'].append(msg)
                    return data
        ################################
        # Se realiza la validacion de los demas campos y se almacena los valores
        for id_tecno, doc in tecno.items():
            try:
                if id_tecno in data['exportado']:
                    continue
                if id_tecno not in lineas_tecno:
                    msg = f"EXCEPCION: {id_tecno} - NO SE ENCONTRARON LINEAS PARA EL DOCUMENTO"
                    data['logs'].append(msg)
                    data['exportado'][id_tecno] = 'E'
                    continue
                nit_cedula = doc.nit_Cedula.replace('\n',"")
                party = None
                if nit_cedula in parties['active']:
                    party = parties['active'][nit_cedula]
                if not party:
                    if nit_cedula not in parties['inactive']:
                        msg = f"EXCEPCION: NO SE ENCONTRO EL TERCERO {nit_cedula} DEL DOCUMENTO {id_tecno}"
                        data['logs'].append(msg)
                        data['exportado'][id_tecno] = 'E'
                    continue
                condicion = str(doc.condicion)
                if condicion not in payment_term:
                    msg = f"EXCEPCION: NO SE ENCONTRO EL PLAZO {condicion} DEL DOCUMENTO {id_tecno}"
                    data['logs'].append(msg)
                    data['exportado'][id_tecno] = 'E'
                    continue
                account = None
                if _type == 'out':
                    if party.account_receivable:
                        account = party.account_receivable
                    elif AccountConfiguration.default_account_receivable:
                        account = AccountConfiguration.default_account_receivable
                elif _type == 'in':
                    if party.account_payable:
                        account = party.account_payable
                    elif AccountConfiguration.default_account_payable:
                        account = AccountConfiguration.default_account_payable
                if not account:
                    msg = f"EXCEPCION: {id_tecno} Hace falta la configuración de las cuentas por defecto pagar/cobrar"
                    data['logs'].append(msg).append(msg)
                    data['exportado'][id_tecno] = 'E'
                    continue
                fecha = str(doc.fecha_hora).split()[0].split('-')
                invoice_date = datetime.date(int(fecha[0]), int(fecha[1]), int(fecha[2]))
                description = (doc.notas).replace('\n', ' ').replace('\r', '')
                retencion_rete = False
                if doc.retencion_causada > 0:
                    if doc.retencion_iva == 0 and doc.retencion_ica == 0:
                        retencion_rete = True
                    elif (doc.retencion_iva + doc.retencion_ica) != doc.retencion_causada:
                        retencion_rete = True
                invoice = {
                    'number': f"{doc.tipo}-{doc.Numero_documento}",
                    'dcto_base': f"{doc.Tipo_Docto_Base}-{doc.Numero_Docto_Base}",
                    'party': party,
                    'payment_term': payment_term[condicion],
                    'invoice_date': invoice_date,
                    'description': description,
                    'account': account,
                    'retencion_rete': retencion_rete,
                    'retencion_iva': doc.retencion_iva,
                    'retencion_ica': doc.retencion_ica,
                    'retencion_causada': doc.retencion_causada,
                    'valor_total': doc.valor_total,
                    'type': _type,
                    'type_note': _type_note,
                }
                data['tryton'][id_tecno] = {
                    'invoice': invoice
                }
            except Exception as ex:
                msg = f"EXCEPCION: {id_tecno} - {ex}"
                data['logs'].append(msg)
                data['exportado'][id_tecno] = 'E'
        ################################
        # Se procede a validar los valores de las lineas del documento
        for id_tecno, lineas in lineas_tecno.items():
            if id_tecno in data['exportado']:
                continue
            for linea in lineas:
                try:
                    id_producto = str(linea.IdProducto)
                    if not productos_lin[id_producto]:
                        msg = f"EXCEPCION: El producto con código {id_producto} no se encontro, revisar si esta inactivo"
                        data['logs'].append(msg).append(msg)
                        data['exportado'][id_tecno] = 'E'
                        break
                    if _type_note == 'credit':
                        quantity = abs(round(linea.Cantidad_Facturada, 3)) * -1
                    else:
                        quantity = abs(round(linea.Cantidad_Facturada, 3))
                    line = {
                        'product': productos_lin[id_producto],
                        'quantity': quantity,
                        'unit_price': linea.Valor_Unitario,
                    }
                    # Se verifica si la línea tiene descuento y se agrega su valor
                    if linea.Porcentaje_Descuento_1 > 0:
                        descuento = (linea.Valor_Unitario * Decimal(linea.Porcentaje_Descuento_1)) / 100
                        line['discount'] = Decimal(linea.Valor_Unitario - descuento)
                    if linea.Impuesto_Consumo > 0:
                        line['impuesto_consumo'] = impuesto_consumo[linea.Impuesto_Consumo]
                    if 'lines' not in data['tryton'][id_tecno]:
                        data['tryton'][id_tecno]['lines'] = [line]
                    else:
                        data['tryton'][id_tecno]['lines'].append(line)
                except Exception as ex:
                    msg = f"EXCEPCION: {id_tecno} - {ex}"
                    data['logs'].append(msg)
                    data['exportado'][id_tecno] = 'E'
        return data
    

    @classmethod
    def _create_lines_tecno(cls, data, invoice):
        Line = Pool().get('account.invoice.line')
        id_tecno = invoice.id_tecno
        lineas = data['tryton'][id_tecno]['lines']
        _type = data['tryton'][id_tecno]['invoice']['type']
        lines = []
        for linea in lineas:
            line = Line()
            line.invoice = invoice
            line.product = linea['product']
            line.quantity = linea['quantity']
            line.unit_price = linea['unit_price']
            if 'operation_center' in data:
                line.operation_center = data['operation_center']
            line.on_change_product()
            taxes = []
            for tax in line.taxes:
                if tax in taxes:
                    continue
                if _type == 'in':
                    kind = 'purchase'
                else:
                    kind = 'sale'
                if tax.group.kind != 'both' and tax.group.kind != kind:
                    continue
                classification = tax.classification_tax_tecno
                if classification in ['05', '06', '07']:
                    if classification == '05' and \
                        data['tryton'][id_tecno]['invoice']['retencion_iva'] > 0:
                        taxes.append(tax)
                    elif classification == '07' and \
                        data['tryton'][id_tecno]['invoice']['retencion_ica'] > 0:
                        taxes.append(tax)
                    elif classification == '06' and \
                        data['tryton'][id_tecno]['invoice']['retencion_rete']:
                        taxes.append(tax)
                elif tax.consumo and 'impuesto_consumo' in linea:
                    taxes.append(linea['impuesto_consumo'])
                elif not tax.consumo:
                    taxes.append(tax)
            line.taxes = taxes
            if 'discount' in linea:
                line.unit_price = linea['discount']
                line.on_change_product()
                line.gross_unit_price = linea['unit_price']
            if _type == 'in':
                line.account = line.product.account_category.account_expense
            lines.append(line)
        return lines


    @classmethod
    def _create_invoice_tecno(cls, data):
        if not data['tryton']:
            return data
        Invoice = Pool().get('account.invoice')
        to_save = []
        for id_tecno, values in data['tryton'].items():
            inv = values['invoice']
            invoice = Invoice()
            invoice.id_tecno = id_tecno
            invoice.party = inv['party']
            # Se usa el on_change para traer la dirección del tercero
            invoice.on_change_party()
            invoice.invoice_date = inv['invoice_date']
            invoice.number = inv['number']
            invoice.reference = inv['dcto_base']
            # if inv['type_note'] == 'credit':
            #     invoice.reference = inv['dcto_base']
            # else:
            #     invoice.comment = inv['dcto_base']
            invoice.description = inv['description']
            invoice.account = inv['account']
            invoice.type = inv['type']
            if inv['type'] == 'out':
                invoice.invoice_type = 'C'
            invoice.on_change_type()
            invoice.payment_term = inv['payment_term']
            invoice.lines = cls._create_lines_tecno(data, invoice)
            invoice.on_change_lines()
            to_save.append(invoice)
        with Transaction().set_context(_skip_warnings=True):
            Invoice.save(to_save)
            Invoice.validate_invoice(to_save)
            to_post = []
            for invoice in to_save:
                documento = data['tryton'][invoice.id_tecno]['invoice']
                result = cls._validate_total_tecno(invoice.total_amount, documento)
                if not result['value']:
                    msg = f"REVISAR: ({invoice.id_tecno}) "\
                    f"El total de Tryton {invoice.total_amount} "\
                    f"es diferente al total de TecnoCarnes {result['total_tecno']} "\
                    f"La diferencia es de {result['diferencia']}"
                    data['logs'].append(msg)
                else:
                    to_post.append(invoice)
                data['exportado'][invoice.id_tecno] = 'T'
            Invoice.post(to_post)
            if inv['type_note'] == 'credit' and to_post:
                cls._check_cross_invoices(to_post)
        return data
    

    # Función encargada de importar notas débito y crédito de TecnoCarnes
    @classmethod
    def _import_notas_tecno(cls, sw):
        print(f"RUN {_SW[sw]['name']}")
        pool = Pool()
        Config = pool.get('conector.configuration')
        configuration = Config.get_configuration()
        if not configuration:
            return
        Actualizacion = pool.get('conector.actualizacion')
        actualizacion = Actualizacion.create_or_update(_SW[sw]['name'])
        documentos = Config.get_documentos_tecno(sw)
        if not documentos:
            print(f"FINISH {_SW[sw]['name']}")
            return
        # Se procede a validar los documentos importados de TecnoCarnes
        data = cls._validate_documentos_tecno(documentos)
        # Se procede a crear las facturas que hayan cumplido con la validación
        data = cls._create_invoice_tecno(data)
        # Se marca los documentos en Tecnocarnes de acuerdo a las diferentes excepciones
        for idt, exportado in data['exportado'].items():
            Config.update_exportado(idt, exportado)
        Actualizacion.add_logs(actualizacion, data['logs'])
        print(f"FINISH {_SW[sw]['name']}")


    # Metodo encargado de validar el total de la factura en Tryton y TecnoCarnes
    @classmethod
    def _validate_total_tecno(cls, total_tryton, documento):
        result = {
            'value': False,
        }
        retencion_causada = abs(documento['retencion_causada'])
        total_tecno = abs(documento['valor_total'])
        total_tryton = abs(total_tryton)
        total_tecno = total_tecno - retencion_causada
        diferencia = abs(total_tryton - total_tecno)
        if diferencia < Decimal('6.0'):
            result['value'] = True
        result['total_tecno'] = total_tecno
        result['diferencia'] = diferencia
        return result


    # Nota de crédito
    @classmethod
    def import_credit_note(cls):
        cls._import_notas_tecno('32')

    # Nota de débito
    @classmethod
    def import_debit_note(cls):
        cls._import_notas_tecno('31')

    # Nota de crédito de compras
    @classmethod
    def import_credit_note_purchase(cls):
        cls._import_notas_tecno('27')

    # Nota de débito de compras
    @classmethod
    def import_debit_note_purchase(cls):
        cls._import_notas_tecno('28')


    @classmethod
    def __setup__(cls):
        super(Invoice, cls).__setup__()
        cls._buttons.update({
            'submit': {
                'invisible': True
            },
            'send_email': {
                'invisible': True
            },
            'send_support_document': {
                'invisible': Or(
                    And(Eval('type') != 'out', ~Eval('equivalent_invoice')),
                    Eval('electronic_state') == 'authorized',
                    Eval('number', None) == None,
                    Eval('authorization', None) == None,
                    Eval('state') != 'validated',
                )}
            },)
    
    @classmethod
    def check_duplicated_reference(cls, invoice):
        if invoice.total_amount < 0:
            return
        today = datetime.date.today()
        target_date = today - datetime.timedelta(days=90)
        if invoice.reference:
            duplicates = cls.search_read([
                ('reference', '=', invoice.reference),
                ('party', '=', invoice.party.id),
                ('invoice_date', '>=', target_date),
            ], fields_names=['reference'])
            if len(duplicates) >= 2:
                raise UserError(gettext(
                    'account_col.msg_duplicated_reference_invoice')
                    )


    # Boton (función) que sirve para enviar los documentos soporte al proveedor tecnologico
    @classmethod
    @ModelView.button
    def send_support_document(cls, records):
        for invoice in records:
            if invoice.invoice_type not in ('05', '95'):
                continue
            if invoice.authorization and not invoice.event:
                _ = SendElectronicInvoice(invoice, invoice.authorization)
            else:
                invoice.get_message('El campo proveedor de autorización no ha sido seleccionado')


    @staticmethod
    def _check_cross_invoices(invoices=None):
        print('RUN validar cruce de facturas')
        pool = Pool()
        Invoice = pool.get('account.invoice')
        MoveLine = pool.get('account.move.line')
        Reconciliation = pool.get('account.move.reconciliation')
        Actualizacion = pool.get('conector.actualizacion')
        actualizacion = Actualizacion.create_or_update(f'CRUCE DE FACTURAS')
        logs = []
        if not invoices:
            cursor = Transaction().connection.cursor()
            # (FIX) CONSULTA SOLO PARA NOTAS CREDITO
            query = "SELECT id FROM account_invoice WHERE state = 'posted' AND invoice_type != '92' \
                AND number != reference AND number like '%-%' AND reference like '%-%'"
            cursor.execute(query)
            invoices_id = cursor.fetchall()
            _ids = []
            for invoice in invoices_id:
                _ids.append(invoice[0])
            invoices = Invoice.browse(_ids)

        cross = {}
        numbers = []
        for inv in invoices:
            if inv.reference not in cross:
                cross[inv.reference] = [inv]
                numbers.append(inv.reference)
            else:
                cross[inv.reference].append(inv)

        origin_invoices = Invoice.search([
            ('number', 'in', numbers),
            ('state', 'in', ['posted', 'paid'])
        ])
        to_save = []
        for origin in origin_invoices:
            if origin.state == 'paid':
                msg = f"LA FACTURA CON ID {origin} YA SE ENCUENTRA EN ESTADO PAGADA "\
                    f"PERO LA(S) FACTURA(S) CRUCE CON ID {cross[origin.number]} "\
                    "SE ENCUENTRAN AUN EN ESTADO CONTABILIZADO"
                logs.append(msg)
                continue
            lines_to_pay = []
            for inv in cross[origin.number]:
                lines_to_pay += list(inv.lines_to_pay)
            payment_lines = list(origin.payment_lines)
            for line in lines_to_pay:
                if line not in payment_lines:
                    payment_lines.append(line)
            if len(payment_lines) > len(origin.payment_lines):
                all_lines = list(origin.lines_to_pay) + payment_lines
                reconciliations = []
                amount = _ZERO
                for line in all_lines:
                    if line.reconciliation:
                        reconciliations.append(line.reconciliation)
                    if origin.type == 'out':
                        amount += line.debit - line.credit
                    elif origin.type == 'in':
                        amount += line.credit - line.debit
                if amount >= _ZERO:
                    origin.payment_lines = payment_lines
                    to_save.append(origin)
                    if amount == _ZERO:
                        Reconciliation.delete(reconciliations)
                        MoveLine.reconcile(all_lines)
                else:
                    msg = f"LA FACTURA CON ID {origin} TIENE UN PAGO MAYOR "\
                        f"POR LA(S) FACTURA(S) CRUCE {cross[origin.number]}"
                    logs.append(msg)
        Invoice.save(to_save)
        Actualizacion.add_logs(actualizacion, logs)
        print('FINISH validar cruce de facturas')

    # Función encargada de obtener los ids de los registros a eliminar
    @classmethod
    def _get_delete_invoices(cls, invoices):
        ids_tecno = []
        to_delete = {
            'reconciliation': [],
            'move': [],
            'invoice': [],
        }
        for invoice in invoices:
            ids_tecno.append(invoice.id_tecno)
            if hasattr(invoice, 'electronic_state') and \
                invoice.electronic_state == 'submitted':
                    raise UserError('account_col.msg_with_electronic_invoice')
            if invoice.state == 'paid':
                for line in invoice.move.lines:
                    if line.reconciliation and line.reconciliation.id not in to_delete['reconciliation']:
                        to_delete['reconciliation'].append(line.reconciliation.id)
            if invoice.move:
                if invoice.move.id not in to_delete['move']:
                    to_delete['move'].append(invoice.move.id)
            if invoice.id not in to_delete['invoice']:
                to_delete['invoice'].append(invoice.id)
        return ids_tecno, to_delete

    # Función creada con base al asistente force_draft del módulo sale_pos de presik
    # Esta función se encarga de eliminar los registros mediante cursor
    @classmethod
    def _delete_invoices(cls, to_delete):
        invoice_table = Table('account_invoice')
        move_table = Table('account_move')
        reconciliation_table = Table('account_move_reconciliation')
        cursor = Transaction().connection.cursor()
        # Se procede a realizar la eliminación de todos los registros
        print(to_delete)
        if to_delete['reconciliation']:
            cursor.execute(*reconciliation_table.delete(
                where=reconciliation_table.id.in_(to_delete['reconciliation']))
            )
        if to_delete['move']:
            cursor.execute(*move_table.update(
                columns=[move_table.state],
                values=['draft'],
                where=move_table.id.in_(to_delete['move']))
            )
            cursor.execute(*move_table.delete(
                where=move_table.id.in_(to_delete['move']))
                )
        if to_delete['invoice']:
            cursor.execute(*invoice_table.update(
                columns=[invoice_table.state, invoice_table.number],
                values=['validate', None],
                where=invoice_table.id.in_(to_delete['invoice']))
            )
            cursor.execute(*invoice_table.delete(
                where=invoice_table.id.in_(to_delete['invoice']))
            )

    # Función encargada de eliminar y marcar para importar ventas de importadas de TecnoCarnes
    @classmethod
    def delete_imported_notes(cls, invoices):
        Cnxn = Pool().get('conector.configuration')
        ids_tecno, to_delete = cls._get_delete_invoices(invoices)
        cls._delete_invoices(to_delete)
        for idt in ids_tecno:
            Cnxn.update_exportado(idt, 'N')


class InvoiceLine(metaclass=PoolMeta):
    __name__ = 'account.invoice.line'

    @classmethod
    def __setup__(cls):
        super(InvoiceLine, cls).__setup__()

    def _get_latin_move_lines(self, amount, type_, account_stock_method):
        result = super(InvoiceLine, self)._get_latin_move_lines(amount, type_, account_stock_method)
        if self.invoice.id_tecno:
            id_tecno = self.invoice.id_tecno.split('-')
            if id_tecno[0] in _SW:
                return []
        return result


class UpdateInvoiceTecno(Wizard):
    'Update Invoice Tecno'
    __name__ = 'account.invoice.update_invoice_tecno'
    start_state = 'do_submit'
    do_submit = StateTransition()

    def transition_do_submit(self):
        pool = Pool()
        Invoice = pool.get('account.invoice')
        Sale = pool.get('sale.sale')
        Purchase = pool.get('purchase.purchase')

        ids = Transaction().context['active_ids']

        to_delete_sales = []
        to_delete_purchases = []
        to_delete_note = []
        for invoice in Invoice.browse(ids):
            rec_name = invoice.rec_name
            party_name = invoice.party.name
            rec_party = rec_name+' de '+party_name
            if invoice.number and '-' in invoice.number:
                if invoice.id_tecno:
                    sw = invoice.id_tecno.split('-')[0]
                    if sw in _SW.keys():
                        to_delete_note.append(invoice)
                        continue
                if invoice.type == 'out':
                    sale = Sale.search([('number', '=', invoice.number)])
                    if sale:
                        to_delete_sales.append(sale[0])
                elif invoice.type == 'in':
                    purchase = Purchase.search([('number', '=', invoice.number)])
                    if purchase:
                        to_delete_purchases.append(purchase[0])
            else:
                raise UserError("Revisa el número de la factura (tipo-numero): ", rec_party)
        if to_delete_sales:
            Sale.delete_imported_sales(to_delete_sales)
        if to_delete_purchases:
            Purchase.delete_imported_purchases(to_delete_purchases)
        if to_delete_note:
            Invoice.delete_imported_notes(to_delete_note)
        return 'end'

    def end(self):
        return 'reload'


# Asistente encargado de cambiar la fecha del asiento y la nota contable para que coincidan
class UpdateNoteDate(Wizard):
    'Update Note Date'
    __name__ = 'account.invoice.update_note_date'
    start_state = 'to_update'
    to_update = StateTransition()

    def transition_to_update(self):
        pool = Pool()
        Warning = pool.get('res.user.warning')
        Invoice = pool.get('account.invoice')
        move_table = Table('account_move')
        note_table = Table('account_note')
        cursor = Transaction().connection.cursor()
        ids = Transaction().context['active_ids']

        warning_name = 'warning_udate_note_%s' % ids
        if Warning.check(warning_name):
            raise UserWarning(warning_name, "Se va a actualizar las fechas de los anticipos cruzados con respecto a la fecha de la factura.")

        for invoice in Invoice.browse(ids):
            rec_name = invoice.rec_name
            party_name = invoice.party.name
            rec_party = rec_name+' de '+party_name
            if invoice.state == 'posted' or invoice.state == 'paid':
                movelines = invoice.reconciliation_lines or invoice.payment_lines
                if movelines:
                    for line in movelines:
                        if line.move_origin and hasattr(line.move_origin, '__name__') and line.move_origin.__name__ == 'account.note':
                            cursor.execute(*move_table.update(
                                columns=[move_table.date, move_table.post_date, move_table.period],
                                values=[invoice.invoice_date, invoice.invoice_date, invoice.move.period.id],
                                where=move_table.id == line.move.id)
                            )
                            cursor.execute(*note_table.update(
                                columns=[note_table.date],
                                values=[invoice.invoice_date],
                                where=note_table.id == line.move_origin.id)
                            )
            else:
                raise UserError("La factura debe estar en estado contabilizada o pagada.", rec_party)
        return 'end'