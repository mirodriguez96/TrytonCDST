from decimal import Decimal

from trytond.exceptions import UserError
from trytond.i18n import gettext
from trytond.model import ModelSQL, fields
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Eval

from collections import OrderedDict
from trytond.wizard import Wizard, StateView, Button, StateReport
from trytond.report import Report

_ZERO = Decimal('0.0')

TAX_TECNO = [
    ('01', 'IVA'),
    ('02', 'IC'),
    ('03', 'ICA'),
    ('04', 'INC'),
    ('05', 'ReteIVA'),
    ('06', 'ReteFuente'),
    ('07', 'ReteICA'),
    ('20', 'FtoHorticultura'),
    ('21', 'Timbre'),
    ('22', 'Bolsas'),
    ('23', 'INCarbono'),
    ('24', 'INCombustibles'),
    ('25', 'Sobretasa Combustibles'),
    ('26', 'Sordicom'),
    ('ZZ', 'Otro'),
    ('NA', 'No Aceptada'),
    ('renta', 'renta'),
    ('autorenta', 'autorenta'),
    (None, None),
]

__all__ = [
    'Tax',
]


# Heredamos del modelo sale.sale para agregar el campo id_tecno
class Tax(metaclass=PoolMeta):
    'Tax'
    __name__ = 'account.tax'
    id_tecno = fields.Integer('Id TecnoCarnes', required=False)
    consumo = fields.Boolean('Tax consumption')
    classification_tax_tecno = fields.Selection(TAX_TECNO,
                                                'Classification Tax Tecno')


class MiddleModel(ModelSQL):
    "Middle Model"
    __name__ = 'account.tax.rule.line-account.tax'

    rule_line = fields.Many2One('account.tax.rule.line', 'Rule Line')
    tax = fields.Many2One('account.tax', 'Tax')


class TaxRuleLine(metaclass=PoolMeta):
    'Tax Rule Line'
    __name__ = 'account.tax.rule.line'

    additional_taxes = fields.Many2Many('account.tax.rule.line-account.tax',
                                        "rule_line", "tax", "Additional Taxes")

    @classmethod
    def __setup__(cls):
        super(TaxRuleLine, cls).__setup__()

    def get_taxes(self, origin_tax):
        taxes = super().get_taxes(origin_tax)
        if taxes is not None and self.additional_taxes:
            for tax in self.additional_taxes:
                taxes.append(tax.id)
        return taxes


class TaxesConsolidationStart(metaclass=PoolMeta):
    'Taxes Consolidation Start'
    __name__ = 'account_voucher.taxes_consolidation.start'

    # payoff_account_cds = fields.Many2One('account.account',
    #                                      'Payoff Account',
    #                                      domain=[
    #                                          ('type', '!=', None),
    #                                      ],
    #                                      required=True)

    date_note = fields.Many2One('account.period',
                                'Date Note',
                                domain=[
                                    ('fiscalyear', '=', Eval('fiscalyear')),
                                ],
                                required=True)

    operation_center = fields.Many2One('company.operation_center',
                                       'Operation Center',
                                       domain=[
                                           ('company', '=', Eval('company')),
                                       ],
                                       required=True)


class TaxesConsolidation(metaclass=PoolMeta):
    'Taxes Consolidation'
    __name__ = 'account_voucher.taxes_consolidation'

    def transition_create_(self):
        pool = Pool()
        Note = pool.get('account.note')
        Move = pool.get('account.move')
        MoveLine = pool.get('account.move.line')
        NoteLine = pool.get('account.note.line')

        taxes_accounts = []
        for tax in self.start.taxes:
            if not tax.invoice_account.reconcile:
                raise UserError(
                    gettext('account_voucher.msg_tax_account_no_reconcile',
                            invoice=tax.invoice_account.name,
                            tax=tax.name))
            if not tax.credit_note_account.reconcile:
                raise UserError(
                    gettext('account_voucher.msg_tax_account_no_reconcile',
                            invoice=tax.invoice_account.name,
                            tax=tax.name))

            taxes_accounts.extend(
                [tax.invoice_account.id, tax.credit_note_account.id])
        periods_ids = [p.id for p in self.start.periods]

        moves_draft = Move.search([
            ('period', 'in', periods_ids),
            ('state', '=', 'draft'),
        ])

        if moves_draft:
            raise UserError(gettext('account_voucher.msg_moves_in_draft'))

        move_lines = MoveLine.search([
            ('move.period', 'in', periods_ids),
            ('account', 'in', taxes_accounts),
            ('reconciliation', '=', None),
            ('account.reconcile', '=', True),
            ('move.state', '=', 'posted'),
            ('state', '=', 'valid'),
        ])

        max_period = self.start.date_note

        note, = Note.create([{
            'period': max_period.id,
            'date': max_period.end_date,
            'journal': self.start.journal.id,
            'state': 'draft',
            'description': self.start.description,
        }])

        balance = []
        lines_to_create = []
        note_id = note.id
        for line in move_lines:

            lines_to_create.append({
                'account':
                line.account.id,
                'party':
                line.party.id if line.party else None,
                'debit':
                line.credit,
                'credit':
                line.debit,
                'operation_center':
                self.start.operation_center.id,
                'description':
                line.description,
                'note':
                note_id,
                'move_line':
                line.id,
            })
            if line.account.party_required and not line.party:
                raise UserError(
                    gettext('account_voucher.msg_line_party_required',
                            s=line.account.code or '[-]'))
            balance.append(line.debit - line.credit)
        NoteLine.create(lines_to_create)

        payable_line = {
            'account': self.start.payoff_account.id,
            'note': note.id,
            'debit': _ZERO,
            'credit': _ZERO,
            'party': self.start.party.id,
        }

        amount = sum(balance)
        if amount > _ZERO:
            payable_line['debit'] = abs(amount)
        else:
            payable_line['credit'] = abs(amount)
        NoteLine.create([payable_line])
        note.set_number()
        # self.result = UserError(gettext(
        #    'account_voucher.msg_note_created',
        #    s=note.number
        # ))
        self.result = f"Note {note.number} created."
        return 'done'


