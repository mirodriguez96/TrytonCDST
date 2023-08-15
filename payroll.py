from decimal import Decimal
from datetime import timedelta

from trytond.model import ModelSQL, ModelView, fields
from trytond.pool import Pool, PoolMeta
from trytond.wizard import (
    Wizard, StateView, Button, StateReport, StateTransition
)
from trytond.pyson import Eval, Or, Not
from trytond.transaction import Transaction
from trytond.report import Report
from trytond.exceptions import UserError, UserWarning

from . it_supplier_noova import ElectronicPayrollCdst

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
# from trytond.pyson import Id
# from trytond.i18n import gettext
# from .exceptions import (
# MissingSecuenceCertificate,
#  )

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

class WageType(metaclass=PoolMeta):
    __name__ = 'staff.wage_type'
    non_working_days = fields.Boolean('Non-working days', 
                                      states={'invisible': (Eval('type_concept') != 'holidays')
                                              })

class Liquidation(metaclass=PoolMeta):
    __name__ = "staff.liquidation"
    sended_mail = fields.Boolean('Sended Email')

    # Funcion encargada de contar los días festivos
    def count_holidays(self, start_date, end_date):
        sundays = 0
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
        ], count=True)
        return sundays + holidays
    
    def _validate_holidays_lines(self, event):
        amount_day = (self.contract.salary / 30)
        # amount = amount_day * event.days_of_vacations
        holidays = self.count_holidays(event.start_date, event.end_date)
        workdays = event.days - holidays
        # breakpoint()
        amount_workdays = round(amount_day * workdays, 2)
        amount_holidays = round(amount_day * holidays, 2)
        line, = self.lines
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
            line.adjustments = [Adjustment(
                    account=adjustment_account,
                    amount=adjustment,
                    description=line.description
                )]
            line.amount = amount_workdays
            line.days = workdays
        line.save()
        if amount_holidays > 0:
            WageType = Pool().get('staff.wage_type')
            wage_type  = WageType.search([('non_working_days', '=', True)], limit=1)
            if not wage_type:
                raise UserError('Wage Type', 'missing wage_type (non_working_days)')
            wage_type, = wage_type
            value = {
                'sequence': wage_type.sequence,
                'wage': wage_type.id,
                'description': wage_type.name,
                'amount': amount_holidays,
                'account': wage_type.debit_account,
                'days': holidays,
                'adjustments': [('create', [{
                    'account': wage_type.debit_account.id,
                    'amount': amount_holidays,
                    'description': wage_type.debit_account.name,
                }])]
            }
            self.write([self], {'lines': [('create', [value])]})



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

# Se genera un reporte con los campos necesarios para el envío de la nómina mediante la plataforma de Bancolombia
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
            if type_document not in _TYPE_DOCUMENT:
                raise UserError('error: type_document', f'{type_document} not found for type_document bancolombia')
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

class LiquidationPaymentStartBcl(ModelView):
    'Liquidation Payment Start'
    __name__ = 'staff.payroll_liquidation_payment_bancolombia.start'
    company = fields.Many2One('company.company', 'Company', required=True)
    department = fields.Many2One('company.department', 'Department')
    payment_type = fields.Selection(_TYPES_PAYMENT, 'Type payment', required=True)
    send_sequence = fields.Char('Send sequence', size=1)
    type_bank_account = fields.Selection(_TYPES_BANK_ACCOUNT, 'Type of account to be debited', required=True)
    reference = fields.Char('Reference', required=True, size=9)
    type_transaction = fields.Selection(_TYPE_TRANSACTION, 'Type of transaction', required=True)
    kind = fields.Selection([
            ('contract', 'Contract'),
            ('bonus_service', 'Bonus Service'),
            ('interest', 'Interest'),
            ('unemployment', 'Unemployment'),
            ('holidays', 'Vacation'),
            ('convencional_bonus', 'Convencional Bonus'),
        ], 'Kind', required=True)
    date = fields.Date('Date',required=True)

    @staticmethod
    def default_company():
        return Transaction().context.get('company')
    
    @staticmethod
    def default_kind():
        return 'contract'

# Asistente encargado de recoger la información de las liquidaciones que se van a utilizar para el reporte
class LiquidationPaymentBcl(Wizard):
    'Liquidation Payment'
    __name__ = 'staff.payroll.liquidation_payment'
    start = StateView('staff.payroll_liquidation_payment_bancolombia.start',
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
            'type_bank_account': self.start.type_bank_account,
            'reference': self.start.reference,
            'type_transaction': self.start.type_transaction,
            'kind': self.start.kind,
            }
        return action, data

    def transition_print_(self):
        return 'end'

