from trytond.model import fields
from trytond.pool import PoolMeta


class Configuration(metaclass=PoolMeta):
    'Account Configuration'
    __name__ = 'account.configuration'

    uvt = fields.Numeric('UVT')
