from trytond.model import ModelSQL, ModelView, fields
import datetime

__all__ = [
    'Actualizacion',
    ]

class Actualizacion(ModelSQL, ModelView):
    'Actualizacion'
    __name__ = 'conector.actualizacion'

    name = fields.Char('Update', required=True, readonly=True)
    logs = fields.Text("Logs", readonly=True)

    @classmethod
    def add_logs(cls, actualizacion, logs):
        now = datetime.datetime.now() - datetime.timedelta(hours=5)
        registos = actualizacion.logs
        for log in logs:
            registos += f"\n{now} - {log}"
        actualizacion.logs = registos
        actualizacion.save()
        
        