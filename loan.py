from trytond.pool import Pool, PoolMeta
from trytond.transaction import Transaction
from trytond.tools import reduce_ids, grouped_slice
from datetime import date
import calendar
# from trytond.exceptions import UserError
from trytond.pyson import Eval

class Loan(metaclass=PoolMeta):
    __name__ = "staff.loan"

    @classmethod
    def __setup__(cls):
        super(Loan, cls).__setup__()
        cls.amount.states.update({
            'readonly': Eval('state') != 'draft',
        })
        cls.number_instalment.states.update({
            'readonly': Eval('state') != 'draft',
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
                    days_of_month = sorted(set(d.day_of_month for d in loan.days_of_month))
                    month = next_date
                    for d in days_of_month:
                        try:
                            next_date = date(month.year, month.month, d)
                        except:
                            _,last_day = calendar.monthrange(month.year, month.month)
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
            # if amount != loan_amount:
            #     raise UserError('Invalid lines amount', f'must be {amount}')
            for to_pay in loan.lines_to_pay:
                if to_pay.reconciliation and to_pay.origin \
                    and ('-1' not in to_pay.origin) \
                    and to_pay.origin.state != 'paid':
                    reconciled.append(to_pay.origin.id)
        #
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
                        columns=[table.state],
                        values=['paid'],
                        where=red_sql))