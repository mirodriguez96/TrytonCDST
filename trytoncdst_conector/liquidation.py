import calendar
from datetime import datetime, timedelta, date
from decimal import Decimal
import re

from dateutil import tz
from trytond.exceptions import UserError
from trytond.model import ModelView, fields
from trytond.modules.analytic_account import AnalyticMixin
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Bool, Eval, If, Not

from .constants import EXTRAS


def ultimo_dia_del_mes(year, month):
    return calendar.monthrange(year, month)[1]


from_zone = tz.gettz('UTC')
to_zone = tz.gettz('America/Bogota')

CONCEPT_ACCESS = {
    'HED': 'hedo',
    'HEN': 'heno',
    'HRN': 'hedf',
    'HEDDF': 'recf',
    'HENDF': 'henf',
    'HRDDF': 'reco',
    'HRNDF': 'dom',
}


TYPE_CONCEPT_ELECTRONIC = [
    ('', ''),
    ('Basico', 'Basico'),
    ('AuxilioTransporte', 'Auxilio Transporte'),
    ('ViaticoManuAlojS', 'Viatico Manu Aloj S'),
    ('ViaticoManuAlojNS', 'Viatico Manu Aloj NS'),
    ('HED', 'HORA EXTRA DIURNA'),
    ('HEN', 'HORA EXTRA NOCTURNA'),
    ('HRN', 'HORA RECARGO NOCTURNO'),
    ('HEDDF', 'HORA EXTRA DIURNA DOMINICAL Y FESTIVOS'),
    ('HRDDF', 'HORA RECARGO DIURNO DOMINICAL Y FESTIVOS'),
    ('HENDF', 'HORA EXTRA NOCTURNA DOMINICAL Y FESTIVOS'),
    ('HRNDF', 'HORA RECARGO NOCTURNO DOMINICAL Y FESTIVOS'),
    ('VacacionesComunes', 'Vacaciones Comunes'),
    ('VacacionesCompensadas', 'Vacaciones Compensadas'),
    ('PrimasS', 'Primas S'),
    ('PrimasNS', 'Primas NS'),
    ('Cesantias', 'Cesantias'),
    ('IntCesantias', 'Int Cesantias'),
    ('IncapacidadComun', 'Incapacidad Comun'),
    ('IncapacidadProfesional', 'Incapacidad Profesional'),
    ('IncapacidadLaboral', 'Incapacidad Laboral'),
    ('LicenciaMP', 'Licencia MP'),
    ('LicenciaR', 'Licencia R'),
    ('LicenciaNR', 'Licencia NR'),
    ('BonificacionS', 'Bonificacion S'),
    ('BonificacionNS', 'Bonificacion NS'),
    ('AuxilioS', 'Auxilio S'),
    ('AuxilioNS', 'Auxilio NS'),
    ('HuelgaLegal', 'Huelga Legal'),
    ('ConceptoS', 'Otro Concepto S'),
    ('ConceptoNS', 'Otro Concepto NS'),
    ('CompensacionO', 'Compensacion O'),
    ('CompensacionE', 'Compensacion E'),
    ('PagoS', 'Bono EPCTV S'),
    ('PagoNS', 'Bono EPCTV NS'),
    ('PagoAlimentacionS', 'Pago Alimentacion S'),
    ('PagoAlimentacionN', 'Pago Alimentacion NS'),
    ('Comision', 'Comision'),
    ('PagoTercero', 'Pago Tercero'),
    ('Anticipo', 'Anticipo'),
    ('Dotacion', 'Dotacion'),
    ('ApoyoSost', 'Apoyo Sost'),
    ('Teletrabajo', 'Teletrabajo'),
    ('BonifRetiro', 'BonifRetiro'),
    ('Indemnizacion', 'Indemnizacion'),
    ('Reintegro', 'Reintegro'),
    ('Salud', 'Salud'),
    ('FondoPension', 'Fondo Pension'),
    ('FondoSP', 'Fondo SP'),
    ('FondoSPSUB', 'Fondo SP SUB'),
    ('Sindicato', 'Sindicato'),
    ('SancionPublic', 'Sancion Public'),
    ('SancionPriv', 'Sancion Priv'),
    ('Libranza', 'Libranza'),
    ('OtraDeduccion', 'Otra Deduccion'),
    ('PensionVoluntaria', 'Pension Voluntaria'),
    ('RetencionFuente', 'Retencion Fuente'),
    ('AFC', 'AHORRO FOMENTO A LA CONSTRUCCION'),
    ('Cooperativa', 'Cooperativa'),
    ('EmbargoFiscal', 'Embargo Fiscal'),
    ('PlanComplementario', 'Plan Complementario'),
    ('Educacion', 'Educacion'),
    ('Reintegro', 'Re-integro'),
    ('Deuda', 'Deuda'),
]

EXTRAS_CORE = EXTRAS

EXTRAS = {
    'HED': {'code': 1, 'percentaje': '25.00'},
    'HEN': {'code': 2, 'percentaje': '75.00'},
    'HRN': {'code': 3, 'percentaje': '35.00'},
    'HEDDF': {'code': 4, 'percentaje': '100.00'},
    'HRDDF': {'code': 5, 'percentaje': '75.00'},
    'HENDF': {'code': 6, 'percentaje': '150.00'},
    'HRNDF': {'code': 7, 'percentaje': '110.00'},
}

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

CONTRACT = [
    'bonus_service',
    'health',
    'retirement',
    'unemployment',
    'interest',
    'holidays',
    'convencional_bonus',
]

CONCEPT = ['health', 'retirement']

CONCEPT_ELECTRONIC = ['Libranza']

MONTH = {
    '01': 'ENERO',
    '02': 'FEBRERO',
    '03': 'MARZO',
    '04': 'ABRIL',
    '05': 'MAYO',
    '06': 'JUNIO',
    '07': 'JULIO',
    '08': 'AGOSTO',
    '09': 'SEPTIEMBRE',
    '10': 'OCTUBRE',
    '11': 'NOVIEMBRE',
    '12': 'DICIEMBRE',
}

STATE = {
    'invisible': Not(Bool(Eval('access_register'))),
    'readonly': Bool(Eval('state') != 'draft'),
}


