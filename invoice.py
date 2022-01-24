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
        SaleForceDraft = pool.get('account_col.force_draft', type='wizard')
        User = pool.get('res.user')

        ids = Transaction().context['active_ids']

        #sale_to_delete = []
        #purchase_to_delete = []
        for invoice in Invoice.browse(ids):
            rec_name = invoice.rec_name
            party_name = invoice.party.name
            if invoice.state != 'posted' and invoice.state != 'paid' and invoice.number:
                if '-' in invoice.number:
                    with Transaction().set_user(1):
                        context = User.get_preferences()
                    with Transaction().set_context(context):
                        sdraft = SaleForceDraft(session_id=1)
                    if invoice.type == 'out':
                        print('Factura de cliente')
                        #id_tecno = '1-'+invoice.number
                        sale = Sale.search([('number', '=', invoice.number)])
                        sdraft.transition_force_draft()
                        if sale:
                            Sale.delete(sale)
                        print(sale)
                    elif invoice.type == 'in':
                        print('Factura de proveedor')
                        #id_tecno = '3-'+invoice.number
                        purchase = Purchase.search([('number', '=', invoice.number)])
                        print(purchase)
            else:
                raise UserError("Revisar el estado y número de la factura: ", rec_name+' de '+party_name)
        return 'end'