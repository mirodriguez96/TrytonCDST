from trytond.wizard import Wizard, StateTransition
from trytond.pool import Pool
from trytond.transaction import Transaction
from trytond.exceptions import UserError, UserWarning


class VoucherMoveUnreconcile(Wizard):
    'Voucher Move Unreconcile'
    __name__ = 'account.move.voucher_unreconcile'
    start_state = 'do_unreconcile'
    do_unreconcile = StateTransition()

    def transition_do_unreconcile(self):
        pool = Pool()
        Voucher = pool.get('account.voucher')
        Reconciliation = pool.get('account.move.reconciliation')
        #Move = pool.get('account.move')
        ids_ = Transaction().context['active_ids']
        if ids_:
            to_unreconcilie = []
            for voucher in Voucher.browse(ids_):
                if voucher.move:
                    to_unreconcilie.append(voucher.move)
            for move in to_unreconcilie:
                reconciliations = [
                    l.reconciliation for l in move.lines if l.reconciliation
                ]
                if reconciliations:
                    Reconciliation.delete(reconciliations)
        return 'end'


class DeleteVoucherTecno(Wizard):
    'Delete Voucher Tecno'
    __name__ = 'account.voucher.delete_voucher_tecno'
    start_state = 'do_submit'
    do_submit = StateTransition()

    def transition_do_submit(self):
        pool = Pool()
        Warning = pool.get('res.user.warning')
        Voucher = pool.get('account.voucher')
        ids = Transaction().context['active_ids']
        #Se agrega un nombre unico a la advertencia
        warning_name = 'mywarning_%s' % ids
        if Warning.check(warning_name):
            raise UserWarning(warning_name, "Los comprobantes debieron ser desconciliado primero.")
        to_delete = []
        for voucher in Voucher.browse(ids):
            rec_name = voucher.rec_name
            party_name = voucher.party.name
            rec_party = rec_name+' de '+party_name
            if voucher.number and '-' in voucher.number and voucher.id_tecno:
                to_delete.append(voucher)
            else:
                raise UserError("Revisa el número del comprobante (tipo-numero): ", rec_party)
        Voucher.delete_imported_vouchers(to_delete)
        return 'end'

    def end(self):
        return 'reload'


#Pendiente por terminar...
class MoveForceDraft(Wizard):
    'Move Force Drafts'
    __name__ = 'account.move.force_drafts'
    start_state = 'force_drafts'
    force_draft = StateTransition()

    def transition_force_drafts(self):
        ids_ = Transaction().context['active_ids']
        if ids_:
            Move = Pool().get('account.move')
            Move.drafts(ids_)
        return 'end'


#Asistente encargado de revertir las producciones
class ReverseProduction(Wizard):
    'Reverse Production'
    __name__ = 'production.reverse_production'
    start_state = 'reverse_production'
    reverse_production = StateTransition()

    def transition_reverse_production(self):
        Production = Pool().get('production')
        ids = Transaction().context['active_ids']
        to_reverse = []
        if ids:
            for production in Production.browse(ids):
                to_reverse.append(production)
        Production.reverse_production(to_reverse)
        return 'end'
    
    def end(self):
        return 'reload'

