from trytond.pool import PoolMeta
from trytond.pyson import Eval, Not, If, Bool
from trytond.model import fields

STATE = {
        'invisible':  Not(Bool(Eval('access_register')))
    }

class Cron(metaclass=PoolMeta):
    'Cron'
    __name__ = 'ir.cron'

    access_register = fields.Boolean('Access register', states={
        'invisible': (Eval('method') != 'conector.actualizacion|biometric_access_dom'),
    }, depends=['method'])

    enter_timestamp = fields.Time('Enter',format='%H:%M:%S', states=STATE)
    
    exit_timestamp = fields.Time('Exit',format='%H:%M:%S', states=STATE)
    

    @classmethod
    def __setup__(cls):
        super().__setup__()
        cls.method.selection.append(
            ('party.party|import_parties_tecno', "Importar terceros"),
            )
        cls.method.selection.append(
            ('party.party|import_addresses_tecno', "Importar direcciones de terceros"),
            )
        cls.method.selection.append(
            ('sale.sale|import_data_sale', "Importar ventas"),
            )
        cls.method.selection.append(
            ('product.product|update_product_parent', "Actualizar costo productos hijos"),
            )
        cls.method.selection.append(
            ('sale.sale|import_data_sale_return', "Importar devoluciones de ventas"),
            )
        cls.method.selection.append(
            ('stock.location|import_warehouse', "Importar bodegas"),
            )
        cls.method.selection.append(
            ('product.product|import_products_tecno', "Importar productos"),
            )
        cls.method.selection.append(
            ('product.category|import_categories_tecno', "Importar categorias de productos"),
            )
        cls.method.selection.append(
            ('sale.device|import_data_pos', "Importar Config Pos"),
            )
        cls.method.selection.append(
            ('account.voucher|import_voucher', "Importar comprobantes de ingreso"),
            )
        cls.method.selection.append(
            ('account.voucher|import_voucher_payment', "Importar comprobantes de egreso"),
            )
        cls.method.selection.append(
            ('account.voucher.paymode|update_paymode', "Importar formas de pago"),
            )
        cls.method.selection.append(
            ('account.invoice.payment_term|import_payment_term', "Importar plazos de pago"),
            )
        cls.method.selection.append(
            ('purchase.purchase|import_data_purchase', "Importar compras"),
            )
        cls.method.selection.append(
            ('purchase.purchase|import_data_purchase_return', "Importar devoluciones de compras"),
            )
        cls.method.selection.append(
            ('account.invoice|import_credit_note', "Importar Notas de Crédito"),
            )
        cls.method.selection.append(
            ('account.invoice|import_debit_note', "Importar Notas de Débito"),
            )
        cls.method.selection.append(
            ('account.invoice|import_credit_note_purchase', "Importar notas de crédito para compras"),
            )
        cls.method.selection.append(
            ('account.invoice|import_debit_note_purchase', "Importar notas de débito para compras"),
            )
        cls.method.selection.append(
            ('production|import_data_production', "Importar producciones"),
            )
        cls.method.selection.append(
            ('purchase.purchase|import_order_tecno', "Importar entrada de mercancia"),
            )
        cls.method.selection.append(
            ('account.voucher|_check_cross_vouchers', "Validar cruce de comprobantes"),
            )
        cls.method.selection.append(
            ('account.invoice|_check_cross_invoices', "Validar cruce de facturas"),
            )
        cls.method.selection.append(
            ('conector.actualizacion|_missing_documents', "Validar documentos faltantes"),
            )
        cls.method.selection.append(
            ('conector.actualizacion|import_biometric_access', 'Import biometric accesses'),
        )
        cls.method.selection.append(
            ('stock.shipment.internal|import_tecnocarnes', 'Importar traslados'),
        )
        cls.method.selection.append(
            ('conector.actualizacion|biometric_access_dom', 'Generar Ingresos Domingos'),
        )
        cls.method.selection.append(
            ('conector.actualizacion|holidays_access_fes', 'Generar Ingresos Festivos'),
        )