class AnalyticAccountEntry(metaclass=PoolMeta):
    __name__ = 'analytic.account.entry'

    @classmethod
    def _get_origin(cls):
        origins = super(AnalyticAccountEntry, cls)._get_origin()
        return origins + ['staff.liquidation.line']


class Liquidation(metaclass=PoolMeta):
    __name__ = 'staff.liquidation'
    sended_mail = fields.Boolean('Sended Email')
    payment_liquidation_date = fields.Date('Payment liquidation date')
    origin = fields.Reference('Origin', selection='get_origin')

    @classmethod
    def _get_origin(cls):
        'Return list of Model names for origin Reference'
        return ['staff.event']

    @classmethod
    def get_origin(cls):
        Model = Pool().get('ir.model')
        get_name = Model.get_name
        models = cls._get_origin()
        return [(None, '')] + [(m, get_name(m)) for m in models]

    @classmethod
    def __setup__(cls):
        super(Liquidation, cls).__setup__()
        cls.state.selection.append(('wait', 'Wait'))
        cls._buttons.update(
            {
                'wait': {
                    'invisible': Eval('state') != 'wait',
                },
            }
        )

    @classmethod
    @ModelView.button
    def wait(cls, records):
        for i in records:
            i.state = 'draft'
            i.save()

    # Funcion encargada de contar los días festivos
    def count_holidays(self, start_date, end_date, event):
        sundays = 0
        if (
            event.category.wage_type.type_concept == 'holidays'
            and event.category.wage_type.type_concept_electronic
            == 'VacacionesCompensadas'
        ):
            return sundays
        day = timedelta(days=1)
        # Iterar sobre todas las fechas dentro del rango
        current_date = start_date
        while current_date <= end_date:
            if current_date.weekday() == 6:  # 6 representa el domingo
                sundays += 1
            current_date += day
        Holiday = Pool().get('staff.holidays')
        holidays = Holiday.search(
            [
                ('holiday', '>=', start_date),
                ('holiday', '<=', end_date),
            ],
            count=True,
        )
        return sundays + holidays

    def _validate_holidays_lines(self, event, start_date, end_date, days):
        line = None
        for l in self.lines:
            if l.wage.type_concept == 'holidays':
                line = l
        if not line:
            return
        if event.edit_amount:
            amount_day = event.amount
        else:
            amount_day = self.contract.salary / 30
        # amount = amount_day * event.days_of_vacations
        holidays = self.count_holidays(start_date, end_date, event)
        workdays = days - holidays
        amount_workdays = round(amount_day * workdays, 2)
        amount_holidays = round(amount_day * holidays, 2)
        # line, = self.lines
        move_lines = []
        value = 0
        for move_line in line.move_lines:
            value += move_line.credit
            move_lines.append(move_line)
            if value > amount_workdays:
                break
        line.move_lines = move_lines
        if value != amount_workdays:
            Adjustment = Pool().get('staff.liquidation.line_adjustment')
            adjustment = amount_workdays - value
            if adjustment < 0:
                adjustment_account = line.wage.credit_account
            else:
                adjustment_account = line.wage.debit_account
            line.adjustments = [
                Adjustment(
                    account=adjustment_account,
                    amount=adjustment,
                    description=line.description,
                )
            ]
            line.amount = amount_workdays
            line.days = workdays
        line.save()
        if amount_holidays > 0:
            WageType = Pool().get('staff.wage_type')
            wage_type = WageType.search(
                [
                    ('non_working_days', '=', True),
                    ('department', '=', self.employee.department),
                ],
                limit=1,
            )
            if not wage_type:
                raise UserError(
                    'Wage Type', 'missing wage_type (non_working_days)')
            (wage_type,) = wage_type
            value = {
                'sequence': wage_type.sequence,
                'wage': wage_type.id,
                'description': wage_type.name,
                'amount': amount_holidays,
                'account': wage_type.debit_account,
                'days': holidays,
                'adjustments': [
                    (
                        'create',
                        [
                            {
                                'account': wage_type.debit_account.id,
                                'amount': amount_holidays,
                                'description': wage_type.debit_account.name,
                            }
                        ],
                    )
                ],
            }

            self.write([self], {'lines': [('create', [value])]})

    def create_move(self):
        pool = Pool()
        Period = pool.get('account.period')
        Move = pool.get('account.move')
        if self.move:
            return

        move_lines, grouped = self.get_moves_lines()
        if move_lines:
            lines = self.lines[0].get_move_line(move_lines)
            period_id = Period.find(
                self.company.id, date=self.liquidation_date)
            (move,) = Move.create(
                [
                    {
                        'journal': self.journal.id,
                        'origin': str(self),
                        'period': period_id,
                        'date': self.liquidation_date,
                        'description': self.description,
                        'lines': [('create', lines)],
                    }
                ]
            )
            self.write([self], {'move': move.id})
            self.reconcile_lines(move.lines, grouped)
            self.reconcile_loans(move)
            Move.post([move])
            Move.save([move])

    def reconcile_lines(self, move_lines, grouped):
        pool = Pool()
        Note = pool.get('account.move.reconcile.write_off')
        MoveLine = pool.get('account.move.line')
        reconcile = True

        if self.kind == 'contract':
            for ml in move_lines:
                if (ml.account.id, ml.description, 'payment') not in grouped.keys() or (
                    ml.account.type.statement not in ('balance')
                ):
                    continue
                to_reconcile = [ml]

                if grouped[(ml.account.id, ml.description, 'payment')]:
                    to_reconcile.extend(
                        grouped[(ml.account.id, ml.description,
                                 'payment')]['lines']
                    )
                if len(to_reconcile) > 1:
                    note = Note.search([])
                    writeoff = None
                    if note:
                        writeoff = note[0]
                    MoveLine.reconcile(set(to_reconcile), writeoff=writeoff)
        else:
            for ml in move_lines:
                if (ml.account.id, ml.description, 'payment') not in grouped.keys() or (
                    ml.account.type.statement not in ('balance')
                ):
                    continue
                to_reconcile = [ml]

                if grouped[(ml.account.id, ml.description, 'payment')]:
                    to_reconcile.extend(
                        grouped[(ml.account.id, ml.description,
                                 'payment')]['lines']
                    )
                if len(to_reconcile) > 1 and reconcile:
                    reconcile = False
                    note = Note.search([])
                    writeoff = None
                    if note:
                        writeoff = note[0]
                    MoveLine.reconcile(set(to_reconcile), writeoff=writeoff)

    def reconcile_loans(self, move):
        pool = Pool()
        AccountMoveLine = pool.get('account.move.line')
        LoanLines = pool.get('staff.loan.line')
        balance = 0
        conciled_lines = []
        if self.kind == 'contract':
            for line in self.lines:
                if line.wage.type_concept_electronic == 'Deuda':
                    loan_line = LoanLines.search([('origin', '=', line)])
                    if loan_line:
                        loan_move_line = AccountMoveLine.search(
                            [
                                ('origin', '=', loan_line[0]),
                                ('reconciliation', '=', None),
                            ]
                        )
                        if (loan_move_line and loan_move_line[0]
                                in conciled_lines):
                            break
                        reference = loan_line[0].loan.number
                        for move_line in move.lines:
                            if move_line in conciled_lines:
                                continue
                            balance = 0
                            try:
                                if move_line.description == line.description:
                                    lines_to_reconcile = []
                                    balance += (
                                        move_line.debit
                                        - move_line.credit
                                        + loan_move_line[0].debit
                                        - loan_move_line[0].credit
                                    )
                                    if balance == 0:
                                        move_line.reference = reference
                                        move_line.save()
                                        lines_to_reconcile.append(
                                            loan_move_line[0])
                                        lines_to_reconcile.append(move_line)
                                        if lines_to_reconcile:
                                            AccountMoveLine.reconcile(
                                                lines_to_reconcile
                                            )
                                            conciled_lines.append(move_line)
                                            conciled_lines.append(
                                                loan_move_line[0])
                                            break
                            except Exception as error:
                                print(error)
        else:
            for lines in move.lines:
                origin = lines.origin
                reference = lines.reference
                balance = 0

                # Validate if is loan lines to conciliate
                if origin and reference and origin.__name__ == LoanLines.__name__:

                    move_lines = AccountMoveLine.search(
                        [
                            ('origin', '=', origin),
                            ('reference', '=', reference),
                            ('reconciliation', '=', None),
                        ]
                    )

                    if len(move_lines) % 2 == 0 and move_lines:
                        for line in move_lines:
                            balance += line.debit - line.credit
                        if balance == 0:
                            AccountMoveLine.reconcile(move_lines)
                    else:
                        for line in self.lines:
                            if line.wage.type_concept_electronic == 'Deuda':
                                balance = 0
                                already_concile = False
                                if line in conciled_lines:
                                    continue
                                conciled_lines.append(line)

                                loan_line = LoanLines.search(
                                    ['origin', '=', line])
                                if loan_line:
                                    loan_move_line = AccountMoveLine.search(
                                        [
                                            ('origin', '=', loan_line[0]),
                                            ('reconciliation', '=', None),
                                        ]
                                    )

                                    for lines in loan_move_line:
                                        if lines in conciled_lines:
                                            already_concile = True
                                    if already_concile:
                                        break

                                    for lines in loan_move_line:
                                        balance += lines.debit - lines.credit
                                    try:
                                        if balance == 0:
                                            lines_to_reconcile = []
                                            lines_to_reconcile = list(
                                                loan_move_line)
                                            if lines_to_reconcile:
                                                AccountMoveLine.reconcile(
                                                    lines_to_reconcile
                                                )
                                                for line in loan_move_line:
                                                    conciled_lines.append(line)
                                                break
                                    except Exception as error:
                                        print(error)

    def get_moves_lines(self):
        pool = Pool()
        LoanLines = pool.get('staff.loan.line')
        grouped = {}
        to_reconcile = []
        lines_moves = []
        amount = []
        validate = True
        result = None

        wages = [
            wage_type
            for wage_type in self.employee.mandatory_wages
            if wage_type.wage_type.type_concept == 'retirement'
            and self.kind == 'holidays'
        ]

        for line in self.lines:
            analytic_account = None
            data = {'origin': None, 'reference': None}
            analytic_account = self.get_wage_analytic_account(line)

            if line.origin and line.origin.__name__ == LoanLines.__name__:
                data['origin'] = line.origin
                data['reference'] = line.origin.loan.number

            if line.move_lines:
                for moveline in line.move_lines:
                    to_reconcile.append(moveline)
                    amount_line = moveline.debit - moveline.credit * -1
                    account_id = (
                        moveline.account.id,
                        line.description,
                        line.wage.definition,
                    )
                    if account_id not in grouped.keys():
                        grouped[account_id] = {
                            'amount': [],
                            'description': line.description,
                            'wage': line.wage,
                            'party_to_pay': line.party_to_pay,
                            'lines': [],
                            'origin': data['origin'],
                            'reference': data['reference'],
                        }
                    grouped[account_id]['amount'].append(amount_line)
                    grouped[account_id]['lines'].append(moveline)
                    amount.append(amount_line)
            elif line.wage.definition == 'discount':
                account_id = (line.account.id, line,
                              line.description, line.amount)
                if account_id not in grouped.keys():
                    grouped[account_id] = {
                        'amount': [],
                        'description': line.description,
                        'wage': line.wage,
                        'party_to_pay': line.party_to_pay,
                        'lines': [],
                        'origin': data['origin'],
                        'reference': data['reference'],
                    }
                grouped[account_id]['amount'].append(line.amount)
                amount.append(line.amount)

            for adjust in line.adjustments:
                key = (adjust.account.id, adjust.description)
                if key not in grouped.keys():
                    grouped[key] = {
                        'amount': [],
                        'description': adjust.description,
                        'wage': line.wage,
                        'party_to_pay': line.party_to_pay,
                        'lines': [],
                        'origin': data['origin'],
                        'reference': data['reference'],
                        'analytic': analytic_account,
                    }

                grouped[key]['amount'].append(adjust.amount)
                amount.append(adjust.amount)

        for account_id, values in grouped.items():
            account_id = account_id[0]
            party_payment = values['party_to_pay']
            wage = values['wage']
            origin_ = values['origin']
            reference_ = values['reference']

            if party_payment:
                for wage in wages:
                    if validate:
                        if values['wage'].id == wage.wage_type.id:
                            party_payment = wage.party.id
                            validate = False
                            result = self._prepare_line(
                                values['description'],
                                wages[0].wage_type.debit_account.id,
                                debit=round(self.gross_payments
                                            * Decimal(0.12), 2),
                                credit=_ZERO,
                                analytic=values.get('analytic', None),
                                origin=origin_,
                                reference=reference_,
                                wage=values['wage'],
                                wages=wages
                            )

                            values['amount'] = [
                                round(self.gross_payments
                                      * Decimal(0.16), 2) * -1
                            ]

            _amount = sum(values['amount'])
            debit = _amount
            credit = _ZERO
            lines_moves.append(
                self._prepare_line(
                    values['description'],
                    account_id,
                    debit=debit,
                    credit=credit,
                    party_to_pay_concept=party_payment,
                    analytic=values.get('analytic', None),
                    origin=origin_,
                    reference=reference_,
                    wage=values['wage'],
                    wages=wages,
                )
            )

        if result is not None:
            lines_moves.append(result)

        if lines_moves:
            lines_moves.append(
                self._prepare_line(
                    self.description,
                    self.account,
                    credit=sum(amount),
                    party_to_pay=self.party_to_pay,
                    wages=wages,
                )
            )
        return lines_moves, grouped

    def get_wage_analytic_account(self, line):
        pool = Pool()
        AnalyticAccount = pool.get('analytic_account.account')
        MandatoryWage = Pool().get('staff.payroll.mandatory_wage')
        analytic_account = []
        if line.wage.debit_account:
            analytic_required = line.wage.debit_account.analytical_management
            if analytic_required:
                if line.liquidation.origin:
                    analytic_code = line.liquidation.origin.analytic_account
                    analytic_account = AnalyticAccount.search(
                        ['code', '=', analytic_code]
                    )

                else:
                    employee = (
                        line.liquidation.employee
                        if line.liquidation.employee
                        else line.liquidation.contract.employee
                    )
                    mandatories = MandatoryWage.search(
                        ['employee', '=', employee])
                    if mandatories:
                        for mandatory in mandatories:
                            if (
                                mandatory.analytic_account
                                and mandatory.analytic_account.type == 'normal'
                            ):
                                analytic_account.append(
                                    mandatory.analytic_account)
                                break
                return analytic_account[0] if analytic_account else None
            else:
                return None
        else:
            return None

    def _prepare_line(
        self,
        description,
        account_id,
        debit=_ZERO,
        credit=_ZERO,
        party_to_pay=None,
        analytic=None,
        party_to_pay_concept=None,
        origin=None,
        reference=None,
        wage=None,
        wages=None
    ):
        party_id = None
        if debit < _ZERO:
            credit = debit
            debit = _ZERO
        elif credit < _ZERO:
            debit = credit
            credit = _ZERO

        credit = abs(credit)
        debit = abs(debit)

        if party_to_pay:
            party_id = self.party_to_pay.id
        if party_to_pay_concept:
            party_id = party_to_pay_concept

        if not party_id:
            party_id = self.get_party_liquidation_line(
                wage, wages)
        if not party_id:
            party_id = self.employee.party.id

        res = {
            'description': description,
            'debit': debit,
            'credit': credit,
            'account': account_id,
            'party': party_id,
            'origin': origin,
            'reference': reference,
        }

        if analytic and debit > 0:
            res['analytic_lines'] = [
                (
                    'create',
                    [
                        {
                            'debit': res['debit'],
                            'credit': res['credit'],
                            'account': analytic.id,
                            'date': self.liquidation_date,
                        }
                    ],
                )
            ]
        return res

    def get_party_liquidation_line(self, wage, mandatories):
        party = None
        if wage and mandatories:
            for mandatory in mandatories:
                if mandatory.wage_type == wage:
                    if mandatory.party:
                        party = mandatory.party
        return party

    def set_liquidation_lines(self):
        pool = Pool()
        Payroll = pool.get('staff.payroll')
        LiquidationMove = pool.get('staff.liquidation.line-move.line')

        if not self.contract:
            message = ("""Debe seleccionar el contrato""")
            clean_message = re.sub(r'\s+', ' ', message).strip()
            raise UserError('Error', clean_message)

        date_start, date_end = self._get_dates_liquidation()
        payrolls = Payroll.search(
            [
                ('employee', '=', self.employee.id),
                ('start', '>=', date_start),
                ('end', '<=', date_end),
                ('contract', '=', self.contract.id),
                ('state', '=', 'posted'),
            ]
        )
        wages = {}
        wages_target = {}

        for payroll in payrolls:
            mandatory_wages = [
                i.wage_type for i in payroll.employee.mandatory_wages]
            for l in payroll.lines:
                if not l.wage_type.contract_finish:
                    continue
                if self.kind == 'contract':
                    if l.wage_type.type_concept not in CONTRACT:
                        continue
                elif self.kind != l.wage_type.type_concept:
                    continue

                if (
                    l.wage_type.id not in wages_target.keys()
                    and l.wage_type in mandatory_wages
                ):
                    mlines = self.get_moves_lines_pending(
                        payroll.employee, l.wage_type, date_end)
                    if not mlines:
                        continue
                    wages_target[l.wage_type.id] = [
                        l.wage_type.credit_account.id,
                        mlines,
                        l.wage_type,
                    ]

        if not payrolls:
            if self.kind == 'bonus_service':
                wages_ = [
                    mw for mw in self.employee.mandatory_wages
                    if mw.wage_type.type_concept == 'bonus_service'
                ]
                if wages_:
                    wage = wages_[0]
                    lines = self.get_moves_lines_pending(
                        self.employee, wage.wage_type, self.end,
                    )
                    if lines:
                        wages_target[wage.wage_type.id] = [
                            wage.wage_type.credit_account.id,
                            lines,
                            wage.wage_type,
                        ]

        # Get days by current liquidation period
        date_start, date_end = self._get_dates()

        for account_id, lines, wage_type in wages_target.values():
            values = []
            lines_to_reconcile = []
            days = self.time_contracting
            if self.kind == 'contract':
                days = self.get_days_line_liquidation(
                    date_start, date_end, self.contract, wage_type)
                if days == 0:
                    days = self.contract.get_time_days_contract(
                        date_start, date_end)
            for line in lines:
                _line = LiquidationMove.search([('move_line', '=', line.id)])
                if not _line:
                    values.append(abs(line.debit - line.credit))
                    lines_to_reconcile.append(line.id)
            value = self.get_line_(
                wage=wage_type,
                amount=sum(values),
                days=days,
                account_id=account_id,
                party=self.party_to_pay,
            )

            value.update(
                {
                    'move_lines': [('add', lines_to_reconcile)],
                }
            )
            wages[wage_type.id] = value

        self.write([self], {'lines': [('create', wages.values())]})
        self.lines = self.validate_liquidation_line_values(
            self.lines, self.contract, self.kind)
        self.save()
        if self.kind == 'contract':
            self.process_loans_to_pay()
        if self.kind == 'holidays':
            self.process_loans_to_pay_holidays()

    def validate_liquidation_line_values(self, lines, contract, kind):
        pool = Pool()
        WageType = pool.get('staff.wage_type')
        Adjustment = Pool().get('staff.liquidation.line_adjustment')
        for line in lines:
            wage = WageType(line.wage)
            concept_electronic = wage.type_concept_electronic
            concept = wage.type_concept
            if ((concept_electronic == 'Cesantias'
                or concept_electronic == 'PrimasS'
                or concept_electronic == 'IntCesantias')
                    or (kind != 'holidays' and concept == 'holidays')):
                line_amount = self.get_salary_prom(contract, line, kind)

                if line.amount != line_amount:
                    add_amount = round(line_amount - line.amount, 2)
                    if add_amount != 0:
                        line.adjustments = [Adjustment(
                                account=wage.debit_account.id,
                                amount=add_amount,
                                description=f"AJUSTE {line.description}")]
                        line.amount += add_amount
                        line.save()
        return lines

    def get_salary_prom(self, contract, line_, kind):
        pool = Pool()
        Payroll = pool.get('staff.payroll')
        employee = contract.employee
        transport_bonus = contract.transport_bonus if contract.transport_bonus else 0
        total_base_salary = 0
        total_base_extras = 0

        if (line_.wage.type_concept_electronic == 'PrimasS'
                and kind == 'unemployment'):
            if not self.payment_liquidation_date:
                message = (
                    """Debe proporcionar la fecha de pago de la liquidacion""")
                clean_message = re.sub(r'\s+', ' ', message).strip()
                raise UserError('Error', clean_message)

        domain = [('employee', '=', employee), ('contract', '=', contract)]
        if (kind == 'contract' or kind == 'unemployment'
                or kind == 'bonus_service' or kind == 'interest'):
            start_period = self.start_period.start
            end_period = self.end_period.end
            end_year_period = end_period.year
            start_year_period = start_period.year
            if ((line_.wage.type_concept_electronic == 'PrimasS')
                    and end_year_period == start_year_period):
                if start_period.month != end_period.month:
                    if end_period.month > 6:
                        start_period = datetime(start_period.year, 7, 1)
            elif (line_.wage.type_concept_electronic == 'PrimasS'
                    and end_year_period != start_year_period):
                start_period = date(end_year_period, 1, 1)
                end_period = contract.end_date
            work_days = self.get_work_days_line_liquidation(
                start_period, end_period, contract, line_.wage)
            domain.append(('end', '>=', start_period))
            domain.append(('end', '<=', end_period))

        payrolls = Payroll.search(domain, order=[('id', 'ASC')])

        if work_days == 0 and kind == 'contract':
            message = ("""No se encontraron dias laborados para el periodo, 
                       revise si esta proporcionando la fecha de finalizacion
                       del contrato""")
            clean_message = re.sub(r'\s+', ' ', message).strip()
            raise UserError('Error', clean_message)
        payrolls = Payroll.search(domain, order=[('id', 'ASC')])
        # extras, recargos, bonificaciones y comisiones
        for payroll in payrolls:
            payroll_value = 0

            if not payroll.payment_extras and not payroll_value:
                salary = self.get_salary_base(
                        contract, payroll, end_period)
                salary_daily = salary / 30
                payroll_value = salary_daily * payroll.worked_days

            for line in payroll.lines:
                concept = line.wage_type.type_concept
                concept_electronic = line.wage_type.type_concept_electronic
                salary = 0
                if line_.wage.type_concept != 'holidays':
                    if concept == 'extras':
                        total_base_extras += (line.quantity * line.unit_value)
                    if concept_electronic == 'BonificacionS':
                        total_base_extras += (line.quantity * line.unit_value)
                    if concept_electronic == 'Comision':
                        total_base_extras += (line.quantity * line.unit_value)
            total_base_salary += payroll_value
        percentage_factor = round(Decimal(work_days / 30), 6)

        # Calculo de extras nocturnas
        if line_.wage.type_concept == 'holidays':
            start_period_ = start_period - timedelta(days=365)
            domain = [('employee', '=', employee), ('contract', '=', contract),
                      ('end', '>=', start_period_), ('end', '<=', end_period)]
            payrolls = Payroll.search(domain, order=[('id', 'ASC')])
            for payroll in payrolls:
                for line in payroll.lines:
                    concept_electronic = line.wage_type.type_concept_electronic
                    if concept_electronic == 'HRN':
                        total_base_extras += (line.quantity
                                              * line.unit_value)

        if (line_.wage.type_concept_electronic == 'PrimasS'
                and kind == 'unemployment'):
            if start_period.month != end_period.month:
                day_liquidation_payments = self.payment_liquidation_date.day
                if day_liquidation_payments >= 15:
                    total_base_salary += contract.salary / 2
                else:
                    total_base_salary += contract.salary
        if line_.wage.type_concept == 'holidays':
            days = self.get_days_line_liquidation(
                start_period, end_period, contract, line_.wage)
            total_base_salary = contract.salary
            total_base = round(Decimal(total_base_extras
                               / work_days * 30) + total_base_salary, 2)
            salary_prom = round((total_base / 30) * days, 2)
        else:
            total_base = round(total_base_salary + total_base_extras, 2)
            salary_prom = (total_base / percentage_factor) + transport_bonus

        if line_.wage.type_concept_electronic == 'Cesantias':
            salary_prom = (salary_prom * line_.days) / 360
        if line_.wage.type_concept_electronic == 'PrimasS':
            salary_prom = (salary_prom * work_days) / 360
        if line_.wage.type_concept_electronic == 'IntCesantias':
            val_cesantias = (salary_prom * line_.days) / 360
            salary_prom = ((val_cesantias * Decimal('0.12'))
                          / 360) * line_.days
        return salary_prom

    def get_work_days_line_liquidation(self, start_period, end_period,
            contract, wage):
        work_days = 0
        start_date = None
        end_date = None
        date_end_year = end_period.year
        date_start_year = start_period.year
        first_of_july = date(date_end_year, 7, 1)
        start_date_contract = contract.start_date

        if wage.type_concept_electronic == 'PrimasS':
            if ((end_period > first_of_july)
                    and date_end_year == date_start_year):
                start_date = first_of_july if first_of_july > contract.start_date else contract.start_date
                if contract.end_date:
                    end_date = contract.end_date if contract.end_date < end_period else end_period
                else:
                    end_date = end_period

            elif date_start_year != date_end_year:
                start_date = date(date_end_year, 1, 1)
                end_date = contract.end_date
            elif ((end_period < first_of_july)
                  and (start_date_contract > start_period)):
                start_date = start_date_contract
                end_date = contract.end_date if contract.end_date else end_period
            elif ((end_period < first_of_july)
                  and (start_date_contract < start_period)):
                start_date = start_period
                end_date = contract.end_date if contract.end_date else end_period
            else:
                start_date = start_period
                end_date = end_period
        else:
            start_date = start_period if start_period > contract.start_date else contract.start_date
            end_date = contract.end_date if contract.end_date else end_period
        work_days = contract.get_time_days_contract(start_date, end_date)
        return work_days

    def get_days_line_liquidation(self, start_period, end_period,
            contract, wage):
        days = 0
        start_date = None
        end_date = None
        date_end_year = end_period.year
        date_start_year = start_period.year
        first_of_july = date(date_end_year, 7, 1)

        if (self.kind != 'holidays'
                and wage.type_concept == 'holidays'):
            days = round((Decimal(15 / 360) * contract.time_worked)
                         - contract.days_enjoy, 12)
            return days
        elif wage.type_concept_electronic == 'PrimasS':
            if ((end_period > first_of_july)
                    and date_end_year == date_start_year):
                start_date = first_of_july if first_of_july > contract.start_date else contract.start_date
                end_date = contract.end_date
            elif date_start_year != date_end_year:
                start_date = date(date_end_year, 1, 1)
                end_date = contract.end_date
            else:
                start_date = start_period
                end_date = end_period
        else:
            start_date = start_period if start_period > contract.start_date else contract.start_date
            end_date = contract.end_date
        days = contract.get_time_days_contract(start_date, end_date)
        return days

    def get_salary_base(self, contract, payroll, end_period):
        pool = Pool()
        Futhermore = pool.get('staff.contract.futhermore')
        validate_futhermore_ = self.validate_futhermore(end_period, contract)

        if not validate_futhermore_:
            salary = contract.salary
        else:
            futhermore = Futhermore.search(
                [('contract', '=', contract.id),
                ('futhermore_date', '<=', payroll.date_effective)],
                order=[('futhermore_date', 'DESC')],
                limit=1
                )
            if not futhermore:
                message = (f"""Falta informacion de 'Otro si' para el empleado
                                {contract.employee.party.name}""")
                clean_message = re.sub(r'\s+', ' ', message).strip()
                raise UserError('Error', clean_message)

            if futhermore:
                salary = futhermore[0].salary
        return salary

    def validate_futhermore(self, end_period, contract):
        pool = Pool()
        Futhermore = pool.get('staff.contract.futhermore')

        futhermore_validate = Futhermore.search(
            [('contract', '=', contract.id), ('state', '=', 'confirmed'),
                ('futhermore_date', '<=', end_period)],
            order=[('futhermore_date', 'DESC')],
            limit=1
            )

        if futhermore_validate:
            futhermore_date = futhermore_validate[0].futhermore_date
            if isinstance(end_period, str):
                end_period = datetime.strptime(end_period, '%Y-%m-%d')
            if isinstance(futhermore_date, str):
                futhermore_date = datetime.strptime(
                    futhermore_date, '%Y-%m-%d')

            three_months_ago = end_period - timedelta(days=3 * 30)

            if futhermore_date > three_months_ago:
                return True
            return False

    def process_loans_to_pay_holidays(self):
        pool = Pool()
        MoveLine = pool.get('account.move.line')
        LoanLine = pool.get('staff.loan.line')
        LiquidationLine = pool.get('staff.liquidation.line')
        dom = [
            ('loan.wage_type', '!=', None),
            ('loan.party', '=', self.employee.party.id),
            ('state', 'in', ['pending', 'partial']),
            ('loan.wage_type.pay_liqudation', '=', True),
            ('maturity_date', '>=', self.start_period.start),
            ('maturity_date', '<=', self.end_period.end),
        ]

        lines_loan = LoanLine.search(dom)
        for loan in lines_loan:

            move_lines = MoveLine.search(
                [
                    ('origin', 'in', ['staff.loan.line,' + str(loan)]),
                ]
            )
            party = loan.loan.party_to_pay.id if loan.loan.party_to_pay else None
            res = self.get_line_(
                loan.loan.wage_type,
                loan.amount * -1,
                1,
                loan.loan.account_debit.id,
                party=party,
            )
            res['origin'] = loan
            res['move_lines'] = [('add', move_lines)]
            res['liquidation'] = self.id
            (line_,) = LiquidationLine.create([res])
            loan.amount = abs(loan.amount * -1)
            loan.save()
            LoanLine.write([loan], {'state': 'paid', 'origin': line_})

    @fields.depends('start_period', 'end_period', 'contract', 'kind')
    def on_change_with_time_contracting(self):
        delta = None

        if self.start_period and self.end_period and self.contract:
            try:
                date_start, date_end = self._get_dates()
                if self.kind == 'contract':
                    date_start = self.contract.start_date
                delta = self.contract.get_time_days_contract(
                    date_start, date_end)
            except Exception as error:
                raise UserError('Error', f'{self.employee.party.name} {error}')
        return delta

    @classmethod
    def create_withholding(cls, liquidation):
        rec = liquidation
        pool = Pool()
        UvtWithholding = pool.get('staff.payroll.uvt_withholding')
        WageType = pool.get('staff.wage_type')
        fields_names = [
            'unit_price_formula', 'concepts_salary', 'salary_constitute',
            'name', 'sequence', 'definition', 'unit_price_formula',
            'expense_formula', 'uom', 'default_quantity', 'type_concept',
            'salary_constitute', 'receipt', 'concepts_salary',
            'contract_finish', 'limit_days', 'month_application',
            'minimal_amount', 'adjust_days_worked', 'round_amounts',
            'debit_account.name', 'credit_account.name',
            'deduction_account.name', 'account_60_40.name',
        ]
        wage_tax = WageType.search_read([('type_concept', '=', 'tax')],
            fields_names=fields_names)
        if not wage_tax:
            return

        wage_tax = wage_tax[0]
        deductions_month = sum([
            ln.amount for ln in rec.lines if ln.wage.definition != 'payment'
        ])
        salary_full = rec.net_payment
        payrolls = {p.end: p for p in rec.payrolls}
        if not payrolls:
            return
        max_date = max(payrolls.keys())
        if rec.liquidation_date.month == max_date.month:
            payroll = payrolls[max_date]
            line_tax = None
            for line in payroll.lines:
                if line.wage_type.type_concept == 'tax' and line.amount:
                    line_tax = line
            if not line_tax:
                deductions_month += payroll.get_deductions_month()
                salary_args = payroll.get_salary_full_(wage_tax)
                salary_full += salary_args['salary']

        base_salary_withholding = salary_full - deductions_month
        amount_tax = UvtWithholding.compute_withholding(
            base_salary_withholding)
        amount_tax = rec.currency.round(Decimal(amount_tax))

        date_start, date_end = rec._get_dates()
        delta = rec.contract.get_time_days_contract(
                    date_start, date_end)
        if amount_tax:
            create_tax = {
                'sequence': wage_tax['sequence'],
                'wage': wage_tax['id'],
                'description': wage_tax['name'],
                'amount': amount_tax * -1,
                'days': delta,
                'account': wage_tax['credit_account.']['id'],
            }
            cls.write([rec], {
                'lines': [('create', [create_tax])],
            })


