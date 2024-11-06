""" Staff Access module"""

from datetime import datetime, timedelta
from decimal import Decimal

from dateutil import tz
from sql import Table
from trytond.exceptions import UserError, UserWarning
from trytond.model import ModelSQL, ModelView, fields
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Eval, If
from trytond.report import Report
from trytond.transaction import Transaction
from trytond.wizard import (Button, StateReport, StateTransition, StateView,
                            Wizard)

from_zone = tz.gettz('UTC')
to_zone = tz.gettz('America/Bogota')

_ZERO = Decimal('0.0')
RESTDAY_DEFAULT = 0
WEEK_DAYS = {
    1: 'monday',
    2: 'tuesday',
    3: 'wednesday',
    4: 'thursday',
    5: 'friday',
    6: 'saturday',
    7: 'sunday',
}
PAYMENT_METHOD = [('extratime', 'Extratime'), ('fixed_amount', 'Fixed Amount'),
                  ('holidays', 'Holidays')]


class StaffAccessRests(ModelSQL, ModelView):
    'Staff Access Rests'
    __name__ = 'staff.access.rests'
    access = fields.Many2One('staff.access', 'rests', 'Rests', required=True)
    start = fields.DateTime('Start')
    end = fields.DateTime('End')
    amount = fields.Function(fields.Numeric('Amount', digits=(3, 2)),
                             'on_change_with_amount')
    pay = fields.Boolean('Pay')

    @fields.depends('start', 'end')
    def on_change_with_amount(self, name=None):
        if self.start and self.end:
            # if self.start <  self.access.enter_timestamp \
            #     or self.start > self.access.exit_timestamp \
            #     or self.end < self.start:
            #     raise UserError("Date rest", "invalid_date")
            return self.compute_timedelta(self.start, self.end)
        return None

    def compute_timedelta(self, start, end):
        delta = end - start
        res = float(delta.seconds) / 3600
        res = Decimal(str(round(res, 2)))
        return res


