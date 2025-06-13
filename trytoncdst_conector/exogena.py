from datetime import date, datetime
from decimal import Decimal

from trytond.exceptions import UserError
from trytond.i18n import gettext
from trytond.pool import Pool, PoolMeta
from trytond.report import Report
from trytond.model import fields
from trytond.transaction import Transaction
from collections import defaultdict, namedtuple

_ZERO = Decimal(0)
DEFINITIONS = {
    '': {},
    '1001': {
        '1001_pagoded': 'Pago Deducible',
        '1001_pagonoded': 'Pago No Deducible',
        '1001_ivaded': 'IVA Deducible',
        '1001_ivanoded': 'IVA No Deducible',
        '1001_retprac': 'Retenciones Practicadas',
        '1001_retasum': 'Retenciones Asumidas',
        '1001_retpracivarc': 'Retenfte Pract. IVA RC',
        '1001_retasumivars': 'Retenfte Pract. IVA RS',
        '1001_retpracivanodo': 'Retenfte Pract. IVA ND',
        '1001_retpracree': 'Retenfte Pract. CREE',
        '1001_retasumcree': 'Retenfte Asum. CREE',
    },
    '1003': {
        '1003_pagosujeret':
        'Valor acumulado del pago o abono sujeto a Retencion en la fuente.',
        '1003_retpract': 'Retencion que le Practicaron',
    },
    '1005': {
        '1005_impdescon': 'Impuesto Descontable.',
        '1005_ivadev': 'IVA resultante por devoluciones en ventas anuladas. rescindidas o resueltas',
        '1005_ivacosgas': 'IVA tratado como mayor valor del costo o gasto',
    },
    '1006': {
        '1006_impgen': 'Impuesto generado',
        '1006_ivarecup':
        'IVA recuperado en devoluciones en compras anuladas, rescindidas o resueltas',
        '1006_impoconsumo': 'Impuesto Consumo',
    },
    '1007': {
        '1007_ingbrutprop':
        'Ingresos brutos recibidos por operaciones propias.',
        '1007_ingbruconsorut':
        'Ingresos brutos a traves de Consorcio o Uniones Temporales',
        '1007_ingcontraadm':
        'Ingresos a traves de Contratos de mandato o administracion delegada',
        '1007_ingexplo':
        'Ingresos a traves de exploracion y explotacion de minerales',
        '1007_ingfidu': 'Ingresos a traves de fiducia',
        '1007_ingtercer': 'Ingresos recibidos a traves de terceros',
        '1007_ingdev': 'Devoluciones, rebajas y descuentos',
    },
    '1008': {
        '1008_saldocxc': 'Saldo cuentas por cobrar al 31-12.',
    },
    '1009': {
        '1009_saldocxp': 'Saldo cuentas por pagar al 31-12.',
    },
    '1010': {
        '1010_vlrnom': 'Valor Nominal de la Accion, Aporte o Derecho Social a 31 diciembre',
        '1010_vlrprim': 'Valor prima en colocacion de acciones a 31 diciembre',
        '1010_porpar': 'Porcentaje de participacion',
        '1010_porpardec': 'Porcentaje de participacion (posicion decimal)',
    },
    '1011': {
        '1011_saldo': 'Saldo cuentas al 31-12.',
    },
    '1012': {
        '1012_saldo': 'Saldo cuentas al 31-12.',
    },
    '1043': {
        '1043_pago_abono': 'Valor del pago o abono en cuenta',
        '1043_ivamayor_valor_costo': 'Iva mayor valor al costo',
        '1043_retencion_prac': 'Retención en la fuente practicada',
        '1043_retencion_asu': 'Valor de retención en la fuente asumida',
        '1043_reteiva_regcomun': 'Retención Iva practicada Régimen Común',
        '1043_retencion_regsim': 'Retención asumida Régimen Simplificado',
        '1043_retencion_asum_no_dom':
        'Retención en la fuente asumida No domicialiados',
        '1043_retencion_cree': 'Retención en la fuente practicadas CREE',
        '1043_retencion_cree_asum': 'Retención en la fuente asumidas CREE',
    },
    '1045': {
        '1045_ingresos_brutos_rec': 'Ingresos Brutos Recibidos',
        '1045_dev_rebajas': 'Devoluciones y rebajas',
    },
    '2015': {
        '2015_valor': 'Valor base la retencion',
        '2015_ret': 'Retencion',
    },
    '5247': {
        '5247_pago_abono':
        'Valor del pago o abono en cuenta',
        '5247_ivamayor_valor_costo':
        'Iva mayor valor al costo',
        '5247_retencion_prac':
        'Retención en la fuente practicada',
        '5247_retencion_asu':
        'Valor de retención en la fuente asumida',
        '5247_reteiva_regcomun':
        'Retención Iva practicada Régimen Común',
        '5247_retencion_asum_no_dom':
        'Retención en la fuente asumida No domicialiados',
    },
    '5248': {
        '5248_ingresos_brutos': 'Valor de ingresos brutos recibidos',
        '5248_dev_descuentos': 'Devoluciones, rebajas y descuentos',
    },
    '5249': {
        '5249_iva_descontable': 'Valor de Iva descontable',
        '5249_iva_devoluciones': 'Iva resultante por devoluciones aplicadas',
    },
    '5250': {
        '5250_iva_generado': 'Valor Ivan generado',
        '5250_iva_rec_devoluciones':
        'Iva recuperado en devoluciones Devoluciones',
        '5250_impuesto_consumo': 'Impuesto al consumo',
    },
    '5251': {
        '5251_saldo_anual': 'Saldo de cuentas a 31-12',
    },
    '5252': {
        '5252_saldo_anual': 'Saldo de cuentas a 31-12',
    },
    '2276': {}
}


