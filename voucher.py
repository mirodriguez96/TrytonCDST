from trytond.model import ModelView, ModelSQL, fields

__all__ = [
    'Voucher',
    #'Cron',
    ]

#Heredamos del modelo sale.sale para agregar el campo id_tecno
class Voucher(ModelSQL, ModelView):
    'Voucher'
    __name__ = 'account.voucher'
    id_tecno = fields.Char('Id Tabla Sqlserver', required=False)