#from trytond.model import ModelView
from trytond.wizard import Wizard, StateTransition#, StateView, StateAction, Button
#import datetime
#from trytond.model import ModelView, fields
from trytond.pool import Pool
from trytond.transaction import Transaction
#from trytond.pyson import PYSONEncoder
from trytond.exceptions import UserError, UserWarning


#__all__ = [
#    'ActualizarVentas',
#    'CargarVentas',
#    ]

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

"""
#Nota: el uso principal de los asistentes suele ser realizar acciones basadas en alguna entrada del usuario.

class ActualizarVentas(Wizard):
    'ActualizarVentas'

    #Los asistentes __name__ normalmente deben estar compuestos
    #por el modelo en el que trabajará el asistente (conector.terceros), 
    #luego la acción que se realizará (actualizar_ventas). 
    #La acción suele ser un verbo.

    __name__ = 'conector.terceros.actualizar_ventas'

    #Estado inicial que le pedira al usuario una entrada
    start_state = 'parameters'
    #vista donde se ingresa la entrada, que activa el siguiente estado
    parameters = StateView('conector.terceros.cargar_ventas.parameters',
        'conector.cargar_ventas_view_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Create', 'actualizar_venta', 'tryton-go-next', default=True)])
    #Estado transitorio activado por la entrada del usuario
    actualizar_venta = StateTransition()
    #open_exemp = StateAction('conector.actualizar_venta')


    def default_parameters(self, name):
        #El context es un diccionario que contiene datos sobre el contexto (...) en el que se está ejecutando el código actual.

        #active_model: es el modelo que se muestra actualmente al usuario. En nuestro caso,conector.terceros
        #active_ids: es la lista de los ID de los registros que se seleccionaron cuando se desencadenó la acción
        #active_id: es el primero de esos registros (o el único si solo se seleccionó un registro).
        
        if Transaction().context.get('active_model', '') != 'conector.terceros':
            #generamos un mensaje de error
            #self.raise_user_error('invalid_model')
            raise UserError("You cannot process.", "because…")
        return {
            #'date': datetime.date.today(),
            #'id': Transaction().context.get('active_id'),
            }

    def do_open_exemplaries(self, action):
        #Aquí configuramos la clave pyson_domain para forzar un dominio / restricción en la pestaña,
        #lo que hará que muestre solo los identificadores que coinciden con los elementos que acabamos de crear.
        action['pyson_domain'] = PYSONEncoder().encode([
                ('id', 'in', [x.id for x in self.parameters.exemplaries])])
        return action, {}


class CargarVentas(ModelView):
    'CargarVentas'
    __name__ = 'conector.terceros.cargar_ventas.parameters'

    def transition_actualizar_venta(self):
        if (not self.parameters):
            print('Error')
            raise UserError("You cannot process.", "because…")
            #self.raise_user_error('invalid_date')
        #Si no...
        Exemplary = Pool().get('library.book.exemplary')
        to_create = []
        while len(to_create) < self.parameters.number_of_exemplaries:
            exemplary = Exemplary()
            exemplary.book = self.parameters.book
            exemplary.acquisition_date = self.parameters.acquisition_date
            exemplary.acquisition_price = self.parameters.acquisition_price
            exemplary.identifier = self.parameters.identifier_start + str(
                len(to_create) + 1)
            to_create.append(exemplary)
        Exemplary.save(to_create)
        self.parameters.exemplaries = to_create
        return 'open_exemplaries'
"""