class LiquidationLine(AnalyticMixin, metaclass=PoolMeta):
    __name__ = 'staff.liquidation.line'
    origin = fields.Reference('Origin', selection='get_origin')

    @classmethod
    def __setup__(cls):
        super(LiquidationLine, cls).__setup__()
        cls.analytic_accounts.domain = [
            (
                'company',
                '=',
                If(
                    ~Eval('_parent_liquidation'),
                    Eval('context', {}).get('company', -1),
                    Eval('_parent_liquidation', {}).get('company', -1),
                ),
            ),
        ]

    @classmethod
    def _get_origin(cls):
        'Return list of Model names for origin Reference'
        return ['staff.loan.line', 'staff.event']

    @classmethod
    def get_origin(cls):
        Model = Pool().get('ir.model')
        get_name = Model.get_name
        models = cls._get_origin()
        return [(None, '')] + [(m, get_name(m)) for m in models]

    def get_analytic_lines(self, account, line, date):
        'Yield analytic lines for the accounting line and the date'
        lines = []
        amount = line['debit'] or line['credit']
        for account, amount in account.distribute(amount):
            analytic_line = {}
            analytic_line['debit'] = amount if line['debit'] else Decimal(0)
            analytic_line['credit'] = amount if line['credit'] else Decimal(0)
            analytic_line['account'] = account
            analytic_line['date'] = date
            lines.append(analytic_line)
        return lines

    def _get_entry(self, line_move):
        if self.analytic_accounts:
            to_create = []
            for entry in self.analytic_accounts:
                if not entry.account:
                    continue
                # Just debits must to create entries, credits not
                if not entry.account or line_move['debit'] == 0:
                    continue
                to_create.extend(
                    self.get_analytic_lines(
                        entry.account, line_move, self.liquidation.liquidation_date
                    )
                )
            if to_create:
                line_move['analytic_lines'] = [('create', to_create)]
        return line_move

    def get_move_line(self, lines):
        lines_ = []
        for line in lines:
            line_ = self._get_entry(line)
            lines_.append(line_)
        return lines_


