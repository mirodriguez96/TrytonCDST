from decimal import Decimal
from datetime import timedelta, datetime, date

from trytond.model import ModelSQL, ModelView, fields, Workflow
from trytond.pool import Pool, PoolMeta
from trytond.wizard import (Wizard, StateView, Button, StateReport,
                            StateTransition)
from sql.aggregate import Sum
from sql.operators import Between
from trytond.pyson import Eval, Or, Not, If, Bool
from trytond.transaction import Transaction
from trytond.report import Report
from trytond.exceptions import UserError, UserWarning

from .it_supplier_noova import ElectronicPayrollCdst
from itertools import chain
import mimetypes
from email.encoders import encode_base64
from email.header import Header
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.nonmultipart import MIMENonMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, getaddresses
from trytond.modules.company import CompanyReport
from trytond.sendmail import sendmail
from trytond.config import config

from dateutil import tz

from_zone = tz.gettz('UTC')
to_zone = tz.gettz('America/Bogota')

CONCEPT_ACCESS = {
    'HED': 'hedo',
    'HEN': 'heno',
    'HRN': 'hedf',
    'HEDDF': 'recf',
    'HENDF': 'henf',
    'HRDDF': 'reco',
    'HRNDF': 'recf',
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

EXTRAS = {
    'HED': {
        'code': 1,
        'percentaje': '25.00'
    },
    'HEN': {
        'code': 2,
        'percentaje': '75.00'
    },
    'HRN': {
        'code': 3,
        'percentaje': '35.00'
    },
    'HEDDF': {
        'code': 4,
        'percentaje': '100.00'
    },
    'HRDDF': {
        'code': 5,
        'percentaje': '75.00'
    },
    'HENDF': {
        'code': 6,
        'percentaje': '150.00'
    },
    'HRNDF': {
        'code': 7,
        'percentaje': '110.00'
    },
}

_ZERO = Decimal('0.0')
WORKDAY_DEFAULT = Decimal(7.83)
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
    '12': 'DICIEMBRE'
}

STATE = {
    'invisible': Not(Bool(Eval('access_register'))),
    'readonly': Bool(Eval('state') != 'draft'),
}

try:
    import html2text
except ImportError:
    html2text = None

HTML_EMAIL = """<!DOCTYPE html>
<html>
<head><title>%(subject)s</title></head>
<body>%(body)s<br/>
<hr style="width: 2em; text-align: start; display: inline-block"/><br/>
%(signature)s</body>
</html>"""


def _get_emails(value):
    "Return list of email from the comma separated list"
    return [e for n, e in getaddresses([value]) if e]


_TYPES_PAYMENT = [('220', '220'), ('225', '225'), ('238', '238'),
                  ('240', '240'), ('239', '239'), ('320', '320'),
                  ('325', "325"), ('820', '820'), ('920', '920')]

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
    'HED': {
        'code': 1,
        'percentaje': '25.00'
    },
    'HEN': {
        'code': 2,
        'percentaje': '75.00'
    },
    'HRN': {
        'code': 3,
        'percentaje': '35.00'
    },
    'HEDDF': {
        'code': 4,
        'percentaje': '100.00'
    },
    'HRDDF': {
        'code': 5,
        'percentaje': '75.00'
    },
    'HENDF': {
        'code': 6,
        'percentaje': '150.00'
    },
    'HRNDF': {
        'code': 7,
        'percentaje': '110.00'
    },
}

_TYPES_BANK_ACCOUNT = [('S', 'S'), ('D', 'D')]

_TYPE_DOCUMENT = {
    '13': '1',  #Cedula
    '22': '2',  #Cedula de extranjeria
    '31': '3',  #Nit
    '12': '4',  #Tarjeta de identidad
    '41': '5',  #Pasaporte
}

_TYPE_TRANSACTION = [
    ('25', 'Pago en efectivo'),
    ('27', 'Abono a cuenta corriente'),
    ('36', 'Pago cheque gerencia'),
    ('37', 'Abono a cuenta de ahorros'),
    ('40', 'Efectivo seguro (visa pagos o tarjeta prepago)'),
]


class Bank(metaclass=PoolMeta):
    'Bank'
    __name__ = 'bank'
    bank_code_sap = fields.Char(
        'Bank code SAP',
        help='bank code used for the bancolombia payment template')


class WageType(metaclass=PoolMeta):
    __name__ = 'staff.wage_type'
    non_working_days = fields.Boolean(
        'Non-working days',
        states={'invisible': (Eval('type_concept') != 'holidays')})

    excluded_payroll_electronic = fields.Boolean(
        'Excluded Payroll',
        states={'invisible': (Eval('type_concept') != 'holidays')})

    pay_liqudation = fields.Boolean('Pay Liquidation',
                                    states={
                                        'invisible':
                                        (Eval('type_concept_electronic')
                                         not in ['Deuda', 'Libranza'])
                                    })


