from decimal import Decimal
from trytond.model import ModelView, fields
from trytond.wizard import Wizard, StateTransition, StateView, Button
from trytond.pool import Pool
from trytond.transaction import Transaction
from trytond.exceptions import UserError, UserWarning
from sql import Table

_EXPORTADO = [
    ('N', '(N) SIN IMPORTAR'),
    ('E', '(E) EXCEPCION'),
    ('X', '(X) NO IMPORTAR'),
    ('T', '(T) IMPORTADO')
]

ZERO = Decimal('0.0')


class DocumentsForImportParameters(ModelView):
    'Documents For Import Parameters'
    __name__ = 'conector.configuration.documents_for_import_parameters'
    tipo = fields.Char('Tipo', required=True)
    numero = fields.Char('Número', required=True)
    exportado = fields.Selection(_EXPORTADO, 'Exportado', required=True)

    @classmethod
    def default_exportado(cls):
        return 'N'

class DocumentsForImport(Wizard):
    'Documents For Import'
    __name__ = 'conector.configuration.documents_for_import'

    start = StateView('conector.configuration.documents_for_import_parameters',
    'conector.documents_for_import_parameters_view_form', [
        Button('Cancel', 'end', 'tryton-cancel'),
        Button('Mark', 'documents_for_import', 'tryton-go-next',
            default=True)])
    documents_for_import = StateTransition()

    def transition_documents_for_import(self):
        pool = Pool()
        Configuration = pool.get('conector.configuration')
        cnx, = Configuration.search([], order=[('id', 'DESC')], limit=1)
        tipo = self.start.tipo
        numero = self.start.numero
        exportado = self.start.exportado
        query = "UPDATE dbo.Documentos SET exportado = '"+exportado+"' WHERE tipo = "+tipo+" and Numero_documento = "+numero
        #print(query)
        cnx.set_data(query)
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
        # Actualizacion = pool.get('conector.actualizacion')
        Log = pool.get('conector.log')
        ids = Transaction().context['active_ids']
        #Se agrega un nombre unico a la advertencia
        warning_name = 'warning_delete_import_records'
        if Warning.check(warning_name):
            raise UserWarning(warning_name, "Los registros de la actualización serán eliminados.")
        # actualizacion_id = []
        # for actualizacion in Actualizacion.browse(ids):
        #     if actualizacion.id not in actualizacion_id:
        #         actualizacion_id.append(actualizacion.id)
        if ids:
            to_delete = Log.search([('actualizacion.id', 'in', ids)])
            Log.delete(to_delete)
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
                move = Move(move_id[0])
                for line in move.lines:
                    if line.account.party_required and not line.party:
                        cursor.execute(*move_line_table.update(
                            columns=[move_line_table.party],
                            values=[move.origin.party.id],
                            where=move_line_table.id == line.id)
                        )
        return 'end'


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
        if ids:
            accounts = Account.browse(ids)
            Account.delete_account_type(accounts)
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
            Actualizacion.revisa_secuencia_imp(actualizacion.name)
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
    date_start = fields.Date('Date initial',required=True)
    date_finish = fields.Date('Date end',required=True)
    date = fields.Date('Date for notes',required=True)

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
            'analytic_account': None,
            'date': self.start.date,
            'date_start': self.start.date_start,
            'date_finish': self.start.date_finish
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


class AddCenterOperationLineP(ModelView):
    'Add Operation Center Parameters'
    __name__ = 'account.note.add_operation_center.parameters'
    code = fields.Char('Operation center code')


class AddCenterOperationLine(Wizard):
    'Add Operation Center'
    __name__ = 'account.note.add_operation_center'
    start = StateView('account.note.add_operation_center.parameters',
            'conector.view_add_operation_center_form', [
                Button('Cancel', 'end', 'tryton-cancel'),
                Button('Add', 'operation_center', 'tryton-ok', default=True),
            ])
    operation_center = StateTransition()

    def transition_operation_center(self):
        pool = Pool()
        Note = pool.get('account.note')
        Line = pool.get('account.note.line')
        OperationCenter = pool.get('company.operation_center')
        operation_center = OperationCenter.search([('code', '=', self.start.code)])
        if not operation_center:
            raise UserError("msg_operation_center_not_found")
        operation_center, = operation_center
        ids_ = Transaction().context['active_ids']
        for note in Note.browse(ids_):
            _lines = []
            for line in note.lines:
                if not line.operation_center:
                    line.operation_center = operation_center
                _lines.append(line)
            Line.save(_lines)
        return 'end'


