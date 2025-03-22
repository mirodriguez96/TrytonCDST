import calendar
import copy
import mimetypes
from datetime import date, timedelta
from decimal import Decimal
from email.encoders import encode_base64
from email.header import Header
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.nonmultipart import MIMENonMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, getaddresses
from itertools import chain
from operator import attrgetter

from dateutil import tz
from dateutil.relativedelta import relativedelta
from sql.aggregate import Sum
from sql.operators import Between
from trytond.exceptions import UserError, UserWarning
from trytond.model import ModelSQL, ModelView, fields, Workflow
from trytond.modules.company import CompanyReport
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Bool, Eval, If, Not, Or
from trytond.report import Report
from trytond.sendmail import sendmail
from trytond.transaction import Transaction
from trytond.wizard import (Button, StateReport, StateTransition, StateView,
                            Wizard)


from .constants import EXTRAS, FIELDS_AMOUNT, SHEET_SUMABLES
from .it_supplier_noova import ElectronicPayrollCdst


def ultimo_dia_del_mes(year, month):
    return calendar.monthrange(year, month)[1]


from_zone = tz.gettz('UTC')
to_zone = tz.gettz('America/Bogota')

CONCEPT_ACCESS = {
    'HED': 'hedo',
    'HEN': 'heno',
    'HRN': 'hedf',
    'HEDDF': 'recf',
    'HENDF': 'henf',
    'HRDDF': 'reco',
    'HRNDF': 'dom',
}


TYPE_CONCEPT_ELECTRONIC = [
    ('', ''),
    ('Basico', 'Basico'),
    ('AuxilioTransporte', 'Auxilio Transporte'),
    ('ViaticoManuAlojS', 'Viatico Manu Aloj S'),
    ('ViaticoManuAlojNS', 'Viatico Manu Aloj NS'),
    ('HED', 'HORA EXTRA DIURNA'),
    ('HEN', 'HORA EXTRA NOCTURNA'),
    ('HRN', 'HORA RECARGO NOCTURNO'),
    ('HEDDF', 'HORA EXTRA DIURNA DOMINICAL Y FESTIVOS'),
    ('HRDDF', 'HORA RECARGO DIURNO DOMINICAL Y FESTIVOS'),
    ('HENDF', 'HORA EXTRA NOCTURNA DOMINICAL Y FESTIVOS'),
    ('HRNDF', 'HORA RECARGO NOCTURNO DOMINICAL Y FESTIVOS'),
    ('VacacionesComunes', 'Vacaciones Comunes'),
    ('VacacionesCompensadas', 'Vacaciones Compensadas'),
    ('PrimasS', 'Primas S'),
    ('PrimasNS', 'Primas NS'),
    ('Cesantias', 'Cesantias'),
    ('IntCesantias', 'Int Cesantias'),
    ('IncapacidadComun', 'Incapacidad Comun'),
    ('IncapacidadProfesional', 'Incapacidad Profesional'),
    ('IncapacidadLaboral', 'Incapacidad Laboral'),
    ('LicenciaMP', 'Licencia MP'),
    ('LicenciaR', 'Licencia R'),
    ('LicenciaNR', 'Licencia NR'),
    ('BonificacionS', 'Bonificacion S'),
    ('BonificacionNS', 'Bonificacion NS'),
    ('AuxilioS', 'Auxilio S'),
    ('AuxilioNS', 'Auxilio NS'),
    ('HuelgaLegal', 'Huelga Legal'),
    ('ConceptoS', 'Otro Concepto S'),
    ('ConceptoNS', 'Otro Concepto NS'),
    ('CompensacionO', 'Compensacion O'),
    ('CompensacionE', 'Compensacion E'),
    ('PagoS', 'Bono EPCTV S'),
    ('PagoNS', 'Bono EPCTV NS'),
    ('PagoAlimentacionS', 'Pago Alimentacion S'),
    ('PagoAlimentacionN', 'Pago Alimentacion NS'),
    ('Comision', 'Comision'),
    ('PagoTercero', 'Pago Tercero'),
    ('Anticipo', 'Anticipo'),
    ('Dotacion', 'Dotacion'),
    ('ApoyoSost', 'Apoyo Sost'),
    ('Teletrabajo', 'Teletrabajo'),
    ('BonifRetiro', 'BonifRetiro'),
    ('Indemnizacion', 'Indemnizacion'),
    ('Reintegro', 'Reintegro'),
    ('Salud', 'Salud'),
    ('FondoPension', 'Fondo Pension'),
    ('FondoSP', 'Fondo SP'),
    ('FondoSPSUB', 'Fondo SP SUB'),
    ('Sindicato', 'Sindicato'),
    ('SancionPublic', 'Sancion Public'),
    ('SancionPriv', 'Sancion Priv'),
    ('Libranza', 'Libranza'),
    ('OtraDeduccion', 'Otra Deduccion'),
    ('PensionVoluntaria', 'Pension Voluntaria'),
    ('RetencionFuente', 'Retencion Fuente'),
    ('AFC', 'AHORRO FOMENTO A LA CONSTRUCCION'),
    ('Cooperativa', 'Cooperativa'),
    ('EmbargoFiscal', 'Embargo Fiscal'),
    ('PlanComplementario', 'Plan Complementario'),
    ('Educacion', 'Educacion'),
    ('Reintegro', 'Re-integro'),
    ('Deuda', 'Deuda'),
]

EXTRAS_CORE = EXTRAS

EXTRAS = {
    'HED': {'code': 1, 'percentaje': '25.00'},
    'HEN': {'code': 2, 'percentaje': '75.00'},
    'HRN': {'code': 3, 'percentaje': '35.00'},
    'HEDDF': {'code': 4, 'percentaje': '100.00'},
    'HRDDF': {'code': 5, 'percentaje': '75.00'},
    'HENDF': {'code': 6, 'percentaje': '150.00'},
    'HRNDF': {'code': 7, 'percentaje': '110.00'},
}

_ZERO = Decimal('0.0')
RESTDAY_DEFAULT = 0
WEEK_DAYS = {
    1: 'monday',
    2: 'tuesday',
    3: 'wednesday',
    4: 'thursday',
    5: 'friday',
    6: 'saturday',
    7: 'sunday',
}

CONTRACT = [
    'bonus_service',
    'health',
    'retirement',
    'unemployment',
    'interest',
    'holidays',
    'convencional_bonus',
]

CONCEPT = ['health', 'retirement']

CONCEPT_ELECTRONIC = ['Libranza']

_TYPES_BANK_ACCOUNT_ = {
    'Cuenta de Ahorros': '37',
    'Cuenta Corriente': '27',
}

_TYPES_BANKS = {
    'Cuenta de Ahorros': 'S',
    'Cuenta Corriente': 'D',
}

MONTH = {
    '01': 'ENERO',
    '02': 'FEBRERO',
    '03': 'MARZO',
    '04': 'ABRIL',
    '05': 'MAYO',
    '06': 'JUNIO',
    '07': 'JULIO',
    '08': 'AGOSTO',
    '09': 'SEPTIEMBRE',
    '10': 'OCTUBRE',
    '11': 'NOVIEMBRE',
    '12': 'DICIEMBRE',
}

STATE = {
    'invisible': Not(Bool(Eval('access_register'))),
    'readonly': Bool(Eval('state') != 'draft'),
}


try:
    import html2text
except ImportError:
    html2text = None

HTML_EMAIL = '''<!DOCTYPE html>
<html>
<head><title>%(subject)s</title></head>
<body>%(body)s<br/>
<hr style='width: 2em; text-align: start; display: inline-block'/><br/>
%(signature)s</body>
</html>'''


def _get_emails(value):
    'Return list of email from the comma separated list'
    return [e for n, e in getaddresses([value]) if e]


_TYPES_PAYMENT = [
    ('220', '220'),
    ('225', '225'),
    ('238', '238'),
    ('240', '240'),
    ('239', '239'),
    ('320', '320'),
    ('325', '325'),
    ('820', '820'),
    ('920', '920'),
]

CONCEPT_ACCESS = {
    'HED': 'hedo',
    'HEN': 'heno',
    'HRN': 'hedf',
    'HEDDF': 'recf',
    'HENDF': 'henf',
    'HRDDF': 'reco',
    'HRNDF': 'recf',
}

EXTRAS = {
    'HED': {'code': 1, 'percentaje': '25.00'},
    'HEN': {'code': 2, 'percentaje': '75.00'},
    'HRN': {'code': 3, 'percentaje': '35.00'},
    'HEDDF': {'code': 4, 'percentaje': '100.00'},
    'HRDDF': {'code': 5, 'percentaje': '75.00'},
    'HENDF': {'code': 6, 'percentaje': '150.00'},
    'HRNDF': {'code': 7, 'percentaje': '110.00'},
}

_TYPE_DOCUMENT = {
    '13': '1',  # Cedula
    '22': '2',  # Cedula de extranjeria
    '31': '3',  # Nit
    '12': '4',  # Tarjeta de identidad
    '41': '5',  # Pasaporte
}

_TYPE_TRANSACTION = [
    ('25', 'Pago en efectivo'),
    ('27', 'Abono a cuenta corriente'),
    ('36', 'Pago cheque gerencia'),
    ('37', 'Abono a cuenta de ahorros'),
    ('40', 'Efectivo seguro (visa pagos o tarjeta prepago)'),
]


class StaffConfiguration(metaclass=PoolMeta):
    __name__ = 'staff.configuration'

    default_hour_biweekly = fields.Numeric(
        'Default Hour Biweekly', digits=(16, 2), required=True, help='In hours'
    )

    @classmethod
    def __setup__(cls):
        super(StaffConfiguration, cls).__setup__()
        cls.default_hour_workday = fields.Numeric(
            'Default Hour Workday', digits=(16, 2), required=True, help='In hours'
        )


class WageType(metaclass=PoolMeta):
    __name__ = 'staff.wage_type'
    non_working_days = fields.Boolean(
        'Non-working days', states={'invisible': (Eval('type_concept') != 'holidays')}
    )

    excluded_payroll_electronic = fields.Boolean(
        'Excluded Payroll', states={'invisible': (Eval('type_concept') != 'holidays')}
    )

    pay_liqudation = fields.Boolean(
        'Pay Liquidation',
        states={
            'invisible': (Eval('type_concept_electronic') not in ['Deuda', 'Libranza'])
        },
    )
    department = fields.Many2One('company.department', 'Department')


class PayrollPaymentStartBcl(ModelView):
    'Payroll Payment Start'
    __name__ = 'staff.payroll_payment_bancolombia.start'
    period = fields.Many2One('staff.payroll.period', 'Period', required=True)
    party = fields.Function(
        fields.Many2One('party.party', 'Party Bank'), 'on_change_with_party'
    )
    company = fields.Many2One('company.company', 'Company', required=True)
    department = fields.Many2One('company.department', 'Department')
    payment_type = fields.Selection(
        _TYPES_PAYMENT, 'Type payment', required=True)
    send_sequence = fields.Char('Shipping sequence', size=1)
    reference = fields.Char('Reference', required=True, size=9)
    type_transaction = fields.Selection(
        _TYPE_TRANSACTION, 'Type of transaction', required=True
    )
    bank = fields.Many2One(
        'bank.account',
        'Bank Account',
        domain=[('owners', '=', Eval('party'))],
        depends=['party'],
        required=True,
    )

    @fields.depends('company')
    def on_change_with_party(self, name=None):
        res = None
        if self.company:
            res = self.company.party.id
        return res

    @staticmethod
    def default_company():
        return Transaction().context.get('company')


# Asistente encargado de recoger la información de las nominas que se van a utilizar para el reporte
class PayrollPaymentBcl(Wizard):
    'Payroll Payment'
    __name__ = 'staff.payroll.payment_bancolombia'
    start = StateView(
        'staff.payroll_payment_bancolombia.start',
        'staff_payroll_cdst.payroll_payment_start_bancolombia_view_form',
        [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Print', 'print_', 'tryton-ok', default=True),
        ],
    )
    print_ = StateReport('staff.payroll.payment_report_bancolombia')

    def do_print_(self, action):
        pool = Pool()
        Type_bank_numbers = pool.get('bank.account.number')
        Payroll = pool.get('staff.payroll')
        clause = [('state', '=', 'posted')]
        if self.start.department:
            clause.append(('employee.department', '=', self.start.department))
        if self.start.period:
            clause.append(('period', '=', self.start.period))
        if self.start.send_sequence:
            send_sequence = (self.start.send_sequence).upper()
        else:
            send_sequence = 'A'
        # Se realiza la búsqueda de todas las nóminas que coincidan
        payrolls = Payroll.search(clause)
        result = []
        values = {}
        id_numbers = []
        nothin_accounts = ''
        duplicate_employees = None
        bank = self.start.bank.bank
        for payroll in payrolls:
            accouns_bank = list(payroll.employee.party.bank_accounts)
            if accouns_bank == []:
                nothin_accounts = (
                    nothin_accounts
                    + f'EL empleado {payroll.employee.party.name} no tiene una cuenta asociada  \n'
                )
                continue
            # for ref in accouns_bank:
            #     if bank == ref.bank:
            values = values.copy()
            values['employee'] = payroll.employee.party.name
            type_document = payroll.employee.party.type_document
            if type_document not in _TYPE_DOCUMENT:
                raise UserError(
                    'error: type_document',
                    f'{type_document} not found for type_document bancolombia',
                )
            values['type_document'] = _TYPE_DOCUMENT[type_document]
            values['id_number'] = (
                str(payroll.employee.party.number_pay_payroll)
                + str(payroll.employee.party.id_number)
                if type_document == '41'
                else payroll.employee.party.id_number
            )
            values['email'] = payroll.employee.party.email
            bank_code_sap = None
            if payroll.employee.party.bank_accounts:
                bank_code_sap = payroll.employee.party.bank_accounts[
                    0
                ].bank.bank_code_sap
            values['bank_code_sap'] = bank_code_sap
            values['bank_account'] = payroll.employee.party.bank_account
            type_account_payment_party = Type_bank_numbers.search(
                [('number', '=', str(payroll.employee.party.bank_account))]
            )
            values['type_account_payment'] = _TYPES_BANK_ACCOUNT_.get(
                type_account_payment_party[0].type_string
            )
            net_payment = Decimal(round(payroll.net_payment, 0))
            values['net_payment'] = net_payment
            if values['id_number'] in id_numbers:
                if not duplicate_employees:
                    duplicate_employees = values['employee']
                else:
                    duplicate_employees += ', ' + values['employee']
            id_numbers.append(values['id_number'])
            result.append(values)
            #     break
            # else:
            #     continue

            # Se valida si se encontraron nóminas del mismo empleado en el periodo seleccionado y se muestra una alerta.
        if duplicate_employees or nothin_accounts:
            Warning = pool.get('res.user.warning')
            warning_name = 'warning_payment_report_bancolombia'
            if duplicate_employees:
                duplicate_employees = (
                    'Existen empleados con más de 1 nómina en el mismo periodo. '
                    f'Revisar: {duplicate_employees}'
                )
            if Warning.check(warning_name):
                raise UserWarning(
                    warning_name, f'{duplicate_employees} \n {nothin_accounts}.'
                )

        # Se construye diccionario a retornar
        type_bank_account = _TYPES_BANKS.get(
            str(self.start.bank.numbers[0].type_string)
        )
        data = {
            'company': {
                'id_number': self.start.company.party.id_number,
                'name': self.start.company.party.name,
                'bank_account': self.start.bank.numbers[0].number,
            },
            'payment_type': self.start.payment_type,
            'send_sequence': send_sequence,
            'type_bank_account': type_bank_account,
            'reference': self.start.reference,
            'result': result,
        }
        return action, data

    def transition_print_(self):
        return 'end'


