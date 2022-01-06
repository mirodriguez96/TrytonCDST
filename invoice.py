from trytond.pool import PoolMeta
from trytond.model import fields
from trytond.pyson import Eval


__all__ = [
    'Invoice'
    ]


ELECTRONIC_STATES = [
    ('none', 'None'),
    ('submitted', 'Submitted'),
    ('pending', 'Pending'),
    ('rejected', 'Rejected'),
    ('authorized', 'Authorized'),
    ('accepted', 'Accepted'),
]

class Invoice(metaclass=PoolMeta):
    'Invoice'
    __name__ = 'account.invoice'
    electronic_state = fields.Selection(ELECTRONIC_STATES, 'Electronic State',
                                        states={'invisible': Eval('type') != 'out'}, readonly=True)


    @staticmethod
    def default_electronic_state():
        return 'none'