class ExogenaConcepto(metaclass=PoolMeta):
    'Exogena Concepto'
    __name__ = 'account.exogena_concepto'

    @classmethod
    def get_report(cls):
        return [(str(d), str(d)) for d in DEFINITIONS]

    @fields.depends('report')
    def selection_definition(self):
        res = [('', '')]
        if self.report:
            res.extend(DEFINITIONS[self.report].items())
        return res


class ExogenaDefinitionAccountStart(metaclass=PoolMeta):
    'Exogena Definition Account Start'
    __name__ = 'account_exo.exogena_definition_account.start'

    @fields.depends('report')
    def selection_definition(self):
        res = []
        if self.report:
            res.extend(DEFINITIONS[self.report].items())
        return res


class PrintReportExogenaStart(metaclass=PoolMeta):
    'Print Report Exogena Start'
    __name__ = 'account_exo.print_report_exogena.start'

    @classmethod
    def __setup__(cls):
        super().__setup__()
        cls.report.domain = ['OR', ('module', '=', 'account_exo'),
                ('module', '=', 'conector')
        ]


class TemplateExogena(metaclass=PoolMeta):
    "0000 Template"
    __name__ = 'account.f0000'

    @classmethod
    def get_context(cls, records, header, data):
        """Function to build info to exogena"""

        pool = Pool()
        Configuration = pool.get('account.configuration')
        Concept = pool.get('account.exogena_concepto')
        Company = pool.get('company.company')
        Period = pool.get('account.period')
        Party = pool.get('party.party')
        Move = pool.get('account.move')
        Bank = pool.get('bank')

        lines_by_account = {}
        accounts_target = {}
        records_cuantia = {}
        concept_banks = {}
        records = {}
        parties = {}
        moves = {}

        concept_accounts = []
        line_ids = []
        party_cuantia = None

        lines_by_account = defaultdict(list)
        report_context = Report.get_context(records, header, data)
        configuration = Configuration(1)
        company = Company(1)
        party_cuantias = Party.search([('id_number', '=', '222222222')])
        if party_cuantias:
            party_cuantia = party_cuantias[0]

        report_number = cls.__name__[-4:]
        uvt = configuration.uvt
        if not uvt and report_number in ('1001', '1008', '1009'):
            raise UserError("ERROR", "Debe configurar el valor de la UVT en la compañia")

        definitions = DEFINITIONS[report_number].copy()
        start_period = Period(data['start_period'])
        end_period = Period(data['end_period'])
        data['start_date'] = start_period.start_date
        data['end_date'] = end_period.end_date

        concepts = Concept.search([
            ('report', '=', report_number),
            ('concept', '!=', ''),
            ('definition', '!=', ''),
        ], order=[('concept', 'DESC')])

        if not concepts:
            raise UserError("ERROR", "No se encontraron conceptos")

        for c in concepts:
            if not c.definition or not c.concept:
                raise UserError(
                    gettext('account_exo.msg_concept_empty', s=c.account.name))
            accounts_target[c.id] = {
                'definition': c.definition,
                'concept': c.concept,
                'dtp': c.distribute_to_peer,
                'rate_not_deducible': c.rate_not_deducible,
                'nature_account': c.nature_account,
                'exclude_reconciled': c.exclude_reconciled,
                'restar_debit_credit': c.restar_debit_credit,
            }
            if c.account and c.account not in concept_accounts:
                concept_accounts.append(c.account.id)
        banks = Bank.search([('account_expense', 'in', concept_accounts)])
        if banks:
            for bank in banks:
                concept_banks[bank.account_expense] = bank

        if report_number in ('1009', '1008'):
            periods = Period.search([
                ('start_date', '<=', end_period.start_date),
            ])
        else:
            periods = Period.search([
                ('fiscalyear', '=', data['fiscalyear']),
                ('start_date', '>=', start_period.start_date),
                ('start_date', '<=', end_period.start_date),
                ('type', '=', 'standard'),
            ])

        period_ids = [p.id for p in periods]

        # Obtener saldos iniciales 1012
        if report_number == '1012':
            accounts_concept_map = {c.account.id: c for c in concepts}
            accounts_ = list(accounts_concept_map.keys())
            result = cls.get_start_balances(accounts_, period_ids)
            if result:
                TotalTuple = namedtuple('LineTuple', ['id', 'account_id', 'party', 'debit', 'credit'])
                for row in result:
                    line = TotalTuple(*row)
                    lines_by_account[line.account_id].append(line)
                    line_ids.append(line.id)

        # Obtener saldos iniciales 1011
        if report_number == '1011':
            accounts_party_required = [c.account.id for c in concepts if c.account.party_required]
            accounts_party_not_required = [c.account.id for c in concepts if not c.account.party_required]
            result = cls.get_start_balances1011(accounts_party_required, period_ids, True)
            if result:
                TotalTuple = namedtuple('LineTuple', ['id', 'account_id', 'party', 'debit', 'credit'])
                for row in result:
                    line = TotalTuple(*row)
                    lines_by_account[line.account_id].append(line)
                    line_ids.append(line.id)
            result = cls.get_start_balances1011(accounts_party_not_required, period_ids, False)
            if result:
                TotalTuple = namedtuple('LineTuple', ['id', 'account_id', 'party', 'debit', 'credit'])
                for row in result:
                    line = TotalTuple(*row)
                    lines_by_account[line.account_id].append(line)
                    line_ids.append(line.id)

            result = cls.get_lines1011(accounts_party_not_required, period_ids, False)
            if result:
                LineTuple = namedtuple('LineTuple', ['id', 'account_id', 'party', 'debit', 'credit', 'move_id'])

                for row in result:
                    line = LineTuple(*row)
                    lines_by_account[line.account_id].append(line)
                    line_ids.append(line.id)

            result = cls.get_lines1011(accounts_party_required, period_ids, True)
            if result:
                LineTuple = namedtuple('LineTuple', ['id', 'account_id', 'party', 'debit', 'credit', 'move_id'])
                for row in result:
                    line = LineTuple(*row)
                    lines_by_account[line.account_id].append(line)
                    line_ids.append(line.id)

            # Preparar línea segura para SQL IN
            if len(line_ids) == 1:
                line_ids = f"({line_ids[0]})"
            else:
                line_ids = str(tuple(line_ids))

            # Obtener los impuestos asociados a las líneas de movimiento
            result_tax = cls.get_move_taxes(line_ids)
            lines_tax_map = {line_id: rate for line_id, _, rate in result_tax}
        else:
            # Obtener las lineas de movimiento para el reporte
            result = cls.get_lines(concepts, concept_banks, period_ids, report_number)
            if not result:
                raise UserError("No se encontraron lineas para este reporte")

            if result:
                # Usar namedtuple para mejorar legibilidad
                LineTuple = namedtuple('LineTuple', ['id', 'account_id', 'party', 'debit', 'credit', 'move_id'])

                for row in result:
                    line = LineTuple(*row)
                    lines_by_account[line.account_id].append(line)
                    line_ids.append(line.id)

                # Preparar línea segura para SQL IN
                if len(line_ids) == 1:
                    line_ids = f"({line_ids[0]})"
                else:
                    line_ids = str(tuple(line_ids))

                # Obtener los impuestos asociados a las líneas de movimiento
                result_tax = cls.get_move_taxes(line_ids)
                lines_tax_map = {line_id: rate for line_id, _, rate in result_tax}

        # Iterar por concepto y procesar solo las líneas de su cuenta
        for c in concepts:
            acc_id = c.account.id
            if acc_id not in lines_by_account:
                continue

            lines = lines_by_account[acc_id]
            concept_info = accounts_target.get(c.id, {})
            is_dtp = concept_info.get('dtp')
            definition = concept_info.get('definition')
            concept_exo = concept_info.get('concept')
            rate_not_deducible = concept_info.get('rate_not_deducible')
            nature_account = concept_info.get('nature_account')
            restar_debit_credit = concept_info.get('restar_debit_credit')

            for line in lines:
                if concept_banks and c.account in concept_banks:
                    party = concept_banks[c.account].party
                else:
                    if line.party not in parties.keys():
                        parties[line.party] = Party(line.party)
                    party = parties[line.party]

                if report_number == '1011':
                    party = company.party

                if not party.id:
                    continue

                # Configurar tercero nombre según tipo de persona
                if party.type_person != 'persona_natural':
                    party.first_name = party.second_name = party.first_family_name = party.second_family_name = None
                else:
                    party.name = None

                # Determinar valor base de impuesto si aplica
                base = 0
                tax_lines = lines_tax_map.get(line.id, [])
                if tax_lines:
                    amount_tax = line.debit if line.debit > 0 else line.credit
                    rate = tax_lines
                    if rate:
                        base = amount_tax / rate

                # Determinar valor según naturaleza
                if nature_account == 'debit':
                    if restar_debit_credit:
                        value = line.debit - line.credit
                    else:
                        if line.debit <= 0:
                            continue
                        value = line.debit
                elif nature_account == 'credit':
                    if restar_debit_credit:
                        value = line.credit - line.debit
                    else:
                        if line.credit <= 0:
                            continue
                        value = line.credit
                else:
                    value = line.debit - line.credit

                # Reasignar concepto si es DTP
                if is_dtp:
                    if line.move_id not in moves.keys():
                        moves[line.move_id] = Move(line.move_id)
                    move = moves[line.move_id]
                    for ml in move.lines:
                        if ml.account.id == line.account_id:
                            continue
                        if (ml.debit > _ZERO and line.debit > _ZERO) or (ml.credit > _ZERO and line.credit > _ZERO):
                            peer_info = accounts_target.get(ml.account.id)
                            if peer_info:
                                concept_exo = peer_info['concept']
                                break

                # Inicializar estructuras si es necesario
                definitions['base'] = 0
                records.setdefault(concept_exo, {})
                records[concept_exo].setdefault(party, {}.fromkeys(definitions.keys(), Decimal(0)))

                if party_cuantia:
                    records_cuantia.setdefault(concept_exo, {})

                # Ajustes por no deducible
                if rate_not_deducible and report_number == '1001':
                    deducible = value * (100 - rate_not_deducible) / 100
                    not_deducible = value - deducible
                    if 'iva' in definition:
                        definition_not_ded = '1001_ivanoded'
                    else:
                        definition_not_ded = '1001_pagonoded'
                    records[concept_exo][party][definition_not_ded] += not_deducible
                    value = deducible

                records[concept_exo][party][definition] += value
                if base != 0:
                    records[concept_exo][party]['base'] += abs(base)

        if not records:
            raise UserError('No se encontraron registros para este reporte')

        if party_cuantia and (
                report_number == '1001' or report_number == '1007'
                or report_number == '1008' or report_number == '1009'):
            records = cls.update_cuantia_data(records.items(),
                                              party_cuantia,
                                              records_cuantia,
                                              definitions,
                                              report_number,
                                              concepts)
        for concept in records:
            for party in records[concept]:
                for key in records[concept][party]:
                    records[concept][party][key] = round(records[concept][party][key])

        report_context['records'] = records.items()
        return report_context

    @classmethod
    def get_lines(cls, concepts, concept_banks, period_ids, report_number=None):
        cursor = Transaction().connection.cursor()
        accounts_concept_map = {c.account.id: c for c in concepts}
        accounts_with_banks = set(c.account.id for c in concepts if concept_banks and c.account in concept_banks)
        accounts_ = list(accounts_concept_map.keys())

        if accounts_with_banks:
            query = """SELECT ml.id, ml.account, ml.party, ml.debit, ml.credit, ml.move
                FROM account_move_line AS ml
                JOIN account_move AS m ON ml.move=m.id
                WHERE ml.account = ANY(%s)
                AND m.period = ANY(%s)"""
        else:
            query = """SELECT ml.id, ml.account, ml.party, ml.debit, ml.credit, ml.move
                FROM account_move_line AS ml
                JOIN account_move AS m ON ml.move=m.id
                WHERE ml.account = ANY(%s)
                AND m.period = ANY(%s)
                AND ml.party IS NOT NULL"""
        cursor.execute(query, (accounts_, period_ids))
        return cursor.fetchall()

    @classmethod
    def get_lines1011(cls, accounts, period_ids, party_required):
        cursor = Transaction().connection.cursor()

        if party_required:
            query = """SELECT ml.id, ml.account, ml.party, ml.debit, ml.credit, ml.move
                FROM account_move_line AS ml
                JOIN account_move AS m ON ml.move=m.id
                WHERE ml.account = ANY(%s)
                AND m.period = ANY(%s)
                AND ml.party IS NOT NULL"""
        else:
            query = """SELECT ml.id, ml.account, ml.party, ml.debit, ml.credit, ml.move
                FROM account_move_line AS ml
                JOIN account_move AS m ON ml.move=m.id
                WHERE ml.account = ANY(%s)
                AND m.period = ANY(%s)"""
        cursor.execute(query, (accounts, period_ids))
        return cursor.fetchall()

    @classmethod
    def get_start_balances(cls, accounts, period_ids):
        cursor = Transaction().connection.cursor()
        first_period = min(period_ids)
        query = """SELECT ml.id, ml.account, ml.party, SUM(ml.debit) AS total_debit, SUM(ml.credit) AS total_credit
            FROM account_move_line AS ml
            JOIN account_move AS m ON ml.move = m.id
            WHERE ml.account = ANY(%s)
            AND m.period < %s
            GROUP BY ml.id, ml.account, ml.party"""
        cursor.execute(query, (accounts, first_period))
        return cursor.fetchall()

    @classmethod
    def get_start_balances1011(cls, accounts, period_ids, party_required):
        cursor = Transaction().connection.cursor()
        first_period = min(period_ids)
        if party_required:
            query = """SELECT ml.id, ml.account, ml.party, SUM(ml.debit) AS total_debit, SUM(ml.credit) AS total_credit
                FROM account_move_line AS ml
                JOIN account_move AS m ON ml.move = m.id
                WHERE ml.account = ANY(%s)
                AND m.period < %s
                AND ml.party IS NOT NULL
                GROUP BY ml.id, ml.account, ml.party"""
        else:
            query = """SELECT ml.id, ml.account, ml.party, SUM(ml.debit) AS total_debit, SUM(ml.credit) AS total_credit
                FROM account_move_line AS ml
                JOIN account_move AS m ON ml.move = m.id
                WHERE ml.account = ANY(%s)
                AND m.period < %s
                GROUP BY ml.id, ml.account, ml.party"""
        cursor.execute(query, (accounts, first_period))
        return cursor.fetchall()

    @classmethod
    def get_move_taxes(cls, line_ids):
        cursor = Transaction().connection.cursor()
        query_tax = f"""
            SELECT t.move_line, t.tax, ct.rate
            FROM account_tax_line AS t
            JOIN account_tax AS ct ON t.tax = ct.id
            WHERE t.move_line IN {line_ids}
        """
        cursor.execute(query_tax)
        return cursor.fetchall()

    @classmethod
    def update_cuantia_data(cls, records, party_cuantia, records_cuantia,
                            definitions, report, concepts):

        if report == "1001":
            records_cuantia_ = cls.get_records_1001(records, party_cuantia,
                                                   records_cuantia,
                                                   definitions,
                                                   concepts)
        if report == "1007":
            records_cuantia_ = cls.get_records_1007(records, party_cuantia,
                                                   records_cuantia,
                                                   definitions)
        if report == "1008":
            records_cuantia_ = cls.get_records_1008(records, party_cuantia,
                                                   records_cuantia,
                                                   definitions)
        if report == "1009":
            records_cuantia_ = cls.get_records_1009(records, party_cuantia,
                                                   records_cuantia,
                                                   definitions)
        return records_cuantia_

    @classmethod
    def get_records_1001(cls, records, party_cuantia, records_cuantia, definitions, concepts):
        """Function to update data of exogena 1001"""

        pool = Pool()
        Configuration = pool.get('account.configuration')
        configuration = Configuration(1)
        uvt = configuration.uvt
        uvt_limit = uvt * 3

        for concept, parties in records:
            if concept == '0000':
                for party, values in parties.items():
                    # Valores mayores que cero
                    if values["1001_pagoded"] >= 0 and values["1001_pagonoded"] >= 0:
                        # Valores menores a 3 UVT
                        if (values["1001_pagoded"] < uvt_limit) and (values["1001_pagonoded"] < uvt_limit):
                            if (values["1001_ivaded"] > 0
                                    or values["1001_ivanoded"] > 0):
                                if party not in records_cuantia[concept]:
                                    records_cuantia[concept].setdefault(
                                        party,
                                        {}.fromkeys(definitions.keys(), Decimal(0)),
                                    )
                                for key, value in values.items():
                                    records_cuantia[concept][party][key] += value

        for concept, parties in records:
            for party, values in parties.items():
                # Valores mayores que cero
                if values["1001_pagoded"] >= 0 and values["1001_pagonoded"] >= 0:
                    # Valores menores a 3 UVT
                    if (values["1001_pagoded"] < uvt_limit) and (values["1001_pagonoded"] < uvt_limit):
                        if values["1001_pagoded"] > 0 or values["1001_pagonoded"] > 0:

                            if party not in records_cuantia['0000']:
                                if party_cuantia not in records_cuantia[concept]:
                                    records_cuantia[concept].setdefault(
                                        party_cuantia,
                                        {}.fromkeys(definitions.keys(), Decimal(0)),
                                    )
                                for key, value in values.items():
                                    records_cuantia[concept][party_cuantia][key] += value
                                continue

                            if records_cuantia['0000'][party]['1001_ivanoded'] > 0:
                                if party not in records_cuantia[concept]:
                                    records_cuantia[concept].setdefault(
                                        party,
                                        {}.fromkeys(definitions.keys(), Decimal(0)),
                                    )
                                for key, value in values.items():
                                    records_cuantia[concept][party][key] += value
                            else:
                                if party_cuantia not in records_cuantia[concept]:
                                    records_cuantia[concept].setdefault(
                                        party_cuantia,
                                        {}.fromkeys(definitions.keys(), Decimal(0)),
                                    )
                                for key, value in values.items():
                                    records_cuantia[concept][party_cuantia][key] += value
                        elif (values["1001_ivaded"] > 0
                              or values["1001_ivanoded"] > 0
                              or values["1001_retprac"] > 0
                              or values["1001_retasum"] > 0
                              or values["1001_retpracivarc"] > 0
                              or values["1001_retasumivars"] > 0
                              or values["1001_retpracivanodo"] > 0
                              or values["1001_retpracree"] > 0
                                or values["1001_retasumcree"] > 0) and concept != '0000':
                            if party not in records_cuantia[concept]:
                                records_cuantia[concept].setdefault(
                                    party,
                                    {}.fromkeys(definitions.keys(), Decimal(0)),
                                )
                            for key, value in values.items():
                                records_cuantia[concept][party][key] += value
                    # Valores que no estan entre [0, 3 UVT]
                    else:
                        if party not in records_cuantia[concept]:
                            records_cuantia[concept].setdefault(
                                party,
                                {}.fromkeys(definitions.keys(), Decimal(0)),
                            )
                        for key, value in values.items():
                            records_cuantia[concept][party][key] = value

        list_concepts = set([_concept.concept for _concept in concepts])
        for concept, parties in records_cuantia.items():
            if concept == '0000':
                for party, values in parties.items():
                    total_pay_deductible = 0
                    total_pay_non_deductible = 0
                    iva_total = values.get('1001_ivaded', 0)
                    iva_total_non_deductible = values.get('1001_ivanoded', 0)

                    # Para almacenar pagos por concepto
                    pagos_deductibles = {}
                    pagos_no_deductibles = {}

                    for _concept in list_concepts:
                        if _concept != concept and party in records_cuantia.get(_concept, {}):
                            data = records_cuantia[_concept][party]
                            pay_deductible = data.get('1001_pagoded', 0)
                            pay_non_deductible = data.get('1001_pagonoded', 0)

                            pagos_deductibles[_concept] = pay_deductible
                            pagos_no_deductibles[_concept] = pay_non_deductible

                            total_pay_deductible += pay_deductible
                            total_pay_non_deductible += pay_non_deductible

                    # Calcular y asignar IVAs distribuidos proporcionalmente
                    for _concept in list_concepts:
                        if _concept != concept and party in records_cuantia.get(_concept, {}):
                            if total_pay_deductible > 0 and pagos_deductibles.get(_concept, 0) > 0:
                                iva_deductible = round(pagos_deductibles[_concept] / total_pay_deductible * iva_total)
                                records_cuantia[_concept][party]['1001_ivaded'] = iva_deductible

                            if total_pay_non_deductible > 0 and pagos_no_deductibles.get(_concept, 0) > 0:
                                iva_non_deductible = round(pagos_no_deductibles[_concept] / total_pay_non_deductible * iva_total_non_deductible)
                                records_cuantia[_concept][party]['1001_ivanoded'] = iva_non_deductible

        del records_cuantia['0000']
        return records_cuantia

    @classmethod
    def get_records_1007(cls, records, party_cuantia, records_cuantia, definitions):
        """Function to update data of exogena 1007"""

        for concept, parties in records:
            for party, values in parties.items():
                if party and party.id_number == '222222222222':
                    if party_cuantia not in records_cuantia[concept]:
                        records_cuantia[concept].setdefault(
                            party_cuantia,
                            {}.fromkeys(definitions.keys(), Decimal(0)),
                        )
                    for key, value in values.items():
                        records_cuantia[concept][party_cuantia][key] += value
                elif (values["1007_ingbrutprop"] < 0
                      or (0 <= values["1007_ingbrutprop"] < 1 and values["1007_ingdev"] == 0)):
                    if party_cuantia not in records_cuantia[concept]:
                        records_cuantia[concept].setdefault(
                            party_cuantia,
                            {}.fromkeys(definitions.keys(), Decimal(0)),
                        )
                    for key, value in values.items():
                        records_cuantia[concept][party_cuantia][key] += value
                else:
                    records_cuantia[concept].setdefault(
                        party,
                        {}.fromkeys(definitions.keys(), Decimal(0)),
                    )
                    for key, value in values.items():
                        records_cuantia[concept][party][key] = value
        return records_cuantia

    @classmethod
    def get_records_1008(cls, records, party_cuantia, records_cuantia, definitions):
        """Function to update data of exogena 1008"""

        pool = Pool()
        Configuration = pool.get('account.configuration')
        configuration = Configuration(1)
        uvt = configuration.uvt

        for concept, parties in records:
            for party, values in parties.items():
                if 0 < values["1008_saldocxc"] < uvt * 12:
                    if party_cuantia not in records_cuantia[concept]:
                        records_cuantia[concept].setdefault(
                            party_cuantia,
                            {}.fromkeys(definitions.keys(), Decimal(0)),
                        )
                    for key, value in values.items():
                        records_cuantia[concept][party_cuantia][key] += value
                else:
                    records_cuantia[concept].setdefault(
                        party,
                        {}.fromkeys(definitions.keys(), Decimal(0)),
                    )
                    for key, value in values.items():
                        records_cuantia[concept][party][key] = value
        return records_cuantia

    @classmethod
    def get_records_1009(cls, records, party_cuantia, records_cuantia, definitions):
        """Function to update data of exogena 1009"""

        pool = Pool()
        Configuration = pool.get('account.configuration')
        configuration = Configuration(1)
        uvt = configuration.uvt

        for concept, parties in records:
            for party, values in parties.items():
                if 0 < values["1009_saldocxp"] < uvt * 12:
                    if party_cuantia not in records_cuantia[concept]:
                        records_cuantia[concept].setdefault(
                            party_cuantia,
                            {}.fromkeys(definitions.keys(), Decimal(0)),
                        )
                    for key, value in values.items():
                        records_cuantia[concept][party_cuantia][key] += value
                else:
                    records_cuantia[concept].setdefault(
                        party,
                        {}.fromkeys(definitions.keys(), Decimal(0)),
                    )
                    for key, value in values.items():
                        records_cuantia[concept][party][key] = value
        return records_cuantia


