from trytond.pool import Pool, PoolMeta
from trytond.transaction import Transaction
from trytond.tools import reduce_ids, grouped_slice


class LoanLine(metaclass=PoolMeta):
    'Loan Line'
    __name__ = 'staff.loan.line'


    @classmethod
    def validate_line(cls, records):
        super(LoanLine, cls).validate_line(records)
        Line = Pool().get('account.move.line')
        line = cls.__table__()
        cursor = Transaction().connection.cursor()
        pending_lines = []
        for record in records:
            if record.state != 'paid':
                pending_lines.append(str(record))
        move_lines = Line.search([
            ('origin', 'in', pending_lines),
            ('reconciliation', '!=', None),
        ])
        paid_lines = []
        for move_line in move_lines:
            paid_lines.append(move_line.origin.id)
        if paid_lines:
            for sub_ids in grouped_slice(paid_lines):
                red_sql = reduce_ids(line.id, sub_ids)
                print(red_sql)
                # Use SQL to prevent double validate loop
                cursor.execute(*line.update(
                        columns=[line.state],
                        values=['paid'],
                        where=red_sql))