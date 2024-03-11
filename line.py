from trytond.pool import Pool, PoolMeta


class Line(metaclass=PoolMeta):
    'Analytic Line'
    __name__ = 'analytic_account.line'

    @classmethod
    def create(cls, vlist):
        pool = Pool()
        MoveLine = pool.get('account.move.line')
        AnalitycLine = pool.get('analytic_account.line')
        lines = super(Line, cls).create(vlist)
        for line in lines:
            new_date = line.move_line.move.date
            print(f"fecha efectiva {new_date}")
            line.date = new_date
        AnalitycLine.save(lines)
        move_lines = [l.move_line for l in lines]
        MoveLine.set_analytic_state(move_lines)
        MoveLine.save(move_lines)
        return lines
