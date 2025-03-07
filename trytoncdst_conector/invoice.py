"""INVOICE MODULE"""
from datetime import date, datetime, timedelta
from decimal import Decimal

from sql import Table
from trytond.exceptions import UserError, UserWarning
from trytond.i18n import gettext
from trytond.model import ModelView, fields
from trytond.pool import Pool, PoolMeta
from trytond.pyson import And, Eval, Or
from trytond.transaction import Transaction
from trytond.wizard import Button, StateTransition, StateView, Wizard

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
        'name': 'NOTA DEBITO COMPRAS',
        'type': 'in',
        'type_note': 'debit',
    },
    '28': {
        'name': 'NOTA CREDITO COMPRAS',
        'type': 'in',
        'type_note': 'credit',
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


class AnalyticAccountEntry(metaclass=PoolMeta):
    __name__ = 'analytic.account.entry'

    @classmethod
    def _get_origin(cls):
        origins = super(AnalyticAccountEntry, cls)._get_origin()
        return origins + ['account.invoice.line', 'account.invoice']


class Invoice(metaclass=PoolMeta):
    'Account Invoice'
    __name__ = 'account.invoice'
    id_tecno = fields.Char('Id Tabla Sqlserver (credit note)', required=False)
    note_analytic_account = ''
    note_adjustment_account = ''
    note_date = ''
    note_invoice_type = ''

    @classmethod
    def __setup__(cls):
        super(Invoice, cls).__setup__()
        cls._buttons.update(
            {
                'submit': {
                    'invisible': True
                },
                'send_email': {
                    'invisible': True
                },
                'send_support_document': {
                    'invisible':
                    Or(
                        And(
                            Eval('type') != 'out',
                            ~Eval('equivalent_invoice')),
                        Eval('electronic_state') == 'authorized',
                        Eval('number', None) == None,
                        Eval('authorization', None) == None,
                        Eval('state') != 'validated',
                    )
                }
            }, )

    @staticmethod
    def default_electronic_state():
        return 'none'

    @classmethod
    def launch(cls, data):
        pool = Pool()
        Invoice = pool.get('account.invoice')
        invoices = Invoice.search([('type', '=', data['invoice_type']),
                                   ('state', '=', 'posted'),
                                   ('invoice_date', '>=', data['date_start']),
                                   ('invoice_date', '<=', data['date_finish'])
                                   ])
        transaction = Transaction()
        context = transaction.context
        cls.note_analytic_account = data['analytic_account']
        cls.note_invoice_type = data['invoice_type']
        cls.note_adjustment_account = data['adjustment_account']
        cls.note_date = data['date']

        inv_adjustment = [
            inv for inv in invoices if 0 < inv.amount_to_pay <= data['amount']
        ]

        if not inv_adjustment:
            raise UserError("ERROR: No se encontraron facturas asociadas.")

        for invoice in inv_adjustment:
            invoice_ = cls.__queue__.create_adjustment_note(invoice)
            with transaction.set_context(
                    queue_batch=context.get('queue_batch', True)):
                cls.__queue__.process([invoice_])

    @classmethod
    def create_adjustment_note(cls, inv):
        """Function to create account note for invoices
        to required adjustment"""

        pool = Pool()
        Period = pool.get('account.period')
        Config = pool.get('account.voucher_configuration')
        Note = pool.get('account.note')
        Line = pool.get('account.note.line')
        Note = pool.get('account.note')
        config = Config.get_configuration()

        adjustment_account = cls.note_adjustment_account
        analytic_account = cls.note_analytic_account
        invoice_type = cls.note_invoice_type
        note_date = cls.note_date

        operation_center = pool.get('company.operation_center')(1)
        lines_to_create = []
        note = Note()

        last_date = inv.invoice_date
        amount_to_pay = inv.amount_to_pay
        move_lines = inv.move.lines
        payment_lines = inv.payment_lines

        for ml in move_lines:
            account_move = inv.account
            account_move_line = ml.account
            payable_move_line = ml.account.type.payable
            receivable_move_line = ml.account.type.receivable

            if account_move == account_move_line and (payable_move_line
                                                      or receivable_move_line):
                _line = Line()
                _line.debit = ml.credit
                _line.credit = ml.debit
                _line.party = ml.party
                _line.account = ml.account
                _line.description = ml.description
                _line.move_line = ml

                operation_center = ml.operation_center\
                    if ml.operation_center else operation_center
                _line.operation_center = operation_center
                lines_to_create.append(_line)

        for pl in payment_lines:
            _line = Line()
            _line.debit = pl.credit
            _line.credit = pl.debit
            _line.party = pl.party
            _line.account = pl.account
            _line.description = pl.description
            _line.move_line = pl
            _line.operation_center = operation_center

            if last_date:
                if last_date < pl.date:
                    last_date = pl.date
            else:
                last_date = pl.date
            lines_to_create.append(_line)
        inv.payment_lines = []
        inv.save()

        # created adjusted line
        _line = Line()
        _line.party = inv.party
        _line.account = adjustment_account
        _line.description = f"AJUSTE FACTURA {inv.number}"

        if invoice_type == 'out':
            _line.debit = amount_to_pay
            _line.credit = 0
        else:
            _line.debit = 0
            _line.credit = amount_to_pay
        if operation_center:
            _line.operation_center = operation_center
        if analytic_account:
            _line.analytic_account = analytic_account
        lines_to_create.append(_line)

        # build note info
        period = Period.search([('state', '=', 'open'),
                                ('start_date', '>=', last_date),
                                ('end_date', '<=', last_date)])
        if period:
            note.date = last_date
        else:
            note.date = note_date
        note.journal = config.default_journal_note
        note.description = f"AJUSTE FACTURA {inv.number}"
        note.lines = lines_to_create
        Note.save([note])
        Note.post([note])
        return inv

    @classmethod
    @ModelView.button
    def validate_invoice(cls, invoices, sw=None):
        """Function that use check button in view,
        validate invoices

        Args:
            invoices (object): object from account_invoice model
            sw ():pending. Defaults to None.
        """
        for inv in invoices:
            if inv.type == 'out':
                cls.validate_tax(inv, sw=sw)
        super(Invoice, cls).validate_invoice(invoices)

    # se sobreescribe el metodo del modulo account_col
    @classmethod
    def validate_tax(cls, invoice, sw=None):
        pool = Pool()
        Config = pool.get('account.configuration')
        Line = pool.get('account.invoice.line')
        InvoiceTax = Pool().get('account.invoice.tax')
        config = Config(1)

        if not sw:
            taxes_validate = [
                t for t in invoice.taxes
                if t.base and t.tax.base and t.tax.base > abs(t.base)
            ]
        else:
            taxes_validate = []

        if taxes_validate and config.remove_tax:
            lines_to_change = [l for l in invoice.lines if l.type == 'line']
            Line.write(
                lines_to_change,
                {'taxes': [('remove', [t.tax.id for t in taxes_validate])]})
            InvoiceTax.delete(taxes_validate)
            invoice.save()

    # se sobreescribe el metodo del modulo account_col
    @classmethod
    def set_number(cls, invoices):
        to_save = []
        for invoice in invoices:
            if not invoice.number and invoice.type == 'out' \
                    and invoice.authorization:
                invoice.check_authorization()
                invoice.number = invoice.authorization.sequence.get()
                to_save.append(invoice)
            if invoice.type == 'in' and invoice.equivalent_invoice \
                    and not invoice.number_alternate:
                invoice.check_authorization()
                invoice.number_alternate = invoice.authorization.sequence.get()
                to_save.append(invoice)
        if to_save:
            cls.save(to_save)
        super(Invoice, cls).set_number(invoices)

    # Funcion encargada de eliminar loas conciliaciones del asiento pasado como parametro
    @classmethod
    def unreconcile_move(self, move):
        Reconciliation = Pool().get('account.move.reconciliation')
        reconciliations = [
            l.reconciliation for l in move.lines if l.reconciliation
        ]
        if reconciliations:
            Reconciliation.delete(reconciliations)

    @classmethod
    def get_analytic_tipodocto(cls, tipos_doctos):
        analytic_types = {}
        if tipos_doctos:
            pool = Pool()
            Config = pool.get('conector.configuration')
            ids_tipos = ids_tipos = "(" + ", ".join(map(str,
                                                        tipos_doctos)) + ")"
            tbltipodocto = Config.get_tbltipodoctos_encabezado(ids_tipos)
            _values = {}
            for tipodocto in tbltipodocto:
                if tipodocto.Encabezado and tipodocto.Encabezado != '0':
                    encabezado = str(tipodocto.Encabezado)
                    idtipod = str(tipodocto.idTipoDoctos)
                    if encabezado not in _values:
                        _values[encabezado] = []
                    _values[encabezado].append(idtipod)
            if _values:
                AnalyticAccount = pool.get('analytic_account.account')
                analytic_accounts = AnalyticAccount.search([('code', 'in',
                                                             _values.keys())])
                for ac in analytic_accounts:
                    idstipo = _values[ac.code]
                    for idt in idstipo:
                        analytic_types[idt] = ac
        return analytic_types

    # Metodo encargado de validar los datos (importados) requeridos para la creación de la factura
    def _validate_documentos_tecno(documentos):
        try:
            data = {
                'exportado': {},
                'logs': {},
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
            # id_company = Transaction().context.get('company')
            # company = pool.get('company.company')(id_company)
            Tax = pool.get('account.tax')
            Period = pool.get('account.period')
            Actualizacion = pool.get('conector.actualizacion')
            actualizacion = Actualizacion.create_or_update(
                'VALIDAR CREAR NOTAS')
            logs = {}
            to_exception = []
            _type = None
            _type_note = None
            # Se valida si el módulo centro de operaciones está activo y es requerido en la línea de la factura
            operation_center = hasattr(Line, 'operation_center')
            if operation_center:
                OperationCenter = pool.get('company.operation_center')
                operation_center = OperationCenter.search([],
                                                          order=[
                                                              ('id', 'DESC')],
                                                          limit=1)
                if not operation_center:
                    data['logs'][
                        'operation_center'] = "SE REQUIERE LA CREACION DE UN CENTRO DE OPERACION"
                    return data
                data['operation_center'], = operation_center
            # Se comienza a recorrer los registros importados
            tipos_doctos = []
            tecno = {}
            for doc in documentos:
                id_tecno = f"{doc.sw}-{doc.tipo}-{doc.Numero_documento}"
                if doc.anulado.upper() == 'S':
                    data['logs'][id_tecno] = f"Documento anulado en TecnoCarnes"
                    data['exportado'][id_tecno] = 'X'
                    continue
                # Proceso de validacion del periodo, si este se encuentra cerrado,
                # no permitira ninguna operacion con el documento

                if doc.fecha_hora and isinstance(doc.fecha_hora,
                                                 datetime):
                    fecha_hora = doc.fecha_hora.date()

                    if isinstance(fecha_hora, date):

                        validate_period = Period.search([
                            ('start_date', '>=', fecha_hora),
                            ('end_date', '<=', fecha_hora),
                        ])
                        if validate_period:
                            if validate_period[0].state == 'close':
                                to_exception.append(id_tecno)
                                logs[
                                    id_tecno] = "EXCEPCION: EL PERIODO DEL DOCUMENTO SE ENCUENTRA CERRADO \
                                Y NO ES POSIBLE SU CREACION"

                                continue

                        if id_tecno not in tecno:
                            tecno[id_tecno] = doc
                        if not _type:
                            _type = _SW[str(doc.sw)]['type']
                        if not _type_note:
                            _type_note = _SW[str(doc.sw)]['type_note']
                        if str(doc.tipo) not in tipos_doctos:
                            tipos_doctos.append(str(doc.tipo))
                    else:
                        to_exception.append(id_tecno)
                        logs[
                            id_tecno] = "EXCEPCION: EL PERIODO NO CONTIENE FECHA CORRECTA"
                        continue

                else:
                    to_exception.append(id_tecno)
                    logs[
                        id_tecno] = "EXCEPCION: EL PERIODO NO CONTIENE FECHA CORRECTA"
                    continue

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
                msg = "EL DOCUMENTO YA EXISTE EN TRYTON"
                data['exportado'][id_tecno] = 'T'
                anulado = tecno[id_tecno].anulado
                if anulado.upper() == 'S':
                    msg = "EL DOCUMENTO FUE ANULADO EN TecnoCarnes (eliminar)"
                    data['exportado'][id_tecno] = 'X'
                # Se elimina del diccionario de los documentos por validar
                del tecno[id_tecno]
                data['logs'][id_tecno] = msg
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
            products = Product.search([
                'OR', ('id_tecno', 'in', productos_lin.keys()),
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
                    [
                        'OR',
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
                        data['logs'][id_tecno] = msg
                        return data
            ################################
            # Se realiza la validacion de los demas campos y se almacena los valores
            for id_tecno, doc in tecno.items():
                try:
                    if id_tecno in data['exportado']:
                        continue
                    if id_tecno not in lineas_tecno:
                        data['logs'][
                            id_tecno] = "NO SE ENCONTRARON LINEAS PARA EL DOCUMENTO"
                        data['exportado'][id_tecno] = 'E'
                        continue
                    nit_cedula = doc.nit_Cedula.replace('\n', "")
                    party = None
                    if nit_cedula in parties['active']:
                        party = parties['active'][nit_cedula]
                    if not party:
                        if nit_cedula not in parties['inactive']:
                            msg = f"EXCEPCION: NO SE ENCONTRO EL TERCERO {nit_cedula} DEL DOCUMENTO"
                            data['logs'][id_tecno] = msg
                            data['exportado'][id_tecno] = 'E'
                        continue
                    condicion = str(doc.condicion)
                    if condicion not in payment_term:
                        msg = f"EXCEPCION: NO SE ENCONTRO EL PLAZO {condicion}"
                        data['logs'][id_tecno] = msg
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
                        msg = "EXCEPCION: Hace falta la configuración de las cuentas por defecto pagar/cobrar"
                        data['logs'][id_tecno] = msg
                        data['exportado'][id_tecno] = 'E'
                        continue
                    fecha = str(doc.fecha_hora).split()[0].split('-')
                    invoice_date = date(int(fecha[0]), int(fecha[1]),
                                        int(fecha[2]))
                    description = (doc.notas).replace(
                        '\n', ' ').replace('\r', '')
                    retencion_rete = False
                    if doc.retencion_causada > 0:
                        if doc.retencion_iva == 0 and doc.retencion_ica == 0:
                            retencion_rete = True
                        elif (doc.retencion_iva
                              + doc.retencion_ica) != doc.retencion_causada:
                            retencion_rete = True
                    invoice = {
                        'number': f"{doc.tipo}-{doc.Numero_documento}",
                        'dcto_base':
                        f"{doc.Tipo_Docto_Base}-{doc.Numero_Docto_Base}",
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
                    data['tryton'][id_tecno] = {'invoice': invoice}
                except Exception as ex:
                    data['logs'][id_tecno] = f"EXCEPCION: {ex}"
                    data['exportado'][id_tecno] = 'E'
            ################################
            analytic_types = Invoice.get_analytic_tipodocto(tipos_doctos)
            # Se procede a validar los valores de las lineas del documento
            for id_tecno, lineas in lineas_tecno.items():
                if id_tecno in data['exportado']:
                    continue
                for linea in lineas:
                    try:
                        id_producto = str(linea.IdProducto)
                        if not productos_lin[id_producto]:
                            msg = f"EXCEPCION: El producto con código {id_producto} no se encontro, revisar si esta inactivo"
                            data['logs'][id_tecno] = msg
                            data['exportado'][id_tecno] = 'E'
                            break
                        if _type_note == 'credit':
                            quantity = abs(
                                round(linea.Cantidad_Facturada, 3)) * -1
                        else:
                            quantity = abs(round(linea.Cantidad_Facturada, 3))

                        line = {
                            'product': productos_lin[id_producto],
                            'quantity': quantity,
                            'unit_price': linea.Valor_Unitario,
                        }
                        if str(doc.tipo) in analytic_types:
                            line['analytic_account'] = analytic_types[str(
                                doc.tipo)]
                        # Se verifica si la línea tiene descuento y se agrega su valor
                        if linea.Porcentaje_Descuento_1 > 0:
                            descuento = (linea.Valor_Unitario * Decimal(
                                linea.Porcentaje_Descuento_1)) / 100
                            line['discount'] = Decimal(linea.Valor_Unitario
                                                       - descuento)
                        if linea.Impuesto_Consumo > 0:
                            line['impuesto_consumo'] = impuesto_consumo[
                                linea.Impuesto_Consumo]
                        if 'lines' not in data['tryton'][id_tecno]:
                            data['tryton'][id_tecno]['lines'] = [line]
                        else:
                            data['tryton'][id_tecno]['lines'].append(line)
                    except Exception as ex:
                        data['logs'][id_tecno] = f"EXCEPCION: {ex}"
                        data['exportado'][id_tecno] = 'E'
                        if id_tecno in data['tryton']:
                            # Se elimina de las facturas a crear
                            del data['tryton'][id_tecno]
            if to_exception:
                actualizacion.add_logs(logs)
            return data
        except Exception as error:
            print(f"ERROR NOTA: {error}")

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

            if _type == 'out':
                category = line.product.account_category
                id_tecno = line.invoice.id_tecno
                if category:
                    if id_tecno.split('-')[0] in ['32']:
                        if category.account_credit_note:
                            line.account = category.account_credit_note
                        elif category.account_return_sale:
                            line.account = category.account_return_sale

            if 'analytic_account' in linea:
                line.analytic_account = linea['analytic_account']
                line.on_change_analytic_account()
            lines.append(line)
        return lines

    @classmethod
    def _create_invoice_tecno(cls, data):
        try:
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
                    result = cls._validate_total_tecno(invoice.total_amount,
                                                       documento)
                    if not result['value']:
                        msg = f"REVISAR: ({invoice.id_tecno}) "\
                            f"El total de Tryton {invoice.total_amount} "\
                            f"es diferente al total de TecnoCarnes {result['total_tecno']} "\
                            f"La diferencia es de {result['diferencia']}"
                        data['logs'][invoice.id_tecno] = msg
                    else:
                        to_post.append(invoice)
                    data['exportado'][invoice.id_tecno] = 'T'
                Invoice.post(to_post)
                if inv['type_note'] == 'credit' and to_post:
                    cls._check_cross_invoices(to_post)
            return data
        except Exception as error:
            print(f'ERROR NOTA: {error}')

    @classmethod
    def _import_notas_tecno(cls, sw):

        pool = Pool()
        Config = pool.get('conector.configuration')
        configuration = Config.get_configuration()
        import_name = _SW[sw]['name']
        print(f"---------------RUN {import_name}---------------")
        if not configuration:
            return
        Actualizacion = pool.get('conector.actualizacion')
        actualizacion = Actualizacion.create_or_update(_SW[sw]['name'])
        documentos = Config.get_documentos_tecno(sw)
        if not documentos:
            print(f"---------------FINISH {import_name}---------------")
            return
        for document in documentos:
            try:
                # Se procede a validar los documentos importados de TecnoCarnes
                data = cls._validate_documentos_tecno([document])
                # Se procede a crear las facturas que hayan cumplido con la validación
                data = cls._create_invoice_tecno(data)
                # Se marca los documentos en Tecnocarnes de acuerdo a las diferentes excepciones
                for idt, exportado in data['exportado'].items():
                    if exportado != 'E':
                        Config.update_exportado(idt, exportado)
                actualizacion.add_logs(data['logs'])
            except Exception as error:
                Transaction().rollback()
                log = {"EXCEPCION": error}
                print(f"ROLLBACK-{import_name}: {error}")
                actualizacion.add_logs(log)

        print(f"---------------FINISH {import_name}---------------")

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
        cls._import_notas_tecno('28')

    # Nota de débito de compras
    @classmethod
    def import_debit_note_purchase(cls):
        cls._import_notas_tecno('27')

    @classmethod
    def check_duplicated_reference(cls, invoice):
        exception = False
        count_reference = 0
        if (invoice.total_amount < 0 or not invoice.reference
                or not invoice.number):
            return
        id_tecno = invoice.id_tecno if invoice.id_tecno else None
        sw_ = id_tecno.split('-')[0] if id_tecno else None
        invoices_ = cls.search([('reference', '=', invoice.reference),
                                ('state', '!=', 'cancelled'),
                                ('party', '=', invoice.party)])
        count_reference = len(invoices_)
        if (sw_ and sw_ == '3' and count_reference > 1):
            exception = True
        elif not sw_ and count_reference > 1:
            exception = True

        if exception:
            raise UserError(
                gettext('account_col.msg_duplicated_reference_invoice'))

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
                invoice.get_message(
                    'El campo proveedor de autorización no ha sido seleccionado'
                )

    @staticmethod
    def _check_cross_invoices(invoices=None):
        pool = Pool()
        Invoice = pool.get('account.invoice')
        MoveLine = pool.get('account.move.line')
        Reconciliation = pool.get('account.move.reconciliation')
        Actualizacion = pool.get('conector.actualizacion')

        import_name = "CRUCE DE FACTURAS"
        try:
            actualizacion = Actualizacion.create_or_update(
                'CRUCE DE FACTURAS')
            print(f'---------------RUN {import_name}---------------')
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

            origin_invoices = Invoice.search([('number', 'in', numbers),
                                              ('state', 'in', ['posted', 'paid'])])
            logs = {}
            for origin in origin_invoices:
                try:
                    if origin.state == 'paid':
                        msg = f"LA FACTURA CON ID {origin} YA SE ENCUENTRA EN ESTADO PAGADA "\
                            f"PERO LA(S) FACTURA(S) CRUCE CON ID {cross[origin.number]} "\
                            "SE ENCUENTRAN AUN EN ESTADO CONTABILIZADO"
                        logs[origin.number] = msg
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
                            Invoice.save([origin])
                            if amount == _ZERO:
                                Reconciliation.delete(reconciliations)
                                MoveLine.reconcile(all_lines)
                        else:
                            msg = f"LA FACTURA CON ID {origin} TIENE UN PAGO MAYOR "\
                                f"POR LA(S) FACTURA(S) CRUCE {cross[origin.number]}"
                            logs[origin.number] = msg
                except Exception as error:
                    logs[cross[origin.number]
                        [0].number] = f'EXCEPCION: {error}'
                    Transaction().rollback()
                    print(f"ROLLBACK-{import_name}: {error}")
            actualizacion.add_logs(logs)
            print(f'---------------FINISH {import_name}---------------')
        except Exception as error:
            Transaction().rollback()
            print(f"ROLLBACK-{import_name}: {error}")
            logs["EXCEPCION"] = error
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
                    if line.reconciliation and line.reconciliation.id not in to_delete[
                            'reconciliation']:
                        to_delete['reconciliation'].append(
                            line.reconciliation.id)
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

    # Función encargada de eliminar y marcar para importar ventas de importadas de TecnoCarnes
    @classmethod
    def delete_imported_notes(cls, invoices):
        Cnxn = Pool().get('conector.configuration')
        ids_tecno, to_delete = cls._get_delete_invoices(invoices)
        cls._delete_invoices(to_delete)
        for idt in ids_tecno:
            Cnxn.update_exportado(idt, 'N')

    @classmethod
    def _post(cls, invoices):
        pool = Pool()
        Move = pool.get('account.move')
        reconciled: list = []
        moves: list = []

        cls.set_number(invoices)
        for invoice in invoices:
            move = invoice.get_move()
            if move != invoice.move:
                if invoice.type == 'out':
                    move = cls.configure_party(invoice, move)
                invoice.move = move
                moves.append(move)
        if moves:
            Move.save(moves)
        for invoice in invoices:
            if invoice.reconciled:
                reconciled.append(invoice)
            if invoice.state != 'posted':
                invoice.state = 'posted'
        cls.save(invoices)
        Move.post([i.move for i in invoices if i.move.state != 'posted'])
        if reconciled:
            cls.__queue__.process(reconciled)

        for invoice in invoices:
            if invoice.type == 'in' and invoice.state != 'posted':
                cls.process_pruchases(invoice)

    @classmethod
    def process_pruchases(cls, invoice):
        """ Function to process purchase from invoice type in
            after post it invoice
        """
        pool = Pool()
        Purchase = pool.get('purchase.purchase')
        for line in invoice.lines:
            origin = line.origin if line.origin else None
            if origin:
                purchases = [origin.purchase]
                Purchase.process(purchases)

    @classmethod
    def configure_party(cls, invoice, move):
        """Function to change party if invoice type out
        in the move lines

        Args:
            move (object): account_move model
            invoice (object): account_invoice model
        """
        for lines in invoice.lines:
            if hasattr(lines, 'account') and hasattr(lines, 'product'):
                product = lines.product
                account_code = lines.account.code
                if product.account_cogs_used and product.account_stock_in_used:
                    account_cogs_used = product.account_cogs_used.code
                    account_stock_in_used = product.account_stock_in_used.code

                    if account_cogs_used and account_stock_in_used:
                        for lines_ in move.lines:
                            if lines_.account.code != account_code:
                                if lines_.account.code == account_cogs_used or\
                                        lines_.account.code == account_stock_in_used:
                                    lines_.party = invoice.company.party
        return move


class InvoiceLine(metaclass=PoolMeta):
    __name__ = 'account.invoice.line'

    @classmethod
    def __setup__(cls):
        super(InvoiceLine, cls).__setup__()

    def _get_latin_move_lines(self, amount, type_, account_stock_method):
        result = super(InvoiceLine,
                       self)._get_latin_move_lines(amount, type_,
                                                   account_stock_method)
        if self.invoice.id_tecno:
            id_tecno = self.invoice.id_tecno.split('-')
            if id_tecno[0] in _SW:
                return []
        return result

    @classmethod
    def trigger_create(cls, records):
        """Inheritance function from account_col"""

        for line in records:
            try:
                if line.type != 'line':
                    continue
                if line.product and line.product.account_category and line.quantity < 0:
                    category = line.product.account_category
                    account_id = None
                    if line.invoice.type == 'in':
                        """
                        Se añade validación para agregar la cuenta de devolución de compra
                        solamente a los productos de tipo servicio
                        """
                        if category.account_return_purchase and line.product.type == 'service':
                            account_id = category.account_return_purchase.id

                    if not account_id:
                        continue
                    line.write([line], {'account': account_id})
            except Exception as error:
                print(f'ERROR TRIGGER CREATE: {error}')

    def get_move_lines(self):
        """Inheritance function to add analytic lines to move lines"""
        lines = super(InvoiceLine, self).get_move_lines()
        analytic_account = None
        for line in lines:
            if hasattr(line, 'analytic_lines'):
                if line.analytic_lines:
                    analytic_account = line.analytic_lines[0].account
                    break

        if analytic_account:
            for line in lines:
                analytic_required = line.account.analytical_management
                if analytic_required and not hasattr(line, 'analytic_lines'):
                    line = self.build_analytic_lines(line, analytic_account)
        return lines

    def build_analytic_lines(self, line, analytic_account):
        '''
        Build the analytic lines for account move line
        '''
        pool = Pool()
        AnalyticLines = pool.get('analytic_account.line')
        analytic_line = AnalyticLines()
        analytic_line.debit = Decimal(line.debit)
        analytic_line.credit = Decimal(line.credit)
        analytic_line.account = analytic_account
        analytic_line.date = self.invoice.invoice_date
        line.analytic_lines = [analytic_line]
        return line


class UpdateInvoiceTecnoStart(ModelView):
    'Delete Invoice Tecno Start'
    __name__ = 'delete.invoice.wizard.start'
    user = fields.Many2One('res.user', 'User', readonly=True)
    validate = fields.Boolean('Validate',
                              readonly=True,
                              on_change_with='on_change_with_validate')

    @staticmethod
    def default_user():
        return Transaction().user

    @fields.depends('user')
    def on_change_with_validate(self):
        pool = Pool()
        user_permission = pool.get('conector.permissions')
        permission = pool.get('res.user-ir.action.wizard')
        action = user_permission.search([('user_permission', '=',
                                        Transaction().user)])
        action = [i.id for i in action]
        validated = permission.search([
            ('user_permission', 'in', action),
            ('wizard.wiz_name', '=', 'account.invoice.update_invoice_tecno'),
        ])
        if validated:
            return True
        return False


class UpdateInvoiceTecno(Wizard):
    'Update Invoice Tecno'
    __name__ = 'account.invoice.update_invoice_tecno'

    start = StateView(
        'delete.invoice.wizard.start',
        'conector.validated_identity_invoice_view_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Confirm', 'do_submit', 'tryton-ok', default=True),
        ])

    do_submit = StateTransition()

    def transition_do_submit(self):
        pool = Pool()
        Actualizacion = pool.get('conector.actualizacion')
        actualizacion = Actualizacion.create_or_update('ACCIONES')
        Dunning = pool.get('account.dunning')
        logs = {}
        exceptions = []
        log_delete_note = []
        log_delete_purchase = []
        log_delete_sale = []
        if self.start.validate:
            Invoice = pool.get('account.invoice')
            Sale = pool.get('sale.sale')
            Purchase = pool.get('purchase.purchase')
            Reclamacion = pool.get('account.dunning')
            Mails = pool.get('account.dunning.email.log')

            ids = Transaction().context['active_ids']
            cursor = Transaction().connection.cursor()
            to_delete_sales = []
            to_delete_purchases = []
            to_delete_note = []
            print('Eliminando y reimportando')
            for invoice in Invoice.browse(ids):

                id_tecno = invoice.id_tecno or invoice.reference

                if invoice.move:
                    if invoice.move.period.state == 'close':
                        exceptions.append(id_tecno)
                        logs[
                            id_tecno] = "EXCEPCION: EL PERIODO DEL DOCUMENTO SE ENCUENTRA CERRADO \
                        Y NO ES POSIBLE SU ELIMINACION O MODIFICACION"

                        continue

                reclamacion = Reclamacion.search([('line.move.origin', '=',
                                                 invoice)])
                rec_name = invoice.rec_name
                party_name = invoice.party.name
                rec_party = rec_name + ' de ' + party_name
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
                        purchase = Purchase.search([('number', '=',
                                                   invoice.number)])
                        if purchase:
                            to_delete_purchases.append(purchase[0])

                    if reclamacion:
                        dunningTable = Dunning.__table__()
                        emails_delete = Mails.search([('dunning', 'in',
                                                     reclamacion)])
                        if emails_delete:
                            Mails.delete(emails_delete)

                        if reclamacion[0].state != 'draft':
                            cursor.execute(*dunningTable.update(
                                columns=[
                                    dunningTable.state,
                                ],
                                values=["draft"],
                                where=dunningTable.id == reclamacion[0].id))

                        cursor.execute(*dunningTable.delete(
                            where=dunningTable.id == reclamacion[0].id))

                else:
                    raise UserError(
                        "Revisa el número de la factura (tipo-numero): ",
                        rec_party)
            print('llegamos aqui')
            if to_delete_sales:
                Sale.delete_imported_sales(to_delete_sales)
                log_delete_sale = [i.number for i in to_delete_sales]
            if to_delete_purchases:
                Purchase.delete_imported_purchases(to_delete_purchases)
                log_delete_purchase = [i.number for i in to_delete_purchases]
            if to_delete_note:
                Invoice.delete_imported_notes(to_delete_note)
                log_delete_note = [i.number for i in to_delete_note]
            print('llegamos aqui2')
            if exceptions:
                actualizacion.add_logs(logs)
                return 'end'
            logs[
                self.start.user.
                name] = f"El usuario {self.start.user.name}, realizo la accion de eliminar y reimportar facturas \
            eliminando los siguientes documentos \
            ventas:{log_delete_sale},\
            compras:{log_delete_purchase},\
            notas:{log_delete_note}"
            print('llegamos aqui2.1')
            actualizacion.add_logs(logs)
            print('llegamos aqui2.2')
            return 'end'

        print('llegamos aqui3')
        logs[self.start.user.name] = f"El usuario {self.start.user.name}, \
        intento ejecutar el asistente de eliminar y reimportar facturas \
        para el cual, no cuenta con los permisos requeridos"

        print('llegamos aqui4')
        actualizacion.add_logs(logs)
        print('llegamos aqui5')
        raise UserError(
            f"EL usuario {self.start.user.name}, no cuenta con los permisos para realizar esta accion"
        )

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
        Actualizacion = pool.get('conector.actualizacion')
        logs = {}
        exceptions = []
        actualizacion = Actualizacion.create_or_update(
            'CAMBIO DE FECHA DE ASIENTO DE FACTURAS')

        warning_name = 'warning_udate_note_%s' % ids
        if Warning.check(warning_name):
            raise UserWarning(
                warning_name,
                "Se va a actualizar las fechas de los anticipos cruzados con respecto a la fecha de la factura."
            )

        for invoice in Invoice.browse(ids):
            if invoice.move.period.state == 'close':
                exceptions.append(invoice.id_tecno)
                logs[
                    invoice.
                    id_tecno] = "EXCEPCION: EL PERIODO DEL DOCUMENTO SE ENCUENTRA CERRADO \
                Y NO ES POSIBLE SU ELIMINACION O MODIFICACION"

                continue
            rec_name = invoice.rec_name
            party_name = invoice.party.name
            rec_party = rec_name + ' de ' + party_name
            if invoice.state == 'posted' or invoice.state == 'paid':
                movelines = invoice.reconciliation_lines or invoice.payment_lines
                if movelines:
                    for line in movelines:
                        if line.move_origin and hasattr(
                                line.move_origin, '__name__'
                        ) and line.move_origin.__name__ == 'account.note':
                            cursor.execute(*move_table.update(
                                columns=[
                                    move_table.date, move_table.post_date,
                                    move_table.period
                                ],
                                values=[
                                    invoice.invoice_date, invoice.invoice_date,
                                    invoice.move.period.id
                                ],
                                where=move_table.id == line.move.id))
                            cursor.execute(*note_table.update(
                                columns=[note_table.date],
                                values=[invoice.invoice_date],
                                where=note_table.id == line.move_origin.id))
            else:
                raise UserError(
                    "La factura debe estar en estado contabilizada o pagada.",
                    rec_party)
        if exceptions:
            actualizacion.add_logs(logs)
            raise UserError(
                f"Los documentos {exceptions} no pueden ser eliminados porque su periodo se encuentra cerrado"
            )
        return 'end'


class CreditInvoice(metaclass=PoolMeta):
    'Credit Invoice Note Wizard'
    __name__ = 'account.invoice.credit'

    def default_start(self, fields):
        default = {
            'with_refund': True,
            'with_refund_allowed': True,
        }
        for invoice in self.records:
            print("verificando estado")
            if invoice.state == 'paid':
                raise UserError(
                    'AVISO', 'La factura se encuentra pagada y'
                    ' no se puede agregar una nota credito')

            if invoice.state != 'posted' or invoice.type == 'in':
                default['with_refund'] = False
                default['with_refund_allowed'] = False
                break

            if invoice.payment_lines:
                default['with_refund'] = False

        return default


class AdvancePayment(metaclass=PoolMeta):
    'Advance Payment Wizard'
    __name__ = 'account.invoice.advance_payment'

    def transition_add_link(self):
        pool = Pool()
        Note = pool.get('account.note')
        Invoice = pool.get('account.invoice')
        MoveLine = pool.get('account.move.line')
        invoice = Invoice(Transaction().context.get('active_id'))
        Config = pool.get('account.voucher_configuration')
        config = Config.get_configuration()

        if not self.start.lines:
            return 'end'

        if not config.default_journal_note:
            raise UserError(
                gettext('account_voucher.msg_missing_journal_note'))

        lines_to_create = []
        reconcile_advance = []
        reconcile_invoice = []

        # recon: reconciliation
        do_recon_invoice = False
        do_recon_advance = False

        balance, lines_advance_recon = self.start.get_balance()

        def _set_to_reconcile():
            res = []
            for mline in invoice.move.lines:
                if mline.account.id == invoice.account.id:
                    res.append(mline)

            for pl in invoice.payment_lines:
                if not pl.reconciliation:
                    res.append(pl)
            return res

        # Find previous cross payments
        line_advance = self.start.lines[0]

        previous_discounts = self.start.get_previous_cross_moves()
        # previous_discounts = invoice.payment_lines
        sum_last_advances = sum([abs(l.credit - l.debit)
                                for l in previous_discounts])
        sum_start_advances = sum(
            [abs(line.debit - line.credit) for line in self.start.lines]
        )

        amount_balance = sum_start_advances - sum_last_advances
        ignore_previous_discounts = False
        if amount_balance < 0:
            amount_balance = sum_start_advances
            ignore_previous_discounts = True
        if amount_balance > invoice.amount_to_pay:
            do_recon_invoice = True
            credit = 0
            debit = 0
            if invoice.type == 'in':
                credit = invoice.amount_to_pay
            else:
                debit = invoice.amount_to_pay
            lines_to_create.append({
                'debit': debit,
                'credit': credit,
                'party': line_advance.party.id,
                'account': line_advance.account.id,
                'description': line_advance.description,
                'move_line': line_advance,
            })
            lines_to_create.append({
                'debit': credit,
                'credit': debit,
                'party': line_advance.party.id,
                'account': invoice.account.id,
                'description': invoice.description,
            })
        else:
            sum_debit = 0
            sum_credit = 0
            do_recon_advance = True

            # Cofigure reconciliation
            if not ignore_previous_discounts:
                move_lines_ad = MoveLine.search([
                    ('origin', 'in', ['account.note.line,' + str(l.id)
                     for l in previous_discounts])
                ])
                reconcile_advance.extend(move_lines_ad)
            for line in self.start.lines:
                reconcile_advance.append(line)
            if invoice.type == 'in':
                sum_credit = abs(amount_balance)
            else:
                sum_debit = abs(amount_balance)

            lines_to_create.append({
                'debit': sum_debit,
                'credit': sum_credit,
                'party': line_advance.party.id,
                'account': line_advance.account.id,
                'description': line_advance.description,
                'move_line': line_advance,
            })

            pending_advance = abs(sum_debit - sum_credit)
            if pending_advance == invoice.amount_to_pay:
                do_recon_invoice = True

            lines_to_create.append({
                'debit': sum_credit,
                'credit': sum_debit,
                'party': invoice.party.id,
                'account': invoice.account.id,
                'description': invoice.description,
            })

        if hasattr(line_advance, 'operation_center'):
            operation_center = line_advance.operation_center.id
            for l in lines_to_create:
                l['operation_center'] = operation_center

        if invoice.type == 'in':
            description = f"ANTICIPO FACTURA PROVEEDOR-{invoice.reference}"
        else:
            description = f"ANTICIPO FACTURA CLIENTE-{invoice.reference}"

        note, = Note.create([{
            'description': description,
            'journal': config.default_journal_note.id,
            'date': date.today(),
            'state': 'draft',
            'lines': [('create', lines_to_create)],
        }])
        Note.post([note])
        note.save()

        payment_lines = []
        adv_accounts_ids = [l.account.id for l in reconcile_advance]

        if do_recon_invoice:
            reconcile_invoice = _set_to_reconcile()

        for nm_line in note.move.lines:
            if do_recon_advance and nm_line.account.id in adv_accounts_ids:
                reconcile_advance.append(nm_line)

            if nm_line.account.id == invoice.account.id:
                payment_lines.append(nm_line)
                if do_recon_invoice:
                    reconcile_invoice.append(nm_line)

        Invoice.write([invoice], {
            'payment_lines': [('add', payment_lines)],
        })
        reconcile_advance = [
            r for r in reconcile_advance if not r.reconciliation]

        if [r for r in reconcile_advance if not r.reconciliation]:
            MoveLine.reconcile(reconcile_advance)

        pending_to_pay = sum(
            [ri.debit - ri.credit for ri in reconcile_invoice])
        if reconcile_invoice and not pending_to_pay:
            MoveLine.reconcile(reconcile_invoice)
        return 'end'


class InvoicesReport(metaclass=PoolMeta):
    'Invoices Report'
    __name__ = 'invoice_report.invoices_report'

    @classmethod
    def get_record(cls, invoice):
        invoice = {
            'date': invoice.invoice_date,
            'reference': invoice.reference,
            'payment_term': invoice.payment_term,
            'number': invoice.number,
            'party': invoice.party.rec_name,
            'id_number': invoice.party.id_number,
            'description': invoice.description,
            'iva': 0,
            'ret': 0,
            'ica': 0,
            'ic': 0,
            'untaxed_amount': 0,
            'taxed_amount': 0,
            'total_amount': invoice.total_amount,
            'state': invoice.state_string
        }
        return invoice
