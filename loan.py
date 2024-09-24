from trytond.wizard import (Wizard, StateTransition)
from trytond.tools import reduce_ids, grouped_slice
from trytond.transaction import Transaction
from trytond.exceptions import UserError
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Eval

from decimal import Decimal
from datetime import date, datetime
from dateutil.relativedelta import relativedelta
from sql import Table, Literal
import calendar


class Loan(metaclass=PoolMeta):
    __name__ = "staff.loan"

    @classmethod
    def __setup__(cls):
        super(Loan, cls).__setup__()
        cls.amount.states.update({
            'readonly': Eval('state') != 'draft',
        })
        cls.number_instalment.states.update({
            'readonly':
            Eval('state') != 'draft',
        })
        cls.currency.states.update({
            'readonly': Eval('state') != 'draft',
        })
        cls.first_pay_date.states.update({
            'readonly': Eval('state') != 'draft',
        })

    @classmethod
    def validate_loan(cls, loans):
        super(Loan, cls).validate_loan(loans)
        LineLiquidation = Pool().get('staff.liquidation.line')
        LinePayroll = Pool().get('staff.payroll.line')

        cls.validate_amount_loan(loans)
        for loan in loans:
            for line in loan.lines:
                if line.origin and line.state == "paid":
                    if line.origin.__name__ == LineLiquidation.__name__:
                        line_liquidation = LineLiquidation(line.origin)
                        cls.calculate_loan_liquidation(
                            line_liquidation, line)
                    elif line.origin.__name__ == LinePayroll.__name__:
                        line_payroll = LinePayroll(line.origin)
                        cls.calculate_loan_payroll(
                            line_payroll, line)


    @classmethod
    def validate_amount_loan(cls, loans):
        LoanLine = Pool().get('staff.loan.line')
        for loan in loans:
            total_amount_loan = loan.amount
            total_amount_lines = sum(line.amount for line in loan.lines)
            difference = total_amount_loan - total_amount_lines
            if difference != 0:
                if difference > 0:
                    new_loan_line = cls.get_new_loan_line_line(
                        loan.lines[-1], difference)
                    LoanLine.create(new_loan_line)
                else:
                    LoanLine.delete([loan.lines[-1]])

    @classmethod
    def calculate_loan_liquidation(cls, line_liquidation, loan_line):
        LoanLine = Pool().get('staff.loan.line')
        difference = 0
        lines_loan = LoanLine.search(
            [('loan', '=', loan_line.loan), ('state', '=', 'pending')])

        liquidation_amount = abs(line_liquidation.amount)
        loan_amount = abs(loan_line.amount)
        difference = liquidation_amount - loan_amount

        if difference != 0:
            if lines_loan:
                loan_line.amount = liquidation_amount
                LoanLine.save([loan_line])
                line_to_update = lines_loan[-1]
                new_amount = line_to_update.amount - difference
                line_to_update.amount = new_amount
                LoanLine.save([line_to_update])
            else:
                if difference < 0:
                    loan_line.amount = liquidation_amount
                    LoanLine.save([loan_line])
                    new_loan_line = cls.get_new_loan_line_line(
                        loan_line, abs(difference))
                    LoanLine.create(new_loan_line)

    @classmethod
    def calculate_loan_payroll(cls, line_payroll, loan_line):
        LoanLine = Pool().get('staff.loan.line')
        difference = 0
        lines_loan = LoanLine.search(
            [('loan', '=', loan_line.loan), ('state', '=', 'pending')])

        payroll_amount = abs(line_payroll.amount)
        loan_amount = abs(loan_line.amount)
        difference = payroll_amount - loan_amount

        if difference != 0:
            if lines_loan:
                loan_line.amount = payroll_amount
                LoanLine.save([loan_line])
                line_to_update = lines_loan[-1]
                new_amount = line_to_update.amount - difference
                line_to_update.amount = new_amount
                LoanLine.save([line_to_update])
            else:
                if difference < 0:
                    loan_line.amount = payroll_amount
                    LoanLine.save([loan_line])
                    new_loan_line = cls.get_new_loan_line_line(
                        loan_line, abs(difference))
                    LoanLine.create(new_loan_line)

    @classmethod
    def get_new_loan_line_line(cls, loan_line, difference):
        maturity_date = loan_line.maturity_date
        day_loan = maturity_date.day
        if day_loan == 15:
            maturity_date = maturity_date + relativedelta(days=15)
        else:
            maturity_date = maturity_date + \
                relativedelta(months=1) - relativedelta(days=15)

        new_line = [{
            "loan": loan_line.loan,
            'maturity_date': maturity_date,
            'amount': difference,
            'state': 'pending',
        }]
        return new_line

    @classmethod
    def _post(cls, loans):
        """Function to post loan including refference

        Args:
            loans (object): staff_loan model
        """
        pool = Pool()
        Move = pool.get('account.move')
        reconciled = []
        moves = []

        loans = [l for l in loans if l.type != 'external']
        for loan in loans:
            move = loan.get_move()
            if move != loan.account_move:
                loan.account_move = move
                moves.append(move)
            if loan.state != 'posted':
                loan.state = 'posted'

        if moves:
            if move.lines:
                for lines in move.lines:
                    lines.reference = loan.number
            Move.save(moves)
        cls.save(loans)
        Move.post(
            [i.account_move for i in loans if i.account_move.state != 'posted'])
        for loan in loans:
            if loan.reconciled:
                reconciled.append(loan)
        if reconciled:
            cls.__queue__.refresh(reconciled)


