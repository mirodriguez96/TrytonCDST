from trytond.wizard import (StateReport, Wizard)
from trytond.transaction import Transaction
from trytond.exceptions import UserError
from trytond.pool import PoolMeta, Pool
from trytond.report import Report

from decimal import Decimal
import datetime


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

            if start_date.month > 2 and self.validate_bisciesto_year(
                    start_date.year):
                pre_count += 1

            return pre_count
        else:
            return 0

    def count_bisciestos_years(self, init_year, end_year):
        count = 0
        for year in range(init_year, end_year + 1):
            if (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0):
                count += 1
        return count

    def validate_bisciesto_year(self, year):
        if year % 4 == 0:
            if year % 100 == 0:
                if year % 400 == 0:
                    return True
                else:
                    return False
            else:
                return True
        else:
            return False

    def get_time_worked(self, name=None):
        start_date = self.start_date
        end_date = datetime.date.today()
        if self.end_date and self.finished_date and self.finished_date < end_date:
            end_date = self.finished_date
        return self.get_time_days_contract(start_date, end_date)

    def get_duration(self, name=None):
        res = None
        field_name = name[9:]
        if self.end_date and self.start_date:
            res = self.get_time_days_contract(self.start_date,
                                              self.finished_date)
            if field_name != 'days':
                res = int(round(res / 30.0, 0))
        return res


class ContractExportAvaliableVacation(Wizard):
    'Vacation Export'
    __name__ = 'staff.contract.export_avaliable_vacation'
    start = StateReport('contract.export_avaliable_vacation')

    def do_start(self, action):
        ids_ = Transaction().context['active_ids']
        data = {
            'ids': ids_
        }
        return action, data

    def transition_start(self):
        return 'end'


class ContractExportAvaliableVacationReport(Report):
    'Production Detailed Report'
    __name__ = 'contract.export_avaliable_vacation'

    @classmethod
    def get_context(cls, records, header, data):
        """Function to build data to report"""
        pool = Pool()
        Contract = pool.get('staff.contract')
        report_context = super().get_context(records, header, data)
        ids_ = data.get('ids', [])
        data = {}
        if len(ids_) == 0:
            raise (UserError('ERROR', 'Debe seleccionar al menos un contrato'))

        for id in ids_:
            contract = Contract(id)
            party = contract.employee.party
            init_year = contract.start_date.year
            end_year = (contract.end_date.year if contract.end_date else
                        datetime.date.today().year)

            holidays = round(Decimal((15 / 360) * contract.time_worked), 2)
            enjoy_holidays = contract.days_enjoy
            days_pending = round(holidays - enjoy_holidays, 2)

            data[id] = {
                'full_name': party.name,
                'init_date': contract.start_date,
                'time_worked': contract.time_worked,
                'holidays': holidays,
                'enjoy_holidays': enjoy_holidays,
                'days_pending': days_pending,
                'years_detail': {}
            }

            for year in range(init_year, end_year + 1):
                if holidays >= 15 and enjoy_holidays >= 15:
                    year_enjoy_holidays = 15
                    year_holidays = 15
                    year_days_pending = 0
                    enjoy_holidays -= 15
                    holidays -= 15
                else:
                    if holidays >= 15:
                        year_enjoy_holidays = enjoy_holidays
                        year_holidays = 15
                        year_days_pending = year_holidays - year_enjoy_holidays
                        enjoy_holidays = 0
                        holidays -= 15
                    else:
                        year_enjoy_holidays = enjoy_holidays
                        year_holidays = holidays
                        year_days_pending = year_holidays - enjoy_holidays
                        enjoy_holidays = 0
                        holidays = 0

                data[id]['years_detail'][f"{year}-{year+1}"] = {
                    'years': f'{year}-{year+1}',
                    'year_holidays': year_holidays,
                    'year_enjoy_holidays': year_enjoy_holidays,
                    'year_days_pending': year_days_pending
                }

            report_context['records'] = data
        return report_context