class StaffAccess(metaclass=PoolMeta):
    __name__ = 'staff.access'
    rests = fields.One2Many('staff.access.rests', 'access', 'Rests')
    line_event = fields.Reference('Origin',
                                  selection='get_origin',
                                  select=True,
                                  readonly=True)

    @classmethod
    def __setup__(cls):
        super(StaffAccess, cls).__setup__()
        cls.payment_method = fields.Selection(PAYMENT_METHOD,
                                              'Payment Method',
                                              required=True)

    @staticmethod
    def _get_origin():
        'Return list of Model names for origin Reference'
        return ['staff.event', 'ir.cron']

    @classmethod
    def get_origin(cls):
        Model = Pool().get('ir.model')
        models = cls._get_origin()
        models = Model.search([
            ('model', 'in', models),
        ])
        return [(None, '')] + [(m.model, m.name) for m in models]

    @fields.depends('rests')
    def on_change_rests(self):
        amount = 0
        for rest in self.rests:
            if rest.amount and not rest.pay:
                amount += rest.amount
        self.rest = amount

    @classmethod
    def delete(cls, instances):
        to_delete = []
        for instance in instances:
            if instance.rests:
                to_delete += list(instance.rests)
        if to_delete:
            Rests = Pool().get('staff.access.rests')
            Rests.delete(to_delete)
        super(StaffAccess, cls).delete(instances)

    def _get_extras(self,
                    employee,
                    enter_timestamp,
                    exit_timestamp,
                    start_rest,
                    end_rest,
                    rest,
                    workday=None,
                    restday=None):
        pool = Pool()
        Holiday = pool.get('staff.holidays')
        Contract = pool.get('staff.contract')
        Config = pool.get('staff.configuration')
        config = Config(1)
        work_day_hours = config.default_hour_workday

        if not work_day_hours:
            raise UserError('ERROR', 'Debe configurar las horas reglamentadas')

        start_date = (enter_timestamp + timedelta(hours=5)).date()
        contracts = Contract.search([
            'OR',
            [
                ('employee', '=', employee.id),
                ('start_date', '<=', start_date),
                ('finished_date', '>=', start_date),
            ],
            [
                ('employee', '=', employee.id),
                ('start_date', '<=', start_date),
                ('finished_date', '=', None),
            ]
        ],
            limit=1,
            order=[('start_date', 'DESC')])

        if not contracts:
            raise UserError(f"staff_access_extratime {start_date}",
                            f"missing_contract {employee.party.name}")

        position_ = contracts[0].position
        if not enter_timestamp or not exit_timestamp \
                or not position_ or not position_.extras:
            return {
                'ttt': 0,
                'het': 0,
                'hedo': 0,
                'heno': 0,
                'reco': 0,
                'recf': 0,
                'dom': 0,
                'hedf': 0,
                'henf': 0
            }

        holidays = [day.holiday for day in Holiday.search([])]

        # Ajuste UTC tz para Colombia timestamp [ -5 ]
        enter_timestamp = enter_timestamp.replace(tzinfo=from_zone)
        enter_timestamp = enter_timestamp.astimezone(to_zone)

        exit_timestamp = exit_timestamp.replace(tzinfo=from_zone)
        exit_timestamp = exit_timestamp.astimezone(to_zone)

        if not workday:
            workday = work_day_hours
        if not restday:
            restday = RESTDAY_DEFAULT

        restday_effective = 0
        if rest:
            restday_effective = Decimal(rest)

        # Verifica si el usuario sale o entra un festivo
        enter_holiday = False
        exit_holiday = False

        if (enter_timestamp.weekday() == 6) or (enter_timestamp.date()
                                                in holidays):
            enter_holiday = True
        if (exit_timestamp.weekday() == 6) or (exit_timestamp.date()
                                               in holidays):
            exit_holiday = True

        # To convert datetime enter/exit to decimal object
        enterd = self._datetime2decimal(enter_timestamp)
        exitd = self._datetime2decimal(exit_timestamp)

        all_rests = []
        for _rest in self.rests:
            start_rest = _rest.start
            end_rest = _rest.end
            if start_rest and end_rest:
                start_rest_timestamp = start_rest.replace(tzinfo=from_zone)
                start_rest_timestamp = start_rest_timestamp.astimezone(to_zone)
                end_rest_timestamp = end_rest.replace(tzinfo=from_zone)
                end_rest_timestamp = end_rest_timestamp.astimezone(to_zone)

                start_rest = self._datetime2decimal(start_rest_timestamp)
                end_rest = self._datetime2decimal(end_rest_timestamp)
                all_rests.append((start_rest, end_rest))

        # To check whether date change inside of shift
        if enter_timestamp.date() == exit_timestamp.date():
            date_change = False
        else:
            date_change = True

        liquid = self._calculate_shift(enterd, exitd, date_change,
                                       enter_holiday, exit_holiday, workday,
                                       restday, all_rests, restday_effective)

        res = {
            'ttt': round(liquid['ttt'], 2),
            'het': round(liquid['het'], 2),
            'reco': round(liquid['reco'], 2),
            'recf': round(liquid['recf'], 2),
            'dom': round(liquid['dom'], 2),
            'hedo': round(liquid['hedo'], 2),
            'heno': round(liquid['heno'], 2),
            'hedf': round(liquid['hedf'], 2),
            'henf': round(liquid['henf'], 2),
        }
        return res

    def _calculate_shift(self, enterd, exitd, date_change, enter_holiday,
                         exit_holiday, workday, restday, all_rests,
                         restday_effective):
        pool = Pool()
        Config = pool.get('staff.configuration')
        config = Config(1)
        work_day_hours = config.default_hour_workday
        if not workday:
            if not work_day_hours:
                raise UserError(
                    'ERROR', 'Debe configurar las horas reglamentadas')
            workday = work_day_hours
        ttt = het = hedo = heno = reco = recf = dom = hedf = henf = _ZERO

        if date_change:
            exitd += 24

        ttt = exitd - enterd - restday_effective
        if ttt <= 0:
            ttt = 0
            return {
                'ttt': ttt,
                'het': het,
                'hedo': hedo,
                'heno': heno,
                'reco': reco,
                'recf': recf,
                'dom': dom,
                'hedf': hedf,
                'henf': henf
            }

        # H.E.T.
        workday_legal = Decimal(workday - restday)

        if ttt > workday_legal:
            het = ttt - workday_legal

        contador = enterd  # Contador que comienza con la hora de entrada
        total = 0  # Sumador que comienza en Cero
        in_extras = False
        cicle = True
        rest_moment = False
        index_rest = 0
        # ---------------------- main iter -----------------------------
        while cicle:
            # Ciclo Inicial
            if contador == enterd:
                if int(enterd) == int(exitd):
                    # Significa que entro y salio en la misma hora
                    sumador = exitd - contador
                    cicle = False
                else:
                    # Significa que salio en una hora distinta a la que entro
                    if int(enterd) == enterd:
                        # Si entra en una hora en punto, suma una hora
                        sumador = 1
                    else:
                        """ Si entra en una hora no en punto suma 
                            el parcial de la hora"""
                        sumador = (int(enterd) + 1) - enterd
            elif contador >= int(exitd):
                # Ciclo Final
                sumador = exitd - int(exitd)
                cicle = False
            else:
                # Ciclo Intermedio
                sumador = 1

            contador = contador + sumador
            if index_rest < len(all_rests):
                start_rest, end_rest = all_rests[index_rest]
                if start_rest and end_rest:
                    if contador == start_rest:
                        pass
                    elif (int(contador)
                          - 1) == int(start_rest) and not rest_moment:
                        # Ajusta sumador por empezar descanso
                        rest_moment = True
                        sumador = start_rest - (contador - 1)
                        if int(start_rest) == int(end_rest):
                            sumador, rest_moment, index_rest =\
                                self._get_all_rests(
                                    index_rest, all_rests, contador)
                        #     index_rest += 1
                    elif contador >= start_rest and contador <= end_rest:
                        continue
                    elif (int(contador) - 1) == int(end_rest) and rest_moment:
                        # Ajusta sumador por terminar descanso
                        sumador = contador - end_rest
                        rest_moment = False
                        index_rest += 1
                    else:
                        pass

            total = total + sumador
            is_night = True
            if (6 < contador <= 21) or (30 < contador <= 46):
                is_night = False

            # Verifica si hay EXTRAS
            sum_partial_rec = 0

            if total > workday:
                # Se calcula el sumador para extras
                in_extras = True
                sum_extra = sumador
                if (total - sumador - restday) <= workday_legal:
                    sum_extra = (total - restday) - workday_legal
                    sum_partial_rec = sumador - sum_extra

                if (contador <= 24 and not enter_holiday) or\
                        (contador > 24 and not exit_holiday):
                    if is_night:
                        heno = self._get_sum(heno, sum_extra)
                    else:
                        hedo = self._get_sum(hedo, sum_extra)
                else:
                    if is_night:
                        henf = self._get_sum(henf, sum_extra)
                    else:
                        hedf = self._get_sum(hedf, sum_extra)

            # Verifica si hay DOM
            if not in_extras:
                if (enter_holiday and contador <= 24) or (exit_holiday
                                                          and contador > 24):
                    dom = self._get_sum(dom, sumador)
                    if dom >= round(Decimal(work_day_hours), 2):
                        dom = round(Decimal(work_day_hours), 2)

            # Verifica si hay REC
            if sum_partial_rec > 0:
                in_extras = False
                sum_rec = sum_partial_rec
            else:
                sum_rec = sumador

            if is_night and not in_extras:
                if (contador <= 24 and not enter_holiday) or\
                        (contador > 24 and not exit_holiday):
                    reco = self._get_sum(reco, sum_rec)
                else:
                    recf = self._get_sum(recf, sum_rec)

        if ttt >= work_day_hours and dom > Decimal(0.0):
            dom = round(Decimal(work_day_hours), 2)
        elif ttt <= work_day_hours and dom > Decimal(0.0):
            dom = ttt

        return {
            'ttt': round(ttt),
            'het': round(het, 2),
            'hedo': round(het - heno, 2) if dom == 0 else hedo,
            'heno': round(heno, 2),
            'reco': round(reco),
            'recf': round(recf),
            'dom': round(dom),
            'hedf': round(het - henf, 2) if dom != 0 else hedf,
            'henf': round(henf, 2)
        }

    # Obtiene la suma de los descansos
    def _get_all_rests(self, index_rest, all_rests, contador):
        sumador = 1
        rest_moment = False
        for start_rest, end_rest in all_rests[index_rest:]:
            if (int(contador) - 1) == int(start_rest):
                rest_moment = True
                if int(start_rest) == int(end_rest):
                    sumador = sumador - (end_rest - start_rest)
                    rest_moment = False
                    index_rest += 1
        return sumador, rest_moment, index_rest


