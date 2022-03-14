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
    quantity = fields.Function(fields.Integer('Quantity'), 'getter_quantity')
    imported = fields.Function(fields.Integer('Imported'), 'getter_imported')
    not_imported = fields.Function(fields.Integer('Not imported'), 'getter_not_imported')
    logs = fields.Text("Logs", readonly=True)


    @classmethod
    def add_logs(cls, actualizacion, logs):
        now = datetime.datetime.now() - datetime.timedelta(hours=5)
        registos = actualizacion.logs
        for log in logs:
            registos += f"\n{now} - {log}"
        actualizacion.logs = registos
        actualizacion.save()
    
    #@classmethod
    def getter_quantity(self, name):
        Config = Pool().get('conector.configuration')
        conexion = Config.search([], order=[('id', 'DESC')], limit=1)
        if conexion:
            conexion, = conexion
        fecha = conexion.date
        fecha = fecha.strftime('%Y-%m-%d %H:%M:%S')
        consult = "SET DATEFORMAT ymd SELECT COUNT(*) FROM dbo.Documentos WHERE fecha_hora >= CAST('"+fecha+"' AS datetime)"
        if self.name == 'VENTAS':
            consult += " AND (sw = 1 or sw = 2)"
        elif self.name == 'COMPRAS':
            consult += " AND (sw = 3 or sw = 4)"
        elif self.name == 'COMPROBANTES':
            consult += " AND (sw = 5 or sw = 6)"
        result = conexion.get_data(consult)
        result = int(result[0][0])
        return result
        
    #@classmethod
    def getter_imported(self, name):
        return 0

    #@classmethod
    def getter_not_imported(self, name):
        return 0