class F1010(Report):
    "1010 Información de las acciones, aportes o derechos sociales"
    __name__ = 'account.f1010'

    @classmethod
    def get_context(cls, records, header, data):
        """Function to build info to exogena"""

        pool = Pool()
        Configuration = pool.get('account.configuration')
        Concept = pool.get('account.exogena_concepto')
        Period = pool.get('account.period')
        Party = pool.get('party.party')
        Move = pool.get('account.move')
        Bank = pool.get('bank')

        lines_by_account = {}
        accounts_target = {}
        concept_banks = {}
        records = {}
        parties = {}
        moves = {}

        concept_accounts = []
        line_ids = []
        lines_by_account = defaultdict(list)
        report_context = Report.get_context(records, header, data)
        configuration = Configuration(1)

        report_number = cls.__name__[-4:]
        uvt = configuration.uvt
        if not uvt and report_number in ('1001', '1008', '1009'):
            raise UserError("ERROR", "Debe configurar el valor de la UVT en la compañia")

        definitions = DEFINITIONS[report_number].copy()
        start_period = Period(data['start_period'])
        end_period = Period(data['end_period'])
        data['start_date'] = start_period.start_date
        data['end_date'] = end_period.end_date

        concepts = Concept.search([
            ('report', '=', report_number),
            ('concept', '!=', ''),
            ('definition', '!=', ''),
        ], order=[('concept', 'DESC')])

        if not concepts:
            raise UserError("ERROR", "No se encontraron conceptos")

        for c in concepts:
            if not c.definition or not c.concept:
                raise UserError(
                    gettext('account_exo.msg_concept_empty', s=c.account.name))
            accounts_target[c.id] = {
                'definition': c.definition,
                'concept': c.concept,
                'dtp': c.distribute_to_peer,
                'rate_not_deducible': c.rate_not_deducible,
                'nature_account': c.nature_account,
                'exclude_reconciled': c.exclude_reconciled,
                'restar_debit_credit': c.restar_debit_credit,
            }
            if c.account and c.account not in concept_accounts:
                concept_accounts.append(c.account.id)

        banks = Bank.search([('account_expense', 'in', concept_accounts)])
        if banks:
            for bank in banks:
                concept_banks[bank.account_expense] = bank

        periods = Period.search([
            ('fiscalyear', '=', data['fiscalyear']),
            ('start_date', '>=', start_period.start_date),
            ('start_date', '<=', end_period.start_date),
            ('type', '=', 'standard'),
        ])
        period_ids = [p.id for p in periods]

        # Obtener los saldos iniciales:
        result = cls.get_start_balances(report_number, period_ids)
        if result:
            TotalTuple = namedtuple('LineTuple', ['id', 'account_id', 'party', 'debit', 'credit'])
            for row in result:
                line = TotalTuple(*row)
                lines_by_account[line.account_id].append(line)
                line_ids.append(line.id)

        # Obtener las lineas de movimiento para el reporte
        result = cls.get_lines(concepts, concept_banks, period_ids)
        if result:
            # Usar namedtuple para mejorar legibilidad
            LineTuple = namedtuple('LineTuple', ['id', 'account_id', 'party', 'debit', 'credit', 'move_id'])

            # Construcción optimizada de lines_by_account y line_ids al mismo tiempo
            for row in result:
                line = LineTuple(*row)
                lines_by_account[line.account_id].append(line)
                line_ids.append(line.id)

        if len(line_ids) == 1:
            line_ids = f"({line_ids[0]})"
        else:
            line_ids = str(tuple(line_ids))

        # Obtener los impuestos asociados a las líneas de movimiento
        result_tax = cls.get_move_taxes(line_ids)
        lines_tax_map = {line_id: rate for line_id, _, rate in result_tax}

        # Iterar por concepto y procesar solo las líneas de su cuenta
        for c in concepts:
            acc_id = c.account.id
            if acc_id not in lines_by_account:
                continue

            lines = lines_by_account[acc_id]
            concept_info = accounts_target.get(c.id, {})
            is_dtp = concept_info.get('dtp')
            definition = concept_info.get('definition')
            concept_exo = concept_info.get('concept')
            nature_account = concept_info.get('nature_account')
            restar_debit_credit = concept_info.get('restar_debit_credit')

            for line in lines:
                if concept_banks and c.account in concept_banks:
                    party = concept_banks[c.account].party
                else:
                    if line.party not in parties.keys():
                        parties[line.party] = Party(line.party)
                    party = parties[line.party]

                if not party.id:
                    continue

                # Configurar tercero nombre según tipo de persona
                if party.type_person != 'persona_natural':
                    party.first_name = party.second_name = party.first_family_name = party.second_family_name = None
                else:
                    party.name = None

                # Determinar valor base de impuesto si aplica
                base = 0
                tax_lines = lines_tax_map.get(line.id, [])
                if tax_lines:
                    amount_tax = line.debit if line.debit > 0 else line.credit
                    rate = tax_lines
                    if rate:
                        base = amount_tax / rate

                # Determinar valor según naturaleza
                if nature_account == 'debit':
                    if restar_debit_credit:
                        value = line.debit - line.credit
                    else:
                        if line.debit <= 0:
                            continue
                        value = line.debit
                elif nature_account == 'credit':
                    if restar_debit_credit:
                        value = line.credit - line.debit
                    else:
                        if line.credit <= 0:
                            continue
                        value = line.credit
                else:
                    value = line.debit - line.credit

                # Reasignar concepto si es DTP
                if is_dtp:
                    if line.move_id not in moves.keys():
                        moves[line.move_id] = Move(line.move_id)
                    move = moves[line.move_id]
                    for ml in move.lines:
                        if ml.account.id == line.account_id:
                            continue
                        if (ml.debit > _ZERO and line.debit > _ZERO) or (ml.credit > _ZERO and line.credit > _ZERO):
                            peer_info = accounts_target.get(ml.account.id)
                            if peer_info:
                                concept_exo = peer_info['concept']
                                break

                # Inicializar estructuras
                definitions['base'] = 0
                records.setdefault(concept_exo, {})
                records[concept_exo].setdefault(party, {}.fromkeys(definitions.keys(), Decimal(0)))

                records[concept_exo][party][definition] += value
                if base != 0:
                    records[concept_exo][party]['base'] += abs(base)

                # Configurar informacion de ubicacion

                if party.addresses and party.addresses[0].street:
                    party.addresses[0].street = cls._validate_string(party.addresses[0].street)

        if not records:
            raise UserError('No se encontraron registros para este reporte')
        total_nominal = cls.set_total_nominal(records.items())
        report_context['records'] = records.items()
        report_context['vlrnomtot'] = total_nominal
        return report_context

    @classmethod
    def _validate_string(cls, string):
        string = string.replace('\n', '').replace('\x1f', '')
        characters_to_remove = r'[~`!@$%^&*()_+={[}\]|\\:;"<,>.?/\']¬°ºª¿¡¨'
        table = str.maketrans("", "", characters_to_remove)
        result = string.translate(table)
        return result

    @classmethod
    def set_total_nominal(cls, records):
        total_nominal = sum(values["1010_vlrnom"] for concept, parties in records
                            for party, values in parties.items())

        if total_nominal != 0:
            for concept, parties in records:
                for party, values in parties.items():
                    porpar_value = round(values["1010_vlrnom"] / total_nominal, 2)
                    porpar_text = str(porpar_value).replace('.', '')
                    values["1010_porpar"] = porpar_text
                    values["1010_porpardec"] = 0 if porpar_value >= 1 else 2
        return total_nominal

    @classmethod
    def get_start_balance_accounts(cls, report_number):
        pool = Pool()
        Concept = pool.get('account.exogena_concepto')
        concepts = Concept.search([
            ('report', '=', report_number),
            ('concept', '!=', ''),
            ('definition', '!=', ''),
            ('definition', '!=', '1010_vlrprim'),
        ], order=[('concept', 'DESC')])

        accounts_concept_map = {c.account.id: c for c in concepts}
        accounts_ = list(accounts_concept_map.keys())
        return accounts_

    @classmethod
    def get_lines(cls, concepts, concept_banks, period_ids):
        cursor = Transaction().connection.cursor()
        accounts_concept_map = {c.account.id: c for c in concepts}
        accounts_with_banks = set(c.account.id for c in concepts if concept_banks and c.account in concept_banks)
        accounts_ = list(accounts_concept_map.keys())

        if accounts_with_banks:
            query = """SELECT ml.id, ml.account, ml.party, ml.debit, ml.credit, ml.move
                FROM account_move_line AS ml
                JOIN account_move AS m ON ml.move=m.id
                WHERE ml.account = ANY(%s)
                AND m.period = ANY(%s)"""
        else:
            query = """SELECT ml.id, ml.account, ml.party, ml.debit, ml.credit, ml.move
                FROM account_move_line AS ml
                JOIN account_move AS m ON ml.move=m.id
                WHERE ml.account = ANY(%s)
                AND m.period = ANY(%s)
                AND ml.party IS NOT NULL"""
        cursor.execute(query, (accounts_, period_ids))
        return cursor.fetchall()

    @classmethod
    def get_start_balances(cls, report_number, period_ids):
        cursor = Transaction().connection.cursor()
        start_balance_accounts = cls.get_start_balance_accounts(report_number)
        first_period = min(period_ids)
        query = """SELECT ml.id, ml.account, ml.party, SUM(ml.debit) AS total_debit, SUM(ml.credit) AS total_credit
            FROM account_move_line AS ml
            JOIN account_move AS m ON ml.move = m.id
            WHERE ml.account = ANY(%s)
            AND m.period < %s
            AND ml.party IS NOT NULL
            GROUP BY ml.id, ml.account, ml.party"""
        cursor.execute(query, (start_balance_accounts, first_period))
        return cursor.fetchall()

    @classmethod
    def get_move_taxes(cls, line_ids):
        cursor = Transaction().connection.cursor()
        query_tax = f"""
            SELECT t.move_line, t.tax, ct.rate
            FROM account_tax_line AS t
            JOIN account_tax AS ct ON t.tax = ct.id
            WHERE t.move_line IN {line_ids}
        """
        cursor.execute(query_tax)
        return cursor.fetchall()


