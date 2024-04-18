from trytond.pool import PoolMeta


class Contract(metaclass=PoolMeta):
    __name__ = 'staff.contract'

    def get_time_days_contract(self, start_date=None, end_date=None):
        if start_date and end_date:
            n = 1
            # init days at start_date
            n1 = start_date.year * 360 + start_date.day
            for i in range(0, start_date.month - 1):
                n1 += 30
            n1 += self.count_leap_years(start_date)

            # end days at end_date
            n2 = end_date.year * 360 + end_date.day
            for i in range(0, end_date.month - 1):
                n2 += 30
            n2 += self.count_leap_years(end_date)
            if end_date.day == 31:
                n = 0

            pre_count = n2 - n1 + n

            # get count bisciestos years
            bisciestos_count = self.count_bisciestos_years(
                start_date.year, end_date.year)
            pre_count -= bisciestos_count
            return pre_count
        else:
            return 0

    def count_bisciestos_years(self, init_year, end_year):
        count = 0
        for year in range(init_year, end_year + 1):
            if (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0):
                count += 1
        return count
