from trytond.model import ModelSQL, ModelView, fields
from trytond.transaction import Transaction
from trytond.pool import Pool
from sql import Table
import datetime
from sql.aggregate import Count


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
        registros_list = registos.split('\n')
        for log in logs:
            log = f"{now} - {log}"
            if log not in registros_list:
                registos += f"\n{log}"
        actualizacion.logs = registos
        actualizacion.save()

    @classmethod
    def reset_writedate(cls, name):
        conector_actualizacion = Table('conector_actualizacion')
        cursor = Transaction().connection.cursor()
        #Se elimina la fecha de última modificación para que se actualicen los terceros desde (primer importe) una fecha mayor rango
        cursor.execute(*conector_actualizacion.update(
                columns=[conector_actualizacion.write_date],
                values=[None],
                where=conector_actualizacion.name == name)
            )

    
    #Se consulta en la base de datos de SQLSERVER
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
        else:
            return None
        result = conexion.get_data(consult)
        result = int(result[0][0])
        print(self.name, result)
        return result
        
    #@classmethod
    def getter_imported(self, name):
        cursor = Transaction().connection.cursor()
        if self.name == 'VENTAS':
            cursor.execute("SELECT COUNT(*) FROM sale_sale WHERE id_tecno LIKE '%-%'")
        elif self.name == 'COMPRAS':
            cursor.execute("SELECT COUNT(*) FROM purchase_purchase WHERE id_tecno LIKE '%-%'")
        elif self.name == 'COMPROBANTES':
            cursor.execute("SELECT COUNT(*) FROM account_voucher WHERE id_tecno LIKE '%-%'")
        else:
            return None
        result = cursor.fetchone()[0]
        print(self.name, result)
        if result:
            return result
        return 0

    #@classmethod
    def getter_not_imported(self, name):
        Config = Pool().get('conector.configuration')
        conexion = Config.search([], order=[('id', 'DESC')], limit=1)
        if conexion:
            conexion, = conexion
        fecha = conexion.date
        fecha = fecha.strftime('%Y-%m-%d %H:%M:%S')
        consult = "SET DATEFORMAT ymd SELECT COUNT(*) FROM dbo.Documentos WHERE fecha_hora >= CAST('"+fecha+"' AS datetime) AND exportado != 'T'"
        if self.name == 'VENTAS':
            consult += " AND (sw = 1 or sw = 2)"
        elif self.name == 'COMPRAS':
            consult += " AND (sw = 3 or sw = 4)"
        elif self.name == 'COMPROBANTES':
            consult += " AND (sw = 5 or sw = 6)"
        else:
            return None
        result = conexion.get_data(consult)
        result = int(result[0][0])
        print(self.name, result)
        return result
