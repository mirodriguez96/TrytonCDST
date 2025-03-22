from trytond.pool import PoolMeta


class Cron(metaclass=PoolMeta):
    'Cron'
    __name__ = 'ir.cron'

    @classmethod
    def __setup__(cls):
        super().__setup__()
        cls.method.selection.append(
            ('party.party|import_parties_tecno', "Importar terceros"), )

        cls.method.selection.append(('party.party|import_addresses_tecno',
                                     "Importar direcciones de terceros"), )