class LiquidationReport(metaclass=PoolMeta):
    __name__ = 'staff.liquidation.report'

    @classmethod
    def get_context(cls, records, header, data):
        report_context = super().get_context(records, header, data)
        pool = Pool()
        Event = pool.get('staff.event-staff.liquidation')
        total_days_holidays = 0
        total_salaries = 0
        licenseNR = 0

        for record in records:
            start_date = record.start_period.name
            end_date = record.end_period.name
            if record.kind == 'holidays':
                for liq_line in record.lines:
                    if (
                        liq_line.wage.type_concept == 'holidays'
                        and liq_line.wage.type_concept_electronic
                        in ('VacacionesComunes', 'VacacionesCompensadas')
                    ):
                        event = Event.search(
                            [('staff_liquidation', '=', liq_line.liquidation.id)]
                        )
                        if event:
                            start_date = event[0].event.start_date
                            end_date = event[0].event.end_date
                        total_days_holidays += liq_line.days
                    if (
                        liq_line.wage.type_concept == 'salary'
                        and liq_line.wage.type_concept_electronic == 'Basico'
                    ):
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


class MoveProvisionBonusService(metaclass=PoolMeta):
    'Move Provision Bonus Service'
    __name__ = 'staff.move_provision_bonus_service'

    def transition_open_(self):
        try:
            pool = Pool()
            Contract = pool.get('staff.contract')
            Move = pool.get('account.move')
            AccountPeriod = pool.get('account.period')
            configuration = Pool().get('staff.configuration')(1)
            journal_id = None
            date_today = datetime.today().date()
            if configuration and configuration.default_journal:
                journal_id = configuration.default_journal.id
            _end_date = self.start.period.end
            _company = self.start.company
            provision_wage = self.start.wage_type
            period_days = (self.start.period.end
                           - self.start.period.start).days + 1

            dom_contract = [('OR', [
                ('end_date', '>', self.start.period.start),
            ], [
                ('end_date', '=', None),
            ]),
                ('employee.contracting_state', '=', 'active'),
                ('kind', '!=', 'learning')
            ]

            if self.start.category:
                dom_contract.append(
                    ('employee.category', '=', self.start.category.id))

            for contract in Contract.search(dom_contract):
                try:
                    move_lines = []
                    analytic_account = None
                    salary_amount = contract.get_salary_in_date(_end_date)
                    period_in_month = 1 if period_days > 15 else 2
                    employee = contract.employee
                    base_ = salary_amount

                    for concept in contract.employee.mandatory_wages:
                        if concept.wage_type.debit_account:
                            debit_account_ = provision_wage.debit_account
                            if (
                                debit_account_.analytical_management
                                and analytic_account is None
                                and concept.analytic_account
                                and concept.analytic_account.type == 'normal'
                            ):
                                analytic_account = concept.analytic_account
                        if concept.wage_type and concept.wage_type.salary_constitute:
                            if concept.wage_type.type_concept == 'transport':
                                base_ += (
                                    concept.wage_type.compute_unit_price(
                                        {'salary': 0})
                                    * concept.wage_type.default_quantity
                                ) * 2
                            if concept.fix_amount:
                                base_ += concept.fix_amount

                    period_id = AccountPeriod.find(_company.id, date=_end_date)

                    provision_amount = provision_wage.compute_unit_price(
                        {'salary': (round((base_ / period_in_month), 2))}
                    )

                    base_lines = [
                        {
                            'debit': provision_amount,
                            'credit': 0,
                            'party': employee.party.id,
                            'account': provision_wage.debit_account.id,
                        },
                        {
                            'debit': 0,
                            'credit': provision_amount,
                            'party': employee.party.id,
                            'account': provision_wage.credit_account.id,
                        },
                    ]

                    if analytic_account:
                        base_lines[0]['analytic_lines'] = [
                            (
                                'create',
                                [
                                    {
                                        'debit': provision_amount,
                                        'credit': 0,
                                        'account': analytic_account,
                                        'date': date_today,
                                    }
                                ],
                            )
                        ]
                    move_lines.extend(base_lines)
                    move_lines = self.get_move_lines_distribution(
                        move_lines)
                    move_description = f"{self.start.description}-{employee.party.name}"
                    move, = Move.create([{
                        'journal': journal_id,
                        'period': period_id,
                        'company': _company.id,
                        'date': _end_date,
                        'state': 'draft',
                        'description': move_description,
                        'lines': [('create', move_lines)],
                    }])
                    move.save()
                except Exception as error:
                    raise UserError(f'Error: {str(error)}')
        except Exception as error:
            raise UserError(f'Error: {str(error)}')

        return 'end'

    def get_move_lines_distribution(self, lines):
        lines_ = []
        for line in lines:
            line_ = self._get_entry(line)
            lines_.append(line_)
        return lines_

    def get_analytic_lines(self, account, line, date):
        'Yield analytic lines for the accounting line and the date'
        lines = []
        amount = line['debit'] or line['credit']
        for account, amount in account.distribute(amount):
            analytic_line = {}
            analytic_line['debit'] = amount if line['debit'] else Decimal(0)
            analytic_line['credit'] = amount if line['credit'] else Decimal(0)
            analytic_line['account'] = account
            analytic_line['date'] = date
            lines.append(analytic_line)
        return lines

    def _get_entry(self, line_move):
        pool = Pool()
        Employee = pool.get('company.employee')
        party = line_move['party']
        analytic_account = None
        if line_move['debit'] > 0:
            if party:
                employee = Employee.search(['party', '=', party])
                if employee:
                    mandatories = employee[0].mandatory_wages
                    if mandatories:
                        analytic_account = mandatories[0].analytic_account

            if (analytic_account
                    and analytic_account.type == "distribution"):
                to_create = []
                date = datetime.now().date()
                to_create.extend(
                    self.get_analytic_lines(
                        analytic_account, line_move, date)
                )
                if to_create:
                    line_move['analytic_lines'] = [('create', to_create)]
        return line_move


