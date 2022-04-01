from trytond.report import Report
from trytond.wizard import Wizard, StateView, Button, StateReport
from datetime import datetime, date
from trytond.model import ModelView, fields
from trytond.pool import Pool
from trytond.transaction import Transaction
#from trytond.exceptions import UserError
import copy
from .constants import (ENTITY_ACCOUNTS)

'''
class PortfolioStatusStart(ModelView):
    'Portfolio Status Start'
    __name__ = 'report.print_portfolio_status.start'
    company = fields.Many2One('company.company', 'Company', required=True)
    detailed = fields.Boolean('Detailed')
    date_to = fields.Date('Date to')
    category_party = fields.MultiSelection('get_category_party', 'Party Categories')
    kind = fields.Selection([
        ('in', 'Supplier'),
        ('out', 'Customer'),
    ], 'Kind', required=True)
    payment_terms = fields.MultiSelection('get_payment_terms', 'Payment Term')

    #procedures = fields.MultiSelection('get_procedures', "Procedures")
    # _get_types_cache = Cache('party.address.subdivision_type.get_types')

    #@classmethod
    #def get_procedures(cls):
    #    pool = Pool()
    #    Procedure = pool.get('collection.procedure')
    #    procedures = Procedure.search_read([], fields_names=['id', 'name'])
    #    return [(r['id'], r['name']) for r in procedures]

    @classmethod
    def get_category_party(cls):
        pool = Pool()
        PartyCategory = pool.get('party.category')
        categories = PartyCategory.search_read([('active', '=', True)], fields_names=['id', 'name'])
        return [(r['id'], r['name']) for r in categories]

    @classmethod
    def get_payment_terms(cls):
        pool = Pool()
        PaymentTerm = pool.get('account.invoice.payment_term')
        payment_terms = PaymentTerm.search_read([], fields_names=['id', 'name'])
        return [(r['id'], r['name']) for r in payment_terms]

    @staticmethod
    def default_company():
        return Transaction().context.get('company')

    @staticmethod
    def default_group():
        return 'customers'


class PortfolioStatus(Wizard):
    'Portfolio Status'
    __name__ = 'report.print_portfolio_status'

    start = StateView('report.print_portfolio_status.start',
                      'conector.print_portfolio_status_start_view_form', [
                          Button('Cancel', 'end', 'tryton-cancel'),
                          Button('Print', 'print_', 'tryton-ok', default=True),
                          ])
    print_ = StateReport('report.portfolio_status_report')

    def do_print_(self, action):
        data = {
            'ids': [],
            'company': self.start.company.id,
            'detailed': self.start.detailed,
            'kind': self.start.kind,
            'category_party': list(self.start.category_party),
            #'procedures': list(self.start.procedures),
            'payment_terms': list(self.start.payment_terms),
            'date_to': self.start.date_to,
        }
        return action, data

    def transition_print_(self):
        return 'end'


class PortfolioStatusReport(Report):
    'Portfolio Status Report'
    __name__ = 'report.portfolio_status_report'

    @classmethod
    def get_domain_invoice(cls, data):
        domain = [
            ('company', '=', data['company']),
            ('type', '=', data['kind']),
        ]
        if data['category_party']:
            domain.append(('party.categories', 'in', data['category_party']))
        if data['payment_terms']:
            domain.append(('payment_term', 'in', data['payment_terms']))
        if data['date_to']:
            to_date = data['date_to']
            dt = datetime.combine(
                date(to_date.year, to_date.month, to_date.day), datetime.min.time())
            dom = [
                'OR',
                [
                    ('payment_lines.date', '>=', data['date_to']),
                    # ('write_date', '>=', dt),
                    ('state', '=', 'paid'),
                ],
                ('state', '=', 'posted')
            ]
            domain.append(dom)
            domain.append(('invoice_date', '<=', data['date_to']))
        else:
            domain.append(('state', '=', 'posted')),
        return domain

    @classmethod
    def get_context(cls, records, header, data):
        report_context = super().get_context(records, header, data)
        pool = Pool()
        Company = pool.get('company.company')
        Invoice = pool.get('account.invoice')
        company = Company(data['company'])

        dom_invoices = cls.get_domain_invoice(data)
        #if data['procedures']:
        #    accounts = []
        #    Procedure = pool.get('collection.procedure')
        #    procedures = Procedure.search_read([
        #            ('id', 'in', data['procedures'])
        #        ], fields_names=['accounts'])
        #    for procedure in procedures:
        #        accounts.extend(list(procedure['accounts']))
        #    if not accounts:
        #        raise UserError('report.msg_missing_account_procedure')
        #    dom_invoices.append(['account', 'in', accounts])
        order = [('party.name', 'DESC'), ('invoice_date', 'ASC')]
        invoices = Invoice.search(dom_invoices, order=order)
        records = {}
        today = date.today()
        deepcopy = copy.deepcopy
        expired_kind = {
            'range_0': [],
            'range_1_30': [],
            'range_31_60': [],
            'range_61_90': [],
            'range_91': [],
        }
        expired_sums = deepcopy(expired_kind)
        expired_sums['total'] = []
        move_ids = []
        append_move_ids = move_ids.append
        for invoice in invoices:
            append_move_ids(invoice.move.id)
            if data['detailed']:
                key_id = str(invoice.party.id) + '_' + str(invoice.id)
            else:
                key_id = str(invoice.party.id)

            if key_id not in records.keys():
                _expired_kind = deepcopy(expired_kind)
                categories = invoice.party.categories
                records[key_id] = {
                    'party': invoice.party,
                    'category': categories[0].name if categories else '',
                    'total': [],
                    'notes': '',
                    'invoice': [],
                    'expired_days': '',
                }
                records[key_id].update(_expired_kind)

            time_forward = 0
            if data['date_to']:
                maturity_date = None
                move_lines_paid = []
                pay_to_date = []
                pay_append = pay_to_date.append
                line_append = move_lines_paid.append

                for line in invoice.payment_lines:
                    if line.move.date <= data['date_to']:
                        pay_append(line.debit - line.credit)
                        line_append(line.id)
                    else:
                        if line.maturity_date and line.maturity_date < maturity_date or maturity_date is None:
                            maturity_date = line.maturity_date

                for line in invoice.move.lines:
                    line_id = line.id
                    if not line.reconciliation:
                        continue
                    for recline in line.reconciliation.lines:
                        if recline.id == line_id or line_id in move_lines_paid:
                            continue
                        if recline.move.date <= data['date_to']:
                            pay_append(recline.debit - recline.credit)

                amount_paid = sum(pay_to_date)
                if not maturity_date:
                    maturity_date = invoice.estimate_pay_date or invoice.invoice_date

                time_forward = (data['date_to'] - maturity_date).days
                amount = invoice.total_amount - amount_paid
            else:
                amount = invoice.amount_to_pay
                if invoice.estimate_pay_date:
                    time_forward = (today - invoice.estimate_pay_date).days

            if time_forward <= 0:
                expire_time = 'range_0'
            elif time_forward <= 30:
                expire_time = 'range_1_30'
            elif time_forward <= 60:
                expire_time = 'range_31_60'
            elif time_forward <= 90:
                expire_time = 'range_61_90'
            else:
                expire_time = 'range_91'

            notes = None
            if hasattr(invoice, 'agent') and invoice.agent:
                notes = invoice.agent.rec_name
            if notes and not records[key_id]['notes']:
                records[key_id]['notes'] = notes
            
            records[key_id][expire_time].append(amount)
            records[key_id]['invoice'].append(invoice)
            records[key_id]['expired_days'] = time_forward
            records[key_id]['total'].append(amount)
            expired_sums[expire_time].append(amount)
            expired_sums['total'].append(amount)

        move_lines_without_invoice = {}
        if data['detailed']:
            cond1 = 'where'
            if data['category_party']:
                cat_ids = str(tuple(data['category_party'])).replace(',', '') if len(
                    data['category_party']) == 1 else str(tuple(data['category_party']))
                cond1 = f"where pcr.category in %s and" % (
                    cat_ids)

            cond2 = ''
            if move_ids:
                cond2 = 'and ml.id not in %s' % (str(tuple(move_ids)).replace(',', '') if len(move_ids) == 1 else str(tuple(move_ids)))
            print(cond2)

            cond3 = ''
            if data['date_to']:
                cond3 = ' and am.date <= %s' % (data['date_to'].strftime("'%Y-%m-%d'"))
            print(cond3)

            type_ = 'receivable'
            if data['kind'] == 'in':
                type_ = 'payable'

            cursor = Transaction().connection.cursor()
            query = f"""SELECT ml.id, ml.move, pp.name, pc.name AS category, pp.id_number, ml.description, ml.reference, am.date, am.number, ml.maturity_date, ac.code, (current_date-ml.maturity_date::date) AS expired_days, COALESCE(sum(av.amount), 0) AS payment_amount,
                CASE WHEN (current_date-ml.maturity_date::date)<=0
                THEN (ml.debit-ml.credit) - COALESCE(sum(av.amount), 0) ELSE 0
                END AS range_0,
                CASE WHEN (current_date-ml.maturity_date::date)<=30 AND (current_date-ml.maturity_date::date) > 0
                THEN (ml.debit-ml.credit) - COALESCE(sum(av.amount), 0) ELSE 0
                END AS range_1_30,
                CASE WHEN (current_date-ml.maturity_date::date)<=60 AND (current_date-ml.maturity_date::date) > 30
                THEN (ml.debit-ml.credit) - COALESCE(sum(av.amount), 0) ELSE 0
                END AS range_31_60,
                CASE WHEN (current_date-ml.maturity_date::date)<=90 AND (current_date-ml.maturity_date::date) > 60
                THEN (ml.debit-ml.credit) - COALESCE(sum(av.amount), 0) ELSE 0
                END AS range_61_90,
                CASE WHEN (current_date-ml.maturity_date::date)>90
                THEN (ml.debit-ml.credit) - COALESCE(sum(av.amount), 0) ELSE 0
                END AS range_91,
                ((ml.debit-ml.credit) - COALESCE(sum(av.amount), 0)) AS total
                from account_move_line AS ml
                LEFT JOIN account_account AS ac
                ON ml.account = ac.id LEFT JOIN account_account_type AS at
                ON ac.type = at.id LEFT JOIN account_voucher_line AS av
                ON ml.id=av.move_line LEFT JOIN account_move AS am
                ON am.id=ml.move LEFT JOIN party_party AS pp
                ON pp.id=ml.party LEFT JOIN (SELECT DISTINCT ON (party) party, category from party_category_rel) AS pcr
                ON pcr.party=pp.id LEFT JOIN party_category AS pc
                ON pcr.category=pc.id
                %s at.{type_}='t' AND ac.reconcile='t' AND ml.maturity_date is not null AND am.origin is null AND ml.reconciliation is null
                %s %s
            group by ml.id, ml.move, pp.name, pc.name, pp.id_number, ml.description, ml.reference, am.date, am.number, ml.maturity_date, ac.code, expired_days, ml.debit, ml.credit;""" % (cond1, cond2, cond3)

            cursor.execute(query)
            columns = list(cursor.description)
            result = cursor.fetchall()
            print('RESULTADO CONSULTA', result)
            for row in result:
                row_dict = {}
                for i, col in enumerate(columns):
                    try:
                        expired_sums[col.name].append(row[i])
                    except:
                        pass
                    row_dict[col.name] = row[i]
                move_lines_without_invoice[row[0]] = row_dict

        lines_without_inv = move_lines_without_invoice.values()
        report_context['lines_without_inv'] = lines_without_inv
        report_context.update(expired_sums)
        report_context['records'] = records.values()
        report_context['company'] = company.party.name
        return report_context
'''