class Liquidation(metaclass=PoolMeta):
    __name__ = "staff.liquidation"
    sended_mail = fields.Boolean('Sended Email')

    # Funcion encargada de contar los días festivos
    def count_holidays(self, start_date, end_date, event):
        sundays = 0
        if event.category.wage_type.type_concept == 'holidays' and event.category.wage_type.type_concept_electronic == 'VacacionesCompensadas':
            return sundays
        day = timedelta(days=1)
        # Iterar sobre todas las fechas dentro del rango
        current_date = start_date
        while current_date <= end_date:
            if current_date.weekday() == 6:  # 6 representa el domingo
                sundays += 1
            current_date += day
        Holiday = Pool().get('staff.holidays')
        holidays = Holiday.search([
            ('holiday', '>=', start_date),
            ('holiday', '<=', end_date),
        ],
                                  count=True)
        return sundays + holidays

    def _validate_holidays_lines(self, event):
        line = None
        for l in self.lines:
            if l.wage.type_concept == 'holidays':
                line = l
        if not line:
            return
        if event.edit_amount:
            amount_day = event.amount
        else:
            amount_day = (self.contract.salary / 30)
        # amount = amount_day * event.days_of_vacations
        holidays = self.count_holidays(event.start_date, event.end_date, event)
        workdays = event.days - holidays
        amount_workdays = round(amount_day * workdays, 2)
        amount_holidays = round(amount_day * holidays, 2)
        # line, = self.lines
        move_lines = []
        value = 0
        for move_line in line.move_lines:
            value += move_line.credit
            move_lines.append(move_line)
            if value > amount_workdays:
                break
        line.move_lines = move_lines
        if value != amount_workdays:
            Adjustment = Pool().get('staff.liquidation.line_adjustment')
            adjustment = amount_workdays - value
            if adjustment > 0:
                adjustment_account = line.wage.credit_account
            else:
                adjustment_account = line.wage.debit_account
            line.adjustments = [
                Adjustment(account=adjustment_account,
                           amount=adjustment,
                           description=line.description)
            ]
            line.amount = amount_workdays
            line.days = workdays
        line.save()
        if amount_holidays > 0:
            WageType = Pool().get('staff.wage_type')
            wage_type = WageType.search([('non_working_days', '=', True)],
                                        limit=1)
            if not wage_type:
                raise UserError('Wage Type',
                                'missing wage_type (non_working_days)')
            wage_type, = wage_type
            value = {
                'sequence':
                wage_type.sequence,
                'wage':
                wage_type.id,
                'description':
                wage_type.name,
                'amount':
                amount_holidays,
                'account':
                wage_type.debit_account,
                'days':
                holidays,
                'adjustments': [('create', [{
                    'account':
                    wage_type.debit_account.id,
                    'amount':
                    amount_holidays,
                    'description':
                    wage_type.debit_account.name,
                }])]
            }
            self.write([self], {'lines': [('create', [value])]})

    def create_move(self):
        pool = Pool()
        Move = pool.get('account.move')
        MoveLine = pool.get('account.move.line')
        Period = pool.get('account.period')
        if self.move:
            return

        move_lines, grouped = self.get_moves_lines()
        if move_lines:
            period_id = Period.find(self.company.id,
                                    date=self.liquidation_date)
            move, = Move.create([{
                'journal': self.journal.id,
                'origin': str(self),
                'period': period_id,
                'date': self.liquidation_date,
                'description': self.description,
                'lines': [('create', move_lines)],
            }])
            self.write([self], {'move': move.id})
            for ml in move.lines:
                if ml.account.id not in grouped.keys() or (
                        ml.account.type.statement not in ('balance')):
                    continue
                to_reconcile = [ml]
                to_reconcile.extend(grouped[ml.account.id]['lines'])
                if len(to_reconcile) > 1:
                    MoveLine.reconcile(set(to_reconcile))
            Move.post([move])

    def get_moves_lines(self):
        lines_moves = []
        to_reconcile = []
        grouped = {}
        amount = []
        validate = True
        validate_health = True
        result = ''
        wages = [
            wage_type for wage_type in self.employee.mandatory_wages
            if wage_type.wage_type.type_concept == 'retirement'
            and self.kind == 'holidays'
        ]
        wages_health = [
            wage_type for wage_type in self.employee.mandatory_wages
            if wage_type.wage_type.type_concept == 'health'
            and self.kind == 'holidays'
        ]
        for line in self.lines:
            if line.move_lines:
                for moveline in line.move_lines:
                    to_reconcile.append(moveline)
                    account_id = moveline.account.id
                    amount_line = moveline.debit - moveline.credit * -1
                    if account_id not in grouped.keys():
                        grouped[account_id] = {
                            'amount': [],
                            'description': line.description,
                            'lines': [],
                        }
                    grouped[account_id]['amount'].append(amount_line)
                    grouped[account_id]['lines'].append(moveline)
                    amount.append(amount_line)
            elif line.wage.definition == 'discount':
                account_id = line.account.id
                if account_id not in grouped.keys():
                    grouped[account_id] = {
                        'amount': [],
                        'description': line.description,
                        'lines': [],
                    }
                grouped[account_id]['amount'].append(line.amount)
                amount.append(line.amount)
            for adjust in line.adjustments:
                key = adjust.account.id
                if key not in grouped.keys():
                    grouped[key] = {
                        'amount': [],
                        'description': adjust.description,
                        'lines': [],
                    }
                    if hasattr(adjust,
                               'analytic_account') and adjust.analytic_account:
                        grouped[key]['analytic'] = adjust.analytic_account
                grouped[adjust.account.id]['amount'].append(adjust.amount)
                amount.append(adjust.amount)

        for account_id, values in grouped.items():
            party_payment = None
            for wage_health in wages_health:
                if wage_health.wage_type.credit_account.name == values[
                        'description']:
                    party_payment = wage_health.party.id
                    validate_health = False

            for wage in wages:
                if validate:
                    if wage.wage_type.credit_account.name == values[
                            'description']:
                        validate = False
                        result = self._prepare_line(
                            values['description'],
                            wages[0].wage_type.debit_account.id,
                            debit=round(self.gross_payments * Decimal(0.12),
                                        2),
                            credit=_ZERO,
                            analytic=values.get('analytic', None))

                        party_payment = wage.party.id
                        values['amount'] = [
                            round(self.gross_payments * Decimal(0.16), 2) * -1
                        ]

            _amount = sum(values['amount'])
            debit = _amount
            credit = _ZERO
            lines_moves.append(
                self._prepare_line(values['description'],
                                   account_id,
                                   debit=debit,
                                   credit=credit,
                                   party_to_pay_concept=party_payment,
                                   analytic=values.get('analytic', None)))

        if result != '':
            lines_moves.append(result)

        if lines_moves:
            lines_moves.append(
                self._prepare_line(
                    self.description,
                    self.account,
                    credit=sum(amount),
                    party_to_pay=self.party_to_pay,
                ))
        return lines_moves, grouped

    def _prepare_line(self,
                      description,
                      account_id,
                      debit=_ZERO,
                      credit=_ZERO,
                      party_to_pay=None,
                      analytic=None,
                      party_to_pay_concept=None):
        if debit < _ZERO:
            credit = debit
            debit = _ZERO
        elif credit < _ZERO:
            debit = credit
            credit = _ZERO

        credit = abs(credit)
        debit = abs(debit)

        party_id = self.employee.party.id
        if party_to_pay:
            party_id = self.party_to_pay.id
        if party_to_pay_concept:
            party_id = party_to_pay_concept

        res = {
            'description': description,
            'debit': debit,
            'credit': credit,
            'account': account_id,
            'party': party_id,
        }

        if analytic:
            res['analytic_lines'] = [('create', [{
                'debit': res['debit'],
                'credit': res['credit'],
                'account': analytic.id,
                'date': self.liquidation_date
            }])]
        return res

    def set_liquidation_lines(self):
        super(Liquidation, self).set_liquidation_lines()
        if self.kind == 'holidays':
            self.process_loans_to_pay_holidays()

    def process_loans_to_pay_holidays(self):
        pool = Pool()
        MoveLine = pool.get('account.move.line')
        LoanLine = pool.get('staff.loan.line')
        LiquidationLine = pool.get('staff.liquidation.line')
        dom = [
            ('loan.wage_type', '!=', None),
            ('loan.party', '=', self.employee.party.id),
            ('state', 'in', ['pending', 'partial']),
            ('loan.wage_type.pay_liqudation', '=', True),
            ('maturity_date', '>=', self.start_period.start),
            ('maturity_date', '<=', self.end_period.end),
        ]

        lines_loan = LoanLine.search(dom)
        for m in lines_loan:

            move_lines = MoveLine.search([
                ('origin', 'in', ['staff.loan.line,' + str(m)]),
            ])
            party = m.loan.party_to_pay.id if m.loan.party_to_pay else None
            res = self.get_line_(m.loan.wage_type,
                                 m.amount * -1,
                                 1,
                                 m.loan.account_debit.id,
                                 party=party)
            res['move_lines'] = [('add', move_lines)]
            res['liquidation'] = self.id
            line_, = LiquidationLine.create([res])
            m.amount = abs(m.amount * -1)
            m.save()
            LoanLine.write([m], {'state': 'paid', 'origin': line_})


class PayrollPaymentStartBcl(ModelView):
    'Payroll Payment Start'
    __name__ = 'staff.payroll_payment_bancolombia.start'
    period = fields.Many2One('staff.payroll.period', 'Period', required=True)
    party = fields.Function(fields.Many2One('party.party', 'Party Bank'),
                            'on_change_with_party')
    company = fields.Many2One('company.company', 'Company', required=True)
    department = fields.Many2One('company.department', 'Department')
    payment_type = fields.Selection(_TYPES_PAYMENT,
                                    'Type payment',
                                    required=True)
    send_sequence = fields.Char('Shipping sequence', size=1)
    reference = fields.Char('Reference', required=True, size=9)
    type_transaction = fields.Selection(_TYPE_TRANSACTION,
                                        'Type of transaction',
                                        required=True)
    bank = fields.Many2One('bank.account',
                           'Bank Account',
                           domain=[('owners', '=', Eval('party'))],
                           depends=['party'],
                           required=True)

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
    start = StateView('staff.payroll_payment_bancolombia.start',
                      'conector.payroll_payment_start_bancolombia_view_form', [
                          Button('Cancel', 'end', 'tryton-cancel'),
                          Button('Print', 'print_', 'tryton-ok', default=True),
                      ])
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
                nothin_accounts = nothin_accounts + f"EL empleado {payroll.employee.party.name} no tiene una cuenta asociada  \n"
                continue
            # for ref in accouns_bank:
            #     if bank == ref.bank:
            values = values.copy()
            values['employee'] = payroll.employee.party.name
            type_document = payroll.employee.party.type_document
            if type_document not in _TYPE_DOCUMENT:
                raise UserError(
                    'error: type_document',
                    f'{type_document} not found for type_document bancolombia')
            values['type_document'] = _TYPE_DOCUMENT[type_document]
            values['id_number'] = str(
                payroll.employee.party.number_pay_payroll
            ) + str(
                payroll.employee.party.id_number
            ) if type_document == '41' else payroll.employee.party.id_number
            values['email'] = payroll.employee.party.email
            bank_code_sap = None
            if payroll.employee.party.bank_accounts:
                bank_code_sap = payroll.employee.party.bank_accounts[
                    0].bank.bank_code_sap
            values['bank_code_sap'] = bank_code_sap
            values['bank_account'] = payroll.employee.party.bank_account
            type_account_payment_party = Type_bank_numbers.search([
                ('number', '=', str(payroll.employee.party.bank_account))
            ])
            values['type_account_payment'] = _TYPES_BANK_ACCOUNT_.get(
                type_account_payment_party[0].type_string)
            net_payment = Decimal(round(payroll.net_payment, 0))
            values['net_payment'] = net_payment
            if values['id_number'] in id_numbers:
                if not duplicate_employees:
                    duplicate_employees = values['employee']
                else:
                    duplicate_employees += ", " + values['employee']
            id_numbers.append(values['id_number'])
            result.append(values)
            #     break
            # else:
            #     continue

            # Se valida si se encontraron nóminas del mismo empleado en el periodo seleccionado y se muestra una alerta.
        if duplicate_employees or nothin_accounts:
            Warning = pool.get('res.user.warning')
            warning_name = "warning_payment_report_bancolombia"
            if duplicate_employees:
                duplicate_employees = "Existen empleados con más de 1 nómina en el mismo periodo. "\
                    f"Revisar: {duplicate_employees}"
            if Warning.check(warning_name):
                raise UserWarning(
                    warning_name,
                    f"{duplicate_employees} \n {nothin_accounts}.")

        # Se construye diccionario a retornar
        type_bank_account = _TYPES_BANKS.get(
            str(self.start.bank.numbers[0].type_string))
        data = {
            'company': {
                'id_number': self.start.company.party.id_number,
                'name': self.start.company.party.name,
                'bank_account': self.start.bank.numbers[0].number
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
    party = fields.Function(fields.Many2One('party.party', 'Party Bank'),
                            'on_change_with_party')
    department = fields.Many2One('company.department', 'Department')
    payment_type = fields.Selection(_TYPES_PAYMENT,
                                    'Type payment',
                                    required=True)
    send_sequence = fields.Char('Send sequence', size=1)
    # type_bank_account = fields.Selection(
    #     _TYPES_BANK_ACCOUNT, 'Type of account to be debited', required=True)
    reference = fields.Char('Reference', required=True, size=9)
    type_transaction = fields.Selection(_TYPE_TRANSACTION,
                                        'Type of transaction',
                                        required=True)
    kind = fields.Selection([
        ('contract', 'Contract'),
        ('bonus_service', 'Bonus Service'),
        ('interest', 'Interest'),
        ('unemployment', 'Unemployment'),
        ('holidays', 'Vacation'),
        ('convencional_bonus', 'Convencional Bonus'),
    ],
                            'Kind',
                            required=True)
    date = fields.Date('Date', required=True)
    bank = fields.Many2One('bank.account',
                           'Bank Account',
                           domain=[('owners', '=', Eval('party'))],
                           depends=['party'],
                           required=True)

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
        'conector.payment_liquidation_start_bancolombia_view_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Print', 'print_', 'tryton-ok', default=True),
        ])
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
        print(clause)
        liquidations = Liquidation.search(clause)
        new_objects = []
        values = {}
        print(liquidations)
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
                    0].bank.bank_code_sap
            values['bank_code_sap'] = bank_code_sap
            type_account_payment_party = Type_bank_numbers.search([
                ('number', '=', str(liquidation.employee.party.bank_account))
            ])
            values['type_account_payment'] = _TYPES_BANK_ACCOUNT_.get(
                type_account_payment_party[0].type_string)
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
                             'Start Period',
                             required=True)
    subject = fields.Char('Subject', size=60, required=True)
    cc = fields.Char('Cc', help='separate emails with commas')

    @staticmethod
    def default_company():
        return Transaction().context.get('company')


