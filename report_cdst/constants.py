# This file is part of Tryton.  The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.

PAYMENTS = [
    'salary',
    'bonus',
    'reco',
    'recf',
    'hedo',
    'heno',
    'dom',
    'hedf',
    'henf',
]

SOCIAL_SEGURITY = [
    'risk', 'health', 'retirement', 'box_family', 'sena', 'icbf'
]

LIM_UVT_DEDUCTIBLE = {
    'fvp_ind': 2500,
    'afc_fvp': (3800 / 12),
    'housing_interest': 100,
    'health_prepaid': 16,
    'dependents': 32,
    'exempted_incom': 240
}

LIM_PERCENT_DEDUCTIBLE = {
    'fvp_ind': 25,
    'dependents': 10,
    'afc_fvp': 30,
    'exempted_income': 25,
    'renta_deductions': 40
}

ENTITY_ACCOUNTS = {
    '830113831': (23700501, 72056901),
    '890102044': (23700514, 72056914),
    '900298372': (23700515, 72056915),
    '860045904': (23700512, 72056912),
    '804002105': (23700513, 72056913),
    '860066942': (23700503, 72056903),
    '805000427': (23700504, 72056904),
    '900226715': (23700505, 72056905),
    '830009783': (23700516, 72056916),
    '900935126': (23700517, 72056917),
    '830003564': (23700506, 72056906),
    '901097473': (23700509, 72056909),
    '806008394': (23700502, 72056902),
    '900156264': (23700510, 72056910),
    '800130907': (23700511, 72056911),
    '800251440': (23700507, 72056907),
    '900604350': (23700518, 72056918),
    '800088702': (23700508, 72056908),
    '800227940': (23803002, 72057002),
    '900336004': (23803001, 72057001),
    '800253055': (23803003, 72057003),
    '800224808': (23803004, 72057004),
    '800229739': (23803005, 72057005),
    '890102002': (2370100102, 72057202),
    '860013570': (2370100101, 72057201),
    '891780093': (2370100103, 72057203),
    '892399989': (2370100104, 72057204),
    '890480023': (2370100105, 72057205),
    '890903790': (23700601, 72056801),
    '890500675': (23700519, 72056919),
    '818000140': (23700520, 72056920),
    '901037916': (23700521, 72056921),
}

FIELDS_AMOUNT = [
    'salary',
    'reco',
    'recf',
    'hedo',
    'heno',
    'dom',
    'hedf',
    'henf',
    'cost_reco',
    'cost_recf',
    'cost_hedo',
    'cost_heno',
    'cost_dom',
    'cost_hedf',
    'cost_henf',
    'bonus',
    'total_extras',
    'gross_payment',
    'health',
    'retirement',
    'food',
    'transport',
    'fsp',
    'retefuente',
    'other_deduction',
    'total_deduction',
    'ibc',
    'net_payment',
    'box_family',
    'box_family',
    'unemployment',
    'interest',
    'holidays',
    'bonus_service',
    'discount',
    'other',
    'total_benefit',
    'risk',
    'health_provision',
    'retirement_provision',
    'total_ssi',
    'total_cost',
    'sena',
    'icbf',
    'acquired_product',
]

EXTRAS = [
    'reco',
    'recf',
    'hedo',
    'heno',
    'dom',
    'hedf',
    'henf',
]

SHEET_SUMABLES = [
    'salary',
    'total_extras',
    'transport',
    'food',
    'bonus',
    'unemployment',
    'interest',
    'holidays',
    'bonus_service',
    'fsp',
    'retefuente',
    'total_deduction',
    'retirement_provision',
    'other_deduction',
    'acquired_product',
    'health_provision',
    'cost_reco',
    'cost_recf',
    'cost_hedo',
    'cost_heno',
    'cost_dom',
    'cost_hedf',
    'cost_henf',
]

SHEET_SUMABLES.extend(SOCIAL_SEGURITY)
SHEET_SUMABLES.extend(EXTRAS)

SHEET_FIELDS_NOT_AMOUNT = [
    'item',
    'employee',
    'id_number',
    'position',
    'legal_salary',
    'salary_day',
    'salary_hour',
    'worked_days',
    'period',
    'department',
]
