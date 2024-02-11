from collections import defaultdict
from decimal import Decimal
from timeit import default_timer as timer
from datetime import date
import operator
from itertools import groupby
try:
    from itertools import izip
except ImportError:
    izip = zip
from trytond.report import Report

from sql import Column, Null, Literal, functions, Cast
from sql.aggregate import Sum, Max, Min
from sql.conditionals import Coalesce
from collections import OrderedDict
from sql.operators import Like, Between

from trytond.model.exceptions import AccessError
from trytond.i18n import gettext
from trytond.exceptions import UserError
from trytond.model import ModelView, fields, Workflow, ModelSQL
from trytond.pyson import Eval, Or, If, Bool, Not
from trytond.transaction import Transaction
from trytond.tools import grouped_slice, reduce_ids, lstrip_wildcard
from trytond.wizard import Wizard, StateView, StateAction, Button, StateReport, StateTransition
from trytond.modules.stock.exceptions import PeriodCloseError
from trytond.pool import Pool, PoolMeta

TYPES_PRODUCT = [('no_consumable', 'No consumable'),
                 ('consumable', 'Consumable')]

_ZERO = Decimal('0.0')


def _get_structured_json_data(json_data):
    data = []
    for i in json_data:
        date_json = list(i)
        dic = dict(zip(date_json, date_json))
        structured_json_body = {
            'reference': dic[date_json[0]] or "",
            'credit': dic[date_json[1]] or 0,
            'account': dic[date_json[2]] or "",
            'debit': dic[date_json[3]] or 0,
            'id': dic[date_json[4]] or "",
            'description': dic[date_json[5]] or "",
            'date': dic[date_json[6]] or "",
            'party.': {
                'name': dic[date_json[10]] or "",
                'id_number': dic[date_json[11]] or "",
                'id': dic[date_json[9]] or "",
            },
            'move.': {
                'number': dic[date_json[7]] or "",
                'id': dic[date_json[8]] or ""
            },
            'move_origin.': {
                'id': '',
                'rec_name': ''
            }
        }

        data.append(structured_json_body)

    return data


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
        if parents:
            Account.write(parents, {'type': None})


class Move(metaclass=PoolMeta):
    __name__ = 'account.move'

    @classmethod
    def _get_origin(cls):
        return super(Move, cls)._get_origin() + [
            'stock.move', 'product.product', 'product.template', 'production'
        ]


class MoveLine(metaclass=PoolMeta):
    __name__ = 'account.move.line'

    @classmethod
    def _get_origin(cls):
        return super()._get_origin() + ['stock.move']


class BalanceStockStart(ModelView):
    'Balance Stock Start'
    __name__ = 'account.fiscalyear.balance_stock.start'
    journal = fields.Many2One('account.journal', "Journal", required=True)
    fiscalyear = fields.Many2One('account.fiscalyear',
                                 "Fiscal Year",
                                 required=True,
                                 domain=[
                                     ('state', '=', 'open'),
                                 ])
    fiscalyear_start_date = fields.Function(
        fields.Date("Fiscal Year Start Date"),
        'on_change_with_fiscalyear_start_date')
    fiscalyear_end_date = fields.Function(
        fields.Date("Fiscal Year End Date"),
        'on_change_with_fiscalyear_end_date')
    date = fields.Date(
        "Date",
        required=True,
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
    start = StateView(
        'account.fiscalyear.balance_stock.start',
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
                        raise UserError('msg_error_balance_stock',
                                        f'{product} account_category_missing')
                    if not product.account_category.account_stock:
                        raise UserError('msg_error_balance_stock',
                                        f'{product} account_stock_missing')
                    stock_account = product.account_category.account_stock
                    cost_price = product.avg_cost_price
                    # if self.start.arbitrary_cost:
                    #     cost_price = Decimal(product.arbitrary_cost(self.start.date))
                    balances[stock_account] += (Decimal(product.quantity) *
                                                cost_price) or Decimal(0)
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
                amount = currency.round(current_balances[stock_account.id] -
                                        balances[stock_account])
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
        ],
                                limit=1)
        if not periods:
            lang = Lang.get()
            raise PeriodCloseError(
                gettext('account_stock.msg_missing_closed_period',
                        date=lang.strftime(self.start.date)))
        move = self.create_move()
        if not move:
            lang = Lang.get()
            raise UserError('account_stock.msg_no_move',
                            lang.strftime(self.start.date))
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
        analytic_lines = super(AnalyticAccountEntry,
                               self).get_analytic_lines(line, date)
        return analytic_lines


class AccountAsset(metaclass=PoolMeta):
    __name__ = 'account.asset'

    accumulated_depreciation = fields.Function(
        fields.Numeric("Accumulated depreciation",
                       digits=(16, Eval('currency_digits', 2)),
                       depends=['currency_digits']), 'get_depreciating_value')

    @classmethod
    def default_accumulated_depreciation(cls):
        return Decimal(0)

    @fields.depends('id')
    def get_depreciating_value(self, name=None):
        pool = Pool()
        AccountAsset = pool.get('account.asset.line')
        cursor = Transaction().connection.cursor()
        accountAsset = AccountAsset.__table__()

        where = accountAsset.asset == self.id
        where &= accountAsset.move == accountAsset.select(
            Max(accountAsset.move), where=(accountAsset.asset == self.id))
        select = accountAsset.select(accountAsset.accumulated_depreciation,
                                     where=where)

        cursor.execute(*select)
        response = cursor.fetchall()
        if response:
            return response[0][0]
        else:
            return Decimal(0)