# Se genera un reporte con los campos necesarios para el envío de liquidaciones mediante la plataforma de Bancolombia
class LiquidationPaymentReportBcl(Report):
    __name__ = 'staff.payroll_payment_liq_report_bancolombia'

    @classmethod
    def get_context(cls, records, header, data):
        report_context = super().get_context(records, header,  data)
        pool = Pool()
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
            type_document = liquidation.employee.party.type_document
            values['type_document'] = _TYPE_DOCUMENT[type_document]
            values['id_number'] = liquidation.employee.party.id_number
            bank_code_sap = None
            if liquidation.employee.party.bank_accounts:
                bank_code_sap = liquidation.employee.party.bank_accounts[0].bank.bank_code_sap
            values['bank_code_sap'] = bank_code_sap
            values['bank_account'] = liquidation.employee.party.bank_account
            net_payment = Decimal(round(liquidation.net_payment, 0))
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
                send_mail(to=email, cc=recipients_secondary, bcc='', subject=subject, body='___',
                    files=None, record=record, reports=reports, attachments=None)
                Payroll.write([payroll], {'sended_mail': True})
                Transaction().connection.commit()
            except Exception as e:
                raise UserError(f'No mail sent, check employee email {payroll.employee.rec_name}', str(e))
    
        return 'end'

