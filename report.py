from trytond.report import Report
from trytond.wizard import Wizard, StateView, Button, StateReport
from datetime import datetime, date
from trytond.model import ModelView, fields
from trytond.pool import Pool
from trytond.transaction import Transaction
from .constants import (ENTITY_ACCOUNTS)

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
