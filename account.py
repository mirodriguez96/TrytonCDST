from collections import defaultdict
from decimal import Decimal

from trytond.i18n import gettext
from trytond.exceptions import UserError
from trytond.model import ModelView, fields
from trytond.pyson import Eval
from trytond.transaction import Transaction
from trytond.tools import grouped_slice
from trytond.wizard import Wizard, StateView, StateAction, Button
from trytond.modules.stock.exceptions import PeriodCloseError
from trytond.pool import Pool, PoolMeta

TYPES_PRODUCT = [
    ('no_consumable', 'No consumable'),
    ('consumable', 'Consumable')
]

class Account(metaclass=PoolMeta):
    __name__ = 'account.account'

    # Funcion encargada de buscar las cuentas padres (parent) y verificar si tiene algún tipo asignado, para quitarselo
    @classmethod
    def delete_account_type(cls, accounts):
        pool = Pool()
        Account = pool.get('account.account')
        parents = []
        for account in accounts:
            if account.code and len(account.code) > 6 and account.type:
                if account.parent and account.parent not in parents:
                    parents.append(account.parent)
        for parent in parents:
            if parent.type:
                Account.write([parent], {'type': None})


class BalanceStockStart(ModelView):
    'Balance Stock Start'
    __name__ = 'account.fiscalyear.balance_stock.start'
    journal = fields.Many2One(
        'account.journal', "Journal", required=True)
    fiscalyear = fields.Many2One(
        'account.fiscalyear', "Fiscal Year", required=True,
        domain=[
            ('state', '=', 'open'),
            ])
    fiscalyear_start_date = fields.Function(
        fields.Date("Fiscal Year Start Date"),
        'on_change_with_fiscalyear_start_date')
    fiscalyear_end_date = fields.Function(
        fields.Date("Fiscal Year End Date"),
        'on_change_with_fiscalyear_end_date')
    date = fields.Date("Date", required=True,
        domain=[
            ('date', '>=', Eval('fiscalyear_start_date')),
            ('date', '<=', Eval('fiscalyear_end_date')),
            ],
        depends=['fiscalyear_start_date', 'fiscalyear_end_date'])
    type = fields.Selection(TYPES_PRODUCT, 'Type', required=True)
    # arbitrary_cost = fields.Boolean('Arbitrary cost')

    @classmethod
    def default_journal(cls, **pattern):
        pool = Pool()
        Configuration = pool.get('account.configuration')

        config = Configuration(1)
        journal = config.get_multivalue('stock_journal', **pattern)
        if journal:
            return journal.id

    @fields.depends('fiscalyear')
    def on_change_with_fiscalyear_start_date(self, name=None):
        if self.fiscalyear:
            return self.fiscalyear.start_date

    @fields.depends('fiscalyear')
    def on_change_with_fiscalyear_end_date(self, name=None):
        if self.fiscalyear:
            return self.fiscalyear.end_date


