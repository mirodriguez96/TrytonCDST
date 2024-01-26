from trytond.model import ModelSQL, fields
from trytond.pool import PoolMeta
from decimal import Decimal
from trytond.model import ModelSQL, fields
from trytond.pool import Pool
from trytond.exceptions import UserError
from trytond.i18n import gettext
from trytond.pyson import Eval

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
]

__all__ = [
    'Tax',
]


#Heredamos del modelo sale.sale para agregar el campo id_tecno
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

    payoff_account_cds = fields.Many2One('account.account',
                                         'Payoff Account',
                                         domain=[
                                             ('type', '!=', None),
                                         ],
                                         required=True)

    date_note = fields.Many2One('account.period',
                                'Date Note',
                                domain=[
                                    ('type', '=', 'adjustment'),
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
        print('Hola')
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
            'account': self.start.payoff_account_cds.id,
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
        #self.result = UserError(gettext(
        #    'account_voucher.msg_note_created',
        #    s=note.number
        #))
        self.result = f"Note {note.number} created."
        return 'done'