class LiquidationGroup(metaclass=PoolMeta):
    "Liquidation Group"
    __name__ = 'staff.liquidation_group'

    def transition_open_(self):
        pool = Pool()
        Liquidation = pool.get('staff.liquidation')
        Contract = pool.get('staff.contract')
        Employee = pool.get('company.employee')
        Period = pool.get('staff.payroll.period')
        to_liquidation = []

        start_period = self.start.start_period.id
        end_period = self.start.end_period.id
        kind = self.start.kind
        liquidation_date = self.start.liquidation_date
        company_id = self.start.company.id
        description = self.start.description
        currency_id = self.start.company.currency.id
        account_id = self.start.account.id

        start_date = self.start.start_period.start
        end_date = self.start.end_period.end

        periods = Period.search([
                ('start', '>=', start_date),
                ('start', '<=', end_date),
                ])

        dom_contracts = [('kind', '=', kind)]
        if self.start.employees:
            employees = self.start.employees
            employee_ids = [e.id for e in employees]
            dom_contracts.append(('employee', 'in', employee_ids))
        else:
            employees = Employee.search([('contract', '!=', None)])

        if periods:
            periods_ids = [p.id for p in periods]
            dom_contracts.append(('start_period', 'in', periods_ids))
            dom_contracts.append(('end_period', 'in', periods_ids))

        contracts = Liquidation.search_read(
            dom_contracts, fields_names=['contract'],
        )
        contract_ids = [i['contract'] for i in contracts]
        for employee in employees:
            contracts = Contract.search([
                ('employee', '=', employee.id),
                ('id', 'not in', contract_ids),
                ('state', '=', 'active'),
                ('kind', '!=', 'learning'),
            ])
            if not contracts:
                continue

            contract = contracts[0]

            if kind == 'unemployment':
                wages = [
                    mw for mw in employee.mandatory_wages
                    if mw.wage_type.type_concept == 'unemployment'
                ]
                if not wages:
                    continue
                wage = wages[0]
                lines = Liquidation.get_moves_lines_pending(
                    employee, wage.wage_type, self.start.end_period.end,
                )
                if not lines:
                    continue

            lqt_create = {
                'start_period': start_period,
                'end_period': end_period,
                'employee': employee.id,
                'contract': contract.id,
                'kind': kind,
                'liquidation_date': liquidation_date,
                'time_contracting': None,
                'state': 'draft',
                'company': company_id,
                'description': description,
                'currency': currency_id,
                'account': account_id,
                'party_to_pay': self.start.party_to_pay.id if self.start.party_to_pay else None,
            }
            liq, = Liquidation.create([lqt_create])
            liq.time_contracting = liq.on_change_with_time_contracting()
            liq.save()
            to_liquidation.append(liq)

        Liquidation.compute_liquidation(to_liquidation)
        return 'end'
