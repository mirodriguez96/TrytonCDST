from trytond.model import ModelView, ModelSQL, fields
from trytond.pool import PoolMeta, Pool
from trytond.pyson import Eval
from trytond.model import Unique
from trytond.wizard import Wizard, StateView, StateTransition
from trytond.wizard import Button
from trytond.transaction import Transaction
from trytond.exceptions import UserError
from decimal import Decimal
import datetime
from .exceptions import (NotMoveStatementeLine)

CONFIRMED_STATES = {
    'readonly': False  #Not(Equal(Eval('statement_line'), None))
}


class BankStatement(metaclass=PoolMeta):
    'Bank Statement'
    __name__ = 'account.bank_statement'

    bank_lines = fields.One2Many('account.bank_statement.bank_line',
                                 'statement',
                                 'Bank lines',
                                 states={'readonly': Eval('state') != 'draft'})


class BankStatementLine(metaclass=PoolMeta):
    'Bank Statement Line'
    __name__ = 'account.bank_statement.line'

    bank_line = fields.One2One(
        'account.bank_statement.line-bank_line',
        'origin',
        'target',
        'Bank line',
        domain=[
            ('statement', '=', Eval('statement')),
            # ('statement_line', '=', None),
        ],
        depends=['statement'])

    # @fields.depends('bank_line')
    # def on_change_bank_line(self):
    #     if self.bank_line and self.state == 'draft':
    #         self.state = 'confirmed'


class BankStatementLineRelation(ModelSQL):
    "Bank Statement Line Relation"
    __name__ = 'account.bank_statement.line-bank_line'

    origin = fields.Many2One('account.bank_statement.line', 'Origin')
    target = fields.Many2One('account.bank_statement.bank_line', 'Target')

    @classmethod
    def __setup__(cls):
        super().__setup__()
        t = cls.__table__()
        cls._sql_constraints += [
            ('origin_uniq', Unique(t, t.origin), 'Origin must be unique'),
            ('target_uniq', Unique(t, t.target), 'Target must be unique')
        ]


class BankStatementBankLine(ModelSQL, ModelView):
    'Bank Statement Bank_line'
    __name__ = 'account.bank_statement.bank_line'
    _rec_name = 'description'

    statement = fields.Many2One('account.bank_statement',
                                'Bank Statement',
                                required=True)
    date = fields.Date('Date', required=True, states=CONFIRMED_STATES)
    description = fields.Char('Description',
                              required=True,
                              states=CONFIRMED_STATES)
    amount = fields.Numeric('Amount',
                            digits=(16, 2),
                            required=True,
                            states=CONFIRMED_STATES)
    statement_line = fields.One2One('account.bank_statement.line-bank_line',
                                    'target',
                                    'origin',
                                    'Statement line',
                                    domain=[
                                        ('statement', '=', Eval('statement')),
                                    ],
                                    depends=['statement'])

    @classmethod
    def delete(cls, instances):
        cls.update_statement_line(instances)
        super(BankStatementBankLine, cls).delete(instances)

    @classmethod
    def update_statement_line(cls, instances):
        to_save = []
        for line in instances:
            if line.statement_line:
                line.statement_line.state = 'draft'
                to_save.append(line.statement_line)
        Line = Pool().get('account.bank_statement.line')
        Line.save(to_save)


# Asistente para cargar el extracto bancario en archivo plano
class CreateBankLine(Wizard):
    'Create Bank_line'
    __name__ = 'account.bank_statement.create_bank_line'

    start_state = 'parameters'
    parameters = StateView(
        'account.bank_statement.create_bank_line.parameters',
        'conector.create_bank_line_parameters_view_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button(
                'Create', 'create_bank_line', 'tryton-go-next', default=True)
        ])
    create_bank_line = StateTransition()

    def default_parameters(self, name):
        if Transaction().context.get('active_model',
                                     '') != 'account.bank_statement':
            raise UserError(
                'invalid_model',
                'This action should be started from a bank_statement')
        return {'file': None}

    def transition_create_bank_line(self):
        if (not self.parameters.file):
            raise UserError(
                'invalid_model',
                'This action should be started from a bank_statement')
        # BankStatement = Pool().get('account.bank_statement')
        Line = Pool().get('account.bank_statement.line')
        BankLine = Pool().get('account.bank_statement.bank_line')
        _id = Transaction().context['active_id']
        # bank_statement = BankStatement(_id)
        file = self.parameters.file.decode()
        file_lines = file.split('\n')
        # Se comienza a recorrer las líneas del archivo cargado
        to_create = []
        for line in file_lines:
            line = line.strip()
            if not line:
                continue
            line = line.split(';')
            # print(line)
            if len(line) != 3:
                raise UserError('invalid_template', 'date;description;amount')
            try:
                date = line[0].strip().split()[0].split('-')
                date = datetime.date(int(date[0]), int(date[1]), int(date[2]))
                description = line[1].strip()
                amount = Decimal(line[2])
            except Exception as e:
                raise UserError('invalid_template', str(e))
            bank_line = {
                'statement': _id,
                'date': date,
                'description': description,
                'amount': amount,
            }
            to_create.append(bank_line)
        bank_lines = BankLine.create(to_create)
        lines = Line.search([('statement', '=', _id), ('state', '=', 'draft')])
        to_save = []
        for line in lines:
            for bank_line in bank_lines:
                if bank_line.date == line.date and \
                    bank_line.amount == line.moves_amount:
                    line.bank_line = bank_line
                    line.state = 'confirmed'
                    to_save.append(line)
                    bank_lines.remove(bank_line)
                    break
        Line.save(to_save)
        return 'end'


class CreateBankLineParameters(ModelView):
    'Create Bank_line Parameters'
    __name__ = 'account.bank_statement.create_bank_line.parameters'

    file = fields.Binary('File',
                         required=True,
                         help='File type CSV, separated by commas(;)')



class StatementLine(metaclass=PoolMeta):
    __name__ = 'account.statement.line'

    move_lines_source = fields.Function(fields.Many2One('account.move', 'Move'),'get_move_value')

    @fields.depends('move')
    def get_move_value(self, name=None):
        res = None
        if self.move:
            res = self.move.id
        return res
    

# Asistente de validar los asiento contable de los estados de cuenta
class StatementMoveValidate(Wizard):
    'Wizard for StatementMoveValidate'
    __name__ = 'account.statement.move_validate'

    start_state = 'run'
    run = StateTransition()

    def transition_run(self):
        pool = Pool()
        account_statement = pool.get('account.statement')
        account_statement_line = pool.get('account.statement.line')
        ids = Transaction().context['active_ids']

        if ids:
            for statement in account_statement.browse(ids):
                lines = account_statement_line.search([
                    ('statement', '=', statement.id),
                ])

                not_moves = [i.sale.number for i in lines if not i.move]

                print(not_moves)
            raise NotMoveStatementeLine(
                'Sin asiento contable',
                f'Del estado de cuenta numero: {statement.name} \t\t \
                fecha: {statement.date} \t\t \
                tiene las venta: {not_moves}'
            )
        return 'end'