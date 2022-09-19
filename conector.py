from trytond.model import ModelSQL, ModelView, fields
from trytond.transaction import Transaction
from trytond.pool import Pool
from sql import Table
import datetime


class Actualizacion(ModelSQL, ModelView):
    'Actualizacion'
    __name__ = 'conector.actualizacion'

    name = fields.Char('Update', required=True, readonly=True)
    quantity = fields.Function(fields.Integer('Quantity'), 'getter_quantity')
    imported = fields.Function(fields.Integer('Imported'), 'getter_imported')
    exceptions = fields.Function(fields.Integer('Exceptions'), 'getter_exceptions')
    cancelled = fields.Function(fields.Integer('Cancelled'), 'getter_cancelled')
    not_imported = fields.Function(fields.Integer('Not imported'), 'getter_not_imported')
    logs = fields.Text("Logs", readonly=True)


    #Crea o actualiza un registro de la tabla actualización en caso de ser necesario
    @classmethod
    def create_or_update(cls, name):
        Actualizacion = Pool().get('conector.actualizacion')
        actualizacion = Actualizacion.search([('name', '=', name)])
        if actualizacion:
            #Se busca un registro con la actualización
            actualizacion, = actualizacion
        else:
            #Se crea un registro con la actualización
            actualizacion = Actualizacion()
            actualizacion.name = name
            actualizacion.logs = 'logs...'
            actualizacion.save()
        return actualizacion


    @classmethod
    def get_fecha_actualizacion(cls, actualizacion):
        fecha = datetime.date(1,1,1)
        if actualizacion.write_date:
            fecha = (actualizacion.write_date - datetime.timedelta(hours=5))
        elif actualizacion.create_date:
            Date = Pool().get('ir.date')
            create_date = actualizacion.create_date.date()
            if create_date != Date.today():
                fecha = (actualizacion.create_date - datetime.timedelta(hours=5))
        return fecha


    @classmethod
    def add_logs(cls, actualizacion, logs):
        now = datetime.datetime.now() - datetime.timedelta(hours=5)
        logs_result = []
        registros = ""
        if actualizacion.logs:
            registros = actualizacion.logs
            for lr in registros.split('\n'):
                res = lr.split(' - ')
                res.pop(0)
                res = " - ".join(res)
                logs_result.append(res)
        for log in logs:
            if log not in logs_result:
                log = f"\n{now} - {log}"
                registros += log
        actualizacion.logs = registros
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
        conexion, = Config.search([], order=[('id', 'DESC')], limit=1)
        fecha = conexion.date
        fecha = fecha.strftime('%Y-%m-%d %H:%M:%S')
        consult = "SET DATEFORMAT ymd SELECT COUNT(*) FROM dbo.Documentos WHERE fecha_hora >= CAST('"+fecha+"' AS datetime)"
        if self.name == 'VENTAS':
            consult += " AND (sw = 1 or sw = 2)"
        elif self.name == 'COMPRAS':
            consult += " AND (sw = 3 or sw = 4)"
        elif self.name == 'COMPROBANTES DE INGRESO':
            consult += " AND sw = 5"
        elif self.name == 'COMPROBANTES DE EGRESO':
            consult += " AND sw = 6"
        else:
            return None
        result = conexion.get_data(consult)
        result = int(result[0][0])
        return result
        
    #@classmethod
    def getter_imported(self, name):
        quantity = None
        cursor = Transaction().connection.cursor()
        if self.name == 'VENTAS':
            cursor.execute("SELECT COUNT(*) FROM sale_sale WHERE id_tecno LIKE '%-%'")
        elif self.name == 'COMPRAS':
            cursor.execute("SELECT COUNT(*) FROM purchase_purchase WHERE id_tecno LIKE '%-%'")
        elif self.name == 'COMPROBANTES DE INGRESO':
            cursor.execute("SELECT COUNT(*) FROM account_voucher WHERE id_tecno LIKE '5-%'")
            quantity = int(cursor.fetchone()[0])
            cursor.execute("SELECT COUNT(*) FROM account_multirevenue WHERE id_tecno LIKE '5-%'")
            quantity2 = int(cursor.fetchone()[0])
            quantity += quantity2
        elif self.name == 'COMPROBANTES DE EGRESO':
            cursor.execute("SELECT COUNT(*) FROM account_voucher WHERE id_tecno LIKE '6-%'")
        else:
            return quantity
        result = cursor.fetchone()
        if result:
            quantity = int(result[0])
        return quantity


    def getter_exceptions(self, name):
        Config = Pool().get('conector.configuration')
        conexion, = Config.search([], order=[('id', 'DESC')], limit=1)
        fecha = conexion.date.strftime('%Y-%m-%d %H:%M:%S')
        consult = "SET DATEFORMAT ymd SELECT COUNT(*) FROM dbo.Documentos WHERE fecha_hora >= CAST('"+fecha+"' AS datetime)"
        if self.name == 'VENTAS':
            consult += " AND (sw = 1 or sw = 2) AND exportado = 'E'"
        elif self.name == 'COMPRAS':
            consult += " AND (sw = 3 or sw = 4) AND exportado = 'E'"
        elif self.name == 'COMPROBANTES DE INGRESO':
            consult += " AND sw = 5 AND exportado = 'E'"
        elif self.name == 'COMPROBANTES DE EGRESO':
            consult += " AND sw = 6 AND exportado = 'E'"
        else:
            return None
        result = conexion.get_data(consult)
        result = int(result[0][0])
        return result


    def getter_cancelled(self, name):
        Config = Pool().get('conector.configuration')
        conexion, = Config.search([], order=[('id', 'DESC')], limit=1)
        fecha = conexion.date.strftime('%Y-%m-%d %H:%M:%S')
        consult = "SET DATEFORMAT ymd SELECT COUNT(*) FROM dbo.Documentos WHERE fecha_hora >= CAST('"+fecha+"' AS datetime)"
        if self.name == 'VENTAS':
            consult += " AND (sw = 1 or sw = 2) AND exportado = 'X'"
        elif self.name == 'COMPRAS':
            consult += " AND (sw = 3 or sw = 4) AND exportado = 'X'"
        elif self.name == 'COMPROBANTES DE INGRESO':
            consult += " AND sw = 5 AND exportado = 'X'"
        elif self.name == 'COMPROBANTES DE EGRESO':
            consult += " AND sw = 6 AND exportado = 'X'"
        else:
            return None
        result = conexion.get_data(consult)
        result = int(result[0][0])
        return result


    def getter_not_imported(self, name):
        Config = Pool().get('conector.configuration')
        conexion, = Config.search([], order=[('id', 'DESC')], limit=1)
        fecha = conexion.date
        fecha = fecha.strftime('%Y-%m-%d %H:%M:%S')
        consult = "SET DATEFORMAT ymd SELECT COUNT(*) FROM dbo.Documentos WHERE fecha_hora >= CAST('"+fecha+"' AS datetime) AND exportado != 'T' AND exportado != 'E' AND exportado != 'X'"
        if self.name == 'VENTAS':
            consult += " AND (sw = 1 or sw = 2)"
        elif self.name == 'COMPRAS':
            consult += " AND (sw = 3 or sw = 4)"
        elif self.name == 'COMPROBANTES DE INGRESO':
            consult += " AND sw = 5"
        elif self.name == 'COMPROBANTES DE EGRESO':
            consult += " AND sw = 6"
        else:
            return None
        result = conexion.get_data(consult)
        result = int(result[0][0])
        return result

    @classmethod
    def revisa_secuencia_imp(cls, table, l_sw, name_a):
        pool = Pool()
        Config = pool.get('conector.configuration')
        Actualizacion = pool.get('conector.actualizacion')
        cursor = Transaction().connection.cursor()
        consult = "SELECT number FROM "+table+" WHERE "
        for sw in l_sw:
            consult += f"id_tecno LIKE '{sw}-%'"
            if l_sw.index(sw) != (len(l_sw)-1):
                consult += " OR "
        cursor.execute(consult)
        result = cursor.fetchall()
        if not result:
            return
        result = [r[0] for r in result]
        config, = Config.search([], order=[('id', 'DESC')], limit=1)
        fecha = config.date
        fecha = fecha.strftime('%Y-%m-%d %H:%M:%S')
        consult2 = "SELECT CONCAT(tipo,'-',numero_documento) FROM Documentos WHERE ("
        for sw in l_sw:
            consult2 += f"sw = {sw}"
            if l_sw.index(sw) != (len(l_sw)-1):
                consult2 += " OR "
        consult2 += ") AND fecha_hora >= CAST('"+fecha+"' AS datetime) AND exportado = 'T' AND tipo<>0 ORDER BY tipo,numero_documento"
        result_tecno = Config.get_data(consult2)
        result_tecno = [r[0] for r in result_tecno]
        list_difference = [r for r in result_tecno if r not in result]
        logs = []
        for falt in list_difference:
            lid = falt.split('-')
            Config.set_data(f"UPDATE dbo.Documentos SET exportado = 'S' WHERE tipo = {lid[0]} AND Numero_documento = {lid[1]}")
            logs.append(f"DOCUMENTO FALTANTE: {falt}")
        actualizacion, = Actualizacion.search([('name', '=', name_a)])
        cls.add_logs(actualizacion, logs)