class F1001(TemplateExogena, metaclass=PoolMeta):
    "1001 Pagos o abonos en cuenta y retenciones practicadas"
    __name__ = 'account.f1001'


class F1003(TemplateExogena, metaclass=PoolMeta):
    "1003 Retenciones en la fuente que le practicaron"
    __name__ = 'account.f1003'


class F1005(TemplateExogena, metaclass=PoolMeta):
    "1005 Impuesto a las ventas por pagar (Descontable)"
    __name__ = 'account.f1005'


class F1006(TemplateExogena, metaclass=PoolMeta):
    "1006 Impuesto a las ventas por pagar (Generado)"
    __name__ = 'account.f1006'


class F1007(TemplateExogena, metaclass=PoolMeta):
    "1007 Ingresos Recibidos"
    __name__ = 'account.f1007'


class F1008(TemplateExogena, metaclass=PoolMeta):
    "1008 Saldo de cuentas por cobrar"
    __name__ = 'account.f1008'


class F1009(TemplateExogena, metaclass=PoolMeta):
    "1009 Saldo de cuentas por Pagar"
    __name__ = 'account.f1009'


class F1011(TemplateExogena, metaclass=PoolMeta):
    "1011 Información de las declaraciones Tributarias"
    __name__ = 'account.f1011'