class PrintTaxesPostedAccumulated(Wizard):
    'Print Taxes Posted'
    __name__ = 'account_col.print_taxes_posted_accumulated'
    start = StateView('account_col.print_taxes_posted.start',
        'account_col.print_taxes_posted_start_view_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Print', 'print_', 'tryton-print', default=True),
            ])
    print_ = StateReport('account_col.taxes_posted_report_accumulated')

    def do_print_(self, action):
        taxes = None
        if self.start.taxes:
            taxes = [tax.id for tax in self.start.taxes]
        data = {
            'company': self.start.company.id,
            'fiscalyear': self.start.fiscalyear.id,
            'start_period': self.start.start_period.id,
            'end_period': self.start.end_period.id,
            'taxes': taxes,

        }
        return action, data

    def transition_print_(self):
        return 'end'


class TaxesPostedAccumulated(Report):
    __name__ = 'account_col.taxes_posted_report_accumulated'

    @classmethod
    def get_context(cls, records, header, data):
        report_context = super().get_context(records, header, data)
        pool = Pool()
        Period = pool.get('account.period')
        Company = pool.get('company.company')
        FiscalYear = pool.get('account.fiscalyear')
        Tax = pool.get('account.tax')
        MoveLine = pool.get('account.move.line')
        company = Company(data['company'])

        start_period = Period(data['start_period'])
        end_period = Period(data['end_period'])

        dom = []
        if data['taxes']:
            dom.append(('id', 'in', data['taxes']))

        taxes = Tax.search(dom, order=[('invoice_account.code', 'ASC')])
        taxes_accounts = {}

        def _get_data_tax(acc):
            val = {
                'code': acc.code,
                'name': acc.rec_name,
                'rate': '',
                'lines': [],
                'sum_base': [],
                'sum_amount': [],
            }
            return val

        for t in taxes:
            for tax_i_acc in (t.invoice_account, t.credit_note_account):
                if tax_i_acc and tax_i_acc.id not in taxes_accounts.keys():
                    taxes_accounts[tax_i_acc.id] = _get_data_tax(tax_i_acc)

        periods = Period.search([
                ('fiscalyear', '=', data['fiscalyear']),
                ('start_date', '>=', start_period.start_date),
                ('end_date', '<=', end_period.end_date),
                ])
        period_ids = [p.id for p in periods]

        lines = MoveLine.search([
            ('account', 'in', set(taxes_accounts.keys())),
            ('move.period', 'in', period_ids),
        ], order=[('date', 'ASC')])

        targets = {}
        for line in lines:
            line_id = line.account.id
            if line_id not in targets.keys():
                targets[line_id] = taxes_accounts[line_id]
            line_ = cls.get_tax_reversed(line)
            targets[line_id]['lines'].append(line_)
            targets[line_id]['sum_base'].append(line_['base'])
            targets[line_id]['sum_amount'].append(line_['tax_amount'])

        ordered_targets = sorted(((v['code'], v) for v in targets.values()), key=lambda tup: tup[0])
        ordered_targets = OrderedDict(ordered_targets)

        report_context['records'] = ordered_targets.values()
        report_context['start_period'] = start_period.name
        report_context['end_period'] = end_period.name
        report_context['company'] = company
        report_context['fiscalyear'] = FiscalYear(data['fiscalyear']).name
        return report_context

    @classmethod
    def get_tax_reversed(cls, line):
        line2 = {'line': line}
        rate = None
        base = _ZERO
        amount = line.debit - line.credit
        if line.tax_lines:
            for tax_line in line.tax_lines:
                if tax_line.tax:
                    rate = tax_line.tax.rate
            if rate:
                base = amount / abs(rate)
                rate = rate * 100

        line2.update({'base': base, 'tax_amount': amount, 'rate': rate})
        return line2
