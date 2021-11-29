# This file is part of Tryton.  The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.
from trytond.pool import PoolMeta
from trytond.model import fields

PAYMENT_TYPE = [
    ('', ''),
    ('1', 'Contado'),
    ('2', 'Credito'),
]


class PaymentTerm(metaclass=PoolMeta):
    __name__ = 'account.invoice.payment_term'

    payment_type = fields.Selection(PAYMENT_TYPE, 'Payment Type', required=True)
    id_tecno = fields.Char('Id Tabla Sqlserver', required=False)

    @staticmethod
    def default_payment_type():
        return '1'
