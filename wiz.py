from trytond.model import ModelView
from trytond.wizard import Wizard, StateView, StateTransition, StateAction, Button

__all__ = [
    'ActualizarVentas',
    'CargarVentas',
    ]


class ActualizarVentas(Wizard):
    'ActualizarVentas'

    """
    Los asistentes __name__ normalmente deben estar compuestos
    por el modelo en el que trabajará el asistente (conector.terceros), 
    luego la acción que se realizará (actualizar_ventas). 
    La acción suele ser un verbo.
    """
    __name__ = 'conector.terceros.actualizar_ventas'

    print('Ejecutando Asistente')


    start_state = 'parameters'
    parameters = StateView('conector.terceros.cargar_ventas.parameters',
        'conector.cargar_ventas_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Create', 'actualizar_venta', 'tryton-go-next', default=True)])
    actualizar_venta = StateTransition()
    #open_exemp = StateAction('conector.actualizar_venta')



class CargarVentas(ModelView):
    'CargarVentas'
    __name__ = 'conector.terceros.cargar_ventas.parameters'
