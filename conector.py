from trytond.model import ModelSQL, ModelView, fields
import datetime
from trytond.pool import Pool

__all__ = [
    'Actualizacion',
    ]

class Actualizacion(ModelSQL, ModelView):
    'Actualizacion'
    __name__ = 'conector.actualizacion'

    name = fields.Char('Update', required=True, readonly=True)
    #quantity = function(fields.Integer('Quantity'), 'getter_quantity')
    #imported = function(fields.Integer('Imported'), 'getter_imported')
    #not_imported = function(fields.Integer('Not imported'), 'getter_not_imported')
    logs = fields.Text("Logs", readonly=True)

    @classmethod
    def add_logs(cls, actualizacion, logs):
        now = datetime.datetime.now() - datetime.timedelta(hours=5)
        registos = actualizacion.logs
        for log in logs:
            registos += f"\n{now} - {log}"
        actualizacion.logs = registos
        actualizacion.save()
        
    def getter_quantity(self, name):
        if not self.name:
            return None
        Config = Pool().get('conector.configuration')
        conexion = Config()
        consult = "SELECT * FROM "

    def getter_imported(self, name):
        if not self.name:
            return None
        return 0

    def getter_imported(self, name):
        pass
        