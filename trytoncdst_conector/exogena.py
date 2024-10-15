from datetime import date
from decimal import Decimal

from trytond.exceptions import UserError
from trytond.i18n import gettext
from trytond.pool import Pool, PoolMeta
from trytond.report import Report

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
        '':
        '',
        '1005_impdescon':
        'Impuesto Descontable.',
        '1005_ivadev':
        'IVA resultante por devoluciones en ventas anuladas. rescindidas o resueltas',
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


class TemplateExogena(Report, metaclass=PoolMeta):
    "0000 Template"
    __name__ = 'account.f0000'

    @classmethod
    def get_context(cls, records, header, data):
        """Function to build info to exogena"""

        pool = Pool()
        Concept = pool.get('account.exogena_concepto')
        LineTax = pool.get('account.tax.line')
        Company = pool.get('company.company')
        Line = pool.get('account.move.line')
        Period = pool.get('account.period')
        Party = pool.get('party.party')
        Bank = pool.get('bank')

        accounts_target = {}
        records_cuantia = {}
        concept_banks = {}
        records = {}
        concept_accounts = []
        party_cuantia = None

        report_context = Report.get_context(records, header, data)
        party_cuantias = Party.search([
            ('id_number', '=', '222222222'),
        ])
        if party_cuantias:
            party_cuantia = party_cuantias[0]

        report_number = cls.__name__[-4:]
        concepts = Concept.search([
            ('report', '=', report_number),
            ('concept', '!=', ''),
            ('definition', '!=', ''),
        ], order=[('concept', 'DESC')])

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

        definitions = DEFINITIONS[report_number].copy()

        start_period = Period(data['start_period'])
        end_period = Period(data['end_period'])
        data['start_date'] = start_period.start_date
        data['end_date'] = end_period.end_date
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
        banks = Bank.search([('account_expense', 'in', concept_accounts)])

        if banks:
            for bank in banks:
                concept_banks[bank.account_expense] = bank

        if concepts:
            for c in concepts:
                dom_lines = [
                    ('account', '=', c.account.id),
                    ('move.period', 'in', period_ids),
                    ('party', '!=', None),
                ]
                if concept_banks and c.account in concept_banks:
                    dom_lines = [
                        ('account', '=', c.account.id),
                        ('move.period', 'in', period_ids),
                    ]

                lines = Line.search(dom_lines)
                for line in lines:
                    lines_taxes = LineTax.search([('move_line.id', '=',
                                                   line.id)])
                    base = 0
                    if lines_taxes:
                        if line.debit > 0:
                            amount_tax = line.debit
                        else:
                            amount_tax = line.credit
                        if lines_taxes[0].tax and lines_taxes[
                                0].tax.rate and lines_taxes[0].tax.rate != 0:
                            base = (amount_tax / lines_taxes[0].tax.rate) or 0

                    is_dtp = accounts_target[c.id]['dtp']
                    definition = accounts_target[c.id]['definition']
                    concept_exo = accounts_target[c.id]['concept']
                    rate_not_deducible = accounts_target[
                        c.id]['rate_not_deducible']
                    nature_account = accounts_target[c.id]['nature_account']
                    exclude_reconciled = accounts_target[
                        c.id]['exclude_reconciled']
                    restar_debit_credit = accounts_target[
                        c.id]['restar_debit_credit']

                    # side, otherside = line.account.type.display_balance.split('-')
                    # Ignore line reconciled counterpart because it not sums value twice
                    # adding to black list reconciled (reconciliation, debit-credit)

                    if concept_banks and c.account in concept_banks:
                        line.party = party = concept_banks[c.account].party
                    party = line.party
                    if party.type_person != 'persona_natural':
                        party.first_name = None
                        party.second_name = None
                        party.first_family_name = None
                        party.second_family_name = None
                    else:
                        party.name = None
                    if party.addresses and party.addresses[0].street:
                        party.addresses[0].street = cls._validate_string(
                            party.addresses[0].street)
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
                    # The objective this sentence is change concept_exo target
                    # because account dtp is must be assigned to another concept
                    if is_dtp:
                        for ml in line.move.lines:
                            if ml.account.id == line.account.id:
                                continue
                            if ml.debit > _ZERO and line.debit > _ZERO or \
                                    ml.credit > _ZERO and line.credit > _ZERO:
                                peer_account = accounts_target.get(
                                    ml.account.id)
                                if peer_account:
                                    concept_exo = peer_account['concept']
                                    break

                    definitions['base'] = 0
                    records.setdefault(concept_exo, {})
                    records[concept_exo].setdefault(party, {}.fromkeys(
                        definitions.keys(), Decimal(0)))
                    # Build dict to cuantia
                    if party_cuantia:
                        records_cuantia.setdefault(concept_exo, {})

                    if rate_not_deducible and report_number == '1001':
                        deducible = value * (100 - rate_not_deducible) / 100
                        not_deducible = value - deducible
                        if report_number == '1001':
                            if 'iva' in definition:
                                definition_not_ded = '1001_ivanoded'
                            else:
                                definition_not_ded = '1001_pagonoded'
                            records[concept_exo][line.party][
                                definition_not_ded] += not_deducible
                            value = deducible
                        else:
                            value = not_deducible
                    records[concept_exo][line.party][definition] += value
                    if base != 0:
                        records[concept_exo][line.party]['base'] += abs(base)

        data['today'] = date.today()
        company = Company(data['company'])
        city_code = ''
        department_code = ''
        if company.party.city_code:
            city_code = company.party.city_code
        if company.party.department_code:
            department_code = company.party.department_code
        if not records:
            raise UserError('No se encontraron registros para este reporte')
        data['city'] = city_code
        data['department'] = department_code
        report_context['records'] = records.items()
        if party_cuantia and (
                report_number == '1001' or report_number == '1005'
                or report_number == '1006' or report_number == '1007'
                or report_number == '1008' or report_number == '1009'):
            new_records = cls.update_cuantia_data(records.items(),
                                                  party_cuantia,
                                                  records_cuantia,
                                                  definitions,
                                                  report_number,
                                                  concepts)
            report_context['records'] = new_records.items()
        return report_context

    @classmethod
    def update_cuantia_data(cls, records, party_cuantia, records_cuantia,
                            definitions, report, concepts):

        if report == "1001":
            records_cuantia = cls.get_records_1001(records, party_cuantia,
                                                   records_cuantia,
                                                   definitions,
                                                   concepts)
        if report == "1005":
            records_cuantia = cls.get_records_1005(records, party_cuantia,
                                                   records_cuantia,
                                                   definitions)
        if report == "1006":
            records_cuantia = cls.get_records_1006(records, party_cuantia,
                                                   records_cuantia,
                                                   definitions)
        if report == "1007":
            records_cuantia = cls.get_records_1007(records, party_cuantia,
                                                   records_cuantia,
                                                   definitions)
        if report == "1008":
            records_cuantia = cls.get_records_1008(records, party_cuantia,
                                                   records_cuantia,
                                                   definitions)
        if report == "1009":
            records_cuantia = cls.get_records_1009(records, party_cuantia,
                                                   records_cuantia,
                                                   definitions)
        return records_cuantia

    @classmethod
    def get_records_1001(cls, records, party_cuantia, records_cuantia, definitions, concepts):
        """Function to update data of exogena 1001"""
        for concept, parties in records:
            for party, values in parties.items():
                if 0 < values["1001_pagoded"] < 100000:
                    records_cuantia[concept].setdefault(
                        party_cuantia,
                        {}.fromkeys(definitions.keys(), Decimal(0)),
                    )
                    for key, value in values.items():
                        records_cuantia[concept][party_cuantia][key] += value
                elif 0 == values["1001_pagoded"]\
                        and (values["1001_pagonoded"] > 0
                             or values["1001_ivaded"] > 0
                             or values["1001_ivanoded"] > 0
                             or values["1001_retprac"] > 0
                             or values["1001_retasum"] > 0
                             or values["1001_retpracivarc"] > 0
                             or values["1001_retasumivars"] > 0
                             or values["1001_retpracivanodo"] > 0
                             or values["1001_retpracree"] > 0
                             or values["1001_retasumcree"] > 0)\
                        and concept != '0000':
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

        list_concepts = set([_concept.concept for _concept in concepts])
        for concept, parties in records_cuantia.items():
            if concept == '0000':
                for party, values in parties.items():
                    total_pay_deductible = 0
                    total_pay_non_deductible = 0
                    iva_total = records_cuantia[concept][party]['1001_ivaded']
                    iva_total_non_deductible = records_cuantia[concept][party]['1001_ivanoded']

                    for _concept in list_concepts:
                        if _concept in records_cuantia\
                                and party in records_cuantia[_concept]\
                                and _concept != concept:
                            for key, value in values.items():
                                if key == '1001_pagoded':
                                    pay_deductible = records_cuantia[_concept][party]['1001_pagoded']
                                    total_pay_deductible += pay_deductible
                                if key == '1001_pagonoded':
                                    pay_non_deductible = records_cuantia[_concept][party]['1001_pagonoded']
                                    total_pay_non_deductible += pay_non_deductible

                    for _concept in list_concepts:
                        if _concept in records_cuantia\
                                and party in records_cuantia[_concept]\
                                and _concept != concept:
                            for key, value in values.items():
                                if key == '1001_pagoded':
                                    pay_deductible = records_cuantia[_concept][party][key]
                                    iva_deductible = round(
                                        (pay_deductible/total_pay_deductible * iva_total))
                                    records_cuantia[_concept][party]['1001_ivaded'] = iva_deductible
                                if key == '1001_pagonoded':
                                    pay_non_deductible = records_cuantia[_concept][party][key]
                                    iva_non_deductible = 0
                                    if total_pay_non_deductible > 0:
                                        iva_non_deductible = round(
                                            (pay_non_deductible/total_pay_non_deductible
                                             * iva_total_non_deductible))
                                    records_cuantia[_concept][party]['1001_ivanoded'] = iva_non_deductible
        del records_cuantia['0000']
        return records_cuantia

    @classmethod
    def get_records_1005(cls, records, party_cuantia, records_cuantia,
                         definitions):
        """Function to update data of exogena 1005"""

        for concept, parties in records:
            for party, values in parties.items():
                if 0 < values["1005_impdescon"] < 500000:
                    records_cuantia[concept].setdefault(
                        party_cuantia,
                        {}.fromkeys(definitions.keys(), Decimal(0)),
                    )
                    for key, value in values.items():
                        records_cuantia[concept][party_cuantia][key] += value

                elif 0 == values["1005_impdescon"] and values[
                        "1005_ivadev"] > 0:
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
    def get_records_1006(cls, records, party_cuantia, records_cuantia,
                         definitions):
        """Function to update data of exogena 1006"""

        for concept, parties in records:
            for party, values in parties.items():
                if 0 < values["1006_impgen"] < 500000:
                    records_cuantia[concept].setdefault(
                        party_cuantia,
                        {}.fromkeys(definitions.keys(), Decimal(0)),
                    )
                    for key, value in values.items():
                        records_cuantia[concept][party_cuantia][key] += value

                elif 0 == values["1006_impgen"] and\
                        (values["1006_ivarecup"] > 0
                         or values["1006_impoconsumo"] > 0):
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
    def get_records_1007(cls, records, party_cuantia, records_cuantia,
                         definitions):
        """Function to update data of exogena 1007"""

        for concept, parties in records:
            for party, values in parties.items():
                if 0 < values["1007_ingbrutprop"] < 500000:
                    records_cuantia[concept].setdefault(
                        party_cuantia,
                        {}.fromkeys(definitions.keys(), Decimal(0)),
                    )
                    for key, value in values.items():
                        records_cuantia[concept][party_cuantia][key] += value

                elif 0 == values["1007_ingbrutprop"]\
                    and (values["1007_ingbruconsorut"] > 0
                         or values["1007_ingcontraadm"] > 0
                         or values["1007_ingexplo"] > 0
                         or values["1007_ingfidu"] > 0
                         or values["1007_ingtercer"] > 0
                         or values["1007_ingdev"] > 0):
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
    def get_records_1008(cls, records, party_cuantia, records_cuantia,
                         definitions):
        """Function to update data of exogena 1008"""

        for concept, parties in records:
            for party, values in parties.items():
                if 0 < values["1008_saldocxc"] < 500000:
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
    def get_records_1009(cls, records, party_cuantia, records_cuantia,
                         definitions):
        """Function to update data of exogena 1009"""

        for concept, parties in records:
            for party, values in parties.items():
                if 0 < values["1009_saldocxp"] < 500000:
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