#reporte de libro auxiliar
class AuxiliaryBookStartCDS(ModelView):
    'Auxiliary Book Start'
    __name__ = 'account_col.auxiliary_book_cds.start'
    fiscalyear = fields.Many2One('account.fiscalyear',
                                 'Fiscal Year',
                                 required=True)
    start_period = fields.Many2One('account.period',
                                   'Start Period',
                                   domain=[
                                       ('fiscalyear', '=', Eval('fiscalyear')),
                                       ('start_date', '<=',
                                        (Eval('end_period'), 'start_date')),
                                   ],
                                   depends=['fiscalyear', 'end_period'],
                                   required=True)
    end_period = fields.Many2One('account.period',
                                 'End Period',
                                 domain=[
                                     ('fiscalyear', '=', Eval('fiscalyear')),
                                     ('start_date', '>=',
                                      (Eval('start_period'), 'start_date'))
                                 ],
                                 depends=['fiscalyear', 'start_period'],
                                 required=True)
    start_account = fields.Many2One('account.account',
                                    'Start Account',
                                    domain=[
                                        ('type', '!=', None),
                                        ('code', '!=', None),
                                    ])
    end_account = fields.Many2One('account.account',
                                  'End Account',
                                  domain=[
                                      ('type', '!=', None),
                                      ('code', '!=', None),
                                  ])
    start_code = fields.Char('Start Code Account')
    end_code = fields.Char('End Code Account')
    party = fields.Many2One('party.party',
                            "Party",
                            context={
                                'company': Eval('company', -1),
                            },
                            depends=['company'])
    company = fields.Many2One('company.company', 'Company', required=True)
    posted = fields.Boolean('Posted Move', help='Show only posted move')
    colgaap = fields.Boolean('Colgaap')
    reference = fields.Char('Reference')
    empty_account = fields.Boolean('Empty Account',
                                   help='With account without move')

    @staticmethod
    def default_fiscalyear():
        FiscalYear = Pool().get('account.fiscalyear')
        return FiscalYear.find(Transaction().context.get('company'),
                               exception=False)

    @staticmethod
    def default_company():
        return Transaction().context.get('company')

    @staticmethod
    def default_posted():
        return False

    @staticmethod
    def default_empty_account():
        return False

    @fields.depends('fiscalyear')
    def on_change_fiscalyear(self):
        self.start_period = None
        self.end_period = None


class PrintAuxiliaryBookCDS(Wizard):
    'Print Auxiliary Book'
    __name__ = 'account_col.auxiliary_book_print'
    start = StateView(
        'account_col.auxiliary_book_cds.start',
        'conector.print_auxiliary_book_start_view_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Print', 'print_', 'tryton-print', default=True),
        ])
    print_ = StateReport('account_col.auxiliary_book_cds.report')

    def _search_records(self):
        pass

    def do_print_(self, action):
        try:
            start_period = self.start.start_period.id
        except:
            start_period = None

        try:
            end_period = self.start.end_period.id
        except:
            end_period = None

        try:
            party = self.start.party.id
        except:
            party = None

        try:
            start_account_id = self.start.start_account.id
        except:
            start_account_id = None

        try:
            end_account_id = self.start.end_account.id
        except:
            end_account_id = None

        data = {
            'ids': [],
            'company': self.start.company.id,
            'fiscalyear': self.start.fiscalyear.id,
            'start_period': start_period,
            'end_period': end_period,
            'posted': self.start.posted,
            'colgaap': self.start.colgaap,
            'start_account': start_account_id,
            'end_account': end_account_id,
            'party': party,
            'empty_account': self.start.empty_account,
            'reference': self.start.reference,
            'fiscalyearname': self.start.fiscalyear.name
        }
        return action, data

    def transition_print_(self):
        return 'end'