# Se genera un reporte con los campos necesarios para el envío de la nómina mediante la plataforma de Bancolombia
class PayrollPaymentReportBcl(Report):
    __name__ = 'staff.payroll.payment_report_bancolombia'

    @classmethod
    def get_context(cls, records, header, data):
        report_context = super().get_context(records, header, data)
        report_context['payment_type'] = data.get('payment_type')
        report_context['send_sequence'] = data.get('send_sequence')
        report_context['type_bank_account'] = data.get('type_bank_account')
        report_context['reference'] = data.get('reference')
        report_context['records'] = data.get('result')
        report_context['company'] = data.get('company')
        return report_context


class LiquidationPaymentStartBcl(ModelView):
    'Liquidation Payment Start'
    __name__ = 'staff.payroll_liquidation_payment_bancolombia.start'
    company = fields.Many2One('company.company', 'Company', required=True)
    party = fields.Function(
        fields.Many2One('party.party', 'Party Bank'), 'on_change_with_party'
    )
    department = fields.Many2One('company.department', 'Department')
    payment_type = fields.Selection(
        _TYPES_PAYMENT, 'Type payment', required=True)
    send_sequence = fields.Char('Send sequence', size=1)
    # type_bank_account = fields.Selection(
    #     _TYPES_BANK_ACCOUNT, 'Type of account to be debited', required=True)
    reference = fields.Char('Reference', required=True, size=9)
    type_transaction = fields.Selection(
        _TYPE_TRANSACTION, 'Type of transaction', required=True
    )
    kind = fields.Selection(
        [
            ('contract', 'Contract'),
            ('bonus_service', 'Bonus Service'),
            ('interest', 'Interest'),
            ('unemployment', 'Unemployment'),
            ('holidays', 'Vacation'),
            ('convencional_bonus', 'Convencional Bonus'),
        ],
        'Kind',
        required=True,
    )
    date = fields.Date('Date', required=True)
    bank = fields.Many2One(
        'bank.account',
        'Bank Account',
        domain=[('owners', '=', Eval('party'))],
        depends=['party'],
        required=True,
    )

    @staticmethod
    def default_company():
        return Transaction().context.get('company')

    @staticmethod
    def default_kind():
        return 'contract'

    @fields.depends('company')
    def on_change_with_party(self, name=None):
        res = None
        if self.company:
            res = self.company.party.id
        return res


# Asistente encargado de recoger la información de las liquidaciones que se van a utilizar para el reporte
class LiquidationPaymentBcl(Wizard):
    'Liquidation Payment'
    __name__ = 'staff.payroll.liquidation_payment'
    start = StateView(
        'staff.payroll_liquidation_payment_bancolombia.start',
        'staff_payroll_cdst.payment_liquidation_start_bancolombia_view_form',
        [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Print', 'print_', 'tryton-ok', default=True),
        ],
    )
    print_ = StateReport('staff.payroll_payment_liq_report_bancolombia')

    def do_print_(self, action):
        date = None
        department_id = None
        if self.start.department:
            department_id = self.start.department.id
        if self.start.date:
            date = self.start.date
        if self.start.send_sequence:
            send_sequence = (self.start.send_sequence).upper()
        else:
            send_sequence = 'A'
        data = {
            'ids': [],
            'company': self.start.company.id,
            'liquidation_date': date,
            'department': department_id,
            'payment_type': self.start.payment_type,
            'send_sequence': send_sequence,
            # 'type_bank_account': self.start.type_bank_account,
            'reference': self.start.reference,
            'kind': self.start.kind,
            'type_bank': self.start.bank.numbers[0].type_string,
            'banc_account': self.start.bank.numbers[0].number,
        }
        return action, data

    def transition_print_(self):
        return 'end'


# Se genera un reporte con los campos necesarios para el envío de liquidaciones mediante la plataforma de Bancolombia
class LiquidationPaymentReportBcl(Report):
    __name__ = 'staff.payroll_payment_liq_report_bancolombia'

    @classmethod
    def get_context(cls, records, header, data):
        report_context = super().get_context(records, header, data)
        pool = Pool()
        Type_bank_numbers = pool.get('bank.account.number')
        user = pool.get('res.user')(Transaction().user)
        Liquidation = pool.get('staff.liquidation')
        clause = [('state', '=', 'posted')]
        if data['liquidation_date']:
            clause.append(('liquidation_date', '=', data['liquidation_date']))
        if data['department']:
            clause.append(('employee.department', '=', data['department']))
        if data['kind']:
            clause.append(('kind', '=', data['kind']))
        liquidations = Liquidation.search(clause)
        new_objects = []
        values = {}
        for liquidation in liquidations:
            values = values.copy()
            values['employee'] = liquidation.employee.party.name
            values['email'] = liquidation.employee.party.email
            type_document = liquidation.employee.party.type_document
            values['type_document'] = _TYPE_DOCUMENT[type_document]
            values['id_number'] = liquidation.employee.party.id_number
            bank_code_sap = None
            if liquidation.employee.party.bank_accounts:
                bank_code_sap = liquidation.employee.party.bank_accounts[
                    0
                ].bank.bank_code_sap
            values['bank_code_sap'] = bank_code_sap
            type_account_payment_party = Type_bank_numbers.search(
                [('number', '=', str(liquidation.employee.party.bank_account))]
            )
            values['type_account_payment'] = _TYPES_BANK_ACCOUNT_.get(
                type_account_payment_party[0].type_string
            )
            values['bank_account'] = liquidation.employee.party.bank_account
            net_payment = Decimal(round(liquidation.net_payment, 0))
            values['net_payment'] = net_payment
            new_objects.append(values)

        type_bank_account = _TYPES_BANKS.get(str(data.get('type_bank')))

        report_context['payment_type'] = data.get('payment_type')
        report_context['send_sequence'] = data.get('send_sequence')
        report_context['reference'] = data.get('reference')
        report_context['type_transaction'] = type_bank_account
        report_context['bank_account'] = data.get('banc_account')
        report_context['records'] = new_objects
        report_context['company'] = user.company
        return report_context


class PayslipSendStart(ModelView):
    'Payslip Send Start'
    __name__ = 'staff.payroll_payslip_send.start'
    company = fields.Many2One('company.company', 'Company', required=True)
    department = fields.Many2One('company.department', 'Department')
    period = fields.Many2One('staff.payroll.period',
                             'Start Period', required=True)
    subject = fields.Char('Subject', size=60, required=True)
    cc = fields.Char('Cc', help='separate emails with commas')

    @staticmethod
    def default_company():
        return Transaction().context.get('company')


# Asistente encargado de recolectar las nóminas y enviarlas por email
class PayslipSend(Wizard):
    'Payslip Send'
    __name__ = 'staff.payroll.payslip_send'
    start = StateView(
        'staff.payroll_payslip_send.start',
        'staff_payroll_cdst.payroll_payslip_send_view_form',
        [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Send', 'send_', 'tryton-ok', default=True),
        ],
    )
    send_ = StateTransition()

    def transition_send_(self):
        pool = Pool()
        model_name = 'staff.payroll'
        # Email = pool.get('ir.email')
        Payroll = pool.get(model_name)
        ActionReport = pool.get('ir.action.report')
        (report,) = ActionReport.search([('report_name', '=', model_name)])
        reports = [report.id]
        subject = self.start.subject
        dom = [
            ('company', '=', self.start.company.id),
            ('period', '=', self.start.period.id),
            ('state', 'in', ['processed', 'posted']),
            ('sended_mail', '=', False),
        ]
        if self.start.department:
            dom.append(('department', '=', self.start.department.id))
        payrolls = Payroll.search(dom)
        for payroll in payrolls:
            # email = 'clancheros@cdstecno.com'
            email = payroll.employee.party.email
            recipients_secondary = ''
            if self.start.cc:
                recipients_secondary = self.start.cc
            record = [model_name, payroll.id]
            try:
                send_mail(
                    to=email,
                    cc=recipients_secondary,
                    bcc='',
                    subject=subject,
                    body='___',
                    files=None,
                    record=record,
                    reports=reports,
                    attachments=None,
                )

                Payroll.write([payroll], {'sended_mail': True})
                Transaction().connection.commit()
            except Exception as e:
                raise UserError(
                    f'No mail sent, check employee email {payroll.employee.rec_name}',
                    str(e),
                )

        return 'end'


class SettlementSendStart(ModelView):
    'Settlement Send Start'
    __name__ = 'staff.payroll_settlement_send.start'
    company = fields.Many2One('company.company', 'Company', required=True)
    department = fields.Many2One('company.department', 'Department')
    date = fields.Date('Date', required=True)
    subject = fields.Char('Subject', size=60, required=True)
    cc = fields.Char('Cc', help='separate emails with commas')
    kind = fields.Selection(
        [
            ('contract', 'Contract'),
            ('bonus_service', 'Bonus Service'),
            ('interest', 'Interest'),
            ('unemployment', 'Unemployment'),
            ('holidays', 'Vacation'),
            ('convencional_bonus', 'Convencional Bonus'),
        ],
        'Kind',
        required=True,
    )

    @staticmethod
    def default_company():
        return Transaction().context.get('company')

    @staticmethod
    def default_kind():
        return 'contract'


class CertificateOfIncomeAndWithholdingSendStart(ModelView):
    'Certificate Send Start'
    __name__ = 'staff.payroll_certificates_send.start'
    company = fields.Many2One('company.company', 'Company', required=True)
    fiscalyear = fields.Many2One(
        'account.fiscalyear', 'Fiscal Year', required=True)
    subject = fields.Char('Subject', size=60, required=True)
    employees = fields.Many2Many(
        'company.employee', None, None, 'Employees', required=True
    )
    cc = fields.Char('Cc', help='separate emails with commas')

    @staticmethod
    def default_company():
        return Transaction().context.get('company')

    @staticmethod
    def default_fiscalyear():
        FiscalYear = Pool().get('account.fiscalyear')
        return FiscalYear.find(Transaction().context.get('company'), exception=False)


class SendCertificateOfIncomeAndWithholding(Wizard):
    'Certificate Send'
    __name__ = 'staff.payroll.certificates_send'
    start = StateView(
        'staff.payroll_certificates_send.start',
        'staff_payroll_cdst.payroll_certificates_send_view_form',
        [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Send', 'send_', 'tryton-ok', default=True),
        ],
    )
    send_ = StateTransition()

    def transition_send_(self):
        pool = Pool()
        model_name = 'company.employee'
        # Email = pool.get('ir.email')
        ActionReport = pool.get('ir.action.report')
        (report,) = ActionReport.search(
            [('report_name', '=', 'staff.payroll.income_withholdings_report')]
        )
        reports = [report.id]
        nameCompany = self.start.company.party.name
        Nit = self.start.company.party.id_number
        company = self.start.company.id
        start_date = self.start.fiscalyear.start_date
        end_date = self.start.fiscalyear.end_date
        year = self.start.fiscalyear.name
        subject = self.start.subject
        recipients_secondary = ''
        if self.start.cc:
            recipients_secondary = self.start.cc

        for employe in self.start.employees:
            body = f'''<html>
            <body>
            <h2>Certificado de Ingreso y Retención</h2>

            <p>Estimado(a) {employe.party.name}</p>

            <p>Adjunto encontrarás el certificado de ingreso y retención correspondiente al {year}.</p>

            <p>Atentamente,<br>
            {nameCompany} <br>
            {Nit}
            </p>
            </body>
            <p>________________________________________________________________________________________</p>
            <p><small>
            Estimado Usuario,
            <br><br>

            Respetamos tu privacidad y queremos asegurarte que cualquier información personal que proporciones será tratada de manera confidencial. Este correo electrónico y cualquier archivo adjunto son confidenciales y están destinados únicamente para el destinatario mencionado.<br>
            La información contenida en este correo electrónico es para uso exclusivo del destinatario y puede contener información privilegiada, confidencial o legalmente protegida. Si has recibido este correo electrónico por error, te pedimos que lo notifiques al remitente de inmediato y elimines cualquier copia del mensaje y los archivos adjuntos de tu sistema.<br>
            Ten en cuenta que la transmisión de información a través de Internet no es completamente segura. Aunque nos esforzamos por proteger tu información personal, no podemos garantizar la seguridad de los datos enviados por correo electrónico. Por lo tanto, te recomendamos que evites enviar información sensible a través de este medio.<br>
            Si tienes alguna duda o preocupación relacionada con la privacidad, no dudes en ponerte en contacto con nosotros. Apreciamos tu confianza y estamos comprometidos en proteger tu privacidad y seguridad.
            <br><br>

            Atentamente,
            <br>
            {nameCompany}
            <br>
            {Nit}
            </small></p>

            </html>'''

            dic = {
                'ids': [],
                'company': company,
                'start_period': start_date,
                'end_period': end_date,
                'employees': [employe.id],
                'action_id': reports[0],
            }

            email = employe.party.email
            record = [model_name, employe]
            try:
                send_mail_certificate(
                    to=email,
                    cc=recipients_secondary,
                    bcc='',
                    subject=subject,
                    body=body,
                    files=None,
                    record=record,
                    reports=reports,
                    attachments=None,
                    dic=dic,
                )

            except Exception as e:
                raise UserError(
                    f'No mail sent, check employee email {employe.rec_name}', str(
                        e)
                )

        return 'end'


# Copia funcion 'send' del modelo 'ir.email' modificando para enviar de forma individual (no transactional) el envio de certificados de ingresos y retencion
def send_mail_certificate(
    to='',
    cc='',
    bcc='',
    subject='',
    body='',
    files=None,
    record=None,
    reports=None,
    attachments=None,
    dic=None,
):

    pool = Pool()
    ActionReport = pool.get('ir.action.report')
    ConfigEmail = pool.get('conector.email')
    Attachment = pool.get('ir.attachment')
    Email = pool.get('ir.email')
    User = pool.get('res.user')
    emails = ConfigEmail.search([])

    if not emails:
        raise UserError(
            'Error email: ', 'No se encontro informacion para envio de emails'
        )
    _email = emails[0]

    transaction = Transaction()
    Model = pool.get(record[0])
    records = Model(record[1])
    user = User(transaction.user)
    body_html = HTML_EMAIL % {
        'subject': subject,
        'body': body,
        'signature': user.signature or '',
    }
    content = MIMEMultipart('alternative')
    if html2text:
        body_text = HTML_EMAIL % {
            'subject': subject,
            'body': body,
            'signature': '',
        }
        converter = html2text.HTML2Text()
        body_text = converter.handle(body_text)
        if user.signature:
            body_text += '\n-- \n' + converter.handle(user.signature)
        part = MIMEText(body_text, 'plain', _charset='utf-8')
        content.attach(part)
    part = MIMEText(body_html, 'html', _charset='utf-8')
    content.attach(part)
    if files or reports or attachments:
        msg = MIMEMultipart('mixed')
        msg.attach(content)
        if files is None:
            files = []
        else:
            files = list(files)
        for report_id in reports or []:
            report = ActionReport(report_id)
            Report = pool.get(report.report_name, type='report')
            # dic['party_index'] = seq
            ext, content, _, title = Report.execute([record[1].id], dic)
            name = '%s.%s' % (title, ext)
            # get_number_sequence_certificate(seq)
            if isinstance(content, str):
                content = content.encode('utf-8')
            files.append((name, content))
        if attachments:
            files += [(a.name, a.data) for a in Attachment.browse(attachments)]
        for name, data in files:
            mimetype, _ = mimetypes.guess_type(name)
            if mimetype:
                attachment = MIMENonMultipart(*mimetype.split('/'))
                attachment.set_payload(data)
                encode_base64(attachment)
            else:
                attachment = MIMEApplication(data)
            attachment.add_header(
                'Content-Disposition', 'attachment', filename=('utf-8', '', name)
            )
            msg.attach(attachment)
    else:
        msg = content
    msg['From'] = from_ = _email.from_to
    if user.email:
        if user.name:
            user_email = formataddr((user.name, user.email))
        else:
            user_email = user.email
        msg['Behalf-Of'] = user_email
        msg['Reply-To'] = user_email
    msg['To'] = ', '.join(formataddr(a) for a in getaddresses([to]))
    msg['Cc'] = ', '.join(formataddr(a) for a in getaddresses([cc]))
    msg['Subject'] = Header(subject, 'utf-8')
    try:
        to_addrs = list(
            filter(
                None,
                map(str.strip, _get_emails(to)
                    + _get_emails(cc) + _get_emails(bcc)),
            )
        )
        sendmail(from_, to_addrs, msg, server=None, strict=True)
        email = Email(
            recipients=to,
            recipients_secondary=cc,
            recipients_hidden=bcc,
            addresses=[{'address': a} for a in to_addrs],
            subject=subject,
            body=body,
            resource=records,
        )
        email.save()
        with Transaction().set_context(_check_access=False):
            attachments_ = []
            for name, data in files:
                attachments_.append(Attachment(
                    resource=email, name=name, data=data))
            Attachment.save(attachments_)

        return email
    except Exception as error:
        raise UserError('Error envio: ', error)


