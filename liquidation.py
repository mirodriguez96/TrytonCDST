from datetime import timedelta
from trytond.pool import PoolMeta, Pool


class LiquidationReport(metaclass=PoolMeta):
    __name__ = 'staff.liquidation.report'

    @classmethod
    def get_context(cls, records, header, data):
        report_context = super().get_context(records, header,  data)
        pool = Pool()
        Event = pool.get('staff.event')
        total_days_holidays = 0
        total_salaries = 0
        end_date = ''
        start_date = ''
        licenseNR = 0

        
        for record in records:
            if record.kind == 'holidays':
                for liq_line in record.lines:
                    if liq_line.wage.type_concept == 'holidays' and liq_line.wage.type_concept_electronic in ('VacacionesComunes','VacacionesCompensadas'):
                        event = Event.search([('staff_liquidation', '=', liq_line.liquidation.id)])
                        start_date = event[0].start_date
                        end_date = event[0].end_date
                        total_days_holidays += liq_line.days
                    if liq_line.wage.type_concept == 'salary' and liq_line.wage.type_concept_electronic == 'Basico':
                        total_salaries += liq_line.days
                    if liq_line.wage.type_concept_electronic == 'LicenciaNR':
                        licenseNR += liq_line.days
        
        report_context['total_days_holidays'] = total_days_holidays
        report_context['total_salaries'] = total_salaries
        report_context['end_date'] = end_date
        report_context['start_date'] = start_date
        report_context['licenseNR'] = licenseNR
        report_context['records'] = records

        return report_context