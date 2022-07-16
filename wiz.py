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
        Invoice = pool.get('account.invoice')
        Sale = pool.get('sale.sale')
        PaymentLine = Pool().get('account.invoice-account.move.line')
        MoveLine = pool.get('account.move.line')
        warning_name = 'warning_fix_bugs_conector'
        if Warning.check(warning_name):
            raise UserWarning(warning_name, "No continue si desconoce el funcionamiento interno del asistente.")
        
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
        # return 'end'

        #Procesamiento devoluciones y coinciliación de facturas
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
                    print(inv.original_invoice)
                    payment_lines = list(inv.original_invoice.payment_lines)
                    payment_lines.append(lp)
                    inv.original_invoice.payment_lines = payment_lines
                    reconcile_invoice = [l for l in inv.original_invoice.payment_lines if not l.reconciliation] 
                    reconcile_invoice.extend([l for l in inv.original_invoice.lines_to_pay if not l.reconciliation])
                    if reconcile_invoice:
                        MoveLine.reconcile(reconcile_invoice)
                    with Transaction().set_context(_skip_warnings=True):
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
    analytic_account = fields.Many2One('analytic_account.account', 'Analytic account', required=True)

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
        Period = pool.get('account.period')
        Config = pool.get('account.voucher_configuration')
        Note = pool.get('account.note')
        Line = pool.get('account.note.line')
        Warning = pool.get('res.user.warning')
        Invoice = pool.get('account.invoice')
        invoices = Invoice.search([('type', '=', self.start.invoice_type), ('state', '=', 'posted')])
        inv_adjustment = []
        for inv in invoices:
            if inv.amount_to_pay < 600 and inv.amount_to_pay > 0:
                inv_adjustment.append(inv)
        if not inv_adjustment:
            return 'end'
        warning_name = 'warning_create_adjustment_note'
        if Warning.check(warning_name):
            raise UserWarning(warning_name, f"Cantidad de facturas a realizar el ajuste: {len(inv_adjustment)}")
        # Se procesa las facturas que cumplan con la condicion
        config = Config.get_configuration()
        for inv in inv_adjustment:
            lines_to_create = []
            print(inv)
            operation_center = None
            inv_account = inv.account
            for ml in inv.move.lines:
                if ml.account == inv_account and (ml.account.type.payable or ml.account.type.receivable):
                    _line = Line()
                    _line.debit = ml.credit
                    _line.credit = ml.debit
                    _line.party = ml.party
                    _line.account = ml.account
                    _line.description = ml.description
                    _line.move_line = ml
                    _line.analytic_account = self.start.analytic_account
                    if hasattr(ml, 'operation_center') and ml.operation_center:
                        operation_center = ml.operation_center
                        _line.operation_center = ml.operation_center
                    lines_to_create.append(_line)
            last_date = inv.invoice_date
            for pl in inv.payment_lines:
                _line = Line()
                _line.debit = pl.credit
                _line.credit = pl.debit
                _line.party = pl.party
                _line.account = pl.account
                _line.description = pl.description
                _line.move_line = pl
                _line.analytic_account = self.start.analytic_account
                if last_date:
                    if last_date < ml.date:
                        last_date = ml.date
                else:
                    last_date = ml.date
                if operation_center:
                    _line.operation_center = operation_center
                lines_to_create.append(_line)
            amount_to_pay = inv.amount_to_pay
            inv.payment_lines = []
            inv.save()
            # Se crea la línea del ajuste
            _line = Line()
            _line.party = inv.party
            _line.account = self.start.adjustment_account
            _line.description = f"AJUSTE FACTURA {inv.number}"
            if self.start.invoice_type == 'out':
                _line.debit = amount_to_pay
                _line.credit = 0
            else:
                _line.debit = 0
                _line.credit = amount_to_pay
            if operation_center:
                _line.operation_center = operation_center
            _line.analytic_account = self.start.analytic_account
            lines_to_create.append(_line)
            note = Note()
            period = Period.search([('state', '=', 'open'), ('start_date', '>=', last_date), ('end_date', '<=', last_date)])
            if period:
                note.date = last_date
            else:
                note.date = datetime.date.today()
            note.journal = config.default_journal_note
            note.description = f"AJUSTE FACTURA {inv.number}"
            note.lines = lines_to_create
            Note.save([note])
            Note.post([note])
            Transaction().connection.commit()
        return 'end'