# Asistente encargado de recolectar las nóminas y enviarlas por email
class PayslipSend(Wizard):
    'Payslip Send'
    __name__ = 'staff.payroll.payslip_send'
    start = StateView('staff.payroll_payslip_send.start',
                      'conector.payroll_payslip_send_view_form', [
                          Button('Cancel', 'end', 'tryton-cancel'),
                          Button('Send', 'send_', 'tryton-ok', default=True),
                      ])
    send_ = StateTransition()

    def transition_send_(self):
        pool = Pool()
        model_name = 'staff.payroll'
        # Email = pool.get('ir.email')
        Payroll = pool.get(model_name)
        ActionReport = pool.get('ir.action.report')
        report, = ActionReport.search([('report_name', '=', model_name)])
        reports = [report.id]
        subject = self.start.subject
        dom = [('company', '=', self.start.company.id),
               ('period', '=', self.start.period.id),
               ('state', 'in', ['processed', 'posted']),
               ('sended_mail', '=', False)]
        if self.start.department:
            dom.append(('department', '=', self.start.department.id))
        payrolls = Payroll.search(dom)
        for payroll in payrolls:
            #email = 'clancheros@cdstecno.com'
            email = payroll.employee.party.email
            recipients_secondary = ''
            if self.start.cc:
                recipients_secondary = self.start.cc
            record = [model_name, payroll.id]
            try:
                send_mail(to=email,
                          cc=recipients_secondary,
                          bcc='',
                          subject=subject,
                          body='___',
                          files=None,
                          record=record,
                          reports=reports,
                          attachments=None)
                Payroll.write([payroll], {'sended_mail': True})
                Transaction().connection.commit()
            except Exception as e:
                raise UserError(
                    f'No mail sent, check employee email {payroll.employee.rec_name}',
                    str(e))

        return 'end'


class SettlementSendStart(ModelView):
    'Settlement Send Start'
    __name__ = 'staff.payroll_settlement_send.start'
    company = fields.Many2One('company.company', 'Company', required=True)
    department = fields.Many2One('company.department', 'Department')
    date = fields.Date('Date', required=True)
    subject = fields.Char('Subject', size=60, required=True)
    cc = fields.Char('Cc', help='separate emails with commas')
    kind = fields.Selection([
        ('contract', 'Contract'),
        ('bonus_service', 'Bonus Service'),
        ('interest', 'Interest'),
        ('unemployment', 'Unemployment'),
        ('holidays', 'Vacation'),
        ('convencional_bonus', 'Convencional Bonus'),
    ],
                            'Kind',
                            required=True)

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
    fiscalyear = fields.Many2One('account.fiscalyear',
                                 'Fiscal Year',
                                 required=True)
    subject = fields.Char('Subject', size=60, required=True)
    employees = fields.Many2Many('company.employee',
                                 None,
                                 None,
                                 'Employees',
                                 required=True)
    cc = fields.Char('Cc', help='separate emails with commas')

    @staticmethod
    def default_company():
        return Transaction().context.get('company')

    @staticmethod
    def default_fiscalyear():
        FiscalYear = Pool().get('account.fiscalyear')
        return FiscalYear.find(Transaction().context.get('company'),
                               exception=False)


class SendCertificateOfIncomeAndWithholding(Wizard):
    'Certificate Send'
    __name__ = 'staff.payroll.certificates_send'
    start = StateView('staff.payroll_certificates_send.start',
                      'conector.payroll_certificates_send_view_form', [
                          Button('Cancel', 'end', 'tryton-cancel'),
                          Button('Send', 'send_', 'tryton-ok', default=True),
                      ])
    send_ = StateTransition()

    def transition_send_(self):
        pool = Pool()
        model_name = 'company.employee'
        # Email = pool.get('ir.email')
        ActionReport = pool.get('ir.action.report')
        report, = ActionReport.search([
            ('report_name', '=', 'staff.payroll.income_withholdings_report')
        ])
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
            body = f"""<html>
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

            </html>"""

            dic = {
                'ids': [],
                'company': company,
                'start_period': start_date,
                'end_period': end_date,
                'employees': [employe.id],
                'action_id': reports[0]
            }

            email = employe.party.email
            record = [model_name, employe]
            try:
                send_mail_certificate(to=email,
                                      cc=recipients_secondary,
                                      bcc='',
                                      subject=subject,
                                      body=body,
                                      files=None,
                                      record=record,
                                      reports=reports,
                                      attachments=None,
                                      dic=dic)

            except Exception as e:
                raise UserError(
                    f'No mail sent, check employee email {employe.rec_name}',
                    str(e))

        return 'end'


# Funcion que agrega el consecutivo a los certificados de ingresos y retenciones
# def get_number_sequence():
#         pool = Pool()
#         Configuration = pool.get('staff.configuration')
#         configuration = Configuration(1)
#         if not configuration.staff_certificate_sequence:
#             raise MissingSecuenceCertificate(gettext('conector.msg_sequence_missing'))
#         seq = configuration.staff_certificate_sequence.get()
#         return seq

# def get_number_sequence_certificate(seq):
#         pool = Pool()
#         Configuration = pool.get('staff.configuration')
#         configuration = Configuration(1)
#         print('get_number_sequence_certificate')
#         cursor = Transaction().connection.cursor()
#         sequence = configuration.staff_certificate_sequence
#         print(sequence)
#         nextNUmber = (int(seq) + 1)
#         cursor.execute(f"UPDATE ir_sequence SET number_next_internal = {nextNUmber} WHERE id = {sequence.id}")
#         return 'OK'


# Copia funcion 'send' del modelo 'ir.email' modificando para enviar de forma individual (no transactional) el envio de certificados de ingresos y retencion
def send_mail_certificate(to='',
                          cc='',
                          bcc='',
                          subject='',
                          body='',
                          files=None,
                          record=None,
                          reports=None,
                          attachments=None,
                          dic=None):

    pool = Pool()
    Email = pool.get('ir.email')
    User = pool.get('res.user')
    ActionReport = pool.get('ir.action.report')
    Attachment = pool.get('ir.attachment')
    transaction = Transaction()
    Model = pool.get(record[0])
    records = Model(record[1])
    user = User(transaction.user)
    # seq = get_number_sequence()
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
        for report_id in (reports or []):
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
            attachment.add_header('Content-Disposition',
                                  'attachment',
                                  filename=('utf-8', '', name))
            msg.attach(attachment)
    else:
        msg = content
    msg['From'] = from_ = config.get('email', 'from')
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
    to_addrs = list(
        filter(
            None,
            map(str.strip,
                _get_emails(to) + _get_emails(cc) + _get_emails(bcc))))
    sendmail(from_, to_addrs, msg, server=None, strict=True)
    email = Email(recipients=to,
                  recipients_secondary=cc,
                  recipients_hidden=bcc,
                  addresses=[{
                      'address': a
                  } for a in to_addrs],
                  subject=subject,
                  body=body,
                  resource=records)
    email.save()
    with Transaction().set_context(_check_access=False):
        attachments_ = []
        for name, data in files:
            attachments_.append(
                Attachment(resource=email, name=name, data=data))
        Attachment.save(attachments_)

    return email