# REPORTE DE NOMINA MODIFICADO
class PayrollExportStart(ModelView):
    'Export Payroll Start'
    __name__ = 'report.payroll.export.start'
    company = fields.Many2One('company.company', 'Company', required=True)
    start_period = fields.Many2One('staff.payroll.period', 'Start Period',
                                   required=True)
    end_period = fields.Many2One('staff.payroll.period', 'End Period',
                                 required=True)
    department = fields.Many2One('company.department', 'Department',
                                 required=False, depends=['employee'])

    @staticmethod
    def default_company():
        return Transaction().context.get('company')


class PayrollExport(Wizard):
    'Payroll Export'
    __name__ = 'report.payroll.export'
    start = StateView('report.payroll.export.start',
                      'conector.payroll_export_start_view_form', [
                          Button('Cancel', 'end', 'tryton-cancel'),
                          Button('Print', 'print_', 'tryton-ok', default=True),
                          ])
    print_ = StateReport('report.payroll.export_report')

    def do_print_(self, action):
        department_id = self.start.department.id \
            if self.start.department else None
        data = {
            'ids': [],
            'company': self.start.company.id,
            'start_period': self.start.start_period.id,
            'end_period': self.start.end_period.id,
            'department_id': department_id,
        }
        return action, data

    def transition_print_(self):
        return 'end'


