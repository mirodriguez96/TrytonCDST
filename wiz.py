from trytond.model import ModelView
from trytond.wizard import Wizard, StateView, StateTransition, StateAction, Button

__all__ = [
    'CargarDatos',
    'CargarDatosParameters',
    ]


class CargarDatos(Wizard):
    'CargarDatos'
    __name__ = 'mimporta.tercero.cargar_datos'

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
