from trytond.wizard import (Wizard, StateTransition)
from trytond.tools import reduce_ids, grouped_slice
from trytond.transaction import Transaction
from trytond.exceptions import UserError
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Eval

from datetime import date
from sql import Table
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
        Line = Pool().get('staff.loan.line')
        to_create = []
        to_save = []
        reconciled = []
        for loan in loans:
            total_lines = 0
            next_date = loan.first_pay_date
            lines = sorted(loan.lines, key=lambda obj: obj.maturity_date)
            for line in lines:
                next_date = line.maturity_date
                if line.origin and ('-1' not in line.origin):
                    if line.origin.amount != line.amount:
                        line.amount = line.origin.amount
                        to_save.append(line)
                total_lines += line.amount
            difference = loan.amount - total_lines
            index = len(lines) - 1
            if difference > 0:
                if lines[index].state == 'pending' \
                        and (not lines[index].origin or '-1' in lines[index].origin):
                    lines[index].amount += difference
                    to_save.append(lines[index])
                else:
                    days_of_month = sorted(
                        set(d.day_of_month for d in loan.days_of_month))
                    month = next_date
                    for d in days_of_month:
                        try:
                            next_date = date(month.year, month.month, d)
                        except:
                            _, last_day = calendar.monthrange(
                                month.year, month.month)
                            next_date = date(month.year, month.month, last_day)
                    to_create.append({
                        'loan': loan.id,
                        'maturity_date': next_date,
                        'amount': difference,
                        'state': 'pending',
                    })
            else:
                if difference != 0 and lines[index].state == 'pending' \
                        and (not lines[index].origin or '-1' in lines[index].origin):
                    lines[index].amount += difference
                    to_save.append(lines[index])
            for to_pay in loan.lines_to_pay:
                if to_pay.reconciliation and to_pay.origin \
                        and ('-1' not in to_pay.origin) \
                        and to_pay.origin.state != 'paid':
                    reconciled.append(to_pay.origin.id)
        if to_save:
            Line.save(to_save)
        if to_create:
            Line.create(to_create)
        if reconciled:
            table = Line.__table__()
            cursor = Transaction().connection.cursor()
            for sub_ids in grouped_slice(reconciled):
                red_sql = reduce_ids(table.id, sub_ids)
                # Use SQL to prevent double validate loop
                cursor.execute(*table.update(
                    columns=[table.state], values=['paid'], where=red_sql))

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
