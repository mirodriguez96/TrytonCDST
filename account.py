from collections import defaultdict
from decimal import Decimal
from timeit import default_timer as timer

import operator
from itertools import groupby
try:
    from itertools import izip
except ImportError:
    izip = zip
from trytond.report import Report

from sql import Column, Null
from sql.aggregate import Sum,Max, Min
from sql.conditionals import Coalesce
from collections import OrderedDict


from trytond.i18n import gettext
from trytond.exceptions import UserError
from trytond.model import ModelView, fields
from trytond.pyson import Eval
from trytond.transaction import Transaction
from trytond.tools import grouped_slice, reduce_ids, lstrip_wildcard
from trytond.wizard import Wizard, StateView, StateAction, Button,StateReport, StateTransition
from trytond.modules.stock.exceptions import PeriodCloseError
from trytond.pool import Pool, PoolMeta

TYPES_PRODUCT = [
    ('no_consumable', 'No consumable'),
    ('consumable', 'Consumable')
]

_ZERO = Decimal('0.0')

def _get_structured_json_data(json_data):
    data = [] 
    for i in json_data:
        date_json = list(i)
        dic = dict(zip(date_json,date_json))
        structured_json_body = {'reference': dic[date_json[0]] or "", 
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
        return super(Move, cls)._get_origin() + ['production']
    

class MoveLine(metaclass=PoolMeta):
    __name__ = 'account.move.line'

    @classmethod
    def _get_origin(cls):
        return super()._get_origin() + ['stock.move']


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


class AccountAsset(metaclass=PoolMeta):
    __name__ = 'account.asset'
    
    accumulated_depreciation = fields.Function(fields.Numeric(
            "Accumulated depreciation",
            digits=(16, Eval('currency_digits', 2)),
            depends=['currency_digits']),
        'get_depreciating_value')


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
        where &= accountAsset.move == accountAsset.select(Max(accountAsset.move), where= (accountAsset.asset == self.id))
        select = accountAsset.select(accountAsset.accumulated_depreciation, where=where)

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
    fiscalyear = fields.Many2One('account.fiscalyear', 'Fiscal Year',
        required=True)
    start_period = fields.Many2One('account.period', 'Start Period',
        domain=[
            ('fiscalyear', '=', Eval('fiscalyear')),
            ('start_date', '<=', (Eval('end_period'), 'start_date')),
            ], depends=['fiscalyear', 'end_period'], required=True)
    end_period = fields.Many2One('account.period', 'End Period',
        domain=[
            ('fiscalyear', '=', Eval('fiscalyear')),
            ('start_date', '>=', (Eval('start_period'), 'start_date'))
            ],
        depends=['fiscalyear', 'start_period'], required=True)
    start_account = fields.Many2One('account.account', 'Start Account',
            domain=[
                ('type', '!=', None),
                ('code', '!=', None),
            ])
    end_account = fields.Many2One('account.account', 'End Account',
            domain=[
                ('type', '!=', None),
                ('code', '!=', None),
            ])
    start_code = fields.Char('Start Code Account')
    end_code = fields.Char('End Code Account')
    party = fields.Many2One(
        'party.party', "Party",
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
        return FiscalYear.find(
            Transaction().context.get('company'), exception=False)

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
    start = StateView('account_col.auxiliary_book_cds.start',
        'conector.print_auxiliary_book_start_view_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Print', 'print_', 'tryton-print', default=True),
        ]
    )
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
        date_initial = []

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
            dom_accounts.append(
                ('code', '>=', start_acc.code)
            )
        end_code = None
        if data['end_account']:
            end_acc = Account(data['end_account'])
            end_code = end_acc.code
            dom_accounts.append(
                ('code', '<=', end_acc.code)
            )
        
        accounts = Account.search(dom_accounts, order=[('code', 'ASC')])

        # partyaccount = AccountParty.search([
        #     ('party', '=', data['party']),
        #     ('account', 'in', accounts),
        #     ])

        # datos = ['credit', 'debit', 'amount_second_currency']
        # print(cls.get_credit_debit(records=partyaccount, names=datos), cls.get_balance(records=partyaccount))

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

        noSelectPerid =  Period.search([('fiscalyear', '<', data['fiscalyear'])])
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
        if data['party']:
            party, = Party.search([('id', '=', data['party'])])
            # --------------------------------------------------------------

            date_initial = start_date + start_period_ids
            period = [a.id for a in accounts]

