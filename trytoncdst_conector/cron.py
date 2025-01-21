from trytond.model import fields
from trytond.pool import PoolMeta
from trytond.pyson import Bool, Eval, If, Not

STATE = {'invisible': Not(Bool(Eval('access_register')))}


class Cron(metaclass=PoolMeta):
    'Cron'
    __name__ = 'ir.cron'

    access_register = fields.Boolean(
        'Access register',
        states={
            'invisible': (Eval('method')
                          != 'conector.actualizacion|biometric_access_dom'),
        },
        depends=['method'])

    enter_timestamp = fields.Time('Enter', format='%H:%M:%S', states=STATE)

    exit_timestamp = fields.Time('Exit', format='%H:%M:%S', states=STATE)

    # OK - Reestructuracion de codigo
    # OK OK - Reestructuracion y ajuste en rollback
    @classmethod
    def __setup__(cls):
        super().__setup__()
        # OK OK
        cls.method.selection.append(
            ('party.party|import_parties_tecno', "Importar terceros"), )

        # OK OK
        cls.method.selection.append(('party.party|import_addresses_tecno',
                                     "Importar direcciones de terceros"), )

        cls.method.selection.append(
            ('sale.sale|import_data_sale', "Importar ventas"), )
        cls.method.selection.append(('sale.sale|import_data_sale_return',
                                     "Importar devoluciones de ventas"), )

        # PDTE POR REESTRUCTURAR ----------
        cls.method.selection.append(('product.product|update_product_parent',
                                     "Actualizar costo productos hijos"), )

        # OK OK
        cls.method.selection.append(
            ('stock.location|import_warehouse', "Importar bodegas"), )

        # OK OK
        cls.method.selection.append(
            ('product.product|import_products_tecno', "Importar productos"), )

        # PDTE POR REESTRUCTURAR / OK
        cls.method.selection.append(
            ('product.category|import_categories_tecno',
             "Importar categorias de productos"), )

        # PDTE POR REESTRUCTURAR / OK
        cls.method.selection.append(
            ('sale.device|import_data_pos', "Importar Config Pos"), )

        # PDTE POR REESTRUCTURAR / OK
        cls.method.selection.append(('account.voucher|import_voucher',
                                     "Importar comprobantes de ingreso"), )
        # PDTE POR REESTRUCTURAR / OK
        cls.method.selection.append(('account.voucher|import_voucher_payment',
                                     "Importar comprobantes de egreso"), )

        # PDTE POR REESTRUCTURAR / OK
        cls.method.selection.append(('account.voucher.paymode|update_paymode',
                                     "Importar formas de pago"), )

        # PDTE POR REESTRUCTURAR / OK
        cls.method.selection.append(
            ('account.invoice.payment_term|import_payment_term',
             "Importar plazos de pago"), )

        # PDTE POR REESTRUCTURAR (CODIGO HORRIBLE)/ OK
        cls.method.selection.append(
            ('purchase.purchase|import_data_purchase', "Importar compras"), )

        # PDTE POR REESTRUCTURAR (CODIGO HORRIBLE)/ OK
        cls.method.selection.append(
            ('purchase.purchase|import_data_purchase_return',
             "Importar devoluciones de compras"), )

        # PDTE POR REESTRUCTURAR / OK
        cls.method.selection.append(('account.invoice|import_credit_note',
                                     "Importar Notas de Crédito"), )

        # PDTE POR REESTRUCTURAR / OK
        cls.method.selection.append(('account.invoice|import_debit_note',
                                     "Importar Notas de Débito"), )

        # PDTE POR REESTRUCTURAR / OK
        cls.method.selection.append(
            ('account.invoice|import_credit_note_purchase',
             "Importar notas de crédito para compras"), )

        # PDTE POR REESTRUCTURAR / OK
        cls.method.selection.append(
            ('account.invoice|import_debit_note_purchase',
             "Importar notas de débito para compras"), )

        # PDTE POR REESTRUCTURAR / OK
        cls.method.selection.append(
            ('production|import_data_production', "Importar producciones"), )

        # PDTE POR REESTRUCTURAR --------
        cls.method.selection.append(('purchase.purchase|import_order_tecno',
                                     "Importar entrada de mercancia"), )

        # PDTE POR REESTRUCTURAR (CODIGO HORRIBLE)/ OK
        cls.method.selection.append(('account.voucher|_check_cross_vouchers',
                                     "Validar cruce de comprobantes"), )

        # PDTE POR REESTRUCTURAR (CODIGO HORRIBLE)/ OK
        cls.method.selection.append(('account.invoice|_check_cross_invoices',
                                     "Validar cruce de facturas"), )

        # PDTE POR REESTRUCTURAR (CODIGO HORRIBLE)--------
        cls.method.selection.append(
            ('conector.actualizacion|_missing_documents',
             "Validar documentos faltantes"), )

        # PDTE POR REESTRUCTURAR (CODIGO HORRIBLE)--------
        cls.method.selection.append(
            ('conector.actualizacion|import_biometric_access',
             'Import biometric accesses'), )

        # PDTE POR REESTRUCTURAR / OK
        cls.method.selection.append(
            ('stock.shipment.internal|get_documentos_traslado',
             'Importar traslados'), )

        # PDTE POR REESTRUCTURAR / OK
        cls.method.selection.append(
            ('stock.shipment.internal|get_documentos_traslado_',
             'Importar traslados - degustaciones'), )

        # OK / OK
        cls.method.selection.append(
            ('conector.actualizacion|update_exception_documents',
             "Actualizar documentos con excepcion."), )

        # OK / OK
        cls.method.selection.append(
            ('conector.log|delete_data_log',
             "Eliminar cache del log."), )