class SettlementSendStart(ModelView):
    'Settlement Send Start'
    __name__ = 'staff.payroll_settlement_send.start'
    company = fields.Many2One('company.company', 'Company', required=True)
    department = fields.Many2One('company.department', 'Department')
    date = fields.Date('Date',required=True)
    subject = fields.Char('Subject', size=60, required=True)
    cc = fields.Char('Cc', help='separate emails with commas')
    kind = fields.Selection([
            ('contract', 'Contract'),
            ('bonus_service', 'Bonus Service'),
            ('interest', 'Interest'),
            ('unemployment', 'Unemployment'),
            ('holidays', 'Vacation'),
            ('convencional_bonus', 'Convencional Bonus'),
        ], 'Kind', required=True)

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
    fiscalyear = fields.Many2One('account.fiscalyear', 'Fiscal Year',
                                 required=True)
    subject = fields.Char('Subject', size=60, required=True)
    employees = fields.Many2Many('company.employee', None, None, 'Employees',required=True)
    cc = fields.Char('Cc', help='separate emails with commas')

    @staticmethod
    def default_company():
        return Transaction().context.get('company')
    
    @staticmethod
    def default_fiscalyear():
        FiscalYear = Pool().get('account.fiscalyear')
        return FiscalYear.find(
            Transaction().context.get('company'), exception=False)


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
        report, = ActionReport.search([('report_name', '=', 'staff.payroll.income_withholdings_report')])
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
            record = [model_name,employe]
            try:
                send_mail_certificate(to=email, cc=recipients_secondary, bcc='', subject=subject, body=body,
                    files=None, record=record, reports=reports, attachments=None, dic=dic)
                
            except Exception as e:
                        raise UserError(f'No mail sent, check employee email {employe.rec_name}', str(e))


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
def send_mail_certificate(to='', cc='', bcc='', subject='', body='',
            files=None, record=None, reports=None, attachments=None, dic=None):
    
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
            ext, content, _, title = Report.execute(
                [record[1].id], dic)
            name = '%s.%s' % (title, ext)
            # get_number_sequence_certificate(seq)
            if isinstance(content, str):
                content = content.encode('utf-8')
            files.append((name, content))
        if attachments:
            files += [
                (a.name, a.data) for a in Attachment.browse(attachments)]
        for name, data in files:
            mimetype, _ = mimetypes.guess_type(name)
            if mimetype:
                attachment = MIMENonMultipart(*mimetype.split('/'))
                attachment.set_payload(data)
                encode_base64(attachment)
            else:
                attachment = MIMEApplication(data)
            attachment.add_header(
                'Content-Disposition', 'attachment',
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
    to_addrs = list(filter(None, map(
                str.strip,
                _get_emails(to) + _get_emails(cc) + _get_emails(bcc))))
    sendmail(
        from_, to_addrs, msg, server=None, strict=True)
    email = Email(
        recipients=to,
        recipients_secondary=cc,
        recipients_hidden=bcc,
        addresses=[{'address': a} for a in to_addrs],
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
        dom = [
            ('company', '=', self.start.company.id),
            ('liquidation_date', '=', self.start.date),
            ('kind', '=', self.start.kind),
            ('sended_mail', '=', False)
         ]
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
                    send_mail(to=email, cc=recipients_secondary, bcc='', subject=subject, body='___',
                        files=None, record=record, reports=reports, attachments=None)
                    Liquidation.write([liquidation], {'sended_mail': True})
                    Transaction().connection.commit() 
                except Exception as e:
                    raise UserError(f'No mail sent, check employee email {liquidation.employee.rec_name}', str(e))
            else:
                pass
        return 'end'



# Copia funcion 'send' del modelo 'ir.email' modificando para enviar de forma individual (no transactional)
def send_mail(to='', cc='', bcc='', subject='', body='',
            files=None, record=None, reports=None, attachments=None):
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
            ext, content, _, title = Report.execute(
                [record.id], {
                    'action_id': report.id,
                    })
            name = '%s.%s' % (title, ext)
            if isinstance(content, str):
                content = content.encode('utf-8')
            files.append((name, content))
        if attachments:
            files += [
                (a.name, a.data) for a in Attachment.browse(attachments)]
        for name, data in files:
            mimetype, _ = mimetypes.guess_type(name)
            if mimetype:
                attachment = MIMENonMultipart(*mimetype.split('/'))
                attachment.set_payload(data)
                encode_base64(attachment)
            else:
                attachment = MIMEApplication(data)
            attachment.add_header(
                'Content-Disposition', 'attachment',
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
    to_addrs = list(filter(None, map(
                str.strip,
                _get_emails(to) + _get_emails(cc) + _get_emails(bcc))))
    sendmail(
        from_, to_addrs, msg, server=None, strict=True)
    email = Email(
        recipients=to,
        recipients_secondary=cc,
        recipients_hidden=bcc,
        addresses=[{'address': a} for a in to_addrs],
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
    analytic_account = fields.Char('Analytic account code', states={'readonly': (Eval('state') != 'draft')})

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
                'invisible': Or(
                    Eval('state') != 'done',
                    Not(Eval('is_vacations')),
                ),
            }
        })

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
                raise UserWarning(warning_name, f"Se creara una liquidacion de vacaciones")
            liquidation = Liquidation()
            liquidation.employee = event.employee
            liquidation.contract = event.contract
            liquidation.kind = 'holidays'
            start_period = Period.search([
                ('start', '>=', event.contract.start_date),
                ('end', '<=', event.contract.start_date)
            ])
            if not start_period:
                start_period = Period.search([], order=[('end', 'ASC')], limit=1)
            liquidation.start_period = start_period[0]
            end_period, = Period.search([
                ('start', '<=', event.start_date),
                ('end', '>=', event.start_date)
            ])
            liquidation.end_period = end_period
            liquidation.liquidation_date = event.event_date
            liquidation.description = event.description
            liquidation.account = Configuration.liquidation_account
            liquidation.save()
            # Se procesa la liquidación
            Liquidation.compute_liquidation([liquidation])
            liquidation._validate_holidays_lines(event)

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
                        analytic_account, = AnalyticAccount.search([('code', '=', line.origin.analytic_account)])
                        acc.write([acc], {'account': analytic_account.id})
                    except:
                        wage = line.wage_type.rec_name
                        raise UserError('staff_event.msg_error_on_analytic_account', wage)
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
                    'receipt':wage_type.receipt,
                    'sequence': wage_type.sequence,
                }

            line, = PayrollLine.create([to_create])
            LoanLine.write([m], {'state': 'paid', 'origin': line})


class PayrollReport(CompanyReport):
    __name__ = 'staff.payroll'
    
    #Metodo para heredar el metodo de generacion del reporte.
    @classmethod
    def get_context(cls, records, header, data):
        report_context = super().get_context(records, header, data)
        Loans = Pool().get('staff.loan')
        party = ''
        amount=0.0
        for record in report_context['records']:
            party = record.employee.party.name
        #busco el prestamo de ese tercero 
        loans =  Loans.search([('party', '=',party),('state', '=','posted')])
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
        result = super(PayrollExo2276, cls)._prepare_lines(payrolls, vals, party_id)
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

        return  result
    

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
                'invisible': Or(
                    Eval('electronic_state') == 'authorized',
                    Eval('state') != 'processed',
                )},
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
    amount = fields.Function(fields.Numeric('Amount', digits=(3, 2)), 'on_change_with_amount')
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

    #
    @fields.depends('rests')
    def on_change_rests(self):
        amount = 0
        for rest in self.rests:
            if rest.amount and not rest.pay:
                amount += rest.amount
        self.rest = amount