# Asistente encargado de recolectar las nóminas y enviarlas por email
class SettlementSend(Wizard):
    'Settlement Send'
    __name__ = 'staff.payroll.settlement_send'
    start = StateView(
        'staff.payroll_settlement_send.start',
        'staff_payroll_cdst.payroll_settlement_send_view_form',
        [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Send', 'send_', 'tryton-ok', default=True),
        ],
    )
    send_ = StateTransition()

    def transition_send_(self):
        pool = Pool()
        model_name = 'staff.liquidation.report'
        Liquidation = pool.get('staff.liquidation')
        ActionReport = pool.get('ir.action.report')
        (report,) = ActionReport.search([('report_name', '=', model_name)])
        reports = [report.id]
        subject = self.start.subject
        print(self.start.kind)
        dom = [
            ('company', '=', self.start.company.id),
            ('liquidation_date', '=', self.start.date),
            ('kind', '=', self.start.kind),
            ('sended_mail', '=', False),
        ]
        if self.start.department:
            dom.append(('department', '=', self.start.department.id))
        liquidations = Liquidation.search(dom)

        for liquidation in liquidations:
            if liquidation.state == 'confirmed' or liquidation.state == 'posted':
                # email = 'gisela.sanchez@cdstecno.com'
                # email = 'andres.genes@cdstecno.com'
                email = liquidation.employee.party.email
                recipients_secondary = ''
                if self.start.cc:
                    recipients_secondary = self.start.cc
                record = ['staff.liquidation', liquidation.id]
                try:
                    send_mail(
                        to=email,
                        cc=recipients_secondary,
                        bcc='',
                        subject=subject,
                        body='___',
                        files=None,
                        record=record,
                        reports=reports,
                        attachments=None,
                    )
                    Liquidation.write([liquidation], {'sended_mail': True})
                    Transaction().connection.commit()
                except Exception as e:
                    raise UserError(
                        f'No mail sent, check employee email {liquidation.employee.rec_name}',
                        str(e),
                    )
            else:
                pass
        return 'end'


# Copia funcion 'send' del modelo 'ir.email' modificando para enviar de forma individual (no transactional)
def send_mail(
    to='',
    cc='',
    bcc='',
    subject='',
    body='',
    files=None,
    record=None,
    reports=None,
    attachments=None,
):
    pool = Pool()
    Email = pool.get('ir.email')
    User = pool.get('res.user')
    ActionReport = pool.get('ir.action.report')
    Attachment = pool.get('ir.attachment')
    ConfigEmail = pool.get('conector.email')
    emails = ConfigEmail.search([])

    if not emails:
        raise UserError(
            'Error email: ', 'No se encontro informacion para envio de emails'
        )
    _email = emails[0]

    transaction = Transaction()
    user = User(transaction.user)
    Model = pool.get(record[0])
    record = Model(record[1])
    body_html = HTML_EMAIL % {
        'subject': subject,
        'body': body,
        'signature': user.signature or '',
    }
    content = MIMEMultipart('alternative')
    if html2text:
        body_text = HTML_EMAIL % {
            'subject': subject,
            'body': body,
            'signature': '',
        }
        converter = html2text.HTML2Text()
        body_text = converter.handle(body_text)
        if user.signature:
            body_text += '\n-- \n' + converter.handle(user.signature)
        part = MIMEText(body_text, 'plain', _charset='utf-8')
        content.attach(part)
    part = MIMEText(body_html, 'html', _charset='utf-8')
    content.attach(part)
    if files or reports or attachments:
        msg = MIMEMultipart('mixed')
        msg.attach(content)
        if files is None:
            files = []
        else:
            files = list(files)
        for report_id in reports or []:
            report = ActionReport(report_id)
            Report = pool.get(report.report_name, type='report')
            ext, content, _, title = Report.execute(
                [record.id],
                {
                    'action_id': report.id,
                },
            )
            name = '%s.%s' % (title, ext)
            if isinstance(content, str):
                content = content.encode('utf-8')
            files.append((name, content))
        if attachments:
            files += [(a.name, a.data) for a in Attachment.browse(attachments)]
        for name, data in files:
            mimetype, _ = mimetypes.guess_type(name)
            if mimetype:
                attachment = MIMENonMultipart(*mimetype.split('/'))
                attachment.set_payload(data)
                encode_base64(attachment)
            else:
                attachment = MIMEApplication(data)
            attachment.add_header(
                'Content-Disposition', 'attachment', filename=('utf-8', '', name)
            )
            msg.attach(attachment)
    else:
        msg = content

    msg['From'] = from_ = _email.from_to
    if user.email:
        if user.name:
            user_email = formataddr((user.name, user.email))
        else:
            user_email = user.email
        msg['Behalf-Of'] = user_email
        msg['Reply-To'] = user_email
    msg['To'] = ', '.join(formataddr(a) for a in getaddresses([to]))
    msg['Cc'] = ', '.join(formataddr(a) for a in getaddresses([cc]))
    msg['Subject'] = Header(subject, 'utf-8')
    try:
        to_addrs = list(
            filter(
                None,
                map(str.strip, _get_emails(to)
                    + _get_emails(cc) + _get_emails(bcc)),
            )
        )
        sendmail(from_, to_addrs, msg, server=None, strict=True)
        email = Email(
            recipients=to,
            recipients_secondary=cc,
            recipients_hidden=bcc,
            addresses=[{'address': a} for a in to_addrs],
            subject=subject,
            body=body,
            resource=record,
        )
        email.save()
        with Transaction().set_context(_check_access=False):
            attachments_ = []
            for name, data in files:
                attachments_.append(Attachment(
                    resource=email, name=name, data=data))
            Attachment.save(attachments_)
        return email
    except Exception as error:
        raise UserError('Error envio: ', error)


class StaffEvent(metaclass=PoolMeta):
    __name__ = 'staff.event'
    analytic_account = fields.Char(
        'Analytic account code', states={'readonly': (Eval('state') != 'draft')}
    )

    edit_amount = fields.Boolean(
        'Edit Amount',
        states={
            'invisible': Not(Bool(Eval('absenteeism'))),
            'readonly': Bool(Eval('state') != 'draft'),
        },
        depends=['absenteeism', 'state'],
    )

    access_register = fields.Boolean(
        'Access register',
        states={
            'invisible': Not(Bool(Eval('absenteeism'))),
            'readonly': Bool(Eval('state') != 'draft'),
        },
        depends=['absenteeism', 'state'],
    )

    enter_timestamp = fields.DateTime(
        'Enter',
        states=STATE,
        domain=[
            If(
                Eval('exit_timestamp') & Eval('enter_timestamp'),
                ('enter_timestamp', '<=', Eval('exit_timestamp')),
                (),
            ),
        ],
        depends=['exit_timestamp', 'access_register', 'state'],
    )

    exit_timestamp = fields.DateTime(
        'Exit',
        states=STATE,
        domain=[
            If(
                Eval('enter_timestamp') & Eval('exit_timestamp'),
                ('exit_timestamp', '>=', Eval('enter_timestamp')),
                (),
            ),
        ],
        depends=['enter_timestamp', 'access_register', 'state'],
    )

    @classmethod
    def __setup__(cls):
        super(StaffEvent, cls).__setup__()
        cls._buttons.update(
            {
                'create_liquidation': {
                    'invisible': Or(
                        Eval('state') != 'done',
                        Not(Eval('is_vacations')),
                    ),
                }
            }
        )

    # @fields.depends('employee', 'contract')
    def on_change_employee(self):
        super(StaffEvent, self).on_change_employee()
        MandatoryWage = Pool().get('staff.payroll.mandatory_wage')
        if not hasattr(MandatoryWage, 'analytic_account'):
            return
        analytic_code = None
        if self.employee:
            for mw in self.employee.mandatory_wages:
                if mw.analytic_account:
                    analytic_code = mw.analytic_account.code
                    break
        self.analytic_account = analytic_code

    @fields.depends('category', 'is_vacations', 'absenteeism')
    def on_change_category(self):
        if self.category:
            self.absenteeism = self.category.absenteeism
            if self.category.wage_type:
                if self.category.wage_type.type_concept == 'holidays':
                    self.is_vacations = True
            else:
                self.is_vacations = False
        else:
            self.absenteeism = False
            self.is_vacations = False

    @fields.depends('contract', 'days_of_vacations')
    def on_change_with_amount(self):
        if self.contract and self.days_of_vacations:
            amount = round(self.contract.salary / 30, 2)
            return amount
        else:
            return self.amount

    def get_line_(self, wage, amount, days, account_id, party=None):
        value = {
            'sequence': wage.sequence,
            'wage': wage.id,
            'account': account_id,
            'description': wage.name,
            'amount': amount,
            'days': days,
            'party_to_pay': party,
        }
        return value

    @classmethod
    @ModelView.button
    def create_liquidation(cls, records):
        pool = Pool()
        Liquidation = pool.get('staff.liquidation')
        Period = pool.get('staff.payroll.period')
        Warning = pool.get('res.user.warning')

        for event in records:
            validate_liquidation = Liquidation.search(['origin', '=', event])

            if validate_liquidation:
                raise (
                    UserError(
                        'ERROR:', 'Ya existe una liquidacion con la ' 'novedad actual.'
                    )
                )

            warning_name = 'mywarning,%s' % event
            if Warning.check(warning_name):
                raise UserWarning(
                    warning_name, f'Se creara una liquidacion de vacaciones'
                )
            _date_start = str(event.start_date).split('-')
            _date_end = str(event.end_date).split('-')

            start_date = f'{_date_start[0]}-{_date_start[1]}'
            end_date = f'{_date_end[0]}-{_date_end[1]}'

            if start_date == end_date:
                end_period = Period.search(
                    [('start', '<=', event.start_date),
                     ('end', '>=', event.start_date)]
                )

                cls.staff_liquidation_event(
                    event=event,
                    end_period=end_period,
                    liquidation_date=event.start_date,
                    days=event.days,
                    end_date=event.end_date,
                )

            else:

                get_day = ultimo_dia_del_mes(
                    year=int(_date_start[0]), month=int(_date_start[1])
                )

                end_period = Period.search(
                    [
                        ('start', '<=', f'{start_date}-{get_day}'),
                        ('end', '>=', f'{start_date}-{get_day}'),
                    ]
                )

                if not end_period:
                    raise UserError(
                        'ERROR:', 'No se encontro periodo para la liquidacion'
                    )

                if get_day == 31:
                    days = abs(int(_date_start[2]) - get_day)
                    end_date_period = end_period[0].end - timedelta(days=1)
                else:
                    days = abs(int(_date_start[2]) - get_day) + 1
                    end_date_period = end_period[0].end

                cls.staff_liquidation_event(
                    event=event,
                    end_period=end_period,
                    liquidation_date=event.start_date,
                    days=days,
                    end_date=end_date_period,
                )

                if get_day != 31:
                    days = event.days - days
                else:
                    days = event.days - days - 1

                end_period = Period.search(
                    [('start', '<=', event.end_date),
                     ('end', '>=', event.end_date)]
                )

                cls.staff_liquidation_event(
                    event=event,
                    end_period=end_period,
                    liquidation_date=end_period[0].start,
                    days=days,
                    end_date=event.end_date,
                )

    def staff_liquidation_event(event, end_period, liquidation_date, days, end_date):
        pool = Pool()
        Configuration = pool.get('staff.configuration')(1)
        Liquidation = pool.get('staff.liquidation')
        Period = pool.get('staff.payroll.period')
        StaffEvent = pool.get('staff.event')
        Staff_event_liquidation = pool.get('staff.event-staff.liquidation')
        liquidation = Liquidation()
        liquidation.employee = event.employee
        liquidation.contract = event.contract
        liquidation.kind = 'holidays'
        liquidation.state = 'wait'
        start_period = Period.search(
            [
                ('start', '>=', event.contract.start_date),
                ('end', '<=', event.contract.start_date),
            ]
        )
        if not start_period:
            start_period = Period.search([], order=[('end', 'ASC')], limit=1)
        liquidation.start_period = start_period[0]
        liquidation.end_period = end_period[0]
        liquidation.liquidation_date = liquidation_date
        liquidation.description = event.description
        liquidation.account = Configuration.liquidation_account
        liquidation.origin = event
        liquidation.save()
        # Se procesa la liquidación
        Liquidation.compute_liquidation([liquidation])
        wages = [
            wage_type
            for wage_type in event.employee.mandatory_wages
            if wage_type.wage_type.type_concept in CONCEPT
            or (
                wage_type.wage_type.type_concept_electronic in CONCEPT_ELECTRONIC
                and wage_type.wage_type.pay_liqudation
            )
        ]
        if wages:
            if event.edit_amount:
                amount_day = event.amount
            else:
                amount_day = liquidation.contract.salary / 30
            workdays = days
            amount_workdays = round(amount_day * workdays * Decimal(0.04), 2)
            for concept in wages:
                amount = amount_workdays * -1
                if concept.fix_amount:
                    amount = concept.fix_amount * -1
                if concept.wage_type.type_concept_electronic in CONCEPT_ELECTRONIC:
                    amount_workdays = 0
                value = {
                    'sequence': concept.wage_type.sequence,
                    'wage': concept.wage_type.id,
                    'description': concept.wage_type.name,
                    'amount': amount,
                    'account': concept.wage_type.credit_account,
                    'days': days,
                    'party_to_pay': concept.party,
                    'origin': event,
                }

                if amount_workdays:
                    value.update(
                        {
                            'adjustments': [
                                (
                                    'create',
                                    [
                                        {
                                            'account': concept.wage_type.credit_account.id,
                                            'amount': amount_workdays * -1,
                                            'description': concept.wage_type.credit_account.name,
                                        }
                                    ],
                                )
                            ]
                        }
                    )
                liquidation.write(
                    [liquidation], {'lines': [('create', [value])]})
        liquidation._validate_holidays_lines(
            event, liquidation_date, end_date, days)

        staff_event_liquidation = Staff_event_liquidation()
        staff_event_liquidation.staff_liquidation = liquidation
        staff_event_liquidation.event = event
        StaffEvent.set_preliquidation(event, liquidation)
        staff_event_liquidation.save()

    def set_preliquidation(self, liquidation):
        debit_accounts = [
            mw.wage_type.debit_account.id
            for mw in liquidation.employee.mandatory_wages
            if mw.analytic_account and mw.wage_type.debit_account
        ]
        group_analytic = {
            mw.wage_type.id: mw.analytic_account.id
            for mw in liquidation.employee.mandatory_wages
            if mw.analytic_account
        }
        for line in liquidation.lines:
            if line.wage.id not in group_analytic.keys():
                if line.account.id not in debit_accounts:
                    continue

            if (
                line.wage.id not in group_analytic.keys()
                and line.account.id in debit_accounts
            ):
                for mandatory in liquidation.employee.mandatory_wages:
                    if mandatory.analytic_account:
                        group_analytic[line.wage.id] = mandatory.analytic_account

            for acc in line.analytic_accounts:
                try:
                    acc.write([acc], {'account': group_analytic[line.wage.id]})
                except Exception as error:
                    print(error)
        liquidation.save()

    @classmethod
    def process_event(cls, events):
        super(StaffEvent, cls).process_event(events)
        pool = Pool()
        Contract = pool.get('staff.contract')
        Access = pool.get('staff.access')

        for event in events:
            if event.category and event.is_vacations:
                contract = event.contract
                Contract.write(
                    [contract], {'events_vacations': [('add', [event])]})

            if (
                event.category
                and event.access_register
                and event.enter_timestamp
                and event.exit_timestamp
            ):
                for i in range(0, event.days):
                    is_access = Access.search(
                        [
                            (
                                'enter_timestamp',
                                '<=',
                                event.enter_timestamp + timedelta(days=i),
                            ),
                            (
                                'exit_timestamp',
                                '>=',
                                event.exit_timestamp + timedelta(days=i),
                            ),
                            ('employee', '=', event.employee),
                        ]
                    )
                    if not is_access:
                        to_save = Access()
                        to_save.employee = event.employee
                        to_save.payment_method = 'extratime'
                        to_save.enter_timestamp = event.enter_timestamp + timedelta(
                            days=i
                        )
                        to_save.exit_timestamp = event.exit_timestamp + timedelta(
                            days=i
                        )
                        to_save.line_event = event
                        to_save.reco = Decimal(0.00)
                        to_save.save()
                        to_save.recf = Decimal(0.00)
                        to_save.save()
                        to_save.dom = Decimal(0.00)
                        to_save.save()
                        to_save.hedo = Decimal(0.00)
                        to_save.save()
                        to_save.heno = Decimal(0.00)
                        to_save.save()
                        to_save.henf = Decimal(0.00)
                        to_save.save()
                        to_save.hedf = Decimal(0.00)
                        to_save.save()

    @classmethod
    def force_draft(cls, events):
        super(StaffEvent, cls).force_draft(events)
        pool = Pool()
        Contract = pool.get('staff.contract')
        Access = pool.get('staff.access')
        for event in events:
            print(event)
            is_access = Access.search([('line_event', '=', event)])
            print(is_access)
            if (
                event.category
                and event.contract
                and event.id in event.contract.events_vacations
            ):
                contract = event.contract
                Contract.write(
                    [contract], {'events_vacations': [('remove', [event])]})
            if is_access:
                Access.delete(is_access)


