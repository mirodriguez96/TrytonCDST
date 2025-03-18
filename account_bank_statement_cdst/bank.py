from trytond.model import fields
from trytond.pool import PoolMeta


class Bank(metaclass=PoolMeta):
    'Bank'
    __name__ = 'bank'
    bank_code_sap = fields.Char(
        'Bank code SAP', help='bank code used for the bancolombia payment template'
    )
