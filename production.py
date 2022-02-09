from trytond.model import fields
from trytond.pool import PoolMeta
from trytond.exceptions import UserError
import logging


__all__ = [
    'Production',
    'Cron',
    ]


#Config = configuration.Configuration()


class Cron(metaclass=PoolMeta):
    'Cron'
    __name__ = 'ir.cron'

    @classmethod
    def __setup__(cls):
        super().__setup__()
        cls.method.selection.append(
            ('sale.sale|import_data_production', "Importar producciones"),
            )


#Heredamos del modelo sale.sale para agregar el campo id_tecno
class Production(metaclass=PoolMeta):
    'Production'
    __name__ = 'production'
    id_tecno = fields.Char('Id Tabla Sqlserver', required=False)


    @classmethod
    def import_data_production(cls):
        pass