class AuxiliaryBookCDS(Report):
    __name__ = 'account_col.auxiliary_book_cds.report'

    @classmethod
    def get_context(cls, records, header, data):

        start = timer()
        report_context = super().get_context(records, header, data)
        pool = Pool()

        Account = pool.get('account.account')
        Move = pool.get('account.move')
        Line = pool.get('account.move.line')
        cursor = Transaction().connection.cursor()
        Period = pool.get('account.period')
        Company = pool.get('company.company')
        Party = pool.get('party.party')
        company = Company(data['company'])

        accountLine = Line.__table__()
        accountmove = Move.__table__()

        start_period_name = None
        end_period_name = None
        dom_accounts = [
            ('company', '=', data['company']),
            ('type', '!=', None),
        ]
        start_code = None
        if data['start_account']:
            start_acc = Account(data['start_account'])
            start_code = start_acc.code
            dom_accounts.append(('code', '>=', start_acc.code))
        end_code = None
        if data['end_account']:
            end_acc = Account(data['end_account'])
            end_code = end_acc.code
            dom_accounts.append(('code', '<=', end_acc.code))

        accounts = Account.search(dom_accounts, order=[('code', 'ASC')])

        # --------------------------------------------------------------
        start_period_ids = [0]
        start_periods = []
        if data['start_period']:
            start_period = Period(data['start_period'])
            start_periods = Period.search([
                ('fiscalyear', '=', data['fiscalyear']),
                ('end_date', '<=', start_period.start_date),
            ])
            start_period_ids += [p.id for p in start_periods]
            start_period_name = start_period.name

        noSelectPerid = Period.search([('fiscalyear', '<', data['fiscalyear'])
                                       ])
        start_date = [p.id for p in noSelectPerid]
        # --------------------------------------------------------------
        end_period_ids = []
        if data['end_period']:
            end_period = Period(data['end_period'])
            end_periods = Period.search([
                ('fiscalyear', '=', data['fiscalyear']),
                ('end_date', '<=', end_period.start_date),
            ])
            if end_period not in end_periods:
                end_periods.append(end_period)
            end_period_name = end_period.name
        else:
            end_periods = Period.search([
                ('fiscalyear', '=', data['fiscalyear']),
            ])
        end_period_ids = [p.id for p in end_periods]

        party = None

        def get_party(account=None, party=None):
            # --------------------------------------------------------------

            # Consulta para los saldos debitos y creeditos iniciales
            initial = ''
            date_initial = ''
            if noSelectPerid:
                date_initial = start_date + start_period_ids
                if data['start_period'] != start_date[0]:
                    initial = str(data['start_period'] - 1)
                else:
                    initial = str(start_date[0])
            else:
                date_initial = start_period_ids
                initial = str(data['start_period'])

            print(initial, date_initial)
            if account:
                where = accountLine.account == account
            if date_initial:
                where &= accountmove.period.in_(date_initial)
            if party:
                where &= accountLine.party == party
            if data['posted']:
                where &= accountmove.state == 'posted'

            # Consulta para el balance inicial
            select2 = accountLine.join(
                accountmove,
                'LEFT',
                condition=(accountLine.move == accountmove.id)).select(
                    Sum(accountLine.credit),
                    Sum(accountLine.debit),
                    Sum(
                        Coalesce(accountLine.debit, 0) -
                        Coalesce(accountLine.credit, 0)),
                    where=where)

            cursor.execute(*select2)
            result_start = cursor.fetchall()

            # initial = str(data['start_period']-1) if data['start_period'] and data['start_period'] != start_date[0]  else str(start_date[0])
            where &= accountmove.period == initial
            if data['posted']:
                where &= accountmove.state == 'posted'

            query = accountLine.join(
                accountmove,
                'LEFT',
                condition=(accountLine.move == accountmove.id)).select(
                    Sum(accountLine.credit),
                    Sum(accountLine.debit),
                    Sum(
                        Coalesce(accountLine.debit, 0) -
                        Coalesce(accountLine.credit, 0)),
                    where=where)

            cursor.execute(*query)
            initial_balance = cursor.fetchall()
            print(initial_balance)
            #retornamos la consulta con los saldos debitos, credito y el balance inicial, ademas, con la cuenta respectiva para asociarlos
            return initial_balance, result_start, account

        with Transaction().set_context(fiscalyear=data['fiscalyear'],
                                       periods=start_period_ids,
                                       party=data['party'],
                                       posted=data['posted'],
                                       colgaap=data['colgaap']):
            start_accounts = Account.browse(accounts)

        end1 = timer()
        delta1 = (end1 - start)
        id2start_account = {}
        balance = {}
        accountBalance = {}
        for account in start_accounts:
            id2start_account[account.id] = account
            #Evalua si el reporte fue filtrado por tercero o no, si lo esta ingresa a realiza la consulta del tercero por cada una de las cuentas seleccionadas
            if data['party'] != None:
                party, = Party.search([('id', '=', data['party'])])
                initial_balance, result_start, accountId = get_party(
                    account=account.id, party=data['party']
                )  # se obtiene los balances iniciales de los terceros con cada una de las cuentas
                if (None in list(initial_balance[0])) or (None in list(
                        result_start[0])):
                    print('esta entrando aqui')
                    accountBalance[accountId] = result_start[0][
                        2]  # En este diccionario se agrega cada saldos inciales asociado a cada una de las cuentas
                    id2start_account[
                        accountId].credit = initial_balance[0][0] or 0
                    id2start_account[
                        accountId].debit = initial_balance[0][1] or 0
                    id2start_account[
                        accountId].balance = result_start[0][2] or 0

        # --------------------------------------------------------------

        with Transaction().set_context(fiscalyear=data['fiscalyear'],
                                       periods=end_period_ids,
                                       party=data['party'],
                                       posted=data['posted'],
                                       colgaap=['colgaap']):
            end_accounts = Account.browse(accounts)

        end2 = timer()
        delta2 = (end2 - end1)
        id2end_account = {}
        for account in end_accounts:
            id2end_account[account.id] = account

        if not data['empty_account']:
            accounts_ids = [a.id for a in accounts]
            account2lines = dict(
                cls.get_lines(accounts, end_periods, data['posted'],
                              data['party'], data['reference'],
                              data['colgaap']))

            accounts_ = account2lines.keys()
            with Transaction().set_context(party=data['party'],
                                           posted=data['posted'],
                                           colgaap=['colgaap']):
                accounts = Account.browse(
                    [a for a in accounts_ids if a in accounts_])

        end3 = timer()
        delta3 = (end3 - end2)

        account_id2lines, result = cls.lines(
            accounts, list(set(end_periods).difference(set(start_periods))),
            data['posted'], data['party'], data['reference'], data['colgaap'])

        if party != None:
            for start_account in accountBalance:
                #Recorremos el diccionario con la informacion de los saldos iniciales de cada una de las cuenta y evaluamos si esta cuenta, tiene informaciones relacionada para cargas los datos
                if start_account in result.keys():
                    credit = result[start_account].get('credit') or 0
                    debit = result[start_account].get('debit') or 0
                    balance = accountBalance.get(start_account) or 0
                    id2end_account[start_account].credit = credit
                    id2end_account[start_account].debit = debit
                    id2end_account[start_account].balance = ((debit - credit) +
                                                             balance)

        report_context['start_period_name'] = start_period_name
        report_context['end_period_name'] = end_period_name
        report_context['start_code'] = start_code
        report_context['end_code'] = end_code
        report_context['party'] = party
        report_context['accounts'] = accounts
        report_context['id2start_account'] = id2start_account
        report_context['id2end_account'] = id2end_account
        report_context['digits'] = company.currency.digits
        report_context['lines'] = lambda account_id: account_id2lines[
            account_id]
        report_context['company'] = company

        end4 = timer()
        delta4 = (end4 - end3)

        end = timer()
        delta_total = (end - start)
        return report_context

    @classmethod
    def get_lines(cls,
                  accounts,
                  periods,
                  posted,
                  party=None,
                  reference=None,
                  colgaap=False):
        cursor = Transaction().connection.cursor()
        _lineas = None
        where = None
        MoveLine = Pool().get('account.move.line')
        Account = Pool().get('account.move')
        Party = Pool().get('party.party')

        moveLine = MoveLine.__table__()
        account = Account.__table__()
        partys = Party.__table__()

        accountfilter = [a.id for a in accounts]
        periodsfilter = [p.id for p in periods]

        #Estructura condicional de where para realizar el filtro de la informacion
        if periodsfilter:
            where = account.period.in_(periodsfilter)
        if accountfilter:
            where &= moveLine.account.in_(accountfilter)
        if party:
            where &= moveLine.party == party
        if posted:
            where &= account.state == 'posted'
        if reference:
            where &= moveLine.reference.like_(reference)
        print(accountfilter, periodsfilter)
        #Consulta que trae cada una de las lineas de las cuentas
        query = moveLine.join(
            partys, 'LEFT', condition=(partys.id == moveLine.party)).join(
                account, 'LEFT',
                condition=(moveLine.move == account.id)).select(
                    moveLine.reference,
                    moveLine.credit,
                    moveLine.account,
                    moveLine.debit,
                    moveLine.id,
                    moveLine.description,
                    account.date,
                    account.number,
                    account.id,
                    moveLine.party,
                    partys.name,
                    partys.id_number,
                    where=where)

        cursor.execute(*query)
        _lineas = cursor.fetchall()

        lines = _get_structured_json_data(
            _lineas
        )  #Aqui se obtiene la estructura de json que pasara para generar el reporte
        key = operator.itemgetter('account')
        lines.sort(key=key)
        val = groupby(lines, key)
        return val

    @classmethod
    def lines(cls,
              accounts,
              periods,
              posted,
              party=None,
              reference=None,
              colgaap=False):
        res = dict((a.id, []) for a in accounts)
        result = {}
        if res:
            account2lines = cls.get_lines(accounts, periods, posted, party,
                                          reference, colgaap)
            for account_id, lines in account2lines:
                balance = _ZERO
                credit = _ZERO
                debit = _ZERO
                rec_append = res[account_id].append
                for line in lines:
                    line['move'] = line['move.']['number']
                    balance += line['debit'] - line['credit']
                    if line['party.']:
                        line['party'] = line['party.']['name']
                        line['party_id'] = line['party.']['id_number']
                    if line['move_origin.']:
                        line['origin'] = line['move_origin.']['rec_name']
                    credit += line['credit']
                    debit += line['debit']
                    line['balance'] = balance
                    rec_append(line)
                if party != None:
                    # Se acomulan los valores creditos y debitos de cada cuenta para realizar el calculo del saldo inicial para el proximo periodo
                    result[account_id] = {
                        'credit': credit,
                        'debit': debit,
                    }
        else:
            # Si el reporte no cuenta con informacion, el usuario recibira este mensaje y no se ejectara el reporte.
            raise UserError(
                message=None,
                description=
                f"El reporte no contiene informacion, no es posible generarlo")
        return res, result