class ReimportExcepcionDocument(Wizard):
    __name__ = 'conector.actualizacion.reimport_excepcion'
    start_state = 'run'
    run = StateTransition()

    def transition_run(self):
        pool = Pool()
        Warning = pool.get('res.user.warning')
        warning_name = 'warning_fix_bugs_conector'
        if Warning.check(warning_name):
            raise UserWarning(warning_name, "Se van a marcar los documentos con excepción para ser importados de nuevo")

        Actualizacion = pool.get('conector.actualizacion')
        Config = pool.get('conector.configuration')
        ids_ = Transaction().context['active_ids']
        cond = ""
        for actualizacion in Actualizacion.browse(ids_):
            if actualizacion.name == 'VENTAS':
                cond += "AND (sw = 1 or sw = 2) "
            elif actualizacion.name == 'COMPRAS':
                cond += "AND (sw = 3 or sw = 4) "
            elif actualizacion.name == 'COMPROBANTES DE INGRESO':
                cond += "AND sw = 5 "
            elif actualizacion.name == 'COMPROBANTES DE EGRESO':
                cond += "AND sw = 6 "
            elif actualizacion.name == 'PRODUCCION':
                cond += "AND sw = 12 "
        if cond:
            query = "UPDATE dbo.Documentos SET exportado = 'N' WHERE exportado = 'E' "+cond
            Config.set_data(query)
        return 'end'

class ConfirmLinesBankstatement(Wizard):
    __name__ = 'account.bank_statement.confirm_bank_statement_lines'
    start_state = 'run'
    run = StateTransition()

    def transition_run(self):
        pool = Pool()
        BankStatement = pool.get('account.bank_statement')
        BankStatementLines = pool.get('account.bank_statement.line')
        ids = Transaction().context['active_ids']
        if ids:
            lineas = []
            for Statement in BankStatement.browse(ids):
                for line in Statement.lines:
                    if line.state != 'confirmed':
                        lineas.append(line)
            BankStatementLines.confirm(lineas)
        return 'end'


class GroupMultirevenueLines(Wizard):
    __name__ = 'account.bank_statement.group_multirevenue_lines'
    start_state = 'run'
    run = StateTransition()

    def transition_run(self):
        pool = Pool()
        BankStatement = pool.get('account.bank_statement')
        BankStatementLine = pool.get('account.bank_statement.line')
        ids = Transaction().context['active_ids']
        if ids:
            for statement in BankStatement.browse(ids):
                lines = BankStatementLine.search([
                    ('statement', '=', statement.id),
                    ('statement.state', '=', 'draft'),
                    ('description', 'like', 'MULTI-INGRESO%')])
                to_group = {}
                lines_group = {}
                to_save = []
                to_delete = []
                for line in lines:
                    # payment_mode = line.bank_move_lines[0].move_origin.payment_mode
                    reference = line.bank_move_lines[0].move_origin.reference
                    # key = (reference, payment_mode)
                    if reference not in to_group.keys():
                        to_group[reference] = list(line.bank_move_lines)
                        lines_group[reference] = line
                    else:
                        to_group[reference] += list(line.bank_move_lines)
                        to_delete.append(line)
                for reference, lines in to_group.items():
                    description = f"MULTI-INGRESO {reference}"
                    lines_group[reference].description = description
                    lines_group[reference].bank_move_lines = lines
                    to_save.append(lines_group[reference])

                BankStatementLine.save(to_save)
                BankStatementLine.delete(to_delete)
        return 'end'

class GroupDatafonoLines(Wizard):
    __name__ = 'account.bank_statement.group_datafono_lines'
    start_state = 'run'
    run = StateTransition()

    def transition_run(self):
        pool = Pool()
        BankStatement = pool.get('account.bank_statement')
        BankStatementLine = pool.get('account.bank_statement.line')
        ids = Transaction().context['active_ids']
        if ids:
            for statement in BankStatement.browse(ids):
                lines = BankStatementLine.search([
                    ('statement', '=', statement.id),
                    ('statement.state', '=', 'draft'),])
                    # ('description', 'like', 'VENTA-POS%')
                to_group = {}
                lines_group = {}
                to_save = []
                to_delete = []
                for line in lines:
                    if line.bank_move_lines[0].move_origin and str(line.bank_move_lines[0].move_origin).split(',')[0] in ['account.statement']:
                        reference = str(line.bank_move_lines[0].move_origin.journal.name)+'-'+str(line.bank_move_lines[0].move_origin.date)
                        # key = (reference, payment_mode)
                        if reference not in to_group.keys():
                            to_group[reference] = list(line.bank_move_lines)
                            lines_group[reference] = line
                        else:
                            to_group[reference] += list(line.bank_move_lines)
                            to_delete.append(line)
                for reference, lines in to_group.items():
                    description = reference
                    lines_group[reference].description = description
                    lines_group[reference].bank_move_lines = lines
                    to_save.append(lines_group[reference])

                BankStatementLine.save(to_save)
                BankStatementLine.delete(to_delete)
        return 'end'