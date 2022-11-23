#from decimal import Decimal
from trytond.model import ModelView, fields
from trytond.wizard import Wizard, StateTransition, StateView, Button
from trytond.pool import Pool
from trytond.transaction import Transaction
from trytond.exceptions import UserError, UserWarning
from sql import Table
#import datetime

_EXPORTADO = [
    ('N', 'SIN IMPORTAR'),
    ('E', 'EXCEPCION'),
    ('X', 'NO IMPORTAR'),
    ('T', 'IMPORTADO')
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

        Voucher = pool.get('account.voucher')
        numbers = [
        253986,
        253987,
        253988,
        253990,
        253991,
        253992,
        253993,
        253994,
        253996,
        253998,
        253999,
        254000,
        254001,
        254002,
        254003,
        254004,
        254006,
        254007,
        254008,
        254009,
        254010,
        254011,
        254012,
        254013,
        254014,
        254015,
        254016,
        254017,
        254018,
        254019,
        254020,
        254021,
        254022,
        254023,
        254024,
        254025,
        254027,
        254028,
        254029,
        254030,
        254031,
        254032,
        254033,
        254034,
        254035,
        254036,
        254037,
        254038,
        254039,
        254040,
        254041,
        254042,
        254043,
        254044,
        254045,
        254046,
        254047,
        254048,
        254049,
        254050,
        254051,
        254053,
        254054,
        254056,
        254057,
        254058,
        254059,
        254060,
        254061,
        254062,
        254063,
        254064,
        254065,
        254066,
        254074,
        254077,
        254078,
        254079,
        254080,
        254082,
        254083,
        254084,
        254085,
        254086,
        254087,
        254088,
        254089,
        254090,
        254091,
        254092,
        254094,
        254095,
        254096,
        254097,
        254098,
        254099,
        254100,
        254101,
        254102,
        254104,
        254105,
        254106,
        254107,
        254108,
        254109,
        254110,
        254111,
        254113,
        254114,
        254115,
        254118,
        254119,
        254120,
        254121,
        254122,
        254123,
        254154,
        254159,
        254175,
        256136,
        256138,
        256140,
        256141,
        256150,
        256155,
        256156,
        256158,
        256160,
        256162,
        256164,
        256166,
        256167,
        256168,
        256170,
        256171,
        256172,
        256173,
        256174,
        256175,
        256176,
        256177,
        256178,
        256179,
        256180,
        256181,
        256183,
        256184,
        256185,
        256186,
        256187,
        256188,
        256189,
        256190,
        256191,
        256192,
        256193,
        256194,
        256195,
        256196,
        256197,
        256198,
        256199,
        256201,
        256203,
        256205,
        256207,
        256208,
        256209,
        256210,
        256211,
        256212,
        256213,
        256214,
        256215,
        256216,
        256217,
        256218,
        256219,
        256220,
        256221,
        256222,
        256223,
        256224,
        256225,
        256226,
        256227,
        256228,
        256229,
        256230,
        256231,
        256232,
        256233,
        256234,
        256236,
        256238,
        256239,
        256240,
        256241,
        256242,
        256243,
        256244,
        256245,
        256246,
        256247,
        256248,
        256249,
        256250,
        256251,
        256252,
        256253,
        256254,
        256255,
        256256,
        256257,
        256258,
        256259,
        256260,
        256261,
        256262,
        256263,
        256265,
        256266,
        256267,
        256268,
        256269,
        256271,
        256272,
        256273,
        256275,
        256276,
        256277,
        256278,
        256279,
        256280,
        256281,
        256282,
        256283,
        256284,
        256285,
        256287,
        256288,
        258469,
        258470,
        258471,
        258472,
        258473,
        258475,
        258476,
        258477,
        258479,
        258480,
        258482,
        258483,
        258485,
        258486,
        258487,
        258488,
        258489,
        258491,
        258492,
        258493,
        258494,
        258495,
        258496,
        258498,
        258499,
        258500,
        258501,
        258502,
        258503,
        258505,
        258506,
        258507,
        258508,
        258509,
        258511,
        258512,
        258513,
        258514,
        258515,
        258517,
        258518,
        258519,
        258520,
        258521,
        258522,
        258523,
        258526,
        258527,
        258529,
        258530,
        258532,
        258533,
        258538,
        258539,
        258541,
        258543,
        258544,
        258547,
        258549,
        258550,
        258551,
        258552,
        258553,
        258554,
        258555,
        258556,
        258557,
        258558,
        258559,
        258560,
        258561,
        258562,
        258564,
        258566,
        258567,
        258568,
        258570,
        258571,
        258572,
        258573,
        258574,
        258575,
        258576,
        258577,
        258578,
        258579,
        258580,
        258581,
        258583,
        258584,
        258585,
        258586,
        258587,
        258588,
        258589,
        258590,
        258591,
        258592,
        258593,
        258595,
        258598,
        258599,
        258600,
        258601,
        258602,
        258603,
        258604,
        258605,
        258607,
        258608,
        258609,
        258610,
        258611,
        258612,
        258614,
        258616,
        258619,
        258620,
        258621,
        258622,
        258623,
        258624,
        260611,
        260612,
        260613,
        260614,
        260615,
        260616,
        260617,
        260618,
        260619,
        260620,
        260621,
        260622,
        260623,
        260624,
        260625,
        260626,
        260627,
        260628,
        260629,
        260630,
        260632,
        260633,
        260634,
        260635,
        260637,
        260638,
        260639,
        260640,
        260641,
        260643,
        260644,
        260645,
        260646,
        260647,
        260648,
        260649,
        260650,
        260652,
        260653,
        260654,
        260655,
        260656,
        260657,
        260658,
        260659,
        260660,
        260661,
        260662,
        260663,
        260664,
        260665,
        260666,
        260667,
        260668,
        260669,
        260670,
        260671,
        260672,
        260675,
        260676,
        260678,
        260680,
        260682,
        260684,
        260686,
        260687,
        260688,
        260690,
        260691,
        260693,
        260694,
        260695,
        260696,
        260697,
        260698,
        260699,
        260700,
        260702,
        260703,
        260704,
        260705,
        260706,
        260707,
        260708,
        260709,
        260710,
        260711,
        260712,
        260713,
        260714,
        260715,
        260716,
        260717,
        260718,
        260719,
        260721,
        260722,
        260723,
        260724,
        260726,
        260727,
        260728,
        260729,
        260730,
        260731,
        260732,
        260734,
        260736,
        260737,
        260738,
        260740,
        260741,
        260742,
        260794,
        263063,
        263064,
        263065,
        263066,
        263067,
        263068,
        263070,
        263071,
        263072,
        263073,
        263074,
        263075,
        263076,
        263077,
        263078,
        263079,
        263080,
        263081,
        263082,
        263083,
        263084,
        263085,
        263086,
        263087,
        263089,
        263090,
        263091,
        263094,
        263096,
        263097,
        263098,
        263099,
        263100,
        263101,
        263102,
        263103,
        263104,
        263106,
        263107,
        263108,
        263109,
        263112,
        263114,
        263117,
        263118,
        263119,
        263121,
        263122,
        263123,
        263124,
        263125,
        263126,
        263127,
        263128,
        263130,
        263131,
        263132,
        263133,
        263134,
        263135,
        263137,
        263138,
        263140,
        263142,
        263143,
        263145,
        263147,
        263148,
        263149,
        263150,
        263151,
        263152,
        263153,
        263154,
        263155,
        263156,
        263157,
        263158,
        263160,
        263161,
        263162,
        263164,
        263165,
        263166,
        263167,
        263168,
        263169,
        263170,
        263171,
        263173,
        263174,
        263176,
        263177,
        263178,
        263180,
        263181,
        263182,
        263183,
        263184,
        263185,
        263186,
        263187,
        263188,
        263189,
        263190,
        263191,
        263196,
        263197,
        263198,
        263199,
        263200,
        263204,
        263205,
        263206,
        263209,
        263211,
        263212,
        263213,
        263214
        ]
        for number in numbers:
            print(number)
            voucher = Voucher.search([('id_tecno', '=', '5-107-'+str(number))])
            print(voucher)
            if voucher:
                Voucher.unreconcilie_move_voucher(voucher)
                Transaction().connection.commit()
                Voucher.delete_imported_vouchers(voucher)
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
        Button('Create', 'documents_for_import', 'tryton-go-next',
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