############################################################################
            if period:
                where = accountLine.account.in_(period)
            if date_initial:
                where &= accountmove.period.in_(date_initial)
            if data["party"]:
                where &= accountLine.party == data["party"]

            select2 = accountLine.join(accountmove, 'LEFT', condition= (accountLine.move == accountmove.id)
            ).select(Sum(accountLine.credit), Sum(accountLine.debit), Sum(Coalesce(accountLine.debit,0) - Coalesce(accountLine.credit,0))
            ,where=where)


            cursor.execute(*select2)
            result_start = cursor.fetchall()


#############################################################################
            #######Trabajando en los saldos inciales###############
            initial = str(data['start_period']-1) if data['start_period'] and data['start_period'] != start_date[0]  else str(start_date[0])
            where &= accountmove.period == initial

            query = accountLine.join(accountmove, 'LEFT', condition= (accountLine.move == accountmove.id)
            ).select(Sum(accountLine.credit), Sum(accountLine.debit), Sum(Coalesce(accountLine.debit,0) - Coalesce(accountLine.credit,0))
            ,where=where)

            
            cursor.execute(*query)
            initial_balance = cursor.fetchall()
            cursor.close() 

        with Transaction().set_context(
                fiscalyear=data['fiscalyear'],
                periods=start_period_ids,
                party=data['party'],
                posted=data['posted'],
                colgaap=data['colgaap']):
            start_accounts = Account.browse(accounts)
        print(start_accounts[0].balance, 'valida  acceso')
        
        end1 = timer()
        delta1 = (end1 - start)
        id2start_account = {}
        
        for account in start_accounts:
            id2start_account[account.id] = account
            if party != None:
                balance = result_start[0][2] or 0
                id2start_account[account.id].credit = initial_balance[0][0] or 0
                id2start_account[account.id].debit = initial_balance[0][1] or 0
                id2start_account[account.id].balance = balance 

        # --------------------------------------------------------------

        with Transaction().set_context(
                fiscalyear=data['fiscalyear'],
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
            account2lines = dict(cls.get_lines(accounts,
                end_periods, data['posted'], data['party'],
                data['reference'], data['colgaap']))

            accounts_ = account2lines.keys()
            with Transaction().set_context(
                party=data['party'],
                posted=data['posted'],
                colgaap=['colgaap']):
                accounts = Account.browse([a for a in accounts_ids if a in accounts_])

        end3 = timer()
        delta3 = (end3 - end2)
        
        account_id2lines, credit, debit = cls.lines(accounts,
            list(set(end_periods).difference(set(start_periods))),
            data['posted'], data['party'], data['reference'], data['colgaap'])

        if party != None:
            for account in end_accounts:
                id2end_account[account.id].credit = credit
                id2end_account[account.id].debit = debit
                id2end_account[account.id].balance = (balance + debit - credit)

        report_context['start_period_name'] = start_period_name
        report_context['end_period_name'] = end_period_name
        report_context['start_code'] = start_code
        report_context['end_code'] = end_code
        report_context['party'] = party
        report_context['accounts'] = accounts
        report_context['id2start_account'] = id2start_account
        report_context['id2end_account'] = id2end_account
        report_context['digits'] = company.currency.digits
        report_context['lines'] = lambda account_id: account_id2lines[account_id]
        report_context['company'] = company

        end4 = timer()
        delta4 = (end4 - end3)

        end = timer()
        delta_total = (end - start)
        return report_context
    

    # @classmethod
    # def query_to_dict_detailed(cls, query):
    #     cursor = Transaction().connection.cursor()
    #     Party = Pool().get('party.party')
    #     cursor.execute(*query)
    #     columns = list(cursor.description)
    #     result = cursor.fetchall()
    #     res_dict = {}
    #     moves_ids = set()
        
    #     for row in result:
    #         row_dict = {}
    #         key_id = str(row[0])+row[1]
    #         for i, col in enumerate(columns):
    #             row_dict[col.name] = row[i]
    #         try:
    #             moves_ids.add(row_dict['move'])
    #         except:
    #             res_dict[key_id] = {
    #                 'party':  Party(row[0]),
    #             }
    #             moves_ids.add(row_dict['move'])
    #     return res_dict, moves_ids

    @classmethod
    def get_lines(cls, accounts, periods, posted, party=None, reference=None, colgaap=False):
        cursor = Transaction().connection.cursor()
        _lineas = None
        where = None
        print('Inicio proceso en esta sesion de get_lines')
        MoveLine = Pool().get('account.move.line')
        Account = Pool().get('account.move')
        Party = Pool().get('party.party')

        moveLine = MoveLine.__table__()
        account = Account.__table__()
        partys = Party.__table__()

        clause = [
            ('account', 'in', [a.id for a in accounts]),
            ('period', 'in', [p.id for p in periods]),
        ]
        
        accountfilter = [a.id for a in accounts]
        periodsfilter = [p.id for p in periods]

        if periodsfilter:
            where = account.period.in_(periodsfilter)
        if accountfilter:
            where &= moveLine.account.in_(accountfilter)
        if party:
            where &= moveLine.party == party
        if posted:
            where &= moveLine.state == 'posted'
        if reference:
            where &= moveLine.reference.like_(reference)

    
        query = moveLine.join(partys, 'LEFT', condition=(partys.id == moveLine.party)
        ).join(account, condition=(moveLine.move == account.id)
        ).select(moveLine.reference, moveLine.credit, moveLine.account, moveLine.debit, moveLine.id, moveLine.description, account.date, account.number, account.id, moveLine.party, partys.name, partys.id_number
        ,where=where) 

        cursor.execute(*query)
        _lineas = cursor.fetchall()
        cursor.close()     
                
        lines  = _get_structured_json_data(_lineas)

        key = operator.itemgetter('account')
        lines.sort(key=key)
        val = groupby(lines, key)
        return val

    @classmethod
    def lines(cls, accounts, periods, posted, party=None, reference=None, colgaap=False):  
        res = dict((a.id, []) for a in accounts)
        if res:
            account2lines = cls.get_lines(accounts, periods, posted, party, reference, colgaap)
            for account_id, lines in account2lines:
                balance = _ZERO
                credit = _ZERO
                debit = _ZERO
                rec_append = res[account_id].append
                for line in lines:
                    line['move'] = line['move.']['number']
                    balance += line['debit'] - line['credit']
                    if party != None:
                        credit += line['credit']
                        debit += line['debit']
                    if line['party.']:
                        line['party'] = line['party.']['name']
                        line['party_id'] = line['party.']['id_number']
                    if line['move_origin.']:
                        line['origin'] = line['move_origin.']['rec_name']

                    line['balance'] = balance
                    rec_append(line)
        else: 
            raise UserError( message=None, description=f"El reporte no contiene informacion, no es posible generarlo")

        return res, credit, debit
    

    # @classmethod
    # def get_balance(cls, records, name=None):
    #     pool = Pool()
    #     Account = pool.get('account.account')
    #     MoveLine = pool.get('account.move.line')
    #     FiscalYear = pool.get('account.fiscalyear')
    #     cursor = Transaction().connection.cursor()

    #     table_a = Account.__table__()
    #     table_c = Account.__table__()
    #     line = MoveLine.__table__()
    #     ids = [a.id for a in records]
    #     account_ids = {a.account.id for a in records}
    #     party_ids = {a.party.id for a in records}
    #     account_party2id = {(a.account.id, a.party.id): a.id for a in records}
    #     balances = dict((i, Decimal(0)) for i in ids)
    #     line_query, fiscalyear_ids = MoveLine.query_get(line)
    #     for sub_account_ids in grouped_slice(account_ids):
    #         account_sql = reduce_ids(table_a.id, sub_account_ids)
    #         for sub_party_ids in grouped_slice(party_ids):
    #             party_sql = reduce_ids(line.party, sub_party_ids)
    #             cursor.execute(*table_a.join(table_c,
    #                     condition=(table_c.left >= table_a.left)
    #                     & (table_c.right <= table_a.right)
    #                     ).join(line, condition=line.account == table_c.id
    #                     ).select(
    #                     table_a.id,
    #                     line.party,
    #                     Sum(
    #                         Coalesce(line.debit, 0)
    #                         - Coalesce(line.credit, 0)),
    #                     where=account_sql & party_sql & line_query,
    #                     group_by=[table_a.id, line.party]))
    #             for account_id, party_id, balance in cursor:
    #                 try:
    #                     id_ = account_party2id[(account_id, party_id)]
    #                 except KeyError:
    #                     # There can be more combinations of account-party in
    #                     # the database than from records
    #                     continue
    #                 balances[id_] = balance
    #     for record in records:
    #         # SQLite uses float for SUM
    #         if not isinstance(balances[record.id], Decimal):
    #             balances[record.id] = Decimal(str(balances[record.id]))
    #         exp = Decimal(str(10.0 ** -record.currency_digits))
    #         balances[record.id] = balances[record.id].quantize(exp)

    #     fiscalyears = FiscalYear.browse(fiscalyear_ids)

    #     def func(records, names):
    #         return {names[0]: cls.get_balance(records, names[0])}
    #     return Account._cumulate(
    #         fiscalyears, records, [name], {name: balances}, func,
    #         deferral=None)[name]

    # @classmethod
    # def get_credit_debit(cls, records, names):
    #     pool = Pool()
    #     Account = pool.get('account.account')
    #     MoveLine = pool.get('account.move.line')
    #     FiscalYear = pool.get('account.fiscalyear')
    #     cursor = Transaction().connection.cursor()

    #     print(records, names)
    #     result = {}
    #     ids = [a.id for a in records]
    #     for name in names:
    #         if name not in {'credit', 'debit', 'amount_second_currency'}:
    #             raise ValueError('Unknown name: %s' % name)
    #         result[name] = dict((i, Decimal(0)) for i in ids)

    #     account_ids = {a.account.id for a in records}
    #     party_ids = {a.party.id for a in records}
    #     account_party2id = {(a.account.id, a.party.id): a.id for a in records}
    #     table = Account.__table__()
    #     line = MoveLine.__table__()
    #     line_query, fiscalyear_ids = MoveLine.query_get(line)
    #     print(line_query)
    #     columns = [table.id, line.party]
    #     for name in names:
    #         columns.append(Sum(Coalesce(Column(line, name), 0)))
    #     for sub_account_ids in grouped_slice(account_ids):
    #         account_sql = reduce_ids(table.id, sub_account_ids)
    #         for sub_party_ids in grouped_slice(party_ids):
    #             party_sql = reduce_ids(line.party, sub_party_ids)
    #             cursor.execute(*table.join(line, 'LEFT',
    #                     condition=line.account == table.id
    #                     ).select(*columns,
    #                     where=account_sql & party_sql & line_query,
    #                     group_by=[table.id, line.party]))
    #             for row in cursor:
    #                 try:
    #                     id_ = account_party2id[tuple(row[0:2])]
    #                 except KeyError:
    #                     # There can be more combinations of account-party in
    #                     # the database than from records
    #                     continue
    #                 for i, name in enumerate(names, 2):
    #                     # SQLite uses float for SUM
    #                     if not isinstance(row[i], Decimal):
    #                         result[name][id_] = Decimal(str(row[i]))
    #                     else:
    #                         result[name][id_] = row[i]
    #     for record in records:
    #         for name in names:
    #             if name == 'amount_second_currency':
    #                 exp = Decimal(str(10.0 ** -record.second_currency_digits))
    #             else:
    #                 exp = Decimal(str(10.0 ** -record.currency_digits))
    #             result[name][record.id] = (
    #                 result[name][record.id].quantize(exp))

    #     cumulate_names = []
    #     if Transaction().context.get('cumulate'):
    #         cumulate_names = names
    #     elif 'amount_second_currency' in names:
    #         cumulate_names = ['amount_second_currency']
    #     if cumulate_names:
    #         fiscalyears = FiscalYear.browse(fiscalyear_ids)
    #         return Account._cumulate(
    #             fiscalyears, records, cumulate_names, result,
    #             cls.get_credit_debit, deferral=None)
    #     else:
    #         return result

    # def get_currency_digits(self, name):
    #     return self.company.currency.digits

    # def get_second_currency_digits(self, name):
    #     return self.account.second_currency_digits



