from decimal import Decimal
from trytond.model import ModelView, fields
from trytond.pool import Pool, PoolMeta
from trytond.wizard import (
    Wizard, StateView, Button, StateReport, StateTransition
)
from trytond.pyson import Eval
from trytond.transaction import Transaction
from trytond.report import Report
from trytond.exceptions import UserError
import time


_TYPES_PAYMENT = [
    ('220', '220'),
    ('225', '225'),
    ('238', '238'),
    ('240', '240'),
    ('239', '239'),
    ('320', '320'),
    ('325', "325"),
    ('820', '820'),
    ('920', '920')
]

_TYPES_BANK_ACCOUNT = [
    ('S', 'S'),
    ('D', 'D')
]

_TYPE_DOCUMENT = {
    '13': '1', #Cedula
    '22': '2', #Cedula de extranjeria
    '31': '3', #Nit
    '12': '4', #Tarjeta de identidad
    '41': '5', #Pasaporte
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
    bank_code_sap = fields.Char('Bank code SAP', help='bank code used for the bancolombia payment template')


class PayrollPaymentStartBcl(ModelView):
    'Payroll Payment Start'
    __name__ = 'staff.payroll_payment_bancolombia.start'
    period = fields.Many2One('staff.payroll.period', 'Period', required=True)
    company = fields.Many2One('company.company', 'Company', required=True)
    department = fields.Many2One('company.department', 'Department')
    payment_type = fields.Selection(_TYPES_PAYMENT, 'Type payment', required=True)
    send_sequence = fields.Char('Send sequence', size=1)
    type_bank_account = fields.Selection(_TYPES_BANK_ACCOUNT, 'Type of account to be debited', required=True)
    reference = fields.Char('Reference', required=True, size=9)
    type_transaction = fields.Selection(_TYPE_TRANSACTION, 'Type of transaction', required=True)

    @staticmethod
    def default_company():
        return Transaction().context.get('company')


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
        period = None
        department_id = None
        if self.start.department:
            department_id = self.start.department.id
        if self.start.period:
            period = self.start.period.id
        if self.start.send_sequence:
            send_sequence = (self.start.send_sequence).upper()
        else:
            send_sequence = 'A'
        data = {
            'ids': [],
            'company': self.start.company.id,
            'period': period,
            'department': department_id,
            'payment_type': self.start.payment_type,
            'send_sequence': send_sequence,
            'type_bank_account': self.start.type_bank_account,
            'reference': self.start.reference,
            'type_transaction': self.start.type_transaction,
            }
        return action, data

    def transition_print_(self):
        return 'end'


class PayrollPaymentReportBcl(Report):
    __name__ = 'staff.payroll.payment_report_bancolombia'

    @classmethod
    def get_context(cls, records, header, data):
        report_context = super().get_context(records, header,  data)
        pool = Pool()
        user = pool.get('res.user')(Transaction().user)
        Payroll = pool.get('staff.payroll')
        clause = [('state', '=', 'posted')]
        if data['period']:
            clause.append(('period', '=', data['period']))
        if data['department']:
            clause.append(('employee.department', '=', data['department']))
        payrolls = Payroll.search(clause)
        new_objects = []
        values = {}
        for payroll in payrolls:
            values = values.copy()
            values['employee'] = payroll.employee.party.name
            type_document = payroll.employee.party.type_document
            values['type_document'] = _TYPE_DOCUMENT[type_document]
            values['id_number'] = payroll.employee.party.id_number
            bank_code_sap = None
            if payroll.employee.party.bank_accounts:
                bank_code_sap = payroll.employee.party.bank_accounts[0].bank.bank_code_sap
            values['bank_code_sap'] = bank_code_sap
            values['bank_account'] = payroll.employee.party.bank_account
            net_payment = Decimal(round(payroll.net_payment, 0))
            values['net_payment'] = net_payment
            new_objects.append(values)

        report_context['payment_type'] = data.get('payment_type')
        report_context['send_sequence'] = data.get('send_sequence')
        report_context['type_bank_account'] = data.get('type_bank_account')
        report_context['reference'] = data.get('reference')
        report_context['type_transaction'] = data.get('type_transaction')
        report_context['records'] = new_objects
        report_context['company'] = user.company
        return report_context

class PayslipSendStart(ModelView):
    'Payslip Send Start'
    __name__ = 'staff.payroll_payslip_send.start'
    company = fields.Many2One('company.company', 'Company', required=True)
    department = fields.Many2One('company.department', 'Department')
    period = fields.Many2One('staff.payroll.period', 'Start Period', required=True)
    subject = fields.Char('Subject', size=60, required=True)
    cc = fields.Char('Cc', help='separate emails with commas')

    @staticmethod
    def default_company():
        return Transaction().context.get('company')


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
        Email = pool.get('ir.email')
        Payroll = pool.get(model_name)
        ActionReport = pool.get('ir.action.report')
        report, = ActionReport.search([('report_name', '=', model_name)])
        reports = [report.id]
        subject = self.start.subject
        dom = [
            ('company', '=', self.start.company.id),
            ('period', '=', self.start.period.id),
            ('state', 'in', ['processed', 'posted']),
            ('sended_mail', '=', False)
         ]
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
                time.sleep(2)
                Email.send(to=email, cc=recipients_secondary, bcc='', subject=subject, body='',
                    files=None, record=record, reports=reports, attachments=None)
                Payroll.write([payroll], {'sended_mail': True})
            except Exception as e:
                raise UserError('No mail sent, check employee email', str(e))
    
        return 'end'


class StaffEvent(metaclass=PoolMeta):
    __name__ = "staff.event"

    analytic_account = fields.Many2One('analytic_account.account',
        'Analytic Account', domain=[
            ('type', 'in', ['normal', 'distribution']),
            ('company', '=', Eval('context', {}).get('company', -1))
        ])

class Payroll(metaclass=PoolMeta):
    __name__ = "staff.payroll"

    @classmethod
    def __setup__(cls):
        super(Payroll, cls).__setup__()

    def set_preliquidation(self, extras, discounts=None):
        super(Payroll, self).set_preliquidation(extras, discounts)
        Event = Pool().get('staff.event')
        if not hasattr(Event, 'analytic_account'):
            return
        for line in self.lines:
            if not line.is_event:
                continue
            if line.origin.analytic_account:
                for acc in line.analytic_accounts:
                    try:
                        acc.write([acc], {'account': line.origin.analytic_account.id})
                    except:
                        wage = line.wage_type.rec_name
                        raise UserError('analytic_event.msg_error_on_wage_type', wage)
        self.save()