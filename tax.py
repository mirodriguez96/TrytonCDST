from trytond.model import fields
from trytond.pool import PoolMeta

TAX_TECNO = [
    ('01', 'IVA'),
    ('02', 'IC'),
    ('03', 'ICA'),
    ('04', 'INC'),
    ('05', 'ReteIVA'),
    ('06', 'ReteFuente'),
    ('07', 'ReteICA'),
    ('20', 'FtoHorticultura'),
    ('21', 'Timbre'),
    ('22', 'Bolsas'),
    ('23', 'INCarbono'),
    ('24', 'INCombustibles'),
    ('25', 'Sobretasa Combustibles'),
    ('26', 'Sordicom'),
    ('ZZ', 'Otro'),
    ('NA', 'No Aceptada'),
    ('renta', 'renta'),
    ('autorenta', 'autorenta'),
]

__all__ = [
    'Tax',
    ]

#Heredamos del modelo sale.sale para agregar el campo id_tecno
class Tax(metaclass=PoolMeta):
    'Tax'
    __name__ = 'account.tax'
    id_tecno = fields.Integer('Id TecnoCarnes', required=False)
    consumo = fields.Boolean('Tax consumption')
    classification_tax_tecno = fields.Selection(TAX_TECNO, 'Classification Tax Tecno')