class LineLiquidationEvent(ModelSQL):
    'Staff Event - Staff Liquidation'
    __name__ = 'staff.event-staff.liquidation'
    _table = 'staff_event_staff_liquidation_rel'
    staff_liquidation = fields.Many2One(
        'staff.liquidation',
        'Liquidation',
        ondelete='RESTRICT',
        select=True,
        required=True,
    )

    event = fields.Many2One(
        'staff.event', 'Event', ondelete='CASCADE', select=True, required=True
    )


class Payroll(metaclass=PoolMeta):
    __name__ = 'staff.payroll'
    payment_extras = fields.Boolean('Payment extras')

    @classmethod
    def __setup__(cls):
        super(Payroll, cls).__setup__()

    def set_preliquidation(self, extras, discounts=None):
        '''Function to add analytic accounts to liquidation'''
        super(Payroll, self).set_preliquidation(extras, discounts)
        PayrollLine = Pool().get('staff.payroll.line')

        if not hasattr(PayrollLine, 'analytic_accounts'):
            return
        AnalyticAccount = Pool().get('analytic_account.account')

        # Create analytic account lines
        for line in self.lines:
            if not line.is_event:
                continue
            if line.origin.analytic_account:
                for acc in line.analytic_accounts:
                    try:
                        (analytic_account,) = AnalyticAccount.search(
                            [('code', '=', line.origin.analytic_account)]
                        )
                        acc.write([acc], {'account': analytic_account.id})
                    except Exception as error:
                        print(error)
                        wage = line.wage_type.rec_name
                        raise UserError(
                            'staff_event.msg_error_on_analytic_account', wage
                        )

        # Save staff payroll lines
        self.lines = tuple(self.lines)
        self.save()

    def _create_payroll_lines(self, wages, extras, discounts=None):
        '''Function to create payroll lines'''

        PayrollLine = Pool().get('staff.payroll.line')
        MoveLine = Pool().get('account.move.line')
        LoanLine = Pool().get('staff.loan.line')
        Contract = Pool().get('staff.contract')
        Event = Pool().get('staff.event')
        Config = Pool().get('staff.configuration')
        config = Config(1)

        salary_args = {}
        validate_event = []
        values = []
        real_hour_biweekly = 0
        discount = 0

        work_day_hours = config.default_hour_workday
        default_hour_biweekly = config.default_hour_biweekly

        if not work_day_hours or not default_hour_biweekly:
            raise UserError('ERROR', 'Debe configurar las horas reglamentadas')

        start_date_extras = self.start_extras
        end_date_extras = self.end_extras
        salary_in_date = self.contract.get_salary_in_date(self.end)
        get_line = self.get_line
        get_line_quantity = self.get_line_quantity
        get_line_quantity_special = self.get_line_quantity_special
        get_salary_full = self.get_salary_full
        values_append = values.append

        self.process_loans_to_pay(LoanLine, PayrollLine, MoveLine)

        # Calculate days registered in assistance
        if self.assistance:
            for assistance in self.assistance:
                if assistance.enter_timestamp.day == 31:
                    real_hour_biweekly += round(assistance.hedo, 2)
                    real_hour_biweekly += round(assistance.heno, 2)
                    real_hour_biweekly += round(assistance.hedf, 2)
                    real_hour_biweekly += round(assistance.henf, 2)
                    continue
                real_hour_biweekly += round(Decimal(str(assistance.ttt)), 2)

        # Validate if select date from extras
        if not start_date_extras or not end_date_extras:
            extras = {}

        if extras:
            sum_extras = sum(
                cant_extras
                for type, cant_extras in extras.items()
                if type == 'hedo' or type == 'heno' or type == 'hedf' or type == 'henf'
            )

            # Validate if party have LicenciaNR to discount it from assistance
            for line in self.lines:
                event = Event.search(
                    [
                        (
                            'category.wage_type.type_concept_electronic',
                            '=',
                            'LicenciaNR',
                        ),
                        ('start_date', '>=', self.start_extras),
                        ('end_date', '<=', self.end_extras),
                        ('employee.id', '=', self.employee.id),
                    ]
                )
                if event not in validate_event:
                    validate_event.append(event)
                else:
                    event = ()

                if event:
                    days = [i.quantity for i in event]
                    default_hour_biweekly -= int(sum(days)) * work_day_hours

            # Validate if ttte is different to real ttt
            if default_hour_biweekly != real_hour_biweekly:
                employee = self.employee.id
                contact = Contract.search(['employee', '=', employee])
                start_date_contract = contact[0].start_date
                end_date_contract = contact[0].end_date

                if start_date_contract > start_date_extras:
                    difference = end_date_extras - start_date_contract
                    default_hour_biweekly = (
                        difference.days + 1) * work_day_hours
                elif end_date_contract and end_date_contract < end_date_extras:
                    difference = end_date_contract - start_date_extras
                    default_hour_biweekly = (
                        difference.days + 1) * work_day_hours

            difference = round(real_hour_biweekly - default_hour_biweekly, 2)

            if difference < 0:
                pending_value = abs(difference)
                for type, cant_extras in extras.items():
                    if (
                        type == 'hedo'
                        or type == 'heno'
                        or type == 'hedf'
                        or type == 'henf'
                    ):
                        if pending_value > 0:
                            if pending_value > cant_extras:
                                pending_value -= cant_extras
                                extras[type] = Decimal(0)
                            else:
                                rest_extras = round(
                                    cant_extras - pending_value, 2)
                                extras[type] = rest_extras
                                pending_value = 0
            else:
                if sum_extras > difference:
                    pending_value = round(sum_extras - difference, 2)
                    for type, cant_extras in extras.items():
                        if (
                            type == 'hedo'
                            or type == 'heno'
                            or type == 'hedf'
                            or type == 'henf'
                        ):
                            if pending_value > 0:
                                if pending_value > cant_extras:
                                    pending_value -= cant_extras
                                    extras[type] = Decimal(0)
                                else:
                                    rest_extras = round(
                                        cant_extras - pending_value, 2)
                                    extras[type] = rest_extras
                                    pending_value = 0

        for wage, party, fix_amount in wages:
            if not fix_amount:
                salary_args = get_salary_full(wage)
                if wage.salary_constitute:
                    salary_args['salary'] = salary_in_date

                unit_value = wage.compute_unit_price(salary_args)
            else:
                unit_value = fix_amount

            discount = None
            if discounts and discounts.get(wage.id):
                discount = discounts.get(wage.id)
            qty = get_line_quantity_special(wage)
            if qty == 0:
                qty = get_line_quantity(
                    wage, self.start, self.end, extras, discount)
            line_ = get_line(wage, qty, unit_value, party)
            values_append(line_)

        PayrollLine.create(values)

    def process_loans_to_pay(self, LoanLine, PayrollLine, MoveLine):
        '''Function to process employee loans to pay'''

        dom = [
            ('loan.party', '=', self.employee.party.id),
            ('loan.wage_type', '!=', None),
            ('maturity_date', '<=', self.end),
            ('state', 'in', ['pending', 'partial']),
        ]
        lines_loan = LoanLine.search(dom)

        for m, r in zip(lines_loan, range(len(lines_loan))):
            party = m.loan.party_to_pay if m.loan.party_to_pay else None
            move_lines = MoveLine.search(
                [
                    ('origin', 'in', ['staff.loan.line,' + str(m)]),
                ]
            )
            wage_type = m.loan.wage_type
            amount = m.amount
            to_create = {
                'origin': m,
                'party': party,
                'quantity': 1,
                'uom': wage_type.uom,
                'unit_value': amount,
                'move_lines': [('add', move_lines)],
                'wage_type': wage_type,
                'description': wage_type.name,
                'payroll': self,
                'receipt': wage_type.receipt,
                'sequence': wage_type.sequence,
            }

            (line,) = PayrollLine.create([to_create])
            LoanLine.write([m], {'state': 'paid', 'origin': line})

    def get_moves_lines(self):
        '''Function to build move lines when post payroll

        Raises:
            UserError: if error ocurred when build lines

        Returns:
            list: A list with account_move_line model registry
        '''

        pool = Pool()
        LoanLines = pool.get("staff.loan.line")
        lines_moves = {}
        result = []
        pool = Pool()
        LoanLines = pool.get("staff.loan.line")

        mandatory_wage_ = [
            mandatory for mandatory in self.employee.mandatory_wages]

        debit_acc2 = None
        attr_getter = attrgetter(
            "amount",
            "amount_60_40",
            "wage_type",
            "wage_type.definition",
            "wage_type.account_60_40",
            "wage_type.debit_account",
            "wage_type.credit_account",
            "wage_type.expense_formula",
        )

        employee_id = self.employee.party.id

        for line in self.lines:
            data = {"origin": None, "reference": None}
            if line.origin and line.origin.__name__ == LoanLines.__name__:
                data["origin"] = line.origin
                data["reference"] = line.origin.loan.number

            (
                amount,
                amount_60_40,
                wage_type,
                definition,
                account_60_40,
                debit_acc,
                credit_acc,
                expense_for,
            ) = attr_getter(line)

            if amount <= 0 or not wage_type:
                continue

            expense = line.get_expense_amount() if expense_for else Decimal(0)

            if definition == "payment":
                amount_debit = amount + expense
                if amount_60_40:
                    amount_debit = amount - amount_60_40
                    amount_debit2 = amount_60_40
                    debit_acc2 = account_60_40
            else:
                if expense:
                    amount_debit = expense
                elif debit_acc:
                    amount_debit = amount

            amount_credit = amount + expense

            try:

                if line.party:
                    party_id = line.party
                else:
                    party_id = self.get_party_payroll_line(
                        line, mandatory_wage_, employee_id
                    )

                if debit_acc and amount_debit > _ZERO:
                    if definition == "discount":
                        amount_debit = amount_debit * (-1)
                    if debit_acc.id not in lines_moves.keys():

                        lines_moves[debit_acc.id] = {
                            employee_id: line.get_move_line(
                                debit_acc, party_id, ("debit",
                                                      amount_debit), data
                            )
                        }
                    else:
                        line.update_move_line(
                            lines_moves[debit_acc.id][employee_id],
                            {"debit": amount_debit, "credit": _ZERO},
                        )

                if debit_acc2:
                    if debit_acc2.id not in lines_moves.keys():
                        lines_moves[debit_acc2.id] = {
                            employee_id: line.get_move_line(
                                debit_acc2, party_id, ("debit",
                                                       amount_debit2), data
                            )
                        }
                    else:
                        line.update_move_line(
                            lines_moves[debit_acc2.id][employee_id],
                            {"debit": amount_debit, "credit": _ZERO},
                        )

                if amount_credit > _ZERO:
                    line_credit_ready = False
                    if credit_acc:
                        if credit_acc.id not in lines_moves.keys():
                            lines_moves[credit_acc.id] = {
                                party_id: line.get_move_line(
                                    credit_acc,
                                    party_id,
                                    ("credit", amount_credit),
                                    data,
                                )
                            }
                            line_credit_ready = True
                        else:
                            if (
                                line.origin
                                and line.origin.__name__ == LoanLines.__name__
                            ):
                                new_id = f"{credit_acc.id}-{line.id}"
                                lines_moves[new_id] = {
                                    party_id: line.get_move_line(
                                        credit_acc,
                                        party_id,
                                        ("credit", amount_credit),
                                        data,
                                    )
                                }
                                line_credit_ready = True

                            if party_id not in lines_moves[credit_acc.id].keys():
                                lines_moves[credit_acc.id].update(
                                    {
                                        party_id: line.get_move_line(
                                            credit_acc,
                                            party_id,
                                            ("credit", amount_credit),
                                            data,
                                        )
                                    }
                                )
                                line_credit_ready = True
                    if definition != "payment":
                        deduction_acc = wage_type.deduction_account
                        if deduction_acc:
                            if deduction_acc.id not in lines_moves.keys():
                                lines_moves[deduction_acc.id] = {
                                    employee_id: line.get_move_line(
                                        deduction_acc,
                                        employee_id,
                                        ("credit", -amount),
                                        data,
                                    )
                                }
                                line_credit_ready = True
                            else:
                                lines_moves[deduction_acc.id][employee_id][
                                    "credit"
                                ] -= amount

                    if credit_acc and not line_credit_ready:
                        lines_moves[credit_acc.id][party_id]["credit"] += amount_credit
            except Exception as e:
                error = f'{wage_type.name}: {e}'
                raise UserError(error)

        for r in lines_moves.values():
            _line = list(r.values())
            if _line[0]["debit"] > 0 and _line[0]["credit"] > 0:
                new_value = _line[0]["debit"] - _line[0]["credit"]
                if new_value >= 0:
                    _line[0]["debit"] = abs(new_value)
                    _line[0]["credit"] = 0
                else:
                    _line[0]["credit"] = abs(new_value)
                    _line[0]["debit"] = 0
            result.extend(_line)
        return result

    def get_party_payroll_line(self, line, mandatories, employee_id):
        for mandatory in mandatories:
            if mandatory.wage_type == line.wage_type:
                if mandatory.party:
                    employee_id = mandatory.party
        return employee_id

    @classmethod
    @ModelView.button
    @Workflow.transition('posted')
    def post(cls, records):
        cls.create_move(records)

    @classmethod
    def create_move(cls, payrolls):
        '''Function to create account_move registry and post it'''
        pool = Pool()
        Move = pool.get('account.move')
        Period = pool.get('account.period')
        MoveLine = pool.get('account.move.line')
        move_post = []
        for payroll in payrolls:
            if payroll.move:
                return

            period_id = Period.find(
                payroll.company.id, date=payroll.date_effective)
            move_lines = payroll.get_moves_lines()
            move, = Move.create([{
                'journal': payroll.journal.id,
                'origin': str(payroll),
                'period': period_id,
                'date': payroll.date_effective,
                'state': 'draft',
                'description': payroll.description,
                'lines': [('create', move_lines)],
            }])
            payroll.write([payroll], {'move': move.id})
            move_post.append(payroll.move)
        if move_post:
            Move.post(move_post)

        grouped = {}
        for payroll in payrolls:
            for line in payroll.lines:
                if line.wage_type.definition != 'payment':
                    account_id = line.wage_type.credit_account.id
                else:
                    account_id = line.wage_type.debit_account.id
                grouped.update({account_id: {'lines': list(line.move_lines)}})

        for payroll in payrolls:
            for p in payroll.move.lines:
                if p.account.id not in grouped or (
                        p.account.type.statement not in ('balance')) or p.reconciliation:
                    continue
                to_reconcile = [p] + grouped[p.account.id]['lines']
                amount = sum([(r.debit - r.credit) for r in to_reconcile])
                if payroll.company.currency.is_zero(amount):
                    MoveLine.reconcile(set(to_reconcile))

        for payroll in payrolls:
            payroll.concile_loan_lines()

    def concile_loan_lines(self):
        '''Function to concile loan lines by liquidation'''
        pool = Pool()
        LoanLines = pool.get('staff.loan.line')
        AccountMoveLine = pool.get('account.move.line')
        conciled_lines = []
        for lines in self.move.lines:
            origin = lines.origin
            reference = lines.reference
            balance = 0
            # Validate if is loan lines to conciliate
            if origin and reference and origin.__name__ == LoanLines.__name__:
                move_lines = AccountMoveLine.search(
                    [
                        ('origin', '=', origin),
                        ('reference', '=', reference),
                        ('reconciliation', '=', None),
                    ]
                )
                if move_lines and len(move_lines) % 2 == 0:
                    for line in move_lines:
                        balance += line.debit - line.credit
                    try:
                        if balance == 0:
                            AccountMoveLine.reconcile(move_lines)
                    except Exception as error:
                        print('aqui')
                        raise (UserError(f"ERROR: {error}"))
                else:
                    for line in self.lines:
                        if line.wage_type.type_concept_electronic == 'Deuda':
                            balance = 0
                            already_concile = False
                            if line in conciled_lines:
                                continue
                            conciled_lines.append(line)

                            loan_line = LoanLines.search(['origin', '=', line])
                            if loan_line:
                                loan_move_line = AccountMoveLine.search(
                                    [
                                        ('origin', '=', loan_line[0]),
                                        ('reconciliation', '=', None),
                                    ]
                                )

                                for lines in loan_move_line:
                                    if lines in conciled_lines:
                                        already_concile = True
                                if already_concile:
                                    break

                                for lines in loan_move_line:
                                    balance += lines.debit - lines.credit

                                try:
                                    if balance == 0 and loan_move_line:
                                        lines_to_reconcile = []
                                        lines_to_reconcile = list(
                                            loan_move_line)
                                        if lines_to_reconcile:
                                            AccountMoveLine.reconcile(
                                                lines_to_reconcile)
                                            for line in loan_move_line:
                                                conciled_lines.append(line)
                                            break
                                except Exception as error:
                                    raise (UserError(f'ERROR: {error}'))

    def compute_salary_full_(self, wage):
        if wage['concepts_salary']:
            salary_full = sum(
                line.amount for line in self.lines if line.wage_type.id in wage['concepts_salary'])
        else:
            salary_full = self.contract.get_salary_in_date(self.end) or 0
        return salary_full

    def get_salary_full_(self, wage):
        """
        Return a dict with sum of total amount of all wages defined
            as salary on context of wage
        """
        salary_full = self.compute_salary_full_(wage)
        return {'salary': salary_full}