class ImportBiometricRecords(Wizard):
    'Import Biometric Records'
    __name__ = 'staff.access.import_biometric_records'

    start_state = 'parameters'
    parameters = StateView(
        'staff.access.import_biometric_records.parameters',
        'access.import_biometric_records_parameters_view_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Import',
                   'import_biometric_records',
                   'tryton-go-next',
                   default=True)
        ])
    import_biometric_records = StateTransition()

    def transition_import_biometric_records(self):
        pool = Pool()
        Actualizacion = pool.get('conector.actualizacion')
        Warning = pool.get('res.user.warning')
        warning_name = 'warning_import_biometric_records'
        event_time = datetime(self.parameters.day.year,
                              self.parameters.day.month,
                              self.parameters.day.day, 0, 0, 0)
        if Warning.check(warning_name):
            raise UserWarning(
                warning_name, f"Se importaran registros del \
                    biometrico en la fecha: {event_time}")
        Actualizacion.import_biometric_access(event_time)
        return 'end'


class ImportBiometricRecordsParameters(ModelView):
    'Import Biometric Records Parameters'
    __name__ = 'staff.access.import_biometric_records.parameters'

    day = fields.Date('Day', required=True)


class StaffAccessView(ModelView):
    "Report Staff Access Start"
    __name__ = "staff.access_view_start"

    company = fields.Many2One('company.company', 'Company', required=True)
    from_date = fields.Date("From Date",
                            domain=[
                                If(
                                    Eval('to_date') & Eval('from_date'),
                                    ('from_date', '<=', Eval('to_date')), ()),
                            ],
                            depends=['to_date'],
                            required=True)
    to_date = fields.Date("To Date",
                          domain=[
                              If(
                                  Eval('from_date') & Eval('to_date'),
                                  ('to_date', '>=', Eval('from_date')), ()),
                          ],
                          depends=['from_date'],
                          required=True)

    @staticmethod
    def default_company():
        return Transaction().context.get('company')