# Asistente encargado de recolectar las nóminas y enviarlas por email
class SettlementSend(Wizard):
    'Settlement Send'
    __name__ = 'staff.payroll.settlement_send'
    start = StateView('staff.payroll_settlement_send.start',
                      'conector.payroll_settlement_send_view_form', [
                          Button('Cancel', 'end', 'tryton-cancel'),
                          Button('Send', 'send_', 'tryton-ok', default=True),
                      ])
    send_ = StateTransition()

    def transition_send_(self):
        pool = Pool()
        model_name = 'staff.liquidation.report'
        Liquidation = pool.get('staff.liquidation')
        ActionReport = pool.get('ir.action.report')
        report, = ActionReport.search([('report_name', '=', model_name)])
        reports = [report.id]
        subject = self.start.subject
        print(self.start.kind)
        dom = [('company', '=', self.start.company.id),
               ('liquidation_date', '=', self.start.date),
               ('kind', '=', self.start.kind), ('sended_mail', '=', False)]
        if self.start.department:
            dom.append(('department', '=', self.start.department.id))
        liquidations = Liquidation.search(dom)

        for liquidation in liquidations:
            if liquidation.state == 'confirmed' or liquidation.state == 'posted':
                #email = 'gisela.sanchez@cdstecno.com'
                #email = 'andres.genes@cdstecno.com'
                email = liquidation.employee.party.email
                recipients_secondary = ''
                if self.start.cc:
                    recipients_secondary = self.start.cc
                record = ['staff.liquidation', liquidation.id]
                try:
                    send_mail(to=email,
                              cc=recipients_secondary,
                              bcc='',
                              subject=subject,
                              body='___',
                              files=None,
                              record=record,
                              reports=reports,
                              attachments=None)
                    Liquidation.write([liquidation], {'sended_mail': True})
                    Transaction().connection.commit()
                except Exception as e:
                    raise UserError(
                        f'No mail sent, check employee email {liquidation.employee.rec_name}',
                        str(e))
            else:
                pass
        return 'end'


# Copia funcion 'send' del modelo 'ir.email' modificando para enviar de forma individual (no transactional)
def send_mail(to='',
              cc='',
              bcc='',
              subject='',
              body='',
              files=None,
              record=None,
              reports=None,
              attachments=None):
    pool = Pool()
    Email = pool.get('ir.email')
    User = pool.get('res.user')
    ActionReport = pool.get('ir.action.report')
    Attachment = pool.get('ir.attachment')
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
        for report_id in (reports or []):
            report = ActionReport(report_id)
            Report = pool.get(report.report_name, type='report')
            ext, content, _, title = Report.execute([record.id], {
                'action_id': report.id,
            })
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
            attachment.add_header('Content-Disposition',
                                  'attachment',
                                  filename=('utf-8', '', name))
            msg.attach(attachment)
    else:
        msg = content
    msg['From'] = from_ = config.get('email', 'from')
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
    to_addrs = list(
        filter(
            None,
            map(str.strip,
                _get_emails(to) + _get_emails(cc) + _get_emails(bcc))))
    sendmail(from_, to_addrs, msg, server=None, strict=True)
    email = Email(recipients=to,
                  recipients_secondary=cc,
                  recipients_hidden=bcc,
                  addresses=[{
                      'address': a
                  } for a in to_addrs],
                  subject=subject,
                  body=body,
                  resource=record)
    email.save()
    with Transaction().set_context(_check_access=False):
        attachments_ = []
        for name, data in files:
            attachments_.append(
                Attachment(resource=email, name=name, data=data))
        Attachment.save(attachments_)
    return email


class StaffEvent(metaclass=PoolMeta):
    __name__ = "staff.event"
    analytic_account = fields.Char(
        'Analytic account code',
        states={'readonly': (Eval('state') != 'draft')})

    edit_amount = fields.Boolean('Edit Amount',
                                 states={
                                     'invisible':
                                     Not(Bool(Eval('absenteeism'))),
                                     'readonly':
                                     Bool(Eval('state') != 'draft'),
                                 },
                                 depends=['absenteeism', 'state'])

    staff_liquidation = fields.Many2One('staff.liquidation', 'liquidation')

    access_register = fields.Boolean('Access register',
                                     states={
                                         'invisible':
                                         Not(Bool(Eval('amount'))),
                                         'readonly':
                                         Bool(Eval('state') != 'draft'),
                                     },
                                     depends=['amount', 'state'])

    enter_timestamp = fields.DateTime(
        'Enter',
        states=STATE,
        domain=[
            If(
                Eval('exit_timestamp') & Eval('enter_timestamp'),
                ('enter_timestamp', '<=', Eval('exit_timestamp')), ()),
        ],
        depends=['exit_timestamp', 'access_register', 'state'],
    )

    exit_timestamp = fields.DateTime(
        'Exit',
        states=STATE,
        domain=[
            If(
                Eval('enter_timestamp') & Eval('exit_timestamp'),
                ('exit_timestamp', '>=', Eval('enter_timestamp')), ()),
        ],
        depends=['enter_timestamp', 'access_register', 'state'],
    )

    # @fields.depends('access_register')
    # def on_change_with_time(self):
    #     if not self.access_register:
    #         return None

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

    @fields.depends('contract', 'days_of_vacations')
    def on_change_with_amount(self):
        if self.contract and self.days_of_vacations:
            amount = round(self.contract.salary / 30, 2)
            return amount
        else:
            return self.amount

    @classmethod
    def __setup__(cls):
        super(StaffEvent, cls).__setup__()
        cls._buttons.update({
            'create_liquidation': {
                'invisible':
                Or(
                    Eval('state') != 'done',
                    Not(Eval('is_vacations')),
                ),
            }
        })

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
        Warning = pool.get('res.user.warning')
        Configuration = pool.get('staff.configuration')(1)
        Liquidation = pool.get('staff.liquidation')
        Period = pool.get('staff.payroll.period')
        for event in records:
            warning_name = 'mywarning,%s' % event
            if Warning.check(warning_name):
                raise UserWarning(warning_name,
                                  f"Se creara una liquidacion de vacaciones")
            liquidation = Liquidation()
            liquidation.employee = event.employee
            liquidation.contract = event.contract
            liquidation.kind = 'holidays'
            start_period = Period.search([
                ('start', '>=', event.contract.start_date),
                ('end', '<=', event.contract.start_date)
            ])
            if not start_period:
                start_period = Period.search([],
                                             order=[('end', 'ASC')],
                                             limit=1)
            liquidation.start_period = start_period[0]
            end_period, = Period.search([('start', '<=', event.start_date),
                                         ('end', '>=', event.start_date)])
            liquidation.end_period = end_period
            liquidation.liquidation_date = event.event_date
            liquidation.description = event.description
            liquidation.account = Configuration.liquidation_account
            liquidation.save()
            # Se procesa la liquidación
            Liquidation.compute_liquidation([liquidation])

            wages = [
                wage_type for wage_type in event.employee.mandatory_wages
                if wage_type.wage_type.type_concept in CONCEPT or wage_type.
                wage_type.type_concept_electronic in CONCEPT_ELECTRONIC
            ]
            if wages:
                if event.edit_amount:
                    amount_day = event.amount
                else:
                    amount_day = (liquidation.contract.salary / 30)
                workdays = event.days
                amount_workdays = round(amount_day * workdays * Decimal(0.04),
                                        2)

                for concept in wages:
                    amount = amount_workdays * -1
                    if concept.fix_amount:
                        amount = concept.fix_amount * -1
                    value = {
                        'sequence':
                        concept.wage_type.sequence,
                        'wage':
                        concept.wage_type.id,
                        'description':
                        concept.wage_type.name,
                        'amount':
                        amount,
                        'account':
                        concept.wage_type.credit_account,
                        'days':
                        event.days,
                        'party_to_pay':
                        concept.party,
                        'adjustments': [('create', [{
                            'account':
                            concept.wage_type.credit_account.id,
                            'amount':
                            amount_workdays * -1,
                            'description':
                            concept.wage_type.credit_account.name,
                        }])]
                    }
                    liquidation.write([liquidation],
                                      {'lines': [('create', [value])]})

            liquidation._validate_holidays_lines(event)
            event.staff_liquidation = liquidation
            event.save()

    @classmethod
    def process_event(cls, events):
        super(StaffEvent, cls).process_event(events)
        pool = Pool()
        Contract = pool.get('staff.contract')
        Access = pool.get('staff.access')

        for event in events:
            if event.category and event.is_vacations:
                contract = event.contract
                Contract.write([contract],
                               {'events_vacations': [('add', [event])]})

            if event.category and event.access_register and event.enter_timestamp and event.exit_timestamp:
                for i in range(0, event.days):
                    print(event.category, event.employee, i)
                    is_access = Access.search([
                        ('enter_timestamp', '<=',
                         event.enter_timestamp + timedelta(days=i)),
                        ('exit_timestamp', '>=',
                         event.exit_timestamp + timedelta(days=i)),
                        ('employee', '=', event.employee)
                    ])
                    print(is_access)
                    if not is_access:
                        to_save = Access()
                        to_save.employee = event.employee
                        to_save.payment_method = 'extratime'
                        to_save.enter_timestamp = event.enter_timestamp + timedelta(
                            days=i)
                        to_save.exit_timestamp = event.exit_timestamp + timedelta(
                            days=i)
                        to_save.line_event = event
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
            if event.category and event.contract and event.id in event.contract.events_vacations:
                contract = event.contract
                Contract.write([contract],
                               {'events_vacations': [('remove', [event])]})
            if is_access:
                Access.delete(is_access)