# Asistente encargado de ajustar las cuentas de inventario
class BalanceStock(Wizard):
    'Balance Stock Move'
    __name__ = 'account.fiscalyear.balance_stock'
    start = StateView('account.fiscalyear.balance_stock.start',
        'conector.balance_stock_start_view_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Create Move', 'balance', 'tryton-ok', default=True),
            ])
    balance = StateAction('account.act_move_form')

    def stock_balance_context(self):
        pool = Pool()
        Location = pool.get('stock.location')
        locations = Location.search([
                ('type', '=', 'warehouse'),
                ])
        return {
            'stock_date_end': self.start.date,
            'locations': list(map(int, locations)),
            'with_childs': True,
            }

    def product_domain(self):
        product_domain = [
            ('type', '=', 'goods'),
            ]
        if self.start.type == 'no_consumable':
            product_domain.append(('consumable', '=', False))
        else:
            product_domain.append(('consumable', '=', True))
        return product_domain

    def account_balance_context(self):
        return {
            'fiscalyear': self.start.fiscalyear.id,
            'date': self.start.date,
            }

    # Funcion encargada de crear un asiento con las diferentes cuentas de inventario ajustadas a una fecha dada
    def create_move(self):
        pool = Pool()
        Account = pool.get('account.account')
        Configuration = pool.get('account.configuration')
        Move = pool.get('account.move')
        Line = pool.get('account.move.line')
        Period = pool.get('account.period')
        Product = pool.get('product.product')
        out_account = Configuration(1).default_category_account_expense
        try:
            balances = defaultdict(Decimal)
            stock_accounts = set()
            with Transaction().set_context(self.stock_balance_context()):
                for product in Product.search(self.product_domain()):
                    if not product.account_category:
                        raise UserError('msg_error_balance_stock', f'{product} account_category_missing')
                    if not product.account_category.account_stock:
                        raise UserError('msg_error_balance_stock', f'{product} account_stock_missing')
                    stock_account = product.account_category.account_stock
                    cost_price = product.avg_cost_price
                    # if self.start.arbitrary_cost:
                    #     cost_price = Decimal(product.arbitrary_cost(self.start.date))
                    balances[stock_account] += (Decimal(product.quantity) * cost_price) or Decimal(0)
                    stock_accounts.add(stock_account.id)
            current_balances = {}
            with Transaction().set_context(self.account_balance_context()):
                for sub_accounts in grouped_slice(
                        Account.search([
                                ('company', '=', self.start.fiscalyear.company.id),
                                ('id', 'in', list(stock_accounts)),
                                ])):
                    for account in sub_accounts:
                        current_balances[account.id] = account.balance
            lines = []
            for stock_account in balances.keys():
                currency = stock_account.company.currency
                amount = currency.round(current_balances[stock_account.id] - balances[stock_account])
                if currency.is_zero(amount):
                    continue
                line = Line()
                line.account = stock_account
                line.debit = Decimal(0)
                line.credit = amount
                if account and stock_account.party_required:
                    line.party = self.start.fiscalyear.company.party
                lines.append(line)
                counterpart_line = Line()
                counterpart_line.account = out_account
                counterpart_line.debit = amount
                counterpart_line.credit = Decimal(0)
                if out_account and out_account.party_required:
                    counterpart_line.party = self.start.fiscalyear.company.party
                lines.append(counterpart_line)
                balances[stock_account] += amount
            if not lines:
                return
        except Exception as e:
            raise UserError('msg_error_balance_stock', str(e))

        move = Move()
        move.company = self.start.fiscalyear.company.id
        move.period = Period.find(move.company.id, date=self.start.date)
        move.journal = self.start.journal
        move.date = self.start.date
        move.lines = lines
        move.save()
        return move

    def do_balance(self, action):
        pool = Pool()
        Period = pool.get('stock.period')
        Lang = pool.get('ir.lang')
        periods = Period.search([
                ('company', '=', self.start.fiscalyear.company.id),
                ('state', '=', 'closed'),
                ('date', '>=', self.start.date),
                ], limit=1)
        if not periods:
            lang = Lang.get()
            raise PeriodCloseError(
                gettext('account_stock.msg_missing_closed_period',
                    date=lang.strftime(self.start.date)))
        move = self.create_move()
        if not move:
            lang = Lang.get()
            raise UserError('account_stock.msg_no_move', date=lang.strftime(self.start.date))
        action['res_id'] = [move.id]
        action['views'].reverse()
        return action, {}


class AnalyticAccountEntry(metaclass=PoolMeta):
    'Analytic Account Entry'
    __name__ = 'analytic.account.entry'

    """
    Se hereda la función get_analytic_lines para pasarle la fecha efectiva
    del asiento, para que la línea analitica no tome por defecto Date.today()
    """
    def get_analytic_lines(self, line, date):
        if hasattr(line, 'move'):
            date = line.move.date or line.move.post_date
        analytic_lines = super(AnalyticAccountEntry, self).get_analytic_lines(line, date)
        return analytic_lines