class PayrollExportReport(Report):
    __name__ = 'report.payroll.export_report'

    @classmethod
    def get_domain_payroll(cls, data=None):
        dom_payroll = []

        return dom_payroll

    @classmethod
    def get_context(cls, records, header, data):
        report_context = super().get_context(records, header, data)
        pool = Pool()
        company = pool.get('company.company')(data['company'])
        Payroll = pool.get('staff.payroll')
        Period = pool.get('staff.payroll.period')
        dom_payroll = cls.get_domain_payroll()
        start_period, = Period.search([('id', '=', data['start_period'])])
        end_period, = Period.search([('id', '=', data['end_period'])])
        dom_payroll.append([
            ('period.start', '>=', start_period.start),
            ('period.end', '<=', end_period.end),
            ('move', '!=', None)
        ])
        if data['department_id'] not in (None, ''):
            dom_payroll.append([
                ('employee.department', '=', data['department_id'])
            ])

        payrolls = Payroll.search(dom_payroll, order=[('period.name', 'ASC')])
        records = {}
        for payroll in payrolls:
            employee = payroll.employee
            """ extract debit account and party mandatory_wages"""
            accdb_party = {mw.wage_type.debit_account.id: mw.party
                           for mw in employee.mandatory_wages
                           if mw.wage_type.debit_account and mw.party}
            move = payroll.move
            accountdb_ids = accdb_party.keys()
            for line in move.lines:
                """Check account code in dict account debit and party"""
                if not line.party:
                    continue
                line_ = {
                    'date': line.move.date,
                    'code': '---',
                    'party': employee.party.id_number,
                    'name': employee.party.name,
                    'description': line.description,
                    'department': employee.department.name if employee.department else '---',
                    'amount': line.debit or line.credit,
                    'type': 'D',
                }
                if line.debit > 0:
                    if line.account.id in accountdb_ids:
                        id_number = accdb_party[line.account.id].id_number
                    else:
                        id_number = None

                    if id_number in ENTITY_ACCOUNTS.keys():
                        line_['code'] = ENTITY_ACCOUNTS[id_number][1]
                    else:
                        line_['code'] = line.account.code

                else:
                    line_['type'] = 'C'
                    id_number = line.party.id_number
                    if id_number in ENTITY_ACCOUNTS.keys():
                        line_['code'] = ENTITY_ACCOUNTS[id_number][0]
                    else:
                        line_['code'] = line.account.code

                if line.account.code not in records.keys():
                    records[line.account.code] = {
                        'name': line.account.name,
                        'lines': []
                        }
                records[line.account.code]['lines'].append(line_)

        report_context['records'] = records
        report_context['start_date'] = start_period.name
        report_context['end_date'] = end_period.name
        report_context['company'] = company.party.name
        return report_context