class Payroll(metaclass=PoolMeta):
    __name__ = "staff.payroll"

    @classmethod
    def __setup__(cls):
        super(Payroll, cls).__setup__()

    # Se hereda y modifica la función preliquidation para añadir las cuentas analiticas en las liquidaciones que la tenga
    def set_preliquidation(self, extras, discounts=None):
        super(Payroll, self).set_preliquidation(extras, discounts)
        PayrollLine = Pool().get('staff.payroll.line')
        if not hasattr(PayrollLine, 'analytic_accounts'):
            return
        AnalyticAccount = Pool().get('analytic_account.account')
        for line in self.lines:
            if not line.is_event:
                continue
            if line.origin.analytic_account:
                for acc in line.analytic_accounts:
                    try:
                        analytic_account, = AnalyticAccount.search([
                            ('code', '=', line.origin.analytic_account)
                        ])
                        acc.write([acc], {'account': analytic_account.id})
                    except:
                        wage = line.wage_type.rec_name
                        raise UserError(
                            'staff_event.msg_error_on_analytic_account', wage)
        self.save()

    def process_loans_to_pay(self, LoanLine, PayrollLine, MoveLine):
        #super(Payroll, self).process_loans_to_pay(self, LoanLine, PayrollLine, MoveLine)
        dom = [
            ('loan.party', '=', self.employee.party.id),
            ('loan.wage_type', '!=', None),
            ('maturity_date', '<=', self.end),
            ('state', 'in', ['pending', 'partial']),
        ]
        lines_loan = LoanLine.search(dom)
        for m, r in zip(lines_loan, range(len(lines_loan))):
            party = m.loan.party_to_pay if m.loan.party_to_pay else None
            move_lines = MoveLine.search([
                ('origin', 'in', ['staff.loan.line,' + str(m)]),
            ])
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

            line, = PayrollLine.create([to_create])
            LoanLine.write([m], {'state': 'paid', 'origin': line})


class PayrollLine(metaclass=PoolMeta):
    __name__ = "staff.payroll.line"

    # Se reescribe el metodo para que aumente támbien el valor de la cuenta analitica a crear
    def update_move_line(self, move_line, values):
        if values['debit']:
            move_line['debit'] += values['debit']
            if 'analytic_lines' in move_line:
                move_line['analytic_lines'][0][1][0]['debit'] += values[
                    'debit']
        if values['credit']:
            move_line['credit'] += values['credit']
            if 'analytic_lines' in move_line:
                move_line['analytic_lines'][0][1][0]['credit'] += values[
                    'credit']

        return move_line


class PayrollReport(CompanyReport):
    __name__ = 'staff.payroll'

    #Metodo para heredar el metodo de generacion del reporte.
    @classmethod
    def get_context(cls, records, header, data):
        report_context = super().get_context(records, header, data)
        Loans = Pool().get('staff.loan')
        party = ''
        amount = 0.0
        for record in report_context['records']:
            party = record.employee.party.name
        #busco el prestamo de ese tercero
        loans = Loans.search([('party', '=', party), ('state', '=', 'posted')])
        #Si no hay prestamo limpio la variable
        if not loans:
            for keys in report_context['records']:
                keys.total_cost = 0.0
        else:
            for loan in loans:
                for line in loan.lines:
                    #busco que las lineas que tenga esten pendientes de pago y las guardo.
                    if line.state == 'pending':
                        amount += float(line.amount)

        #asigno el monto en una variable que no se usa
        for keys in report_context['records']:
            keys.total_cost = amount
        return report_context


class PayrollExo2276(metaclass=PoolMeta):
    __name__ = "staff.payroll_exo2276.report"

    @classmethod
    def _prepare_lines(cls, payrolls, vals, party_id):
        result = super(PayrollExo2276,
                       cls)._prepare_lines(payrolls, vals, party_id)
        payroll_ids = [payroll.id for payroll in payrolls]
        Lines = Pool().get('staff.payroll.line')
        lines = Lines.search([
            ('payroll', 'in', payroll_ids),
            ('payroll.employee.party', '=', party_id),
            ('wage_type.type_concept', 'like', 'incapacity%'),
        ])

        result['incapacity'] = 0
        for line in lines:
            result['incapacity'] += line.amount

        return result


class PayrollElectronic(metaclass=PoolMeta):
    'Staff Payroll Electronic'
    __name__ = 'staff.payroll.electronic'

    @classmethod
    def __setup__(cls):
        super(PayrollElectronic, cls).__setup__()
        cls._buttons.update({
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
                'invisible':
                Or(
                    Eval('electronic_state') == 'authorized',
                    Eval('state') != 'processed',
                )
            },
        })

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


class StaffAccessRests(ModelSQL, ModelView):
    'Staff Access Rests'
    __name__ = 'staff.access.rests'
    access = fields.Many2One('staff.access', 'rests', 'Rests', required=True)
    start = fields.DateTime('Start')
    end = fields.DateTime('End')
    amount = fields.Function(fields.Numeric('Amount', digits=(3, 2)),
                             'on_change_with_amount')
    pay = fields.Boolean('Pay')

    @fields.depends('start', 'end')
    def on_change_with_amount(self, name=None):
        if self.start and self.end:
            # if self.start <  self.access.enter_timestamp \
            #     or self.start > self.access.exit_timestamp \
            #     or self.end < self.start:
            #     raise UserError("Date rest", "invalid_date")
            return self.compute_timedelta(self.start, self.end)
        return None

    def compute_timedelta(self, start, end):
        delta = end - start
        res = float(delta.seconds) / 3600
        res = Decimal(str(round(res, 2)))
        return res


