from trytond.wizard import Wizard, StateTransition
from trytond.pool import Pool
from trytond.transaction import Transaction
from trytond.exceptions import UserError, UserWarning
from sql import Table


class FixBugsConector(Wizard):
    'Fix Bugs Conector'
    __name__ = 'conector.configuration.fix_bugs_conector'
    start_state = 'fix_bugs_conector'
    fix_bugs_conector = StateTransition()

    def transition_fix_bugs_conector(self):
        # pool = Pool()
        # Warning = pool.get('res.user.warning')
        # Invoice = pool.get('account.invoice')
        # Sale = pool.get('sale.sale')
        # PaymentLine = Pool().get('account.invoice-account.move.line')
        # warning_name = 'warning_fix_bugs_conector'
        # if Warning.check(warning_name):
        #     raise UserWarning(warning_name, "No continue si desconoce el funcionamiento interno del asistente.")
        # # invoices = Invoice.search([('amount_to_pay_today', '>', 0), ('amount_to_pay_today', '<', 500)])
        # # for inv in invoices:
        # #     print(inv)
        # # return 'end'
        # sales = Sale.search([('id_tecno', 'like', '2-%')])
        # print(len(sales))
        # for sale in sales:
        #     if sale.invoice and sale.invoice.state == 'posted':
        #         invoice = sale.invoice
        #         origin_invoice = Invoice.search([('number', '=', invoice.reference)])
        #         if not origin_invoice:
        #             #print(invoice)
        #             continue
        #         origin_invoice, = origin_invoice
        #         # if not invoice.original_invoice:
        #         #     cursor = Transaction().connection.cursor()
        #         #     cursor.execute("UPDATE account_invoice SET original_invoice = "+str(origin_invoice.id)+" WHERE id = "+str(invoice.id))
        #         if origin_invoice.state == 'posted':
        #             cruzado = False
        #             for payment_line in origin_invoice.payment_lines:
        #                 for ml in invoice.move.lines:
        #                     if payment_line == ml:
        #                         cruzado = True
        #             if not cruzado and invoice.original_invoice and (origin_invoice.amount_to_pay + invoice.amount_to_pay != 0):
        #                 paymentline = PaymentLine()
        #                 paymentline.invoice = origin_invoice
        #                 paymentline.invoice_account = origin_invoice.account
        #                 paymentline.invoice_party = origin_invoice.party
        #                 for ml in invoice.move.lines:
        #                     if ml.account.type.receivable:
        #                         paymentline.line = ml
        #                 paymentline.save()
        #             print(invoice)
        #             Invoice.reconcile_invoice(invoice)
        #     Transaction().connection.commit()
        return 'end'

class VoucherMoveUnreconcile(Wizard):
    'Voucher Move Unreconcile'
    __name__ = 'account.move.voucher_unreconcile'
    start_state = 'do_unreconcile'
    do_unreconcile = StateTransition()

    def transition_do_unreconcile(self):
        pool = Pool()
        Voucher = pool.get('account.voucher')
        ids_ = Transaction().context['active_ids']
        if ids_:
            vouchers = Voucher.browse(ids_)
            Voucher.unreconcilie_move_voucher(vouchers)
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
            if voucher.number and '-' in voucher.number and voucher.id_tecno:
                to_delete.append(voucher)
            else:
                raise UserError("Revisar el número del comprobante (tipo-numero): ")
        Voucher.delete_imported_vouchers(to_delete)
        return 'end'

    def end(self):
        return 'reload'

class ForceDraftVoucher(Wizard):
    'Force Draft Voucher'
    __name__ = 'account.voucher.force_draft_voucher'
    start_state = 'do_force'
    do_force = StateTransition()

    def transition_do_force(self):
        pool = Pool()
        Warning = pool.get('res.user.warning')
        Voucher = pool.get('account.voucher')
        ids = Transaction().context['active_ids']
        #Se agrega un nombre unico a la advertencia
        warning_name = 'warning_force_draft_voucher'
        if Warning.check(warning_name):
            raise UserWarning(warning_name, "Los comprobantes debieron ser desconciliado primero.")
        to_force = []
        for voucher in Voucher.browse(ids):
            to_force.append(voucher)
        Voucher.force_draft_voucher(to_force)
        return 'end'


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
            raise UserWarning(warning_name, "A continuación se asignara a las lineas de los asientos el tercero de la factura (ORIGEN=FACTURA), en las cuentas que lo requieran.")
        ids = Transaction().context['active_ids']
        if ids:
            cursor.execute("SELECT id FROM account_move WHERE origin LIKE 'account.invoice,%'")
            result = cursor.fetchall()
            if not result:
                return
            for move_id in result:
                #print(move_id[0])
                move = Move(move_id[0])
                #if move.origin and move.origin.__name__ == 'account.invoice':
                for movel in move.lines:
                    if movel.account.party_required and not movel.party:
                        cursor.execute(*move_line_table.update(
                            columns=[move_line_table.party],
                            values=[move.origin.party.id],
                            where=move_line_table.id == movel.id)
                        )
                        #print(move.number)
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

# Asistente encargado de desconciliar los asientos de los comprobantes creados por el multi-ingreso
class UnreconcilieMulti(Wizard):
    'Unreconcilie Multi'
    __name__ = 'account.multirevenue.unreconcilie_multi'
    start_state = 'unreconcilie_multi'
    unreconcilie_multi = StateTransition()

    def transition_unreconcilie_multi(self):
        pool = Pool()
        MultiRevenue = pool.get('account.multirevenue')
        Voucher = pool.get('account.voucher')
        ids = Transaction().context['active_ids']
        if ids:
            for multi in MultiRevenue.browse(ids):
                vouchers = Voucher.search([('reference', '=', multi.code)])
                Voucher.unreconcilie_move_voucher(vouchers)
        return 'end'

# Asistente encargado de marcar el multi-ingreso (documento) para re-importar y elimina los vouchers (comprobantes) creados
class MarkImportMulti(Wizard):
    'Check Imported Documnets'
    __name__ = 'account.multirevenue.mark_rimport'
    start_state = 'mark_import'
    mark_import = StateTransition()

    def transition_mark_import(self):
        pool = Pool()
        Warning = pool.get('res.user.warning')
        MultiRevenue = pool.get('account.multirevenue')
        warning_name = 'warning_mark_rimport_multirevenue'
        if Warning.check(warning_name):
            raise UserWarning(warning_name, "Primero se debe desconciliar los asientos de los multi-ingresos (Desconciliar Asientos Multi-ingreso)")
        ids = Transaction().context['active_ids']
        if ids:
            multingresos = MultiRevenue.browse(ids)
            MultiRevenue.mark_rimport(multingresos)
        return 'end'

    def end(self):
        return 'reload'