class LoanLine(metaclass=PoolMeta):
    'Loan Line Readonly'
    __name__ = 'staff.loan.line'

    @classmethod
    def __setup__(cls):
        super(LoanLine, cls).__setup__()

    @classmethod
    def validate_line(cls, lines):
        line = cls.__table__()
        cursor = Transaction().connection.cursor()
        
        pending_lines = []
        paid_lines = []
        for line_ in lines:
            if not line_.origin and line_.state == 'paid':
                loan_paid = cls.validate_paid_line(line_)
                if not loan_paid:
                    pending_lines.append(line_.id)
            elif line_.origin and line_.state in ('pending', 'partial'):
                paid_lines.append(line_.id)
            elif not line_.origin and line_.state in ('pending', 'partial'):
                loan_paid = cls.validate_paid_line(line_)
                if loan_paid:
                    paid_lines.append(line_.id)

        for move_ids, state in (
                (pending_lines, 'pending'),
                (paid_lines, 'paid'),
                ):
            if move_ids:
                for sub_ids in grouped_slice(move_ids):
                    red_sql = reduce_ids(line.id, sub_ids)
                    # Use SQL to prevent double validate loop
                    print(red_sql)
                    cursor.execute(*line.update(
                            columns=[line.state],
                            values=[state],
                            where=red_sql))

    @classmethod
    def validate_paid_line(cls, line):
        AccountMoveLine = Pool().get('account.move.line')
        loan_move_line = AccountMoveLine.search([('origin','=',line),
                                                 ('reconciliation','!=',None)])
        loan_paid = True if loan_move_line else False        
        return loan_paid

class LoanForceDraft(Wizard):
    """Function to Force draft Loan

    Args:
        Wizard (Inheritance): class type Wizard by tryton

    Raises:
        UserError: if loan its state paid or cancelled
        UserError: if loan had paid state lines

    Returns:
        String: return end when the wizard is finished
    """

    __name__ = 'staff.loan.force_draft'
    start_state = 'force_draft'
    force_draft = StateTransition()

    def transition_force_draft(self):
        pool = Pool()
        Actualizacion = pool.get('conector.actualizacion')
        actualizacion = Actualizacion.create_or_update(
            'FORZAR BORRADOR PRESTAMOS')
        Period = pool.get('account.period')
        logs = {}
        exceptions = []
        Loan = pool.get('staff.loan')
        move_table = Table('account_move')
        cursor = Transaction().connection.cursor()
        to_delete = []
        to_draft = []
        ids_ = Transaction().context['active_ids']
        for id_ in ids_:
            loan = Loan(id_)
            loanTable = Loan.__table__()

            # Validamos si existe un movimiento contables, si no es asi,
            # le asignamos la fecha efectiva del prestamo
            if loan.account_move:
                validate = loan.account_move.state
            else:
                dat = str(loan.date_effective).split()[0].split('-')
                name = f"{dat[0]}-{dat[1]}"
                validate_period = Period.search([('name', '=', name)])
                validate = validate_period[0].state

            if validate == 'close':
                exceptions.append(loan.id)
                logs[
                    loan.
                    id] = "EXCEPCION: EL PERIODO DEL DOCUMENTO SE ENCUENTRA CERRADO \
                Y NO ES POSIBLE FORZAR A BORRADOR"

                continue
            # Validacion para saber si el activo se encuentra cerrado
            if loan.state == 'paid' or loan.state == 'cancelled':
                raise UserError(
                    'AVISO',
                    f'El prestamo {loan.number} se encuentra en estado {loan.state} y no es posible forzar su borrado'
                )
            # Validacion para saber si el activo ya se encuentra en borrador

            for lines in loan.lines:
                if lines.state == 'paid' and lines.origin:
                    raise UserError(
                        'AVISO',
                        f'El prestamo {loan.number} tiene lineas en estado pagado y no es posible forzar su borrado'
                    )

            if loan.state == 'draft':
                return 'end'
            cursor = Transaction().connection.cursor()
            # Consulta que le asigna el estado borrado al activo
            if loan.account_move:
                to_delete.append(loan.account_move.id)
            to_draft.append(id_)

        if to_draft:

            if to_delete:
                cursor.execute(
                    *move_table.update(columns=[move_table.state],
                                       values=['draft'],
                                       where=move_table.id.in_(to_delete)))
                cursor.execute(*move_table.delete(
                    where=move_table.id.in_(to_delete)))
            cursor.execute(*loanTable.update(columns=[
                loanTable.state,
                loanTable.number,
            ],
                values=["draft", ''],
                where=loanTable.id.in_(to_draft)))
        if exceptions:
            actualizacion.add_logs(logs)
        return 'end'