class StaffAccess(metaclass=PoolMeta):
    __name__ = 'staff.access'
    rests = fields.One2Many('staff.access.rests', 'access', 'Rests')
    line_event = fields.Reference('Origin',
                                  selection='get_origin',
                                  select=True,
                                  readonly=True)

    @staticmethod
    def _get_origin():
        'Return list of Model names for origin Reference'
        return ['staff.event', 'ir.cron']

    @classmethod
    def get_origin(cls):
        Model = Pool().get('ir.model')
        models = cls._get_origin()
        models = Model.search([
            ('model', 'in', models),
        ])
        return [(None, '')] + [(m.model, m.name) for m in models]

    #
    @fields.depends('rests')
    def on_change_rests(self):
        amount = 0
        for rest in self.rests:
            if rest.amount and not rest.pay:
                amount += rest.amount
        self.rest = amount

    @classmethod
    def delete(cls, instances):
        to_delete = []
        for instance in instances:
            if instance.rests:
                to_delete += list(instance.rests)
        if to_delete:
            Rests = Pool().get('staff.access.rests')
            Rests.delete(to_delete)
        super(StaffAccess, cls).delete(instances)

    def _get_extras(self,
                    employee,
                    enter_timestamp,
                    exit_timestamp,
                    start_rest,
                    end_rest,
                    rest,
                    workday=None,
                    restday=None):
        pool = Pool()
        Workday = pool.get('staff.workday_definition')
        Holiday = pool.get('staff.holidays')
        Contract = pool.get('staff.contract')

        start_date = (enter_timestamp + timedelta(hours=5)).date()
        contracts = Contract.search([
            'OR',
            [
                ('employee', '=', employee.id),
                ('start_date', '<=', start_date),
                ('finished_date', '>=', start_date),
            ],
            [
                ('employee', '=', employee.id),
                ('start_date', '<=', start_date),
                ('finished_date', '=', None),
            ]
        ],
                                    limit=1,
                                    order=[('start_date', 'DESC')])

        if not contracts:
            raise UserError(f"staff_access_extratime {start_date}",
                            f"missing_contract {employee.party.name}")

        position_ = contracts[0].position
        if not enter_timestamp or not exit_timestamp \
                or not position_ or not position_.extras:
            return {
                'ttt': 0,
                'het': 0,
                'hedo': 0,
                'heno': 0,
                'reco': 0,
                'recf': 0,
                'dom': 0,
                'hedf': 0,
                'henf': 0
            }

        holidays = [day.holiday for day in Holiday.search([])]

        #Ajuste UTC tz para Colombia timestamp [ -5 ]
        enter_timestamp = enter_timestamp.replace(tzinfo=from_zone)
        enter_timestamp = enter_timestamp.astimezone(to_zone)

        exit_timestamp = exit_timestamp.replace(tzinfo=from_zone)
        exit_timestamp = exit_timestamp.astimezone(to_zone)

        # Contexto de cambio de turno
        weekday_number = int(enter_timestamp.strftime("%u"))
        weekday_ = WEEK_DAYS[weekday_number]
        if not workday:
            # position = employee.contract.position or employee.position
            day_work = Workday.search([
                ('weekday', '=', weekday_),
                ('position', '=', position_.id),
            ])
            if day_work and enter_timestamp.date() not in holidays:
                workday, restday = day_work[0].workday, day_work[0].restday
            else:
                workday = WORKDAY_DEFAULT
        if not restday:
            restday = RESTDAY_DEFAULT
            print("Warning: Using default restday!")
        print(workday, 'workday...........', restday)

        restday_effective = 0
        if rest:
            restday_effective = Decimal(rest)

        # Verifica si el usuario sale o entra un festivo
        enter_holiday = False
        exit_holiday = False

        if (enter_timestamp.weekday() == 6) or (enter_timestamp.date()
                                                in holidays):
            enter_holiday = True
        if (exit_timestamp.weekday() == 6) or (exit_timestamp.date()
                                               in holidays):
            exit_holiday = True

        # To convert datetime enter/exit to decimal object
        enterd = self._datetime2decimal(enter_timestamp)
        exitd = self._datetime2decimal(exit_timestamp)

        all_rests = []
        for _rest in self.rests:
            start_rest = _rest.start
            end_rest = _rest.end
            if start_rest and end_rest:
                start_rest_timestamp = start_rest.replace(tzinfo=from_zone)
                start_rest_timestamp = start_rest_timestamp.astimezone(to_zone)
                end_rest_timestamp = end_rest.replace(tzinfo=from_zone)
                end_rest_timestamp = end_rest_timestamp.astimezone(to_zone)

                start_rest = self._datetime2decimal(start_rest_timestamp)
                end_rest = self._datetime2decimal(end_rest_timestamp)
                all_rests.append((start_rest, end_rest))

        # To check whether date change inside of shift
        if enter_timestamp.date() == exit_timestamp.date():
            date_change = False
        else:
            date_change = True

        liquid = self._calculate_shift(enterd, exitd, date_change,
                                       enter_holiday, exit_holiday, workday,
                                       restday, all_rests, restday_effective)

        res = {
            'ttt': liquid['ttt'],
            'het': liquid['het'],
            'reco': liquid['reco'],
            'recf': liquid['recf'],
            'dom': liquid['dom'],
            'hedo': liquid['hedo'],
            'heno': liquid['heno'],
            'hedf': liquid['hedf'],
            'henf': liquid['henf'],
        }
        return res

    def _calculate_shift(self, enterd, exitd, date_change, enter_holiday,
                         exit_holiday, workday, restday, all_rests,
                         restday_effective):
        ttt = het = hedo = heno = reco = recf = dom = hedf = henf = _ZERO

        if date_change:
            exitd += 24

        # T.T.T.
        ttt = exitd - enterd - restday_effective
        if ttt <= 0:
            ttt = 0
            return {
                'ttt': ttt,
                'het': het,
                'hedo': hedo,
                'heno': heno,
                'reco': reco,
                'recf': recf,
                'dom': dom,
                'hedf': hedf,
                'henf': henf
            }

        # H.E.T.
        workday_legal = Decimal(workday - restday)
        # workday_effective = workday - restday_effective?
        if ttt > workday_legal:
            het = ttt - workday_legal

        contador = enterd  # Contador que comienza con la hora de entrada
        total = 0  # Sumador que comienza en Cero
        in_extras = False
        cicle = True
        rest_moment = False
        index_rest = 0
        # ---------------------- main iter -----------------------------
        while cicle:
            # Ciclo Inicial
            if contador == enterd:
                if int(enterd) == int(exitd):
                    # Significa que entro y salio en la misma hora
                    sumador = exitd - contador
                    cicle = False
                else:
                    # Significa que salio en una hora distinta a la que entro
                    if int(enterd) == enterd:
                        # Si entra en una hora en punto, suma una hora
                        sumador = 1
                    else:
                        # Si entra en una hora no en punto suma el parcial de la hora
                        sumador = (int(enterd) + 1) - enterd
            elif contador >= int(exitd):
                # Ciclo Final
                sumador = exitd - int(exitd)
                cicle = False
            else:
                # Ciclo Intermedio
                sumador = 1

            contador = contador + sumador
            if index_rest < len(all_rests):
                start_rest, end_rest = all_rests[index_rest]
                if start_rest and end_rest:
                    if contador == start_rest:
                        pass
                    elif (int(contador) -
                          1) == int(start_rest) and not rest_moment:
                        # Ajusta sumador por empezar descanso
                        rest_moment = True
                        sumador = start_rest - (contador - 1)
                        if int(start_rest) == int(end_rest):
                            sumador, rest_moment, index_rest = self._get_all_rests(
                                index_rest, all_rests, contador)
                        #     index_rest += 1
                    elif contador >= start_rest and contador <= end_rest:
                        continue
                    elif (int(contador) - 1) == int(end_rest) and rest_moment:
                        # Ajusta sumador por terminar descanso
                        sumador = contador - end_rest
                        rest_moment = False
                        index_rest += 1
                    else:
                        pass

            total = total + sumador
            is_night = True
            if (6 < contador <= 21) or (30 < contador <= 46):
                is_night = False

            # Verifica si hay EXTRAS
            sum_partial_rec = 0

            if total > workday:
                # Se calcula el sumador para extras
                in_extras = True
                sum_extra = sumador
                if (total - sumador - restday) <= workday_legal:
                    sum_extra = (total - restday) - workday_legal
                    sum_partial_rec = sumador - sum_extra

                if (contador <= 24 and not enter_holiday) or \
                    (contador > 24 and not exit_holiday):
                    if is_night:
                        heno = self._get_sum(heno, sum_extra)
                    else:
                        hedo = self._get_sum(hedo, sum_extra)
                else:
                    if is_night:
                        henf = self._get_sum(henf, sum_extra)
                    else:
                        hedf = self._get_sum(hedf, sum_extra)

            # Verifica si hay DOM
            if not in_extras:
                if (enter_holiday and contador <= 24) or (exit_holiday
                                                          and contador > 24):
                    dom = self._get_sum(dom, sumador)
                    if dom >= round(Decimal(7.83), 2):
                        dom = round(Decimal(7.83), 2)

            # Verifica si hay REC
            if sum_partial_rec > 0:
                in_extras = False
                sum_rec = sum_partial_rec
            else:
                sum_rec = sumador

            if is_night and not in_extras:
                if (contador <= 24 and not enter_holiday) or \
                    (contador > 24 and not exit_holiday):
                    reco = self._get_sum(reco, sum_rec)
                else:
                    recf = self._get_sum(recf, sum_rec)

        if ttt >= 7.83 and dom > Decimal(0.0):
            dom = round(Decimal(7.83), 2)
        elif ttt <= 7.83 and dom > Decimal(0.0):
            dom = ttt

        # hedo = round(Decimal(ttt) - Decimal(7.83),2) if hedo != float(0) else float(0)
        # heno = round(Decimal(ttt) - Decimal(7.83),2) if heno != float(0) else float(0)
        # hedf = round(Decimal(ttt) - Decimal(7.83),2) if hedf != float(0) else float(0)
        # henf = round(Decimal(ttt) - Decimal(7.83),2) if henf != float(0) else float(0)

        return {
            'ttt': ttt,
            'het': round(het, 2),
            'hedo': round(het - heno, 2) if dom == 0 else hedo,
            'heno': round(heno, 2),
            'reco': reco,
            'recf': recf,
            'dom': dom,
            'hedf': round(het - henf, 2) if dom != 0 else hedf,
            'henf': round(henf, 2)
        }

        # return {'ttt': ttt, 'het': round(het,2), 'hedo': float(0) if hedo <= float(0) else hedo, 'heno': float(0) if heno <= float(0) else heno,
        #         'reco': reco, 'recf': recf, 'dom': dom, 'hedf': float(0) if hedf <= float(0) else hedf, 'henf': float(0) if henf <= float(0) else  henf}

    # Obtiene la suma de los descansos
    def _get_all_rests(self, index_rest, all_rests, contador):
        sumador = 1
        rest_moment = False
        for start_rest, end_rest in all_rests[index_rest:]:
            if (int(contador) - 1) == int(start_rest):
                rest_moment = True
                if int(start_rest) == int(end_rest):
                    sumador = sumador - (end_rest - start_rest)
                    rest_moment = False
                    index_rest += 1
        return sumador, rest_moment, index_rest


class ImportBiometricRecords(Wizard):
    'Import Biometric Records'
    __name__ = 'staff.access.import_biometric_records'

    start_state = 'parameters'
    parameters = StateView(
        'staff.access.import_biometric_records.parameters',
        'conector.import_biometric_records_parameters_view_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Import',
                   'import_biometric_records',
                   'tryton-go-next',
                   default=True)
        ])
    import_biometric_records = StateTransition()

    def transition_import_biometric_records(self):
        pool = Pool()
        Actualizacion = pool.get('conector.actualizacion')
        Warning = pool.get('res.user.warning')
        warning_name = 'warning_import_biometric_records'
        # event_time = datetime.strptime(self.parameters.day, '%Y-%m-%d')
        # print(event_time)
        event_time = datetime(self.parameters.day.year,
                              self.parameters.day.month,
                              self.parameters.day.day, 0, 0, 0)
        if Warning.check(warning_name):
            raise UserWarning(
                warning_name,
                f"Se importaran registros del biometrico en la fecha: {event_time}"
            )
        Actualizacion.import_biometric_access(event_time)
        return 'end'


