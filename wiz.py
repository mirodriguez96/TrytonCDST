from trytond.wizard import Wizard, StateTransition
from trytond.pool import Pool
from trytond.transaction import Transaction
from trytond.exceptions import UserError, UserWarning
from sql import Table


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
        warning_name = 'warning_delete_voucher_tecno'
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

class DeleteImportRecords(Wizard):
    'Delete Import Records'
    __name__ = 'conector.actualizacion.delete_import_records'
    start_state = 'do_submit'
    do_submit = StateTransition()

    def transition_do_submit(self):
        pool = Pool()
        Warning = pool.get('res.user.warning')
        Actualizacion = pool.get('conector.actualizacion')
        ids = Transaction().context['active_ids']
        #Se agrega un nombre unico a la advertencia
        warning_name = 'warning_delete_import_records'
        if Warning.check(warning_name):
            raise UserWarning(warning_name, "Los registros de la actualización serán eliminados.")
        for actualizacion in Actualizacion.browse(ids):
            actualizacion.logs = 'logs...'
            actualizacion.save()
        return 'end'

    def end(self):
        return 'reload'

# Asistente encargado de asignarle a las lineas de los asientos el tercero requerido
class MoveFixParty(Wizard): # ACTUALIZAR PARA SOLUCIONAR ASIENTOS DE CUALLQUIER ORIGEN
    'Move Fix Party'
    __name__ = 'account.move.fix_party_account'
    start_state = 'fix_move'
    fix_move = StateTransition()

    def transition_fix_move(self):
        pool = Pool()
        Warning = pool.get('res.user.warning')
        Move = pool.get('account.move')
        move_line_table = Table('account_move_line')
        cursor = Transaction().connection.cursor()
        warning_name = 'warning_fix_party_account'
        if Warning.check(warning_name):
            raise UserWarning(warning_name, "A continuación se asignara a las lineas de los asientos (ORIGEN=FACTURA) el tercero de la factura, en las cuentas que lo requieran.")
        ids = Transaction().context['active_ids']
        if ids:
            for move in Move.browse(ids):
                if move.origin and move.origin.__name__ == 'account.invoice':
                    for movel in move.lines:
                        if movel.account.party_required and not movel.party:
                            cursor.execute(*move_line_table.update(
                                columns=[move_line_table.party],
                                values=[move.origin.party.id],
                                where=move_line_table.id == movel.id)
                            )
                            print(move.number)
                        # Proceso contrario
                        #if not movel.account.party_required and movel.party:
                        #    cursor.execute(*move_line_table.update(
                        #        columns=[move_line_table.party],
                        #        values=[None],
                        #        where=move_line_table.id == movel.id)
                        #    )
                        #    print(move.number)
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

#Asistente para eliminar tipos en cuentas padres
class DeleteAccountType(Wizard):
    'Delete Account Type'
    __name__ = 'account.delete_account_type'
    start_state = 'delete_account_type'
    delete_account_type = StateTransition()

    def transition_delete_account_type(self):
        pool = Pool()
        Account = pool.get('account.account')
        Warning = pool.get('res.user.warning')
        ids = Transaction().context['active_ids']
        warning_name = 'warning_delete_account_type'
        if Warning.check(warning_name):
            raise UserWarning(warning_name, "Se van a quitar los tipos a las cuentas que lo tenga y que tengan hijos.")
        to_delete = []
        if ids:
            for account in Account.browse(ids):
                to_delete.append(account)
        Account.delete_account_type(to_delete)
        return 'end'
    
    def end(self):
        return 'reload'


#Asistente para eliminar tipos en cuentas padres
class CheckImportedDoc(Wizard):
    'Check Imported Documnets'
    __name__ = 'conector.actualizacion.check_imported'
    start_state = 'check_imported'
    check_imported = StateTransition()

    def transition_check_imported(self):
        pool = Pool()
        Actualizacion = pool.get('conector.actualizacion')
        Actualizacion.revisa_secuencia_imp('sale_sale')
        return 'end'


class MarkImportMulti(Wizard):
    'Check Imported Documnets'
    __name__ = 'account.multirevenue.mark_rimport'
    start_state = 'mark_import'
    mark_import = StateTransition()

    def transition_mark_import(self):
        pool = Pool()
        MultiRevenue = pool.get('account.multirevenue')
        ids = Transaction().context['active_ids']
        to_mark = []
        if ids:
            for multingreso in MultiRevenue.browse(ids):
                to_mark.append(multingreso)
        MultiRevenue.mark_rimport(to_mark)
        return 'end'

    def end(self):
        return 'reload'