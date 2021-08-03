from trytond.model import ModelView
from trytond.wizard import Wizard, StateView, StateTransition, StateAction, Button

__all__ = [
    'ActualizarVentas',
    'CargarDatosParameters',
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
"""
    start_state = 'parameters'
    parameters = StateView('mimporta.tercero.cargar_datos.parameters',
        'mimporta.cargar_datos_parameters_view_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Create', 'create_exemp', 'tryton-go-next',
                default=True)])
    create_exemp = StateTransition()
    open_exemp = StateAction('mimporta.act_tercero')



class CargarDatosParameters(ModelView):
    'CargarDatosParameters'
    __name__ = 'mimporta.tercero.cargar_datos.parameters'
"""