class ImportBiometricRecordsParameters(ModelView):
    'Import Biometric Records Parameters'
    __name__ = 'staff.access.import_biometric_records.parameters'

    day = fields.Date('Day', required=True)


class StaffAccessView(ModelView):
    "Report Staff Access Start"
    __name__ = "staff.access_view_start"

    company = fields.Many2One('company.company', 'Company', required=True)
    from_date = fields.Date("From Date",
                            domain=[
                                If(
                                    Eval('to_date') & Eval('from_date'),
                                    ('from_date', '<=', Eval('to_date')), ()),
                            ],
                            depends=['to_date'],
                            required=True)
    to_date = fields.Date("To Date",
                          domain=[
                              If(
                                  Eval('from_date') & Eval('to_date'),
                                  ('to_date', '>=', Eval('from_date')), ()),
                          ],
                          depends=['from_date'],
                          required=True)

    @staticmethod
    def default_company():
        return Transaction().context.get('company')


class StaffAccessWizard(Wizard):
    'Report Staff Access Wizard'
    __name__ = 'staff.access_wizard'
    start = StateView('staff.access_view_start',
                      'conector.staff_access_report_form', [
                          Button('Cancel', 'end', 'tryton-cancel'),
                          Button('Print', 'print_', 'tryton-ok', default=True),
                      ])
    print_ = StateReport('staff.access_report')

    def do_print_(self, action):

        data = {
            'company': self.start.company.id,
            # 'fiscalyear': self.start.fiscalyear.name,
            'to_date': self.start.to_date,
            'from_date': self.start.from_date,
        }
        return action, data

    def transition_print_(self):
        return 'end'


class StaffAccessReport(Report):
    "Staff access report"
    __name__ = 'staff.access_report'

    @classmethod
    def get_date_fech(cls, date):
        result = ''
        if date not in ['Null', None]:
            date = str((date - timedelta(hours=5))).split(' ')
            result = date[1]

        return result

    @classmethod
    def get_context(cls, records, header, data):
        report_context = super().get_context(records, header, data)
        pool = Pool()
        Staff = pool.get('staff.access')
        StaffRestd = pool.get('staff.access.rests')
        Party = pool.get('party.party')
        Employee = pool.get('company.employee')
        Company = pool.get('company.company')
        cursor = Transaction().connection.cursor()

        #Asignacion de tabalas para extraccion de la data
        staff = Staff.__table__()
        staffRestd = StaffRestd.__table__()
        party = Party.__table__()
        employee = Employee.__table__()

        #Dato de fecha de inicio
        fechfinal = str(data['to_date']).split('-')
        datefinal = str(
            datetime(int(fechfinal[0]), int(fechfinal[1]), int(fechfinal[2]),
                     23, 59, 59))

        #Dato de fecha final para reporte
        fechini = str(data['from_date']).split('-')
        dateintitial = str(
            datetime(int(fechini[0]), int(fechini[1]), int(fechini[2])))

        #Condicionales para extraer los datos
        where = staff.enter_timestamp >= dateintitial
        where &= staff.exit_timestamp <= datefinal

        #Datos que seran extraidos desde la base de datos
        columns = [
            staff.id, party.name, party.id_number, staff.enter_timestamp,
            staff.exit_timestamp, staff.ttt, staff.rest, staffRestd.end,
            staffRestd.start
        ]

        #Consulta que retorna la informacion para el reporte de acceso diario
        select = staff.join(
            staffRestd, 'LEFT', condition=staff.id == staffRestd.access).join(
                employee, 'LEFT',
                condition=staff.employee == employee.id).join(
                    party, 'LEFT',
                    condition=party.id == employee.party).select(
                        *columns,
                        where=where,
                        order_by=[
                            party.id_number, staff.enter_timestamp,
                            staffRestd.start
                        ])

        cursor.execute(*select)

        record_dict = {}

        #Ciclo para generar la data para el informe, todo en formato diccionario
        for index, curso in enumerate(cursor):
            if curso[0] in record_dict:
                record_dict[curso[2], index] = {
                    'party': '',
                    'id_number': '',
                    'enter_timestamp': '',
                    'exit_timestamp': '',
                    'ttt': '',
                    'rest': '',
                    'end': cls.get_date_fech(
                        curso[7]
                    ),  # Funcion que toma solo la hora de la fecha obtenida en la base de datos
                    'start': cls.get_date_fech(curso[8]),
                }
            else:
                record_dict[curso[0]] = {
                    'party': curso[1],
                    'id_number': curso[2],
                    'enter_timestamp': str(curso[3] - timedelta(hours=5)),
                    'exit_timestamp': str(curso[4] - timedelta(hours=5)),
                    'ttt': curso[5],
                    'rest': curso[6],
                    'end': cls.get_date_fech(curso[7]),
                    'start': cls.get_date_fech(curso[8]),
                }

        report_context['records'] = record_dict.values()
        report_context['company'] = Company(data['company'])
        return report_context