class StaffAccessWizard(Wizard):
    'Report Staff Access Wizard'
    __name__ = 'staff.access_wizard'

    start = StateView('staff.access_view_start',
                      'access.staff_access_report_form', [
                          Button('Cancel', 'end', 'tryton-cancel'),
                          Button('Print', 'print_', 'tryton-ok', default=True),
                      ])
    print_ = StateReport('staff.access_report')

    def do_print_(self, action):

        data = {
            'company': self.start.company.id,
            # 'fiscalyear': self.start.fiscalyear.name,
            'to_date': self.start.to_date,
            'from_date': self.start.from_date,
        }
        return action, data

    def transition_print_(self):
        return 'end'


class StaffAccessReport(Report):
    "Staff access report"
    __name__ = 'staff.access_report'

    @classmethod
    def get_date_fech(cls, date):
        result = ''
        if date not in ['Null', None]:
            date = str((date - timedelta(hours=5))).split(' ')
            result = date[1]

        return result

    @classmethod
    def get_context(cls, records, header, data):
        report_context = super().get_context(records, header, data)
        pool = Pool()
        Staff = pool.get('staff.access')
        StaffRestd = pool.get('staff.access.rests')
        Party = pool.get('party.party')
        Employee = pool.get('company.employee')
        Company = pool.get('company.company')
        cursor = Transaction().connection.cursor()

        # Asignacion de tabalas para extraccion de la data
        staff = Staff.__table__()
        staffRestd = StaffRestd.__table__()
        party = Party.__table__()
        employee = Employee.__table__()

        # Dato de fecha de inicio
        fechfinal = str(data['to_date']).split('-')
        datefinal = str(
            datetime(int(fechfinal[0]), int(fechfinal[1]), int(fechfinal[2]),
                     23, 59, 59))

        # Dato de fecha final para reporte
        fechini = str(data['from_date']).split('-')
        dateintitial = str(
            datetime(int(fechini[0]), int(fechini[1]), int(fechini[2])))

        # Condicionales para extraer los datos
        where = staff.enter_timestamp >= dateintitial
        where &= staff.exit_timestamp <= datefinal

        # Datos que seran extraidos desde la base de datos
        columns = [
            staff.id, party.name, party.id_number, staff.enter_timestamp,
            staff.exit_timestamp, staff.ttt, staff.rest, staffRestd.end,
            staffRestd.start
        ]

        # Consulta que retorna la informacion para el reporte de acceso diario
        select = staff.join(
            staffRestd, 'LEFT', condition=staff.id == staffRestd.access).join(
                employee, 'LEFT',
                condition=staff.employee == employee.id).join(
                    party, 'LEFT',
                    condition=party.id == employee.party).select(
                        *columns,
                        where=where,
                        order_by=[
                            party.id_number, staff.enter_timestamp,
                            staffRestd.start
                        ])

        cursor.execute(*select)

        record_dict = {}
        """ Ciclo para generar la data para el informe,
            todo en formato diccionario"""
        for index, curso in enumerate(cursor):
            if curso[0] in record_dict:
                record_dict[curso[2], index] = {
                    'party': '',
                    'id_number': '',
                    'enter_timestamp': '',
                    'exit_timestamp': '',
                    'ttt': '',
                    'rest': '',
                    'end': cls.get_date_fech(
                        curso[7]
                    ),  # Funcion que toma solo la hora de la fecha obtenida
                    'start': cls.get_date_fech(curso[8]),
                }
            else:
                record_dict[curso[0]] = {
                    'party': curso[1],
                    'id_number': curso[2],
                    'enter_timestamp': str(curso[3] - timedelta(hours=5)),
                    'exit_timestamp': str(curso[4] - timedelta(hours=5)),
                    'ttt': curso[5],
                    'rest': curso[6],
                    'end': cls.get_date_fech(curso[7]),
                    'start': cls.get_date_fech(curso[8]),
                }

        report_context['records'] = record_dict.values()
        report_context['company'] = Company(data['company'])
        return report_context