#Forzar a borrador de activo fijo
class ActiveForceDraft(Wizard):
    'Active Force Draft'
    __name__ = 'account.invoice_asset.force_draft'
    start_state = 'force_draft'
    force_draft = StateTransition()

    def transition_force_draft(self):
        pool = Pool()
        Asset = pool.get('account.asset')
        ids_ = Transaction().context['active_ids']
        for id_ in ids_:
            asset = Asset(id_)
            assetTable = Asset.__table__()
            #Validacion para saber si el activo se encuentra cerrado
            if asset.state == 'closed':
                raise UserError(
                    'AVISO',
                    f'El activo numero {asset.number} se encuentra cerrado y no es posible forzar su borrado'
                )
            #Validacion para saber si el activo ya se encuentra en borrador
            if asset.state == 'draft':
                return 'end'
            cursor = Transaction().connection.cursor()
            #Consulta que le asigna el estado borrado al activo
            if id_:
                cursor.execute(*assetTable.update(columns=[
                    assetTable.state,
                ],
                                                  values=["draft"],
                                                  where=assetTable.id == id_))

        return 'end'


# Reporte de estado de resultado integral
class IncomeStatementView(ModelView):
    'Income Statement View'
    __name__ = 'account.income_statement.start'
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

    posted = fields.Boolean('Posted Move', help='Show only posted move')

    accumulated = fields.Boolean('Accumulated',
                                 help='Show detailed report',
                                 on_change_with='on_change_with_accumulated')

    Analitic_filter = fields.Boolean(
        'Analytic Detailed',
        help='Show Analytic Detailed',
        on_change_with='on_change_with_Analitic_filter')

    analytic_accounts = fields.Many2Many('analytic_account.account',
                                         None,
                                         None,
                                         'Analytic Account',
                                         states={
                                             'readonly':
                                             ~Not(Eval('allstart')),
                                             'required':
                                             ~Bool(Eval('allstart'))
                                         },
                                         depends=['allstart'],
                                         domain=[
                                             ('active', '=', True),
                                         ])

    allstart = fields.Boolean('All',
                              help='Show all Analytic',
                              on_change_with='on_change_with_allstart')

    @staticmethod
    def default_fiscalyear():
        FiscalYear = Pool().get('account.fiscalyear')
        return FiscalYear.find(Transaction().context.get('company'),
                               exception=False)

    @staticmethod
    def default_company():
        return Transaction().context.get('company')

    @staticmethod
    def default_posted():
        return False

    @staticmethod
    def default_accumulated():
        return True

    @staticmethod
    def default_allstart():
        return True

    @fields.depends('Analitic_filter')
    def on_change_with_accumulated(self, name=None):
        res = True
        if self.Analitic_filter:
            res = False

        return res

    @fields.depends('accumulated')
    def on_change_with_Analitic_filter(self, name=None):
        res = True
        if self.accumulated:
            res = False

        return res

    @fields.depends('analytic_accounts')
    def on_change_with_allstart(self, name=None):
        res = True
        if self.analytic_accounts:
            res = False
        return res


class IncomeStatementWizard(Wizard):
    'Income Statement Wizard'
    __name__ = 'account.income_statement_wizard_cds'
    start = StateView(
        'account.income_statement.start',
        'conector.detailed_income_statement_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Print', 'print_', 'tryton-print', default=True),
        ])
    print_ = StateReport('account.income_statement_report')

    def do_print_(self, action):
        accumulated = False
        Analitic_filter = False
        allstart = False
        analytic_accounts_ids = []
        if self.start.accumulated:
            accumulated = True
        if self.start.Analitic_filter:
            Analitic_filter = True
        if self.start.allstart:
            allstart = True

        if self.start.analytic_accounts and not allstart:
            analytic_accounts_ids = [
                acc.id for acc in self.start.analytic_accounts
            ]

        data = {
            'company': self.start.company.id,
            'from_date': self.start.from_date,
            'to_date': self.start.to_date,
            'analytic_accounts': analytic_accounts_ids,
            'posted': self.start.posted,
            'accumulated': accumulated,
            'Analitic_filter': Analitic_filter,
            'allstart': allstart
        }
        print(data)
        return action, data

    def transition_print_(self):

        return 'end'


