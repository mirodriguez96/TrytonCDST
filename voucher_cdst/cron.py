from trytond.pool import PoolMeta


class Cron(metaclass=PoolMeta):
    'Cron'
    __name__ = 'ir.cron'

    @classmethod
    def __setup__(cls):
        super().__setup__()

        # PDTE POR REESTRUCTURAR / OK
        cls.method.selection.append(('account.voucher|import_voucher',
                                     "Importar comprobantes de ingreso"), )
        # PDTE POR REESTRUCTURAR / OK
        cls.method.selection.append(('account.voucher|import_voucher_payment',
                                     "Importar comprobantes de egreso"), )
