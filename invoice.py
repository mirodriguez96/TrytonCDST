from trytond.pool import PoolMeta, Pool
from trytond.model import fields
from trytond.pyson import Eval
from trytond.wizard import Wizard, StateTransition
from trytond.transaction import Transaction
from trytond.exceptions import UserError


__all__ = [
    'Invoice',
    'Update Invoice Tecno'
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


class UpdateInvoiceTecno(Wizard):
    'Update Invoice Tecno'
    __name__ = 'account.invoice.update_invoice_tecno'
    start_state = 'do_submit'
    do_submit = StateTransition()

    def transition_do_submit(self):
        pool = Pool()
        Invoice = pool.get('account.invoice')
        Sale = pool.get('sale.sale')
        Purchase = pool.get('purchase.purchase')

        ids = Transaction().context['active_ids']

        to_delete_sales = []
        to_delete_purchases = []
        for invoice in Invoice.browse(ids):
            rec_name = invoice.rec_name
            party_name = invoice.party.name
            rec_party = rec_name+' de '+party_name
            if invoice.state != 'posted' and invoice.state != 'paid' and invoice.number:
                if '-' in invoice.number:
                    if invoice.type == 'out':
                        #print('Factura de cliente: ', rec_party)
                        sale = Sale.search([('number', '=', invoice.number)])
                        if sale:
                            to_delete_sales.append(sale[0])
                        #else:
                        #    raise UserError("No existe la venta para la factura: ", rec_party)
                    elif invoice.type == 'in':
                        #print('Factura de proveedor: ', rec_party)
                        purchase = Purchase.search([('number', '=', invoice.number)])
                        if purchase:
                            to_delete_purchases.append(purchase[0])
                        #else:
                        #    raise UserError("No existe la compra para la factura: ", rec_party)
            else:
                raise UserError("Revisa el estado y número de la factura (tipo-numero): ", rec_party)
        Sale.delete_imported_sales(to_delete_sales)
        Purchase.delete_imported_purchases(to_delete_purchases)
        return 'end'

    def end(self):
        return 'reload'