class IncomeStatementReport(Report):
    'Income Statement Report'
    __name__ = 'account.income_statement_report'

    @classmethod
    def get_context(cls, records, header, data):
        report_context = super().get_context(records, header, data)
        pool = Pool()
        cursor = Transaction().connection.cursor()
        Account = pool.get('account.account')
        Move = pool.get('account.move')
        Line = pool.get('account.move.line')
        AccountType = pool.get('account.account.type')
        Company = pool.get('company.company')
        AnalyticAccount = pool.get('analytic_account.account')
        AnalyticAccountLine = pool.get('analytic_account.line')

        account = Account.__table__()
        accountType = AccountType.__table__()
        move = Move.__table__()
        line = Line.__table__()
        analyticAccount = AnalyticAccount.__table__()
        analyticAccountLine = AnalyticAccountLine.__table__()

        # Realizamos las condiciones para la busqueda en la base de datos
        where = analyticAccountLine.date >= data['from_date']
        where &= analyticAccountLine.date <= data['to_date']
        where &= accountType.statement == 'income'
        where &= analyticAccount.active == True

        # if data['posted']:
        #     where &= move.state == 'posted'

        # si cumple la siguiente codicion, se
        # agregan los id de las cuentas analiticas
        # seleccionadas en los parametros de entrada
        if data['analytic_accounts'] and not data['allstart']:

            where &= analyticAccount.id.in_(data['analytic_accounts'])

        # Aqui se asignan las columnas para los parametros que extraeremos de la db
        columns = {
            'parent_results': accountType.parent,
            'type_account': accountType.name,
            'sequence': accountType.sequence,
            'id_analytic': analyticAccount.code,
            'name_analytic': analyticAccount.name,
            'account': account.code,
            'name': account.name,
            'date': analyticAccountLine.date,
            'description_line': line.description,
            'debit': analyticAccountLine.debit,
            'credit': analyticAccountLine.credit,
            'neto':
            Sum(analyticAccountLine.debit - analyticAccountLine.credit),
        }

        # Construccion de la consulta a la
        # base de datos, con sintaxis de pythom-sql
        selected = analyticAccountLine.join(
            line, 'LEFT',
            condition=analyticAccountLine.move_line == line.id).join(
                account, 'LEFT', condition=account.id == line.account).join(
                    accountType,
                    'LEFT',
                    condition=accountType.id == account.type).join(
                        analyticAccount,
                        'LEFT',
                        condition=analyticAccountLine.account ==
                        analyticAccount.id).select(
                            *columns.values(),
                            where=where,
                            group_by=(accountType.sequence,
                                      analyticAccountLine.id, account.name,
                                      account.code, line.description,
                                      analyticAccount.code,
                                      analyticAccount.name, accountType.name,
                                      accountType.parent),
                            order_by=(account.code))

        # ejecuta la consulta, el * se asigna para que lo pase como un string
        cursor.execute(*selected)

        # Realizamos un fetch a la consulta para extraer los datos obtenidos
        result = cursor.fetchall()

        records = []

        print(result)
        # Realizamos validacion para saber si existen datos extraidos de la db
        if result:
            finalitems = {}
            items = {}

            for index, record in enumerate(result):
                fila_dict = OrderedDict(
                )  # Le damos la extructura de diccionario

                # con esta funcion lo que hacemos es crear el
                # diccionario con las claves de las columnas
                # y asi sea mas facil acceder a los datos
                fila_dict = dict(zip(columns.keys(), record))

                parent_results = fila_dict['parent_results']
                type_account = fila_dict['type_account']
                analytic_name = fila_dict['name_analytic']
                sequence = fila_dict['sequence']

                # Si se selecciono la opcion de 'Analitic_filter'
                # en los parametros de entrada, ingresamos
                # directamente a ingresar el diccionario de datos
                if data['Analitic_filter']:

                    records.append(fila_dict)

                elif data['accumulated']:

                    if analytic_name not in items:
                        items[analytic_name] = {'account_type': {}}

                    if sequence not in items[analytic_name]['account_type']:
                        items[analytic_name]['account_type'][sequence] = {
                            'account_type': type_account,
                            'neto': 0
                        }

                    items[analytic_name]['account_type'][sequence][
                        'neto'] += fila_dict['neto']

                # Es este tramo de codigo, realizamos una acomulacion
                # de los datos para la extrutura de el estado de
                # resultado, utilidas bruta, utilidad antes de
                # impuesto y utilidad neta
                if analytic_name not in finalitems:
                    name = AccountType.search_read(
                        [('name', '=', 'UTILIDAD NETA')],
                        fields_names=['sequence', 'name'])
                    finalitems[analytic_name] = {
                        'parent_results': {},
                        'sequence': name[0]['sequence'],
                        'name': name[0]['name'],
                        'UTILIDAD_NETA': 0
                    }

                if parent_results not in finalitems[analytic_name][
                        'parent_results']:
                    name = AccountType.search_read(
                        [('id', '=', parent_results)],
                        fields_names=['name', 'sequence'])
                    finalitems[analytic_name]['parent_results'][
                        parent_results] = {
                            'account_type_result': name[0]['name'],
                            'sequence': name[0]['sequence'],
                            'neto_secuence': 0,
                        }

                finalitems[analytic_name]['parent_results'][parent_results][
                    'neto_secuence'] += fila_dict['neto']
                finalitems[analytic_name]['UTILIDAD_NETA'] += fila_dict['neto']

        else:
            # Si el reporte no cuenta con informacion, el usuario recibira este mensaje y no se ejectara el reporte.
            raise UserError(
                message=None,
                description=
                f"El reporte no contiene informacion, no es posible generarlo")

        report_context['accumulated'] = str(data['accumulated'])
        report_context['Analitic_filter'] = str(data['Analitic_filter'])
        report_context['finalitems'] = finalitems
        report_context['records'] = records if records else items
        report_context['company'] = Company(
            Transaction().context.get('company'))
        report_context['date'] = Transaction().context.get('date')
        return report_context