class F1012(TemplateExogena, metaclass=PoolMeta):
    "1012 Información de declaraciones tributarias, acciones, inversiones en bonos títulos valores y cuentas de ahorro y cuentas corrientes "
    __name__ = 'account.f1012'


class F1043(TemplateExogena, metaclass=PoolMeta):
    "1043 Pagos o Abonos en cuenta y retenciones practicadas de consorcio y uniones temporales"
    __name__ = 'account.f1043'


class F1045(TemplateExogena, metaclass=PoolMeta):
    "1045 Información de ingresos recibidos por consorcios y uniones temporales"
    __name__ = 'account.f1045'


class F2015(TemplateExogena, metaclass=PoolMeta):
    "2015 Retenciones"
    __name__ = 'account.f2015'


class F2276(TemplateExogena, metaclass=PoolMeta):
    "2276 Información Certificado de Ingresos y Retenciones para Personas Naturales Empleados"
    __name__ = 'account.f2276'


class F5247(TemplateExogena, metaclass=PoolMeta):
    "5247 Pagos o abonos en cuenta y retenciones practicadas en contratos de colaboración empresarial"
    __name__ = 'account.f5247'


class F5248(TemplateExogena, metaclass=PoolMeta):
    "5248 Ingresos recibidos en contratos de colaboración empresarial"
    __name__ = 'account.f5248'


class F5249(TemplateExogena, metaclass=PoolMeta):
    "5249 IVA descontable en contratos de colaboración empresarial"
    __name__ = 'account.f5249'


class F5250(TemplateExogena, metaclass=PoolMeta):
    "5250 IVA generado en contratos de colaboración empresarial"
    __name__ = 'account.f5250'


class F5251(TemplateExogena, metaclass=PoolMeta):
    "5251 Saldos cuentas por cobrar a 31 de diciembre en contratos de colaboración empresarial"
    __name__ = 'account.f5251'


class F5252(TemplateExogena, metaclass=PoolMeta):
    "5252 Saldos de cuentas por pagar al 31 de diciembre en contratos de colaboración empresarial"
    __name__ = 'account.f5252'