class PayrollLine(metaclass=PoolMeta):
    __name__ = 'staff.payroll.line'

    def update_move_line(self, move_line, values):
        '''Function to update analytic account value to create'''

        if values['debit']:
            move_line['debit'] += values['debit']
            if 'analytic_lines' in move_line:
                move_line['analytic_lines'][0][1][0]['debit'] += values['debit']
        if values['credit']:
            move_line['credit'] += values['credit']
            if 'analytic_lines' in move_line:
                move_line['analytic_lines'][0][1][0]['credit'] += values['credit']

        return move_line

    def get_move_line(self, account, party_id, amount, data=None):
        res = super(PayrollLine, self).get_move_line(account, party_id, amount)

        if data and data['origin'] and data['reference']:
            res['origin'] = data['origin']
            res['reference'] = data['reference']
        return res


class PayrollReport(CompanyReport):
    __name__ = 'staff.payroll'

    # Metodo para heredar el metodo de generacion del reporte.
    @classmethod
    def get_context(cls, records, header, data):
        report_context = super().get_context(records, header, data)
        Loans = Pool().get('staff.loan')
        party = ''
        amount = 0.0
        for record in report_context['records']:
            party = record.employee.party.name
        # busco el prestamo de ese tercero
        loans = Loans.search([('party', '=', party), ('state', '=', 'posted')])
        # Si no hay prestamo limpio la variable
        if not loans:
            for keys in report_context['records']:
                keys.total_cost = 0.0
        else:
            for loan in loans:
                for line in loan.lines:
                    # busco que las lineas que tenga esten pendientes de pago y las guardo.
                    if line.state == 'pending':
                        amount += float(line.amount)

        # asigno el monto en una variable que no se usa
        for keys in report_context['records']:
            keys.total_cost = amount
        return report_context


class PayrollExo2276(metaclass=PoolMeta):
    __name__ = 'staff.payroll_exo2276.report'

    @classmethod
    def get_context(cls, records, header, data):
        '''Function to build context to report'''

        report_context = Report.get_context(records, header, data)
        pool = Pool()
        user = pool.get('res.user')(Transaction().user)
        Payroll = pool.get('staff.payroll')
        LiquidationLine = pool.get('staff.liquidation.line')

        new_objects = {}
        employees = []

        index = 0
        start_period = data['start_period']
        end_period = data['end_period']

        domain_ = cls.get_domain_payroll(data)
        domain_ += [('start', '>=', start_period)]
        domain_ += [('end', '<=', end_period)]
        payrolls = Payroll.search([domain_])

        for payroll in payrolls:
            index += 1
            party = payroll.employee.party
            employees.append(payroll.employee.party.id)
            if party.id in new_objects.keys():
                continue

            new_objects[party.id] = {
                'index': index,
                'type_document': party.type_document,
                'id_number': party.id_number,
                'first_family_name': party.first_family_name,
                'second_family_name': party.second_family_name,
                'first_name': party.first_name,
                'second_name': party.second_name,
                'addresses': party.addresses[0].street,
                'department_code': party.department_code,
                'city_code': party.city_code,
                'country_code': party.country_code,
                'email': party.email,
                'salary_payment': 0,
                'total_benefit': 0,
                'other_payments': 0,
                'cesanpag': 0,
                'incapacity': 0,
                'interest': 0,
                'holidays': 0,
                'bonus': 0,
                'bonus_service': 0,
                'total_deduction': 0,
                'health': 0,
                'retirement': 0,
                'fsp': 0,
                'retefuente': 0,
                'other_deduction': 0,
                'retirement_voluntary': 0,
                'afc_account': 0,
                'avc_account': 0,
                'discount': 0,
                'box_family': 0,
                'risk': 0,
                'unemployment': 0,
                'syndicate': 0,
                'commission': 0,
                'gross_payment': 0,
                'others_payments': 0,
                'total_retirement': 0,
                'total_salary': 0,
                'latest_payment': 0,
                'total': 0,
            }
            new_objects[party.id] = cls._prepare_lines(
                payrolls, new_objects[party.id], party.id
            )

            _cesanpag = 0
            _unemployment = 0
            _total_benefit = 0
            _other = 0
            _health = 0
            _retirement = 0
            _tax = 0
            _retirement_voluntary = 0
            _salary_payments = 0

            lines_liquid = LiquidationLine.search_read(
                [
                    ('liquidation.employee.party', '=', party.id),
                    ('liquidation.liquidation_date',
                     '>=', data['start_period']),
                    ('liquidation.liquidation_date', '<=', data['end_period']),
                    (
                        'wage.type_concept',
                        'in',
                        [
                            'unemployment',
                            'interest',
                            'holidays',
                            'bonus_service',
                            'health',
                            'retirement',
                            'tax',
                            'fsp',
                            'other',
                            'extras',
                        ],
                    ),
                ],
                fields_names=[
                    'amount',
                    'wage.type_concept',
                    'wage.name',
                    'liquidation.kind',
                    'wage.type_concept_electronic',
                ],
            )

            for line in lines_liquid:
                if line['wage.']['type_concept'] in ['unemployment', 'interest']:
                    if (
                        line['liquidation.']['kind'] == 'unemployment'
                        and line['wage.']['type_concept'] == 'unemployment'
                    ):
                        _unemployment += line['amount']
                    else:
                        _cesanpag += line['amount']
                elif line['wage.']['type_concept'] == 'convencional_bonus':
                    _other += line['amount']
                elif line['wage.']['type_concept'] == 'health':
                    _health += abs(line['amount'])
                elif (
                    line['wage.']['type_concept'] == 'retirement'
                    or line['wage.']['type_concept'] == 'fsp'
                ):
                    _retirement += abs(line['amount'])
                elif line['wage.']['type_concept'] == 'tax':
                    _tax += abs(line['amount'])
                elif line['wage.']['type_concept'] == 'extras':
                    _salary_payments += line['amount']
                elif line['wage.']['type_concept'] == 'other':
                    if line['wage.']['name'] == 'PENSIONES VOLUNTARIAS':
                        _retirement_voluntary += abs(line['amount'])
                    if line['wage.']['type_concept_electronic'] == 'Indemnizacion':
                        _other += line['amount']
                    if line['wage.']['type_concept_electronic'] == 'PrimasNS':
                        _other += line['amount']
                else:
                    _total_benefit += line['amount']

            new_objects[party.id]['cesanpag'] = _cesanpag
            new_objects[party.id]['total_salary'] += _salary_payments
            new_objects[party.id]['unemployment'] = _unemployment
            new_objects[party.id]['total_benefit'] += _total_benefit
            new_objects[party.id]['others_payments'] += _other
            new_objects[party.id]['health'] += _health
            new_objects[party.id]['total_retirement'] += _retirement
            new_objects[party.id]['retefuente'] += _tax
            new_objects[party.id]['retirement_voluntary'] += _retirement_voluntary

        employees = list(set(employees))

        # Set percent last six months payments
        for party_id in employees:
            cls.get_domain_payroll_employees(
                party_id, end_period=end_period, new_objects=new_objects
            )

        report_context['records'] = new_objects.values()
        report_context['end_period'] = end_period
        report_context['start_period'] = start_period
        report_context['today'] = date.today()
        report_context['company'] = user.company
        return report_context

    @classmethod
    def _prepare_lines(cls, payrolls, vals, party_id):
        '''Function to build data to report'''

        payroll_ids = [payroll.id for payroll in payrolls]
        Lines = Pool().get('staff.payroll.line')
        lines = Lines.search(
            [
                ('payroll', 'in', payroll_ids),
                ('payroll.employee.party', '=', party_id),
            ]
        )
        for line in lines:
            concept = line.wage_type.type_concept
            if line.wage_type.definition == 'payment':
                if concept == 'unemployment' or concept == 'interest':
                    continue
                elif concept == 'salary':
                    vals['salary_payment'] += line.amount
                elif concept == 'extras':
                    vals['salary_payment'] += line.amount
                elif concept == 'incapacity_greater_to_2_days':
                    vals['salary_payment'] += line.amount
                elif concept == 'incapacity_arl':
                    vals['salary_payment'] += line.amount
                elif concept == 'other':
                    if line.wage_type.type_concept_electronic == 'LicenciaR':
                        vals['salary_payment'] += line.amount
                    elif line.wage_type.type_concept_electronic == 'ConceptoS':
                        vals['salary_payment'] += line.amount
                    elif line.wage_type.type_concept_electronic != 'LicenciaNR':
                        vals['other_payments'] += line.amount

                elif concept == 'holidays':
                    if line.wage_type.name == 'VACACIONES DISFRUTADAS EN NOMINA':
                        vals['total_benefit'] += line.amount
                elif concept == 'transport':
                    vals['other_payments'] += line.amount
                elif concept == 'bonus':
                    vals['other_payments'] += line.amount
                elif concept == 'food':
                    vals['other_payments'] += line.amount
                elif concept == 'allowance':
                    vals['other_payments'] += line.amount
                elif concept == 'commission':
                    vals['commission'] += line.amount
                elif concept == 'bonus_service':
                    vals['bonus_service'] += line.amount
                elif concept == 'box_family':
                    vals['box_family'] += line.amount
                elif concept == 'risk':
                    vals['risk'] += line.amount
                else:
                    if concept != 'sena' and concept != 'icbf':
                        vals['other_payments'] += line.amount
            elif line.wage_type.definition == 'deduction':
                vals['total_deduction'] += line.amount
                if concept == 'health':
                    vals['health'] += line.amount
                elif concept == 'retirement':
                    vals['retirement'] += line.amount
                elif concept == 'fsp':
                    vals['fsp'] += line.amount
                elif concept == 'tax':
                    vals['retefuente'] += line.amount
                elif concept == 'other':
                    if line.wage_type.name == 'PENSIONES VOLUNTARIAS':
                        vals['retirement_voluntary'] += line.amount
                    elif line.wage_type.name == 'CUENTAS AFC':
                        vals['afc_account'] += line.amount
                    elif line.wage_type.name == 'CUENTAS AVC':
                        vals['avc_account'] += line.amount
                else:
                    vals['other_deduction'] += line.amount
            else:
                vals['discount'] += line.amount

        vals['total_salary'] = vals['salary_payment']
        vals['others_payments'] = vals['other_payments']
        vals['total_retirement'] = vals['fsp'] + vals['retirement']
        return vals

    @classmethod
    def prepare_lines_employee(cls, payrolls):
        '''Function to build data to report'''

        payroll_ids = [payroll.id for payroll in payrolls]
        Lines = Pool().get('staff.payroll.line')
        lines = Lines.search(
            [
                ('payroll', 'in', payroll_ids),
            ]
        )
        payments = 0
        for line in lines:
            concept = line.wage_type.type_concept
            if line.wage_type.definition == 'payment':
                if concept == 'salary':
                    payments += line.amount
                elif concept == 'extras':
                    payments += line.amount
                elif concept == 'commission':
                    payments += line.amount
                elif concept == 'bonus':
                    payments += line.amount
                elif concept == 'incapacity_greater_to_2_days':
                    payments += line.amount
                elif concept == 'incapacity_arl':
                    payments += line.amount
                elif concept == 'holidays':
                    if line.wage_type.name == 'VACACIONES DISFRUTADAS EN NOMINA':
                        payments += line.amount
                elif concept == 'transport':
                    payments += line.amount
                elif concept == 'other':
                    if line.wage_type.type_concept_electronic == 'LicenciaR':
                        payments += line.amount

        return payments

    @classmethod
    def get_domain_payroll_employees(cls, party_id, end_period=None, new_objects=None):
        '''Last six months payments'''

        Payroll = Pool().get('staff.payroll')
        LiquidationLine = Pool().get('staff.liquidation.line')
        total_payroll = 0
        vacations = 0

        payrolls = Payroll.search(
            [
                ('date_effective', '<=', end_period),
                ('employee.party.id', '=', party_id),
            ],
            order=[('date_effective', 'DESC')],
        )
        end_date = payrolls[0].date_effective if payrolls else None
        start_date = end_date - relativedelta(months=6)
        data = {'start_period': start_date,
                'end_period': end_date, 'employees': None}

        domain = cls.get_domain_payroll(data)
        domain += [('employee.party.id', '=', party_id)]
        payrolls = Payroll.search([domain])

        lines_liquid = LiquidationLine.search_read(
            [
                ('liquidation.employee.party', '=', party_id),
                ('liquidation.kind', '!=', 'contract'),
                ('liquidation.liquidation_date', '>', start_date),
                ('liquidation.liquidation_date', '<=', end_date),
                ('wage.type_concept', '=', 'holidays'),
            ],
            fields_names=[
                'amount',
                'wage.type_concept_electronic',
            ],
        )
        for line in lines_liquid:
            if line['wage.']['type_concept_electronic'] == 'VacacionesComunes':
                vacations += line['amount']

        count_payrolls = Payroll.search(domain, count=True)

        if count_payrolls != 0:
            if count_payrolls % 2 != 0:
                count_payrolls += 1
            count_payrolls /= 2
        else:
            count_payrolls = 1

        for payroll in payrolls:
            value_payroll = cls.prepare_lines_employee([payroll])
            total_payroll += value_payroll
        total = total_payroll + vacations
        month_prom = total / Decimal(count_payrolls)
        new_objects[party_id]['latest_payment'] = round(month_prom, 0)