class TrialBalanceDetailedCds(metaclass=PoolMeta):
    'Balanced Trial Report'
    __name__ = 'account_col.trial_balance_detailed'

    @classmethod
    def get_context(cls, records, header, data):
        """Function that get context and print report"""

        report_context = super().get_context(records, header, data)
        pool = Pool()
        account = pool.get('account.account')
        account_move = pool.get('account.move')
        account_move_line = pool.get('account.move.line')
        period = pool.get('account.period')
        company = pool.get('company.company')
        party = pool.get('party.party')
        fiscal_years = pool.get('account.fiscalyear')
        cursor = Transaction().connection.cursor()

        move = account_move.__table__()
        line = account_move_line.__table__()
        start_period_name = None
        end_period_name = None

        # ----- Set Periods -----
        start_periods = []

        if data['start_period']:
            start_period = period(data['start_period'])
            start_periods = period.search([
                ('end_date', '<', start_period.start_date),
            ])
            start_period_name = start_period.name
        else:
            fiscalyear = fiscal_years(data['fiscalyear'])
            start_periods = period.search([
                ('end_date', '<=', fiscalyear.start_date),
            ])

        if data['end_period']:
            end_period = period(data['end_period'])
            end_periods = period.search([
                ('fiscalyear', '=', data['fiscalyear']),
                ('end_date', '<=', end_period.start_date),
            ])
            end_periods = list(set(end_periods).difference(set(start_periods)))
            end_period_name = end_period.name
            if end_period not in end_periods:
                end_periods.append(end_period)
        else:
            end_periods = period.search([
                ('fiscalyear', '=', data['fiscalyear']),
                ('end_date', '>=', start_period.start_date),
            ])
            end_periods = list(set(end_periods).difference(set(start_periods)))

        # Select Query for In
        in_periods = [p.id for p in end_periods]
        join1 = line.join(move)
        join1.condition = join1.right.id == line.move

        entity = line.party
        default_entity = 0
        if not data['party'] and data['by_reference']:
            entity = line.reference
            default_entity = '0'

        select1 = join1.select(
            line.account,
            Coalesce(entity, default_entity),
            Sum(line.debit),
            Sum(line.credit),
            group_by=(line.account, entity),
            order_by=line.account,
        )

        select1.where = join1.right.period.in_(in_periods)

        if data['party']:
            select1.where = select1.where & (line.party == data['party'])

        if data['accounts']:
            select1.where = select1.where & (line.account.in_(
                data['accounts']))
        if data['posted']:
            select1.where = select1.where & (move.state == 'posted')
        cursor.execute(*select1)
        result_in = cursor.fetchall()

        # Select Query for Start
        start_periods_ids = [p.id for p in start_periods]
        result_start = []

        if start_periods_ids:
            join1 = line.join(move)
            join1.condition = join1.right.id == line.move

            select2 = join1.select(
                line.account,
                Coalesce(entity, default_entity),
                Sum(line.debit) - Sum(line.credit),
                group_by=(line.account, entity),
                order_by=line.account,
            )
            select2.where = join1.right.period.in_(start_periods_ids)

            if data['party']:
                select2.where = select2.where & (line.party == data['party'])

            if data['accounts']:
                select2.where = select2.where & (line.account.in_(
                    data['accounts']))

            cursor.execute(*select2)
            result_start = cursor.fetchall()

        all_result = result_in + result_start
        accs_ids = []
        parties_ids = []
        for r in all_result:
            accs_ids.append(r[0])
            parties_ids.append(r[1])

        accounts = OrderedDict()

        # Prepare accounts
        if accs_ids:
            acc_records = account.search_read([
                ('id', 'in', list(set(accs_ids))),
                ('active', 'in', [False, True]),
            ],
                                              order=[('code', 'ASC')],
                                              fields_names=['code', 'name'])

            for acc in acc_records:
                accounts[acc['id']] = [
                    acc, {}, {
                        'debits': [],
                        'credits': [],
                        'start_balance': [],
                        'end_balance': [],
                    }
                ]

            if not data['by_reference']:
                parties_obj = party.search_read(
                    [
                        ('id', 'in', parties_ids),
                        ('active', 'in', [False, True]),
                    ],
                    fields_names=['id_number', 'name'])

                parties = {p['id']: p for p in parties_obj}
            else:
                parties = {p: p for p in parties_ids}

            cls._get_process_result(parties,
                                    data,
                                    accounts,
                                    kind='in',
                                    values=result_in)

            cls._get_process_result(parties,
                                    data,
                                    accounts,
                                    kind='start',
                                    values=result_start)

        if accounts:
            records = accounts.values()
        else:
            records = accounts
        report_context['accounts'] = records
        report_context['fiscalyear'] = fiscal_years(data['fiscalyear'])
        report_context['start_period'] = start_period_name
        report_context['end_period'] = end_period_name
        report_context['company'] = company(data['company'])
        return report_context

    @classmethod
    def _get_process_result(cls, parties, data, accounts, kind, values):
        for val in values:
            party_id = 0
            id_number = '---'
            party_name = '---'
            if not data['by_reference']:
                if val[1]:
                    party_id = val[1]
                    id_number = parties[party_id]['id_number']
                    party_name = parties[party_id]['name']
            else:
                party_id = val[1]
                id_number = val[1]
                party_name = val[1]

            acc_id = val[0]

            debit = 0
            credit = 0
            start_balance = 0

            if kind == 'in':
                debit = val[2]
                credit = val[3]
                amount = debit - credit
            else:  # kind == start
                start_balance = val[2]
                amount = val[2]
            if debit == credit == start_balance == 0:
                continue

            if party_id not in accounts[acc_id][1].keys():
                end_balance = start_balance + debit - credit
                rec = {
                    'id_number': id_number,
                    'party': party_name,
                    'start_balance': start_balance,
                    'debit': debit,
                    'credit': credit,
                    'end_balance': end_balance,
                }
                accounts[acc_id][1][party_id] = rec
                amount = end_balance
            else:
                dictval = accounts[acc_id][1][party_id]
                if kind == 'in':
                    dictval['debit'] = debit
                    dictval['credit'] = credit
                else:
                    dictval['start_balance'] = start_balance

                end_balance = dictval['start_balance'] + dictval[
                    'debit'] - dictval['credit']
                dictval['end_balance'] = end_balance

            accounts[acc_id][2]['debits'].append(debit)
            accounts[acc_id][2]['credits'].append(credit)
            accounts[acc_id][2]['start_balance'].append(start_balance)
            accounts[acc_id][2]['end_balance'].append(amount)


class PartyWithholdingStart(metaclass=PoolMeta):
    'Party Withholding Start View'
    __name__ = 'account.party_withholding.start'

    addresses = fields.Selection('selection_city',
                                 'City Report',
                                 states={
                                     'invisible': Eval('classification')
                                     != 'ica',
                                     'required':
                                     Eval('classification') == 'ica',
                                 })
    classification = fields.Selection('selection_certificate_type',
                                      'Certificate Report')

    @classmethod
    def selection_city(cls):
        """This function return addresses of company"""
        # pylint: disable=no-member
        pool = Pool()
        id_company = cls.default_company()
        companies = pool.get("company.company")
        parties = pool.get("party.party")
        party_addresses = pool.get("party.address")

        company = companies.search(["id", "=", id_company])
        party = parties.search(["id", "=", company[0].party])
        party_addresses = party_addresses.search(["party", "=", party[0].id])

        options = cls.list_addresses(party_addresses)
        return options

    @classmethod
    def list_addresses(cls, party_addresses):
        """This function return list of address"""
        options = [("", "")]

        for party_address in party_addresses:
            if party_address.name:
                options.append(
                    (party_address.name, party_address.name.title()))

        return options


class PrintPartyWithholding(metaclass=PoolMeta):
    'Print Withholding Wizzard'
    __name__ = 'account.print_party_withholding'
    start = StateView('account.party_withholding.start',
                      'account_col.print_party_withholding_start_view_form', [
                          Button('Cancel', 'end', 'tryton-cancel'),
                          Button('Ok', 'print_', 'tryton-ok', default=True),
                      ])
    print_ = StateReport('account_col.party_withholding')

    def do_print_(self, action):
        if self.start.start_period:
            start_period = self.start.start_period.id
        else:
            start_period = None
        if self.start.end_period:
            end_period = self.start.end_period.id
        else:
            end_period = None

        party_id = None
        if self.start.party:
            party_id = self.start.party.id
        data = {
            'company': self.start.company.id,
            'fiscalyear': self.start.fiscalyear.id,
            'party': party_id,
            'classification': self.start.classification,
            'start_period': start_period,
            'end_period': end_period,
            'detailed': self.start.detailed,
            'addresses': self.start.addresses,
        }
        return action, data


