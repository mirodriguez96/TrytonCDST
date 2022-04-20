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
        registros_list 
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
        return result

    @classmethod
    def revisa_secuencia_imp(cls, table):
        cursor = Transaction().connection.cursor()
        cursor.execute("SELECT number FROM "+table+" WHERE id_tecno LIKE '%-%'")
        result = cursor.fetchall()
        if not result:
            return
        Config = Pool().get('conector.configuration')
        result_tecno = Config.get_data("select CONCAT(tipo,'-',numero_documento) from Documentos where (sw=1 or sw=2) and year(fecha_hora_factura)=2022 and exportado = 'T' and tipo<>0 order by tipo,numero_documento")
        #
        data_tryton = {}
        for r in result:
            tipo = r[0].split('-')[0]
            numero = r[0].split('-')[1]
            if tipo not in data_tryton.keys():
                data_tryton[tipo] = []
            data_tryton[tipo].append(numero)
        #
        data_tecno = {}
        for t in result_tecno:
            tipo = t[0].split('-')[0]
            numero = t[0].split('-')[1]
            if tipo not in data_tecno.keys():
                data_tecno[tipo] = []
            data_tecno[tipo].append(numero)
        faltantes = {}
        for tipo in data_tecno:
            if tipo not in faltantes.keys():
                faltantes[tipo] = []
            for l in data_tecno[tipo]:
                if l not in data_tryton[tipo]:
                    faltantes[tipo].append(l)
        for falt in faltantes:
            for doc in faltantes[falt]:
                Config.set_data("UPDATE dbo.Documentos SET exportado = 'S' WHERE (sw=1 or sw=2) and tipo = "+falt+" and Numero_documento = "+str(doc))
        print(faltantes)