class IncomeWithholdingsReport(PayrollExo2276, metaclass=PoolMeta):
    'Income Withholding Report'
    __name__ = 'staff.payroll.income_withholdings_report'

    @classmethod
    def get_domain_payroll(cls, data=None):
        dom = super(PayrollExo2276, cls).get_domain_payroll(data)
        if data['employees']:
            dom.append(('employee', 'in', data['employees']))
        return dom


class PayrollElectronic(metaclass=PoolMeta):
    'Staff Payroll Electronic'
    __name__ = 'staff.payroll.electronic'

    @classmethod
    def __setup__(cls):
        super(PayrollElectronic, cls).__setup__()
        cls._buttons.update(
            {
                'submit': {
                    'invisible': True,
                },
                'force_response': {
                    'invisible': True,
                },
                'send_email': {
                    'invisible': True,
                },
                'submit_noova': {
                    'invisible': Or(
                        Eval('electronic_state') == 'authorized',
                        Eval('state') != 'processed',
                    )
                },
            }
        )

    @classmethod
    @ModelView.button
    def submit_noova(cls, records):
        for payroll in records:
            if payroll.validate_for_send():
                pool = Pool()
                Configuration = pool.get('staff.configuration')
                configuration = Configuration(1)
                _ = ElectronicPayrollCdst(payroll, configuration)
            else:
                payroll.get_message('Nomina no valida para enviar')


# Reporte FRIGOECOL IBC
class PayrollIBCView(ModelView):
    'Payroll IBC View'
    __name__ = 'staff.payroll_ibc.start'
    company = fields.Many2One('company.company', 'Company', required=True)

    start_period = fields.Many2One(
        'staff.payroll.period',
        'Start Period',
        required=True,
        domain=[('state', '!=', 'draft')],
        states={
            'invisible': ~Not(Eval('accomulated_month')),
            'required': ~Bool(Eval('accomulated_month')),
        },
        depends=['accomulated_month'],
    )

    end_period = fields.Many2One(
        'staff.payroll.period',
        'End Period',
        required=True,
        domain=[
            ('state', '!=', 'draft'),
        ],
        states={
            'invisible': ~Not(Eval('accomulated_month')),
            'required': ~Bool(Eval('accomulated_month')),
        },
        depends=['accomulated_month'],
    )

    department = fields.Many2One('company.department', 'Department')

    accomulated_month = fields.Boolean(
        'accomulated Month',
        help='If this check is selected, it will accumulate by months',
        on_change_with='on_change_with_accomulated_month',
    )

    accomulated_period = fields.Boolean(
        'accomulated Period',
        help='If this check is selected, it will accumulate by period',
        on_change_with='on_change_with_accomulated_period',
    )

    fiscalyear = fields.Many2One(
        'account.fiscalyear',
        'Fiscal Year',
        states={
            'invisible': ~Not(Eval('accomulated_period')),
            'required': ~Bool(Eval('accomulated_period')),
        },
        depends=['accomulated_period'],
    )

    start_period_fiscalyear = fields.Many2One(
        'account.period',
        'Start Period',
        domain=[
            ('fiscalyear', '=', Eval('fiscalyear')),
            ('start_date', '<=', (Eval('end_period_fiscalyear'), 'start_date')),
        ],
        states={
            'invisible': ~Not(Eval('accomulated_period')),
            'required': ~Bool(Eval('accomulated_period')),
        },
        depends=['fiscalyear', 'end_period_fiscalyear', 'accomulated_period'],
    )

    end_period_fiscalyear = fields.Many2One(
        'account.period',
        'End Period',
        domain=[
            ('fiscalyear', '=', Eval('fiscalyear')),
            ('start_date', '>=', (Eval('start_period_fiscalyear'), 'start_date')),
        ],
        states={
            'invisible': ~Not(Eval('accomulated_period')),
            'required': ~Bool(Eval('accomulated_period')),
        },
        depends=['fiscalyear', 'start_period_fiscalyear', 'accomulated_period'],
    )

    @staticmethod
    def default_company():
        return Transaction().context.get('company')

    @fields.depends('fiscalyear')
    def on_change_fiscalyear(self):
        self.start_period_fiscalyear = None
        self.end_period_fiscalyear = None

    @staticmethod
    def default_accomulated_month():
        return True

    # Estas dos funcion nos permite deseleccionar una check cuando el otro este en true
    @fields.depends('accomulated_period')
    def on_change_with_accomulated_month(self, name=None):
        res = True
        if self.accomulated_period:
            res = False
        return res

    @fields.depends('accomulated_month')
    def on_change_with_accomulated_period(self, name=None):
        res = True
        if self.accomulated_month:
            res = False

        return res


class PayrollIBCWizard(Wizard):
    'Payroll IBC wizard'
    __name__ = 'staff.payroll_ibc_wizard'
    start = StateView(
        'staff.payroll_ibc.start',
        'staff_payroll_cdst.payroll_ibc_form',
        [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Print', 'print_', 'tryton-ok', default=True),
        ],
    )

    print_ = StateReport('staff_payroll.ibc_report')

    def do_print_(self, action):
        department_id = None
        start_period = None
        end_period = None

        if self.start.department:
            department_id = self.start.department.id
        if self.start.start_period:
            start_period = self.start.start_period.start
        if self.start.start_period_fiscalyear:
            start_period = self.start.start_period_fiscalyear.start_date
        if self.start.end_period:
            end_period = self.start.end_period.start
        if self.start.end_period_fiscalyear:
            end_period = self.start.end_period_fiscalyear.end_date

        data = {
            'company': self.start.company.id,
            'start_period': start_period,
            'end_period': end_period,
            'department': department_id,
            'accomulated': self.start.accomulated_month,
        }

        return action, data

    def transition_print_(self):
        return 'end'


class PayrollIBCReport(Report):
    __name__ = 'staff_payroll.ibc_report'

    @classmethod
    def get_context(cls, records, header, data):
        report_context = super().get_context(records, header, data)
        cursor = Transaction().connection.cursor()
        pool = Pool()
        StaffPayroll = pool.get('staff.payroll')
        StaffPayrollLine = pool.get('staff.payroll.line')
        Company = pool.get('company.company')
        Party = pool.get('party.party')
        Employee = pool.get('company.employee')
        StaffWage = pool.get('staff.wage_type')
        Department = pool.get('company.department')
        Contract = pool.get('staff.contract')

        # Asignacion de tabalas para extraccion de la data
        staffPayroll = StaffPayroll.__table__()
        staffPayrollLine = StaffPayrollLine.__table__()
        party = Party.__table__()
        employee = Employee.__table__()
        staffWage = StaffWage.__table__()
        department = Department.__table__()
        contract = Contract.__table__()

        # Columnas para representar la data que genera la consulta
        columns = {
            'id_number': party.id_number,
            'name': party.name,
            'department': department.name,
            'amount': Sum(staffPayrollLine.unit_value * staffPayrollLine.quantity),
            'concept': staffWage.name,
            'payroll_number': staffPayroll.number,
            'start': staffPayroll.start,
            'end': staffPayroll.date_effective,
            'type_concept': staffWage.type_concept,
            'wage_type_id': staffPayrollLine.wage_type,
            'description': staffPayroll.description,
        }

        # Condicionales para filtrar la informacion en la consulta
        where = staffWage.type_concept.in_(
            ['extras', 'bonus', 'salary', 'commission'])
        where &= Between(staffPayroll.start,
                         data['start_period'], data['end_period'])
        where &= contract.state == 'active'
        where &= contract.kind != 'learning'

        if data['department']:
            where &= staffPayroll.department == data['department']

        # Estructura de query para lanzar la consulta a la base de datos
        select = (
            staffPayrollLine.join(
                staffPayroll,
                'LEFT',
                condition=staffPayroll.id == staffPayrollLine.payroll,
            )
            .join(
                staffWage, 'LEFT', condition=staffWage.id == staffPayrollLine.wage_type
            )
            .join(employee, 'LEFT', condition=employee.id == staffPayroll.employee)
            .join(party, 'LEFT', condition=party.id == employee.party)
            .join(contract, 'LEFT', condition=employee.id == contract.employee)
            .join(
                department, 'LEFT', condition=department.id == staffPayroll.department
            )
            .select(
                *columns.values(),
                where=where,
                group_by=[
                    party.id_number,
                    party.name,
                    department.name,
                    staffWage.name,
                    staffPayroll.number,
                    staffPayroll.start,
                    staffPayroll.date_effective,
                    staffWage.type_concept,
                    staffPayrollLine.wage_type,
                    staffPayroll.description,
                ],
            )
        )

        # Ejecucion de la consulta
        cursor.execute(*select)

        # Extraccion de la data
        result = cursor.fetchall()

        fila_dict = {}
        items = {}

        # Verificamos que la consulta halla generado data
        if result:
            for record in result:

                # Estructura de diccionario donde las columnas creadas arriba de unen con cada uno de los datos.
                fila_dict = dict(zip(columns.keys(), record))

                # Verificamos que el usuario halla escojido una acomulacion por mes
                if data['accomulated']:

                    # Estraemos el mes al que pertenece dicha informacion para agruparla
                    fila_dict['month'] = MONTH.get(
                        str(fila_dict['start']).split('-')[1]
                    )

                    # Verificamos si el id_number no se encuentra en las estrutura de diccionario
                    # si es asi, le asigna el id_number con un diccionario interno con la data
                    if fila_dict['id_number'] not in items:

                        items[fila_dict['id_number']] = {'data': {}}

                    # Verificamos si el mes no se encuentra dentro del diccionario data interno,
                    # si es asi, lo agrega con la cabecera del mes para acomular la data
                    if fila_dict['month'] not in items[fila_dict['id_number']]['data']:

                        items[fila_dict['id_number']]['data'][fila_dict['month']] = {
                            'id_number': fila_dict['id_number'],
                            'name': fila_dict['name'],
                            'department': fila_dict['department'],
                            'salary': 0,
                            'extras': 0,
                            'recargos': 0,
                            'bonus': 0,
                            'comision': 0,
                            'total': 0,
                        }

                    # Verificamos cual es el tipo de concepto para acomularlo en cada uno de ellos
                    if fila_dict['type_concept'] == 'salary':
                        items[fila_dict['id_number']]['data'][fila_dict['month']][
                            'salary'
                        ] += fila_dict['amount']
                    elif fila_dict['type_concept'] == 'extras':
                        items[fila_dict['id_number']]['data'][fila_dict['month']][
                            'extras'
                        ] += fila_dict['amount']
                    elif fila_dict['type_concept'] == 'bonus':
                        items[fila_dict['id_number']]['data'][fila_dict['month']][
                            'bonus'
                        ] += fila_dict['amount']
                    elif fila_dict['type_concept'] == 'commission':
                        items[fila_dict['id_number']]['data'][fila_dict['month']][
                            'comision'
                        ] += fila_dict['amount']

                    # Aqui acomulamos todos los valores para dar un total final de ese mes.
                    items[fila_dict['id_number']]['data'][fila_dict['month']][
                        'total'
                    ] += fila_dict['amount']

                else:  # Si el valor del bool es quincenal, entonces ingresamos en esta seccion
                    # Agregamos el numero de la nomina como indice para acomular los valores
                    index = fila_dict['payroll_number']

                    if fila_dict['id_number'] not in items:
                        items[index] = {
                            'id_number': fila_dict['id_number'],
                            'name': fila_dict['name'],
                            'department': fila_dict['department'],
                            'description': fila_dict['description'],
                            'values': {},
                        }

                    # Tomamos la description de la nomina para acomular los valores de la data
                    if fila_dict['description'] not in items[index]['values']:

                        items[index]['values'][fila_dict['description']] = {
                            'salary': 0,
                            'extras': 0,
                            'recargos': 0,
                            'bonus': 0,
                            'comision': 0,
                            'total': 0,
                        }

                    # Verificamos cual es el tipo de concepto para acomularlo en cada uno de ellos
                    if fila_dict['type_concept'] == 'salary':
                        items[index]['values'][fila_dict['description']][
                            'salary'
                        ] += fila_dict['amount']
                    elif fila_dict['type_concept'] == 'extras':
                        items[index]['values'][fila_dict['description']][
                            'extras'
                        ] += fila_dict['amount']
                    elif fila_dict['type_concept'] == 'bonus':
                        items[index]['values'][fila_dict['description']][
                            'bonus'
                        ] += fila_dict['amount']
                    elif fila_dict['type_concept'] == 'commission':
                        items[index]['values'][fila_dict['description']][
                            'comision'
                        ] += fila_dict['amount']

                    # Totalisamos los valores
                    items[index]['values'][fila_dict['description']][
                        'total'
                    ] += fila_dict['amount']

        # Funcion para ordenas de manera accedente la informacion
        items = dict(sorted(items.items()))

        report_context['start'] = data['start_period']
        report_context['end'] = data['end_period']
        report_context['accomulated_period'] = str(data['accomulated'])
        report_context['records'] = items
        report_context['company'] = Company(
            Transaction().context.get('company'))
        return report_context