class PartyWithholding(metaclass=PoolMeta):
    'Withholding Report'
    __name__ = 'account_col.party_withholding'

    @classmethod
    def get_context(cls, records, header, data):
        report_context = super().get_context(records, header, data)
        cursor = Transaction().connection.cursor()
        pool = Pool()
        # InvoiceTax = pool.get('account.invoice.tax')
        Tax = pool.get('account.tax')
        MoveLine = pool.get('account.move.line')
        Move = pool.get('account.move')
        Account = pool.get('account.account')
        Company = pool.get('company.company')
        Period = pool.get('account.period')
        Fiscalyear = pool.get('account.fiscalyear')
        Party = pool.get('party.party')
        party_addresses = pool.get("party.address")
        company = Company(data['company'])

        address = {
            "city": company.party.city_name,
            "address": company.party.street
        }

        city = data["addresses"]

        if city:
            address_city = party_addresses.search(["name", "=", city])
            address = {"city": city, "address": address_city[0].street}

        move = Move.__table__()
        line = MoveLine.__table__()
        tax = Tax.__table__()
        account = Account.__table__()

        where = tax.classification != Null
        if data['party']:
            where &= line.party == data['party']
        else:
            where &= line.party != null

        dom_periods = [
            ('fiscalyear', '=', data['fiscalyear']),
        ]
        if data['start_period']:
            start_period = Period(data['start_period'])
            dom_periods.append(('start_date', '>=', start_period.start_date))

        if data['end_period']:
            end_period = Period(data['end_period'])
            dom_periods.append(('start_date', '<=', end_period.start_date))

        periods = Period.search(dom_periods, order=[('start_date', 'ASC')])
        period_ids = [p.id for p in periods]

        where &= move.period.in_(period_ids)
        if data['classification']:
            where &= tax.classification == data['classification']

        if data['detailed']:
            columns = [
                line.party, tax.classification,
                tax.id.as_('tax_id'), tax.rate,
                account.name.as_('account'), tax.description, move.date,
                line.id.as_('line_id'),
                (line.debit - line.credit).as_('amount'), line.move
            ]

            query = tax.join(
                line,
                condition=(
                    (tax.credit_note_account == line.account)
                    or (tax.invoice_account == line.account))).join(
                        move, condition=line.move == move.id).join(
                            account,
                            condition=line.account == account.id).select(
                                *columns,
                                where=where,
                                order_by=[
                                    line.party, tax.classification,
                                    line.create_date.asc
                                ])

            records, move_ids = cls.query_to_dict_detailed(query)
            moves = Move.search_read([('id', 'in', move_ids)],
                                     fields_names=['origin.rec_name'])
            moves_ = {}
            for v in moves:
                try:
                    moves_[v['id']] = v['origin.']['rec_name']
                except:
                    moves_[v['id']] = None
            report_context['moves'] = moves_
        else:
            columns = [
                line.party,
                tax.classification,
                tax.id.as_('tax_id'),
                tax.rate,
                account.name.as_('account'),
                tax.description,
                Sum(line.debit - line.credit).as_('amount'),
            ]
            query = tax.join(
                line,
                condition=(
                    (tax.credit_note_account == line.account)
                    or (tax.invoice_account == line.account))).join(
                        move, condition=line.move == move.id).join(
                            account,
                            condition=line.account == account.id).select(
                                *columns,
                                where=where,
                                group_by=[
                                    line.party, tax.classification, tax.id,
                                    tax.rate, account.name, tax.description
                                ],
                                order_by=[line.party, tax.classification])
            records = cls.query_to_dict(query)

        report_context['records'] = records.values()
        report_context['detailed'] = data['detailed']
        report_context['fiscalyear'] = Fiscalyear(data['fiscalyear'])
        report_context['start_date'] = periods[0].start_date
        report_context['end_date'] = periods[-1].end_date
        report_context['today'] = date.today()
        report_context['company'] = company
        report_context['address'] = address

        return report_context

    @classmethod
    def query_to_dict_detailed(cls, query):
        cursor = Transaction().connection.cursor()
        Party = Pool().get('party.party')
        cursor.execute(*query)
        columns = list(cursor.description)
        result = cursor.fetchall()
        res_dict = {}
        moves_ids = set()

        for row in result:
            row_dict = {}
            key_id = str(row[0]) + row[1]
            for i, col in enumerate(columns):
                row_dict[col.name] = row[i]
            row_dict['base'] = row[8] / row[3] * (-1)
            try:
                res_dict[key_id]['taxes_with'].append(row_dict)
                res_dict[key_id]['total_amount'] += row_dict['amount']
                res_dict[key_id]['total_untaxed'] += row_dict['base']
                moves_ids.add(row_dict['move'])
            except:
                res_dict[key_id] = {
                    'party': Party(row[0]),
                    'tax_type': row_dict['classification'],
                    'taxes_with': [row_dict],
                    'total_amount': row_dict['amount'],
                    'total_untaxed': row_dict['base']
                }
                moves_ids.add(row_dict['move'])
        return res_dict, moves_ids

    @classmethod
    def query_to_dict(cls, query):
        cursor = Transaction().connection.cursor()
        Party = Pool().get('party.party')
        cursor.execute(*query)
        columns = list(cursor.description)
        result = cursor.fetchall()
        res_dict = {}

        for row in result:
            row_dict = {}
            key_id = str(row[0]) + row[1] + str(row[3])
            for i, col in enumerate(columns):
                row_dict[col.name] = row[i]
            row_dict['base'] = row[6] / row[3] * (-1)
            try:
                res_dict[key_id]['amount'] += row_dict['amount']
                res_dict[key_id]['base'] += row_dict['base']
            except:
                res_dict[key_id] = {
                    'party': Party(row[0]),
                    'tax_type': row_dict['classification'],
                    'account': row_dict['account'],
                    'description': row_dict['description'],
                    'amount': row_dict['amount'],
                    'base': row_dict['base']
                }
        return res_dict


class AuxiliaryPartyStart(metaclass=PoolMeta):
    'Auxiliary Party Start'
    __name__ = 'account_col.print_auxiliary_party.start'

    @classmethod
    def __setup__(cls):
        super(AuxiliaryPartyStart, cls).__setup__()
        cls.start_period.required = True
        cls.end_period.required = True


