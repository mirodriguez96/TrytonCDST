from decimal import Decimal
from trytond.model import ModelView, fields
from trytond.wizard import Wizard, StateTransition, StateView, Button
from trytond.pool import Pool
from trytond.transaction import Transaction
from trytond.exceptions import UserError, UserWarning
from sql import Table
import datetime

_EXPORTADO = [
    ('N', '(N) SIN IMPORTAR'),
    ('E', '(E) EXCEPCION'),
    ('X', '(X) NO IMPORTAR'),
    ('T', '(T) IMPORTADO')
]

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

        # Invoice = pool.get('account.invoice')
        # invoices = Invoice.search([
        #     ('number', 'like', '401-%'),
        #     ('state', '=', 'draft')
        #     ])
        # print(invoices)
        # Sale = pool.get('sale.sale')
        # for invoice in invoices:
        #     sale, = Sale.search([('number', '=', invoice.number)])
        #     print(invoice, sale)
        #     Sale.post_invoices(sale)

        cursor = Transaction().connection.cursor()
        sale_table = Table('sale_sale')
        Sale = pool.get('sale.sale')
        Config = pool.get('conector.configuration')
        start_date = datetime.datetime(2023,1,4,21)
        end_date = datetime.datetime(2023,1,7)
        # Reimporta ventas sin impuesto
        cursor.execute(*sale_table.select(sale_table.id,
            where= (sale_table.create_date >= start_date) & (sale_table.create_date < end_date) & (sale_table.id_tecno != None) & (sale_table.tax_amount_cache == Decimal('0.0'))
            ))
        for sale_id in cursor.fetchall():
            sale = Sale(sale_id[0])
            id_tecno = sale.id_tecno
            lista = id_tecno.split('-')
            query = "SELECT * FROM dbo.Documentos WHERE sw="+lista[0]+" AND tipo="+lista[1]+" AND numero_documento="+lista[2]
            datas = Config.get_data(query)
            for data in datas:
                if data.Valor_impuesto != Decimal('0.0') or data.Impuesto_Consumo != Decimal('0.0'):
                    print(id_tecno)
                    Sale.delete_imported_sales([sale])
            Transaction().connection.commit()

        return 'end'

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
                move = Move(move_id[0])
                for line in move.lines:
                    if line.account.party_required and not line.party:
                        cursor.execute(*move_line_table.update(
                            columns=[move_line_table.party],
                            values=[move.origin.party.id],
                            where=move_line_table.id == line.id)
                        )
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