class PayrollPaycheckReportExten(metaclass=PoolMeta):
    __name__ = 'staff.payroll.paycheck_report'

    @classmethod
    def get_context(cls, records, header, data):
        report_context = super(PayrollPaycheckReportExten, cls).get_context(
            records, header, data
        )
        pool = Pool()
        Payroll = pool.get('staff.payroll')
        PayrollLine = pool.get('staff.payroll.line')
        Company = pool.get('company.company')
        total = 0

        dom_payroll = cls.get_domain_payroll(data)
        fields_payroll = [
            'id',
            'employee.party.name',
            'employee.party.id_number',
            'contract.start_date',
            'contract.end_date',
            'date_effective',
            'ibc',
            'contract.last_salary',
            'worked_days',
            'employee',
            'contract',
        ]
        payrolls = Payroll.search_read(
            dom_payroll, fields_names=fields_payroll)
        today = date.today()
        res = {}
        wage_type_default = [
            'health',
            'retirement',
            'risk',
            'box_family',
            'salary',
            'fsp',
            'icbf',
            'sena',
        ]
        for p in payrolls:
            key = str(p['employee']) + '_' + str(p['contract'])
            try:
                res[key]['ibc'] += p['ibc']
                res[key]['variation'] += p['ibc']
                res[key]['worked_days'] += p['worked_days']
            except:
                res[key] = p
                res[key]['today'] = today
                res[key]['ibc'] = p['ibc']
                res[key]['worked_days'] = p['worked_days']
                res[key]['type_contributor'] = '01'
                res[key]['type_id'] = 'CC'
                res[key]['type_affiliation'] = 'D'
                for w in wage_type_default:
                    res[key][w + '_amount'] = 0
                    if w not in ('salary'):
                        res[key][w + '_code'] = ''
                        res[key][w + '_name'] = ''
                        res[key][w + '_rate'] = 0

                res[key]['license_amount'] = 0
                res[key]['incapacity_amount'] = 0
                res[key]['holidays_amount'] = 0
                res[key]['extras'] = 0
                res[key]['variation'] = p['ibc']
                res[key]['subtotal'] = 0

        payroll_ids = [p['id'] for p in payrolls]

        fields_lines = [
            'amount',
            'quantity',
            'party.name',
            'wage_type.type_concept',
            'wage_type.unit_price_formula',
            'wage_type.expense_formula',
            'payroll',
            'start_date',
            'end_date',
            'payroll.employee',
            'payroll.contract',
            'wage_type.salary_constitute',
            'party.code',
            'wage_type.type_concept_electronic',
            'wage_type.excluded_payroll_electronic',
        ]

        dom_line = [
            ('payroll', 'in', payroll_ids),
            [
                'OR',
                ('wage_type.type_concept', 'in', wage_type_default),
                ('wage_type.type_concept', 'ilike', 'incapacity%'),
                ('wage_type.type_concept', 'ilike', 'license%'),
                ('wage_type.type_concept', '=', 'extras'),
                ('wage_type.type_concept', '=', 'holidays'),
                (
                    'wage_type.type_concept_electronic',
                    'in',
                    ['LicenciaR', 'LicenciaMP', 'ConceptoS'],
                ),
                [
                    'AND',
                    ('wage_type.provision_cancellation', '!=', None),
                ],
            ],
        ]

        order = [('payroll.employee', 'DESC'), ('payroll', 'ASC')]
        payroll_lines = PayrollLine.search_read(dom_line,
                                                fields_names=fields_lines,
                                                order=order)
        for line in payroll_lines:
            key = str(line['payroll.']['employee']) + '_' + \
                str(line['payroll.']['contract'])
            cls.values_without_move(line, wage_type_default, res, key)

        total = [line['subtotal'] for line in res.values()]
        suma = sum(total)
        report_context['records'] = res.values()
        report_context['company'] = Company(data['company'])
        report_context['total'] = suma

        return report_context

    def values_without_move(line, wage_type_default, res, key):
        PayrollLine = Pool().get('staff.payroll.line')
        Staff_event_liquidation = Pool().get('staff.event-staff.liquidation')
        staff_lines = {}
        validate = True
        total = 0
        staff_lines_event = []
        concept = line['wage_type.']['type_concept']
        concept_electronic = line['wage_type.']['type_concept_electronic']
        other_health_retirement = line['wage_type.']['excluded_payroll_electronic']

        if concept == 'holidays' and validate:
            (staff_line,) = PayrollLine.search([('id', '=', line['id'])])
            wages = [
                (wage_type.wage_type.credit_account, wage_type)
                for wage_type in staff_line.payroll.contract.employee.mandatory_wages
                if wage_type.wage_type.type_concept in CONCEPT
            ]

            if staff_line.origin:
                event = Staff_event_liquidation.search(
                    [
                        ('event', '=', staff_line.origin.id),
                        (
                            'staff_liquidation.end_period',
                            '=',
                            staff_line.payroll.period.id,
                        ),
                    ]
                )

                for item in event:
                    staff_lines_event += [i for i in item.staff_liquidation.move.lines]

                for line_move in staff_lines_event:
                    for account_, wage in wages:
                        if line_move.account == account_:
                            staff_lines[wage.wage_type.type_concept] = {
                                'amount': line_move.credit
                            }

            if key in res.keys():
                if 'health' in staff_lines.keys():
                    res[key]['health_amount'] += staff_lines['health']['amount']
                    res[key]['subtotal'] += staff_lines['health']['amount']
                if 'retirement' in staff_lines.keys():
                    res[key]['retirement_amount'] += staff_lines['retirement']['amount']
                    res[key]['subtotal'] += staff_lines['retirement']['amount']
                validate = False

        if concept in wage_type_default and concept != 'salary':
            unit_formula = line['wage_type.']['unit_price_formula']

            if unit_formula:
                unit_formula = Decimal(
                    (unit_formula[unit_formula.index('*') + 1:]).strip()
                )
            else:
                unit_formula = 0

            expense_formula = line['wage_type.']['expense_formula']
            if expense_formula:
                expense_formula = Decimal(
                    (expense_formula[expense_formula.index('*') + 1:]).strip()
                )
                line_ = PayrollLine(line['id'])
                expense_amount = line_.get_expense_amount()
                res[key][concept + '_amount'] += expense_amount
                res[key]['subtotal'] += expense_amount
                total += expense_amount
            else:
                expense_formula = 0
            res[key][concept + '_name'] = (
                line['party.']['name'] if line['party.'] else ''
            )
            res[key][concept + '_rate'] = unit_formula + (
                expense_formula if expense_formula < 1 else 0
            )
            res[key][concept + '_code'] = (
                line['party.']['code'] if line['party.'] else ''
            )
            res[key]['subtotal'] += line['amount']
            total += line['amount']
            res[key][concept + '_amount'] += line['amount']

        elif concept_electronic in ['LicenciaR', 'LicenciaMP', 'ConceptoS']:
            res[key]['license_amount'] += line['amount']
            res[key]['variation'] -= line['amount']
        elif concept.startswith('incapacity'):
            res[key]['incapacity_amount'] += line['amount']
            res[key]['variation'] -= line['amount']
        elif concept == 'salary':
            res[key]['salary_amount'] += line['amount']
            res[key]['variation'] -= line['amount']
        elif concept == 'holidays':
            if line['wage_type.']['salary_constitute']:
                res[key]['variation'] -= line['amount']
                res[key]['holidays_amount'] += line['amount']
        elif concept == 'extras':
            res[key]['variation'] -= line['amount']
            res[key]['extras'] += line['amount']


class PayrollElectronicCDS(metaclass=PoolMeta):
    'Staff Payroll Electronic'
    __name__ = 'staff.payroll.electronic'

    def set_mergepayroll(self):
        pool = Pool()
        ElectronicPayrollLine = pool.get('staff.payroll.electronic.line')
        payrolls = self._get_payrolls_month()
        payrolls_lines = [list(p.lines)
                          for p in payrolls if hasattr(p, 'lines')]
        payrolls_lines = list(chain(*payrolls_lines))
        liquidations = self._get_liquidations_month()
        liquidations_lines = [
            list(p.lines) for p in liquidations if hasattr(p, 'lines')
        ]
        liquidations_lines = list(chain(*liquidations_lines))
        wage_to_create = {}
        worked_days = sum(
            [p.worked_days for p in payrolls if hasattr(p, 'worked_days')]
        )
        self.worked_days = worked_days
        self.payrolls_relationship = payrolls
        self.liquidations_relationship = liquidations
        self.save()
        # wage_event = ['VacacionesComunes'] + WAGE_TYPE['Incapacidades'] + WAGE_TYPE['Licencias']
        list_concepts = list(dict(TYPE_CONCEPT_ELECTRONIC).keys())
        for line in payrolls_lines:
            concept = line.wage_type.type_concept_electronic
            concept_normal = line.wage_type.type_concept
            excluded = line.wage_type.excluded_payroll_electronic
            wage_exceptions = [
                'interest',
                'holidays',
                'unemployment',
                'bonus_service',
                'convencional_bonus',
            ]
            if (
                concept
                and line.quantity > 0
                and (
                    concept_normal not in wage_exceptions
                    or not line.wage_type.contract_finish
                )
                and not excluded
            ):
                wage_id = line.wage_type.id
                sequence = list_concepts.index(concept)
                if wage_id not in wage_to_create:
                    wage_to_create[wage_id] = {
                        'payroll': self,
                        'sequence': sequence,
                        'wage_type': line.wage_type,
                        'description': line.description,
                        'quantity': round(line.quantity, 2),
                        'unit_value': abs(line.unit_value),
                        'uom': line.wage_type.uom,
                        'amount': abs(line.amount),
                        'party': line.party,
                        'lines_payroll': [
                            (
                                'add',
                                [
                                    line.id,
                                ],
                            )
                        ],
                    }
                    if concept in EXTRAS.keys():
                        field = line.wage_type.type_concept_electronic
                        # field = field[0].lower()
                        relation_extras = self._get_lines_extras(field)
                        wage_to_create[wage_id].update(
                            {'assitants_line': [('add', relation_extras)]}
                        )
                else:
                    wage_to_create[wage_id]['lines_payroll'][0][1].append(
                        line.id)
                    wage_to_create[wage_id]['quantity'] += round(
                        line.quantity, 2)
                    wage_to_create[wage_id]['amount'] += abs(line.amount)

        for wage in liquidations_lines:
            concept = wage.wage.type_concept_electronic
            if concept:
                days = wage.days or 0
                wage_id = wage.wage.id
                sequence = list_concepts.index(concept)
                if wage_id not in wage_to_create:
                    wage_to_create[wage_id] = {
                        'payroll': self,
                        'sequence': sequence,
                        'wage_type': wage.wage,
                        'description': wage.description,
                        'quantity': days,
                        'unit_value': abs(wage.amount),
                        'uom': wage.wage.uom,
                        'amount': abs(wage.amount),
                        'party': wage.party,
                    }
                else:
                    wage_to_create[wage_id]['quantity'] += days
                    wage_to_create[wage_id]['amount'] += abs(wage.amount)
        # print(wage_to_create.values())
        ElectronicPayrollLine.create(wage_to_create.values())
        return 'end'

    def _get_lines_extras(self, field=None):
        if field:
            field = CONCEPT_ACCESS.get(field)
        pool = Pool()
        Access = pool.get('staff.access')
        payrolls = self.payrolls_relationship
        value = Decimal('0.0')
        accesses = Access.search(
            [
                ('payroll', 'in', payrolls),
            ]
        )
        for a in accesses:
            print(a, field)
            if getattr(a, field) == value:
                accesses.remove(a)
        return accesses


class PayrollGlobalStart(metaclass=PoolMeta):
    'Consolidated Payroll View'
    __name__ = 'staff.payroll_global.start'

    analytic_account = fields.Many2One(
        'analytic_account.account', 'Analytic Account')

    account = fields.Selection('get_wage_types', 'Account')

    @staticmethod
    def get_wage_types():
        pool = Pool()
        WageType = pool.get('staff.wage_type')
        wage_types = WageType.search(['type_concept', '=', 'salary'])
        return [
            (str(wt.debit_account.id), wt.name) for wt in wage_types if wt.debit_account
        ]


class PayrollGlobal(metaclass=PoolMeta):
    'Consolidated Payroll Wizard'
    __name__ = 'staff.payroll.global'

    def do_print_(self, action):
        end_period_id = None
        department_id = None
        analytic_account_id = None
        account_id = None

        if self.start.end_period:
            end_period_id = self.start.end_period.id
        if self.start.department:
            department_id = self.start.department.id
        if self.start.analytic_account:
            analytic_account_id = self.start.analytic_account.id
        if self.start.account:
            account_id = self.start.account

        data = {
            'ids': [],
            'company': self.start.company.id,
            'start_period': self.start.start_period.id,
            'end_period': end_period_id,
            'analytic_account': analytic_account_id,
            'account': account_id,
            'department': department_id,
            'include_finished': self.start.include_finished,
        }
        return action, data