# Reporte FRIGOECOL IBC
class PayrollIBCView(ModelView):
    'Payroll IBC View'
    __name__ = 'staff.payroll_ibc.start'
    company = fields.Many2One('company.company', 'Company', required=True)

    start_period = fields.Many2One('staff.payroll.period',
                                   'Start Period',
                                   required=True,
                                   domain=[('state', '!=', 'draft')],
                                   states={
                                       'invisible':
                                       ~Not(Eval('accomulated_month')),
                                       'required':
                                       ~Bool(Eval('accomulated_month'))
                                   },
                                   depends=['accomulated_month'])

    end_period = fields.Many2One('staff.payroll.period',
                                 'End Period',
                                 required=True,
                                 domain=[
                                     ('state', '!=', 'draft'),
                                 ],
                                 states={
                                     'invisible':
                                     ~Not(Eval('accomulated_month')),
                                     'required':
                                     ~Bool(Eval('accomulated_month'))
                                 },
                                 depends=['accomulated_month'])

    department = fields.Many2One('company.department', 'Department')

    accomulated_month = fields.Boolean(
        'accomulated Month',
        help='If this check is selected, it will accumulate by months',
        on_change_with='on_change_with_accomulated_month')

    accomulated_period = fields.Boolean(
        'accomulated Period',
        help='If this check is selected, it will accumulate by period',
        on_change_with='on_change_with_accomulated_period')

    fiscalyear = fields.Many2One('account.fiscalyear',
                                 'Fiscal Year',
                                 states={
                                     'invisible':
                                     ~Not(Eval('accomulated_period')),
                                     'required':
                                     ~Bool(Eval('accomulated_period'))
                                 },
                                 depends=['accomulated_period'])

    start_period_fiscalyear = fields.Many2One(
        'account.period',
        'Start Period',
        domain=[
            ('fiscalyear', '=', Eval('fiscalyear')),
            ('start_date', '<=', (Eval('end_period_fiscalyear'),
                                  'start_date')),
        ],
        states={
            'invisible': ~Not(Eval('accomulated_period')),
            'required': ~Bool(Eval('accomulated_period'))
        },
        depends=['fiscalyear', 'end_period_fiscalyear', 'accomulated_period'],
    )

    end_period_fiscalyear = fields.Many2One(
        'account.period',
        'End Period',
        domain=[('fiscalyear', '=', Eval('fiscalyear')),
                ('start_date', '>=', (Eval('start_period_fiscalyear'),
                                      'start_date'))],
        states={
            'invisible': ~Not(Eval('accomulated_period')),
            'required': ~Bool(Eval('accomulated_period'))
        },
        depends=[
            'fiscalyear', 'start_period_fiscalyear', 'accomulated_period'
        ],
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
    start = StateView('staff.payroll_ibc.start', 'conector.payroll_ibc_form', [
        Button('Cancel', 'end', 'tryton-cancel'),
        Button('Print', 'print_', 'tryton-ok', default=True),
    ])

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
            'accomulated': self.start.accomulated_month
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

        #Asignacion de tabalas para extraccion de la data
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
            'amount':
            Sum(staffPayrollLine.unit_value * staffPayrollLine.quantity),
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
        where &= Between(staffPayroll.start, data['start_period'],
                         data['end_period'])
        where &= contract.state == 'active'
        where &= contract.kind != 'learning'

        if data['department']:
            where &= staffPayroll.department == data['department']

        # Estructura de query para lanzar la consulta a la base de datos
        select = staffPayrollLine.join(
            staffPayroll,
            'LEFT',
            condition=staffPayroll.id == staffPayrollLine.payroll).join(
                staffWage,
                'LEFT',
                condition=staffWage.id == staffPayrollLine.wage_type).join(
                    employee,
                    'LEFT',
                    condition=employee.id == staffPayroll.employee).join(
                        party, 'LEFT',
                        condition=party.id == employee.party).join(
                            contract,
                            'LEFT',
                            condition=employee.id == contract.employee).join(
                                department,
                                'LEFT',
                                condition=department.id ==
                                staffPayroll.department).select(
                                    *columns.values(),
                                    where=where,
                                    group_by=[
                                        party.id_number, party.name,
                                        department.name, staffWage.name,
                                        staffPayroll.number,
                                        staffPayroll.start,
                                        staffPayroll.date_effective,
                                        staffWage.type_concept,
                                        staffPayrollLine.wage_type,
                                        staffPayroll.description
                                    ])

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
                        str(fila_dict['start']).split('-')[1])

                    # Verificamos si el id_number no se encuentra en las estrutura de diccionario
                    # si es asi, le asigna el id_number con un diccionario interno con la data
                    if fila_dict['id_number'] not in items:

                        items[fila_dict['id_number']] = {'data': {}}

                    # Verificamos si el mes no se encuentra dentro del diccionario data interno,
                    # si es asi, lo agrega con la cabecera del mes para acomular la data
                    if fila_dict['month'] not in items[
                            fila_dict['id_number']]['data']:

                        items[fila_dict['id_number']]['data'][
                            fila_dict['month']] = {
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
                        items[fila_dict['id_number']]['data'][fila_dict[
                            'month']]['salary'] += fila_dict['amount']
                    elif fila_dict['type_concept'] == 'extras':
                        items[fila_dict['id_number']]['data'][fila_dict[
                            'month']]['extras'] += fila_dict['amount']
                    elif fila_dict['type_concept'] == 'bonus':
                        items[fila_dict['id_number']]['data'][
                            fila_dict['month']]['bonus'] += fila_dict['amount']
                    elif fila_dict['type_concept'] == 'commission':
                        items[fila_dict['id_number']]['data'][fila_dict[
                            'month']]['comision'] += fila_dict['amount']

                    # Aqui acomulamos todos los valores para dar un total final de ese mes.
                    items[fila_dict['id_number']]['data'][
                        fila_dict['month']]['total'] += fila_dict['amount']

                else:  # Si el valor del bool es quincenal, entonces ingresamos en esta seccion
                    # Agregamos el numero de la nomina como indice para acomular los valores
                    index = fila_dict['payroll_number']

                    if fila_dict['id_number'] not in items:
                        items[index] = {
                            'id_number': fila_dict['id_number'],
                            'name': fila_dict['name'],
                            'department': fila_dict['department'],
                            'description': fila_dict['description'],
                            'values': {}
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
                            'salary'] += fila_dict['amount']
                    elif fila_dict['type_concept'] == 'extras':
                        items[index]['values'][fila_dict['description']][
                            'extras'] += fila_dict['amount']
                    elif fila_dict['type_concept'] == 'bonus':
                        items[index]['values'][fila_dict['description']][
                            'bonus'] += fila_dict['amount']
                    elif fila_dict['type_concept'] == 'commission':
                        items[index]['values'][fila_dict['description']][
                            'comision'] += fila_dict['amount']

                    #Totalisamos los valores
                    items[index]['values'][fila_dict['description']][
                        'total'] += fila_dict['amount']

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
        report_context = super(PayrollPaycheckReportExten,
                               cls).get_context(records, header, data)
        pool = Pool()
        Payroll = pool.get('staff.payroll')
        PayrollLine = pool.get('staff.payroll.line')
        Company = pool.get('company.company')

        dom_payroll = cls.get_domain_payroll(data)
        fields_payroll = [
            'id', 'employee.party.name', 'employee.party.id_number',
            'contract.start_date', 'contract.end_date', 'date_effective',
            'ibc', 'contract.last_salary', 'worked_days', 'employee',
            'contract'
        ]
        payrolls = Payroll.search_read(dom_payroll,
                                       fields_names=fields_payroll)
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
        PayrollLine = pool.get('staff.payroll.line')

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
        ]

        dom_line = [('payroll', 'in', payroll_ids),
                    [
                        'OR',
                        ('wage_type.type_concept', 'in', wage_type_default),
                        ('wage_type.type_concept', 'ilike', 'incapacity%'),
                        ('wage_type.type_concept', 'ilike', 'license%'),
                        ('wage_type.type_concept', '=', 'extras'),
                        ('wage_type.type_concept', '=', 'holidays'),
                        ('wage_type.type_concept_electronic', 'in',
                         ['LicenciaR', 'LicenciaMP', 'ConceptoS']),
                        [
                            'AND',
                            ('wage_type.provision_cancellation', '!=', None),
                        ]
                    ]]

        order = [('payroll.employee', 'DESC'), ('payroll', 'ASC')]
        payroll_lines = PayrollLine.search_read(dom_line,
                                                fields_names=fields_lines,
                                                order=order)
        total = []
        total_append = total.append
        for line in payroll_lines:
            key = str(line['payroll.']['employee']) + '_' + \
                      str(line['payroll.']['contract'])
            total_append(
                cls.values_without_move(line, wage_type_default, res, key))

        report_context['records'] = res.values()
        report_context['company'] = Company(data['company'])
        report_context['total'] = sum(total)
        return report_context

    def values_without_move(line, wage_type_default, res, key):
        PayrollLine = Pool().get('staff.payroll.line')
        total = 0
        concept = line['wage_type.']['type_concept']
        concept_electronic = line['wage_type.']['type_concept_electronic']
        if concept in wage_type_default and concept != 'salary':
            unit_formula = line['wage_type.']['unit_price_formula']

            if unit_formula:
                unit_formula = Decimal(
                    (unit_formula[unit_formula.index('*') + 1:]).strip())
            else:
                unit_formula = 0

            expense_formula = line['wage_type.']['expense_formula']
            if expense_formula:
                expense_formula = Decimal(
                    (expense_formula[expense_formula.index('*') + 1:]).strip())
                line_ = PayrollLine(line['id'])
                expense_amount = line_.get_expense_amount()
                res[key][concept + '_amount'] += expense_amount
                res[key]['subtotal'] += expense_amount
                total += expense_amount
            else:
                expense_formula = 0
            res[key][
                concept +
                '_name'] = line['party.']['name'] if line['party.'] else ''
            res[key][concept + '_rate'] = unit_formula + \
                (expense_formula if expense_formula < 1 else 0)
            res[key][
                concept +
                '_code'] = line['party.']['code'] if line['party.'] else ''
            res[key]['subtotal'] += line['amount']
            total += line['amount']
            res[key][concept + '_amount'] += line['amount']
        elif concept_electronic in ['LicenciaR', 'LicenciaMP', 'ConceptoS']:
            res[key]['license_amount'] += line['amount']
            res[key]['variation'] -= line['amount']
            # dict_employee[concept]['start_date'] = line['start_date']
            # dict_employee[concept]['end_date'] = line['start_date']
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

            # dict_employee[concept]['start_date'] = line['start_date']
            # dict_employee[concept]['end_date'] = line['start_date']
        return total


class PayrollElectronicCDS(metaclass=PoolMeta):
    'Staff Payroll Electronic'
    __name__ = 'staff.payroll.electronic'

    def set_mergepayroll(self):
        pool = Pool()
        ElectronicPayrollLine = pool.get('staff.payroll.electronic.line')
        payrolls = self._get_payrolls_month()
        payrolls_lines = [
            list(p.lines) for p in payrolls if hasattr(p, 'lines')
        ]
        payrolls_lines = list(chain(*payrolls_lines))
        liquidations = self._get_liquidations_month()
        liquidations_lines = [
            list(p.lines) for p in liquidations if hasattr(p, 'lines')
        ]
        liquidations_lines = list(chain(*liquidations_lines))
        wage_to_create = {}
        worked_days = sum(
            [p.worked_days for p in payrolls if hasattr(p, 'worked_days')])
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
                'interest', 'holidays', 'unemployment', 'bonus_service',
                'convencional_bonus'
            ]
            if concept and line.quantity > 0 and (concept_normal not in wage_exceptions \
                or not line.wage_type.contract_finish) and not excluded:
                wage_id = line.wage_type.id
                sequence = list_concepts.index(concept)
                if wage_id not in wage_to_create:
                    wage_to_create[wage_id] = {
                        'payroll': self,
                        'sequence': sequence,
                        'wage_type': line.wage_type,
                        'description': line.description,
                        'quantity': line.quantity,
                        'unit_value': abs(line.unit_value),
                        'uom': line.wage_type.uom,
                        'amount': abs(line.amount),
                        'party': line.party,
                        'lines_payroll': [('add', [
                            line.id,
                        ])]
                    }
                    if concept in EXTRAS.keys():
                        field = line.wage_type.type_concept_electronic
                        # field = field[0].lower()
                        relation_extras = self._get_lines_extras(field)
                        wage_to_create[wage_id].update(
                            {'assitants_line': [('add', relation_extras)]})
                else:
                    wage_to_create[wage_id]['lines_payroll'][0][1].append(
                        line.id)
                    wage_to_create[wage_id]['quantity'] += line.quantity
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
        accesses = Access.search([
            ('payroll', 'in', payrolls),
        ])
        for a in accesses:
            print(a, field)
            if getattr(a, field) == value:
                accesses.remove(a)
        return accesses