class CreateAccessHolidaysView(ModelView):
    'Create Acess Holyday Start'
    __name__ = 'staff.create_holidays_view_wizard'

    date = fields.Date("Date", required=True)
    time_in = fields.Time("Time in", required=True)
    time_out = fields.Time("Time out", required=True)


class CreateAccessHolidaysWizard(Wizard):
    __name__ = 'staff.create_holidays_wizard'

    start = StateView(
        'staff.create_holidays_view_wizard',
        'access.create_holidays_access_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Confirm', 'excecute_wizard', 'tryton-ok', default=True),
        ])

    excecute_wizard = StateTransition()

    def transition_excecute_wizard(self):
        self.create_staff_access()
        return 'end'

    def create_staff_access(self):
        pool = Pool()
        Access = pool.get('staff.access')
        Employee = pool.get('company.employee')
        Holidays = pool.get('staff.holidays')
        access_table = Table('staff_access')
        Contract = pool.get('staff.contract')
        Config = pool.get('staff.configuration')

        config = Config(1)
        work_day_hours = config.default_hour_workday
        if not work_day_hours:
            raise UserError('ERROR', 'Debe configurar las horas reglamentadas')

        cursor = Transaction().connection.cursor()

        date = self.start.date
        date_today = datetime.today().date()
        date_difference = (date - date_today)
        date_init_day = datetime.combine(
            date, datetime.min.time()) + timedelta(hours=5)
        date_end_day = datetime.combine(
            date, datetime.max.time()) + timedelta(hours=5)
        enter_timestamp = datetime.combine(date, self.start.time_in)
        exit_timestamp = datetime.combine(date, self.start.time_out)
        hour_difference = (exit_timestamp
                           - enter_timestamp).total_seconds() / 3600

        employees = Employee.search([('active', '=', 'active')])
        holiday = Holidays.search([('holiday', '=', date)])

        if date_difference.days > 0:
            raise UserError(
                "ERROR:",
                "La fecha de asistencia no puede ser mayor a la fecha actual")

        if not holiday and date.weekday() != 6:
            raise UserError("ERROR:",
                            "Debe seleccionar un dia dominical/festivo")

        if self.start.time_in >= self.start.time_out:
            raise UserError(
                "ERROR:",
                "La hora de ingreso no puede ser mayor a la hora de salida.")

        if work_day_hours > hour_difference or hour_difference > 8:
            raise UserError(
                "ERROR:",
                "Las horas laboradas deben coincidir con lo reglamentado.")

        for employee in employees:
            contracts = Contract.search([
                'OR',
                [
                    ('employee', '=', employee.id),
                    ('start_date', '<=', self.start.date),
                    ('finished_date', '>=', self.start.date),
                ],
                [
                    ('employee', '=', employee.id),
                    ('start_date', '<=', self.start.date),
                    ('finished_date', '=', None),
                ]
            ],
                limit=1,
                order=[('start_date', 'DESC')])

            if contracts:
                if employee.end_date is None or employee.end_date >= date:
                    is_access = Access.search([
                        ('enter_timestamp', '>=', date_init_day),
                        ('exit_timestamp', '<=', date_end_day),
                        ('employee', '=', employee)
                    ])

                    if not is_access:
                        to_save = Access()
                        to_save.employee = employee
                        to_save.payment_method = 'holidays'
                        to_save.enter_timestamp = enter_timestamp + timedelta(
                            hours=5)
                        to_save.exit_timestamp = exit_timestamp + timedelta(
                            hours=5)
                        # to_save.line_event = date
                        to_save.save()

                        cursor.execute(*access_table.update(
                            columns=[
                                access_table.ttt,
                                access_table.hedo,
                                access_table.heno,
                                access_table.hedf,
                                access_table.henf,
                                access_table.reco,
                                access_table.recf,
                                access_table.dom,
                            ],
                            values=[Decimal(work_day_hours), 0,
                                    0, 0, 0, 0, 0, 0],
                            where=access_table.id.in_([to_save.id])))