class AuxiliaryParty(metaclass=PoolMeta):
    """Party movements report"""
    __name__ = 'account_col.auxiliary_party'

    @classmethod
    def get_context(cls, records, header, data):
        report_context = super().get_context(records, header, data)
        pool = Pool()
        Period = pool.get('account.period')
        Company = pool.get('company.company')
        Move = pool.get('account.move')
        MoveLine = pool.get('account.move.line')

        res = {}
        accounts_id = {}
        dom_move = []
        result_start = []

        cursor = Transaction().connection.cursor()
        account_move = Move.__table__()
        account_move_line = MoveLine.__table__()
        company = Company.search(["id", "=", data["company"]])

        grouped_by_loc = False
        start_period = None
        end_period = None
        location = None
        # Define start period to Account Moves
        start_period = Period(data['start_period'])
        dom_move.append(('period.start_date', '>=', start_period.start_date))

        # Define end period to Account Moves
        end_period = Period(data['end_period'])
        dom_move.append(('period.start_date', '<=', end_period.start_date))

        if data.get('posted'):
            dom_move.append(('state', '=', 'posted'))

        # Get move accounts
        moves = Move.search_read(
            dom_move,
            order=[('date', 'ASC'), ('id', 'ASC')],
            fields_names=['id'],
        )
        moves_ids = [move['id'] for move in moves]
        dom_lines = [('move', 'in', moves_ids)]

        # Build conditions to Account Move Lines
        if data.get('reference'):
            reference_dom = ('reference', 'ilike', data.get('reference'))
            dom_lines.append(reference_dom)

        if data.get('accounts'):
            accounts_dom = ('account', 'in', data['accounts'])
            dom_lines.append(accounts_dom)

        if data.get('party'):
            parties_dom = ('party', '=', data['party'])
            dom_lines.append(parties_dom)

        lines = MoveLine.search(dom_lines, order=[('move.date', 'ASC')])

        if lines:
            for line in lines:
                if not line.party:
                    continue

                if data['only_reference']:
                    id_ = line.reference
                    name = line.reference
                    id_number = ''
                else:
                    id_ = line.party.id
                    name = line.party.rec_name
                    id_number = line.party.id_number

                account_id = line.account.id
                if data['grouped_by_location'] or data['grouped_by_oc']:
                    grouped_by_loc = True
                    if data['grouped_by_location']:
                        city_name = ' '
                        if line.party.city_name:
                            city_name = line.party.city_name
                        id_loc = city_name
                    elif data['grouped_by_oc']:
                        id_loc = 'CO.'
                        if line.operation_center:
                            id_loc = 'CO. [' + line.operation_center.code + '] ' + line.operation_center.name

                    location = id_loc

                    if id_loc not in res.keys():
                        res[id_loc] = {}
                        accounts_id[id_loc] = {
                            'name': id_loc,
                            'sum_debit': [],
                            'sum_credit': [],
                            'balance': []
                        }

                    if id_ not in res[id_loc].keys():
                        res[id_loc][id_] = {
                            'name': name,
                            'id_number': id_number,
                            'accounts': [],
                            'balances': []
                        }
                        accounts_id[id_loc][id_] = {}

                    if account_id not in accounts_id[id_loc][id_].keys():
                        accounts_id[id_loc][id_][account_id] = {
                            'account': line.account,
                            'lines': [],
                            'sum_debit': [],
                            'sum_credit': [],
                            'balance': []
                        }
                        res[id_loc][id_]['accounts'].append(account_id)

                    accounts_id[id_loc][id_][account_id]['lines'].append(line)
                    accounts_id[id_loc][id_][account_id]['sum_debit'].append(
                        line.debit)
                    accounts_id[id_loc][id_][account_id]['sum_credit'].append(
                        line.credit)
                    accounts_id[id_loc][id_][account_id]['balance'].append(
                        line.debit - line.credit)
                    accounts_id[id_loc]['sum_debit'].append(line.debit)
                    accounts_id[id_loc]['sum_credit'].append(line.credit)
                    accounts_id[id_loc]['balance'].append(line.debit -
                                                          line.credit)
                else:
                    if id_ not in res.keys():
                        res[id_] = {
                            'name': name,
                            'id_number': id_number,
                            'accounts': [],
                            'balances': []
                        }
                        accounts_id[id_] = {}

                    # if id_ not in accounts_id.keys():
                    if account_id not in accounts_id[id_].keys():
                        accounts_id[id_][account_id] = {
                            'account': line.account,
                            'lines': [],
                            'sum_debit': [],
                            'sum_credit': [],
                            'balance': []
                        }
                        res[id_]['accounts'].append(account_id)

                    accounts_id[id_][account_id]['lines'].append(line)
                    accounts_id[id_][account_id]['sum_debit'].append(
                        line.debit)
                    accounts_id[id_][account_id]['sum_credit'].append(
                        line.credit)
                    accounts_id[id_][account_id]['balance'].append(line.debit -
                                                                   line.credit)

        # Define start period to balances
        start_period = Period(data['start_period'])
        start_periods = Period.search([
            ('end_date', '<', start_period.start_date),
        ])

        # build conditions
        entity = account_move_line.party
        default_entity = 0
        if not data['party'] and data['by_reference']:
            entity = account_move_line.reference
            default_entity = '0'

        # Select data from start period
        start_periods_ids = [p.id for p in start_periods]

        join1 = account_move_line.join(account_move)
        join1.condition = join1.right.id == account_move_line.move
        select2 = join1.select(
            account_move_line.account,
            Coalesce(entity, default_entity),
            Sum(account_move_line.debit) - Sum(account_move_line.credit),
            group_by=(account_move_line.account, entity),
            order_by=account_move_line.account,
        )
        select2.where = join1.right.period.in_(start_periods_ids)
        if data['party']:
            select2.where = select2.where & (account_move_line.party
                                             == data['party'])
        if data['accounts']:
            select2.where = select2.where & (account_move_line.account.in_(
                data['accounts']))

        if data['posted']:
            select2.where = select2.where & (account_move.state == 'posted')

        cursor.execute(*select2)
        result_start = cursor.fetchall()

        if data['grouped_by_location'] or data['grouped_by_oc']:
            cls._get_process_result(res,
                                    accounts_id,
                                    values=result_start,
                                    by_location=location)
        else:
            cls._get_process_result(res, accounts_id, values=result_start)

        report_context['_records'] = res
        report_context['_accounts'] = accounts_id
        report_context['grouped_by_account'] = data['grouped_by_account']
        report_context['grouped_by_location'] = grouped_by_loc
        report_context[
            'start_period'] = start_period.name if start_period else '*'
        report_context['end_period'] = end_period.name if end_period else '*'
        report_context['company'] = Company
        report_context['company_name'] = company[0].party.name
        return report_context

    @classmethod
    def _get_process_result(cls,
                            records,
                            lines_account,
                            values,
                            by_location=None):
        balances = {}

        for val in values:
            id_account = val[0]
            key = val[1]
            start_balance = Decimal(val[2])

            if by_location:
                sum_debit = sum(
                    lines_account[by_location][key][id_account]['sum_debit'])
                sum_credit = sum(
                    lines_account[by_location][key][id_account]['sum_credit'])

                end_balance = start_balance + sum_debit - sum_credit
                balances[id_account] = {
                    "start_balance": start_balance,
                    "end_balance": end_balance
                }
                records[by_location][key]['balances'].append(balances)
            else:
                sum_debit = sum(lines_account[key][id_account]['sum_debit'])
                sum_credit = sum(lines_account[key][id_account]['sum_credit'])

                end_balance = start_balance + sum_debit - sum_credit
                balances[id_account] = {
                    "start_balance": start_balance,
                    "end_balance": end_balance
                }
                records[key]['balances'].append(balances)