class PayrollGlobalReport(Report, metaclass=PoolMeta):
    'Consolidated Payroll Report'
    __name__ = 'staff.payroll.global_report'

    @classmethod
    def get_context(cls, records, header, data):
        '''Function to build report'''

        report_context = Report.get_context(records, header, data)
        pool = Pool()
        user = pool.get('res.user')(Transaction().user)
        Payroll = pool.get('staff.payroll')
        Period = pool.get('staff.payroll.period')
        Department = pool.get('company.department')
        PayrollLine = Pool().get('staff.payroll.line')

        parties = {}
        sum_total_deductions = []
        sum_gross_payments = []
        sum_net_payment = []
        dom_periods = []

        account_id = None
        analytic_account_id = None

        start_period = Period(data['start_period'])
        if data['end_period']:
            end_period = Period(data['end_period'])
            dom_periods.extend(
                [
                    ('start', '>=', start_period.start),
                    ('end', '<=', end_period.end),
                ]
            )
        else:
            dom_periods.append(('id', '=', start_period.id))

        periods = Period.search(dom_periods)
        dom_pay = cls.get_domain_payroll(data)
        dom_pay.append(
            ('period', 'in', [p.id for p in periods]),
        )
        dom_pay.append(
            ('state', 'in', ['processed', 'posted', 'draft']),
        )
        if data['department']:
            dom_pay.append(
                [
                    'AND',
                    [
                        'OR',
                        [
                            ('employee.department', '=', data['department']),
                            ('department', '=', None),
                        ],
                        [
                            ('department', '=', data['department']),
                        ],
                    ],
                ]
            )
            department = Department(data['department']).name
        else:
            department = 'TODOS LOS DEPARTAMENTOS'

        if not data['include_finished']:
            dom_pay.append(('contract.state', '!=', 'finished'))

        # Build domain to filter by accounts
        if data['analytic_account']:
            analytic_account_id = data['analytic_account']
            lines = PayrollLine.search(
                [
                    ('analytic_accounts.account.id', '=', analytic_account_id),
                    ('payroll.date_effective', '>=', start_period.start),
                    ('payroll.date_effective', '<=', end_period.end),
                    ('wage_type.type_concept', '=', 'salary'),
                ]
            )
            if not lines:
                raise UserError(
                    'Error', 'No se encontro informacion asociada.')

            line_list = list({_line for _line in lines})
            dom_pay.append(('lines', 'in', line_list))

        # Define account if selected in view
        if data['account']:
            account_id = data['account']
            payroll_lines = PayrollLine.search(
                [('wage_type.debit_account.id', '=', account_id)]
            )
            if payroll_lines:
                lines = list([line.id for line in payroll_lines])
                dom_pay.append(('lines', 'in', lines))

        payrolls = Payroll.search(dom_pay)
        if not payrolls:
            raise UserError('Error', 'No se encontro informacion asociada.')

        periods_number = len(periods)
        default_vals = cls.default_values()
        payments = [
            'salary',
            'transport',
            'extras',
            'food',
            'bonus',
            'commission',
            'incapacity_less_to_2_days',
            'incapacity_greater_to_2_days',
            'incapacity_arl',
        ]
        deductions = [
            'health',
            'retirement',
            'tax',
            'syndicate',
            'fsp',
            'acquired_product',
        ]

        for payroll in payrolls:
            party_health = ''
            party_retirement = ''

            employee_id = payroll.employee.id

            if employee_id not in parties.keys():
                position_employee = (
                    payroll.employee.position.name if payroll.employee.position else ''
                )
                position_contract = (
                    payroll.contract.position.name
                    if payroll.contract and payroll.contract.position
                    else ''
                )
                parties[employee_id] = default_vals.copy()
                parties[employee_id]['employee_code'] = payroll.employee.code
                parties[employee_id]['employee'] = payroll.employee.party.name
                parties[employee_id][
                    'employee_id_number'
                ] = payroll.employee.party.id_number
                if payroll.employee.party_health:
                    party_health = payroll.employee.party_health.name
                if payroll.employee.party_retirement:
                    party_retirement = payroll.employee.party_retirement.name
                parties[employee_id]['party_health'] = party_health
                parties[employee_id]['party_retirement'] = party_retirement
                parties[employee_id]['basic_salary'] = (
                    payroll.contract.get_salary_in_date(payroll.end)
                )
                parties[employee_id]['employee_position'] = (
                    position_contract or position_employee or ''
                )
                parties[employee_id]['account'] = None
                parties[employee_id]['analytic_account'] = None

            for line in payroll.lines:
                if line.wage_type.type_concept_electronic == 'Dotacion'\
                        or line.wage_type.type_concept_electronic == 'ViaticoManuAlojNS':
                    continue

                if parties[employee_id]['account'] is None:
                    if line.wage_type.type_concept == 'salary':
                        parties[employee_id][
                            'account'
                        ] = line.wage_type.debit_account.code

                if parties[employee_id]['analytic_account'] is None:
                    if line.wage_type.type_concept == 'salary':
                        analytic_account = line.analytic_accounts
                        if analytic_account:
                            for analytic in analytic_account:
                                if analytic.account is not None:
                                    code = analytic.account.code
                                    name = analytic.account.name
                                    analytic_name = f'{code}-{name}'
                                    parties[employee_id][
                                        'analytic_account'
                                    ] = analytic_name

                if line.wage_type.type_concept in (payments + deductions):
                    concept = line.wage_type.type_concept
                else:
                    if (
                        line.wage_type.definition == 'payment'
                        and line.wage_type.receipt
                    ):
                        concept = 'others_payments'
                    elif (
                        line.wage_type.definition == 'deduction'
                        or line.wage_type.definition == 'discount'
                        and line.wage_type.receipt
                    ):
                        concept = 'others_deductions'
                    else:
                        concept = line.wage_type.type_concept

                if not concept:
                    raise UserError(
                        'ERROR', f'El concepto no existe {line.wage_type.name}'
                    )

                parties[employee_id][concept] += line.amount
            parties[employee_id]['worked_days'] += Decimal(
                payroll.worked_days_effective
            )
            parties[employee_id]['gross_payments'] += payroll.gross_payments
            parties[employee_id]['total_deductions'] += payroll.total_deductions
            parties[employee_id]['net_payment'] += payroll.net_payment
            sum_gross_payments.append(payroll.gross_payments)
            sum_total_deductions.append(payroll.total_deductions)
            sum_net_payment.append(payroll.net_payment)

        employee_dict = {e['employee']: e for e in parties.values()}

        report_context['records'] = sorted(
            employee_dict.items(), key=lambda t: t[0])
        report_context['department'] = department
        report_context['periods_number'] = periods_number
        report_context['start_period'] = start_period
        report_context['end_period'] = end_period
        report_context['company'] = user.company
        report_context['user'] = user
        report_context['sum_gross_payments'] = sum(sum_gross_payments)
        report_context['sum_net_payment'] = sum(sum_net_payment)
        report_context['sum_total_deductions'] = sum(sum_total_deductions)
        return report_context


class PayrollSheetStart(metaclass=PoolMeta):
    'Comprehensive Payroll View'
    __name__ = 'staff.payroll.sheet.start'

    analytic_account = fields.Many2One(
        'analytic_account.account', 'Analytic Account')

    account = fields.Selection('get_wage_types', 'Account')

    @staticmethod
    def get_wage_types():
        pool = Pool()
        WageType = pool.get('staff.wage_type')
        wage_types = WageType.search(['type_concept', '=', 'salary'])
        return [
            (str(wt.debit_account.id), wt.name) for wt in wage_types if wt.debit_account
        ]


class PayrollSheet(metaclass=PoolMeta):
    'Comprehensive Payroll Wizard'
    __name__ = 'staff.payroll.sheet'

    def do_print_(self, action):
        analytic_account_id = None
        account_id = None

        if self.start.analytic_account:
            analytic_account_id = self.start.analytic_account.id
        if self.start.account:
            account_id = self.start.account

        periods = [p.id for p in self.start.periods]
        data = {
            'ids': [],
            'analytic_account': analytic_account_id,
            'account': account_id,
            'company': self.start.company.id,
            'periods': periods,
        }
        return action, data


class PayrollSheetReport(Report, metaclass=PoolMeta):
    'Comprehensive Payroll Report'
    __name__ = 'staff.payroll.sheet_report'

    @classmethod
    def get_context(cls, records, header, data):
        '''Function to build data to report'''

        report_context = Report.get_context(records, header, data)
        pool = Pool()
        user = pool.get('res.user')(Transaction().user)
        Payroll = pool.get('staff.payroll')
        Period = pool.get('staff.payroll.period')
        PayrollLine = Pool().get('staff.payroll.line')

        sum_total_deductions = []
        sum_gross_payments = []
        sum_net_payment = []
        new_objects = []
        list_date_periods = []
        periods_names = ''
        item = 0

        dom_payroll = cls.get_domain_payroll(data)
        if data['periods']:
            periods = Period.browse(data['periods'])
            # Order periodios asc by date
            sorted_periods = sorted(periods, key=lambda period: period.start)

            # save the date in a list
            list_date_periods = [period.start for period in sorted_periods]
            periods_names = [p.name + ' / ' for p in periods]
            dom_payroll.append([('period', 'in', data['periods'])])

        # Build domain to filter by accounts
        if data['analytic_account']:
            analytic_account_id = data['analytic_account']
            lines = PayrollLine.search(
                [
                    ('analytic_accounts.account.id', '=', analytic_account_id),
                    ('payroll.date_effective', '>=', list_date_periods[0]),
                    ('wage_type.type_concept', '=', 'salary'),
                ]
            )
            if not lines:
                raise UserError(
                    'Error', 'No se encontro informacion asociada.')

            line_list = list({_line for _line in lines})
            dom_payroll.append(('lines', 'in', line_list))

        # Define account if selected in view
        if data['account']:
            account_id = data['account']
            payroll_lines = PayrollLine.search(
                [('wage_type.debit_account.id', '=', account_id)]
            )
            if payroll_lines:
                lines = list([line.id for line in payroll_lines])
                dom_payroll.append(('lines', 'in', lines))

        payrolls = Payroll.search(
            dom_payroll, order=[
                ('employee.party.name', 'ASC'), ('period.name', 'ASC')]
        )
        if not payrolls:
            raise UserError('Error', 'No se encontro informacion asociada.')

        default_vals = cls.default_values()
        for payroll in payrolls:
            item += 1
            project = ''

            values = copy.deepcopy(default_vals)
            values['item'] = item
            values['employee'] = payroll.employee.party.name
            values['id_number'] = payroll.employee.party.id_number
            position_name, position_contract = '', ''
            if payroll.employee.position:
                position_name = payroll.employee.position.name
            if payroll.contract and payroll.contract.position:
                position_contract = payroll.contract.position.name
            values['position'] = position_contract or position_name
            values['department'] = (
                payroll.employee.department.name if payroll.employee.department else ''
            )
            values['company'] = user.company.party.name
            values['legal_salary'] = payroll.contract.get_salary_in_date(
                payroll.end)
            values['period'] = payroll.period.name
            salary_day_in_date = payroll.contract.get_salary_in_date(
                payroll.end) / 30
            values['salary_day'] = salary_day_in_date
            values['salary_hour'] = (
                (salary_day_in_date / 8) if salary_day_in_date else 0
            )
            values['worked_days'] = payroll.worked_days
            values['gross_payment'] = payroll.gross_payments
            values['account'] = None
            values['analytic_account'] = None

            # Add compatibility with staff contracting
            if hasattr(payroll, 'project'):
                if payroll.project:
                    project = payroll.project.name

            if hasattr(payroll.employee, 'project_contract'):
                if (
                    payroll.employee.project_contract
                    and payroll.employee.project_contract.reference
                ):
                    project = payroll.employee.project_contract.reference
            values['project'] = project

            values.update(cls._prepare_lines(payroll, values))
            sum_gross_payments.append(payroll.gross_payments)
            sum_total_deductions.append(payroll.total_deductions)
            sum_net_payment.append(payroll.net_payment)
            new_objects.append(values)

        report_context['records'] = new_objects
        report_context['periods'] = periods_names
        report_context['company'] = user.company.rec_name
        report_context['user'] = user
        report_context['sum_gross_payments'] = sum(sum_gross_payments)
        report_context['sum_net_payment'] = sum(sum_net_payment)
        report_context['sum_total_deductions'] = sum(sum_total_deductions)
        return report_context

    @classmethod
    def _prepare_lines(cls, payroll, vals):
        for line in payroll.lines:
            # Add account
            if vals['account'] is None and line.wage_type.type_concept == 'salary':
                vals['account'] = line.wage_type.debit_account.code

            if (
                vals['analytic_account'] is None
                and line.wage_type.type_concept == 'salary'
            ):
                analytic_account = line.analytic_accounts
                if analytic_account:
                    for analytic in analytic_account:
                        if analytic.account is not None:
                            code = analytic.account.code
                            name = analytic.account.name
                            analytic_name = f'{code}-{name}'
                            vals['analytic_account'] = analytic_name

            concept = line.wage_type.type_concept
            amount = line.amount
            definition = line.wage_type.definition
            if definition == 'payment':
                if concept == 'extras':
                    vals['total_extras'].append(amount)
                    for e in EXTRAS_CORE:
                        if e.upper() in line.wage_type.name:
                            vals[e].append(line.quantity or 0)
                            vals['cost_' + e].append(amount)
                            break
                elif concept in FIELDS_AMOUNT:
                    vals[concept].append(amount)
                else:
                    vals['other'].append(amount)
            elif definition == 'deduction':
                vals['total_deduction'].append(amount)
                if concept == 'health':
                    vals['health'].append(amount)
                    vals['health_provision'].append(line.get_expense_amount())
                elif concept == 'retirement':
                    vals['retirement'].append(amount)
                    vals['retirement_provision'].append(
                        line.get_expense_amount())
                else:
                    if concept == 'fsp':
                        vals['fsp'].append(amount)
                    elif concept == 'tax':
                        vals['retefuente'].append(amount)
                    else:
                        vals['other_deduction'].append(amount)
            else:
                vals['discount'].append(amount)
                print('Warning: Line no processed... ', line.wage_type.name)

        for key in SHEET_SUMABLES:
            vals[key] = sum(vals[key])

        vals['gross_payment'] = sum(
            [
                vals['salary'],
                vals['total_extras'],
                vals['transport'],
                vals['food'],
                vals['bonus'],
            ]
        )

        vals['net_payment'] = vals['gross_payment'] - vals['total_deduction']
        vals['ibc'] = vals['gross_payment']
        vals['total_benefit'] = sum(
            [
                vals['unemployment'],
                vals['interest'],
                vals['holidays'],
                vals['bonus_service'],
            ]
        )
        vals['total_parafiscales'] = sum(
            [vals['box_family'], vals['sena'], vals['icbf']]
        )
        vals['total_ssi'] = vals['retirement_provision'] + vals['risk']
        vals['total_cost'] = sum(
            [
                vals['total_ssi'],
                vals['box_family'],
                vals['gross_payment'],
                vals['total_benefit'],
            ]
        )
        return vals


class PayrollGroupStart(metaclass=PoolMeta):
    'Payroll Group Start'
    __name__ = 'staff.payroll_group.start'

    @fields.depends('period', 'description')
    def on_change_period(self):
        if not self.period:
            return
        if self.period.description:
            self.description = self.period.description


class PayrollGroup(metaclass=PoolMeta):
    'Payroll Group'
    __name__ = 'staff.payroll_group'

    def transition_open_(self):
        pool = Pool()
        Employee = pool.get('company.employee')
        Payroll = pool.get('staff.payroll')

        payrolls_period = Payroll.search([
            ('period', '=', self.start.period.id),
        ])

        employee_w_payroll = [p.employee.id for p in payrolls_period]
        dom_employees = self.get_employees_dom(employee_w_payroll)
        payroll_to_create = []
        employees = Employee.search(dom_employees, limit=400)
        get_values = self.get_values
        search_contract_on_period = Payroll.search_contract_on_period
        period = self.start.period
        start = period.start
        end = period.end
        for employee in employees:
            if employee.id in employee_w_payroll:
                continue

            contract = search_contract_on_period(employee, period)
            if not contract:
                continue

            values = get_values(contract, start, end)
            payroll_to_create.append(values)

        wages = [
            (wage_type, None, None) for wage_type in self.start.wage_types
        ]
        PayrollCreate = Payroll.create
        if payroll_to_create:
            for payroll in payroll_to_create:
                try:
                    payroll_, = PayrollCreate([payroll])
                    payroll_.set_preliquidation({}, None)
                    if wages:
                        payroll_._create_payroll_lines(wages, None, {})
                    Transaction().commit()
                except Exception as error:
                    print('Fallo al crear nomina : ',
                        payroll_.employee.party.name)
                    print(error)
        return 'end'
