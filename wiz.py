from trytond.model import ModelView, fields
from trytond.wizard import Wizard, StateTransition, StateView, Button
from trytond.pool import Pool
from trytond.transaction import Transaction
from trytond.exceptions import UserError, UserWarning
from sql import Table
import datetime


class FixBugsConector(Wizard):
    'Fix Bugs Conector'
    __name__ = 'conector.configuration.fix_bugs_conector'
    start_state = 'fix_bugs_conector'
    fix_bugs_conector = StateTransition()

    def transition_fix_bugs_conector(self):
        pool = Pool()
        Warning = pool.get('res.user.warning')
        warning_name = 'warning_fix_bugs_conector'
        if Warning.check(warning_name):
            raise UserWarning(warning_name, "No continue si desconoce el funcionamiento interno del asistente.")
        Invoice = pool.get('account.invoice')
        MoveLine = pool.get('account.move.line')

        # Shipment = pool.get('stock.shipment.out')
        # shipments = Shipment.search([('state', '=', 'waiting')])
        # print(len(shipments))
        # for shipment in shipments:
        #     print(shipment)
        #     with Transaction().set_context(_skip_warnings=True):
        #         Shipment.pick([shipment])
        #         Shipment.pack([shipment])
        #         Shipment.done([shipment])
        #     Transaction().connection.commit()
        
        # Procesar facturas que su estado = contabilizado y por pagar = 0
        # invoices = Invoice.search([('state', '=', 'posted'), ('payment_lines', '!=', None)])
        # print(len(invoices))
        # for inv in invoices:
        #     if inv.amount_to_pay == 0:
        #         print(inv)
        #         reconcile_invoice = [l for l in inv.payment_lines if not l.reconciliation] 
        #         reconcile_invoice.extend([l for l in inv.lines_to_pay if not l.reconciliation])
        #         if reconcile_invoice:
        #             MoveLine.reconcile(reconcile_invoice)
        #         with Transaction().set_context(_skip_warnings=True):
        #             Invoice.process([inv])
        #         Transaction().connection.commit()

        # Procesamiento de devoluciones y coinciliación de facturas
        domain_invoice = [
            ('type', '=', 'out'),
            ('invoice_type', '!=', '91'),
            ('invoice_type', '!=', '92'),
            ('state', '=', 'posted'),
            ('original_invoice', '!=', None),
            ('original_invoice.state', '=', 'posted')
        ]
        invoices = Invoice.search(domain_invoice)
        print(len(invoices))
        for inv in invoices:
            for lp in inv.lines_to_pay:
                if lp not in inv.original_invoice.payment_lines:
                    with Transaction().set_context(_skip_warnings=True):
                        print(inv.original_invoice)
                        if inv.original_invoice.payment_lines:
                            payment_lines = list(inv.original_invoice.payment_lines)
                            if lp.credit <= inv.original_invoice.amount_to_pay:
                                payment_lines.append(lp)
                            else:
                                print(f"Revisar devolucion {inv}")
                                continue
                        else:
                            payment_lines = [lp]
                        inv.original_invoice.payment_lines = payment_lines
                        Invoice.save([inv.original_invoice])
                        if inv.original_invoice.amount_to_pay == 0:
                            reconcile_invoice = [l for l in inv.original_invoice.payment_lines if not l.reconciliation] 
                            reconcile_invoice.extend([l for l in inv.original_invoice.lines_to_pay if not l.reconciliation])
                            if reconcile_invoice:
                                MoveLine.reconcile(reconcile_invoice)
                        Invoice.process([inv.original_invoice])
                        Invoice.process([inv])
            Transaction().connection.commit()

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

# Asistente encargado de asignarle a las lineas de los asientos, el tercero requerido
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


# Asistente encargado de revertir las producciones
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

# Asistente para eliminar tipos en cuentas padres
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


# Asistente para eliminar tipos en cuentas padres
class CheckImportedDoc(Wizard):
    'Check Imported Documnets'
    __name__ = 'conector.actualizacion.check_imported'
    start_state = 'check_imported'
    check_imported = StateTransition()

    def transition_check_imported(self):
        pool = Pool()
        Actualizacion = pool.get('conector.actualizacion')
        ids = Transaction().context['active_ids']
        for actualizacion in Actualizacion.browse(ids):
            if actualizacion.name == 'VENTAS':
                Actualizacion.revisa_secuencia_imp('sale_sale', [1, 2], actualizacion.name)
            elif actualizacion.name == 'COMPRAS':
                Actualizacion.revisa_secuencia_imp('purchase_purchase', [3, 4], actualizacion.name)
            elif actualizacion.name == 'COMPROBANTES DE INGRESO':
                Actualizacion.revisa_secuencia_imp('account_voucher', [5], actualizacion.name)
            elif actualizacion.name == 'COMPROBANTES DE EGRESO':
                Actualizacion.revisa_secuencia_imp('account_voucher', [6], actualizacion.name)
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

# Vista encargada de solicitar la información necesaria para el asistente de ajuste a las facturas
class CreateAdjustmentNotesParameters(ModelView):
    'Create Exemplaries Parameters'
    __name__ = 'account.note.create_adjustment_note.parameters'
    invoice_type = fields.Selection([('in', 'Proveedor'), ('out', 'Cliente')], 'Invoice type', required=True)
    adjustment_account = fields.Many2One('account.account', 'Adjustment account', domain=[('type', '!=', None)], required=True)
    analytic_account = fields.Char('Analytic account')

# Asistente encargado de crear las notas contables que realizaran el ajuste a las facturas con salod menor a 600 pesos
class CreateAdjustmentNotes(Wizard):
    'Create Exemplaries'
    __name__ = 'account.note.create_adjustment_note'
    start = StateView('account.note.create_adjustment_note.parameters',
            'conector.view_adjustment_note_form', [
                Button('Cancel', 'end', 'tryton-cancel'),
                Button('Add', 'add_note', 'tryton-ok', default=True),
            ])
    add_note = StateTransition()

    def transition_add_note(self):
        pool = Pool()
        Note = pool.get('account.note')
        Line = pool.get('account.note.line')
        data = {
            'invoice_type': self.start.invoice_type,
            'adjustment_account': self.start.adjustment_account,
            'analytic_account': None
        }
        config = pool.get('account.voucher_configuration')(1)
        if config.adjustment_amount and config.adjustment_amount > 0:
            data['amount'] = config.adjustment_amount
        else:
            raise UserError("msg_adjustment_amount", "has to be greater than zero")
        if hasattr(Line, 'analytic_account'):
            AnalyticAccount = pool.get('analytic_account.account')
            if self.start.analytic_account:
                analytic_account, = AnalyticAccount.search([('code', '=', self.start.analytic_account)])
                data['analytic_account'] = analytic_account
            else:
                raise UserError("msg_analytic_account_missing")
        Note.create_adjustment_note(data)
        return 'end'
