#from trytond.model import ModelView
from trytond.wizard import Wizard, StateTransition#, StateView, StateAction, Button
import datetime
from trytond.model import ModelView, fields
from trytond.pool import Pool, PoolMeta
from trytond.transaction import Transaction
#from trytond.pyson import PYSONEncoder
from trytond.exceptions import UserError


__all__ = [
    'ActualizarVentas',
    'CargarVentas',
    ]


#Nota: el uso principal de los asistentes suele ser realizar acciones basadas en alguna entrada del usuario.
class ActualizarVentas(Wizard):
    'ActualizarVentas'
    __name__ = 'conector.actualizar_ventas'
    start_state = 'actualizar_venta'
    actualizar_venta = StateTransition()

    def transition_actualizar_venta(self=None):
        print("--------------RUN WIZARD VENTAS--------------")
        return 'end'

"""
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

