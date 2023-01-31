from trytond.pool import PoolMeta

class Cron(metaclass=PoolMeta):
    'Cron'
    __name__ = 'ir.cron'

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
            ('production|import_data_production', "Importar producciones"),
            )
