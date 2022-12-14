from trytond.model import fields
from trytond.pool import PoolMeta

__all__ = [
    'Tax',
    ]

#Heredamos del modelo sale.sale para agregar el campo id_tecno
class Tax(metaclass=PoolMeta):
    'Tax'
    __name__ = 'account.tax'
    id_tecno = fields.Integer('Id TecnoCarnes', required=False)
    consumo = fields.Boolean('Tax consumption')