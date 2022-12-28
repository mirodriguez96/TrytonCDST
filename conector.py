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


    # se obtiene la fecha de la ultima actualizacion (modificacion) de un registro del modelo conector.actualizacion
    # pero la fecha del registro debe ser diferente a la del dia de hoy
    @classmethod
    def get_fecha_actualizacion(cls, actualizacion):
        fecha = datetime.date(1,1,1)
        if actualizacion.write_date:
            fecha = (actualizacion.write_date - datetime.timedelta(hours=11))
        elif actualizacion.create_date:
            Date = Pool().get('ir.date')
            create_date = actualizacion.create_date.date()
            if create_date != Date.today():
                fecha = (actualizacion.create_date - datetime.timedelta(hours=11))
        return fecha

    # se solicita una actualizacion y una lista de registros (logs) para validar si existen
    # y si no existen, se almacena en el campo logs de la actualizacion dada
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
    
    # Se consulta en la base de datos de SQLSERVER por la cantidad de documentos
    # que se van a importar
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
        elif self.name == 'PRODUCCION':
            consult += " AND sw = 12 AND ("
            parametro = Config.get_data_parametros('177')
            valor_parametro = parametro[0].Valor.split(',')
            for tipo in valor_parametro:
                consult += "tipo = "+str(tipo)
                if (valor_parametro.index(tipo)+1) < len(valor_parametro):
                    consult += " OR "
            consult += ")"
        else:
            return None
        result = conexion.get_data(consult)
        result = int(result[0][0])
        return result
        
    # Se consulta la cantidad de documentos (registros) que hay almacenados en Tryton
    # que han sido importados por el modulo conector
    def getter_imported(self, name):
        quantity = None
        cursor = Transaction().connection.cursor()
        if self.name == 'VENTAS':
            cursor.execute("SELECT COUNT(*) FROM sale_sale WHERE id_tecno LIKE '1-%' OR id_tecno LIKE '2-%'")
        elif self.name == 'COMPRAS':
            cursor.execute("SELECT COUNT(*) FROM purchase_purchase WHERE id_tecno LIKE '3-%' OR id_tecno LIKE '4-%'")
        elif self.name == 'COMPROBANTES DE INGRESO':
            cursor.execute("SELECT COUNT(*) FROM account_voucher WHERE id_tecno LIKE '5-%'")
            quantity = int(cursor.fetchone()[0])
            cursor.execute("SELECT COUNT(*) FROM account_multirevenue WHERE id_tecno LIKE '5-%'")
            quantity2 = int(cursor.fetchone()[0])
            quantity += quantity2
            return quantity
        elif self.name == 'COMPROBANTES DE EGRESO':
            cursor.execute("SELECT COUNT(*) FROM account_voucher WHERE id_tecno LIKE '6-%'")
        elif self.name == 'PRODUCCION':
            cursor.execute("SELECT COUNT(*) FROM production WHERE id_tecno LIKE '12-%'")
        else:
            return quantity
        result = cursor.fetchone()
        if result:
            quantity = int(result[0])
        return quantity

    # Se consulta en la base de datos de SQLSERVER los documentos marcados como excepcion
    def getter_exceptions(self, name):
        Config = Pool().get('conector.configuration')
        conexion, = Config.search([], order=[('id', 'DESC')], limit=1)
        fecha = conexion.date.strftime('%Y-%m-%d %H:%M:%S')
        consult = "SET DATEFORMAT ymd SELECT COUNT(*) FROM dbo.Documentos WHERE fecha_hora >= CAST('"+fecha+"' AS datetime) AND exportado = 'E'"
        if self.name == 'VENTAS':
            consult += " AND (sw = 1 or sw = 2)"
        elif self.name == 'COMPRAS':
            consult += " AND (sw = 3 or sw = 4)"
        elif self.name == 'COMPROBANTES DE INGRESO':
            consult += " AND sw = 5"
        elif self.name == 'COMPROBANTES DE EGRESO':
            consult += " AND sw = 6"
        elif self.name == 'PRODUCCION':
            consult += " AND sw = 12"
        else:
            return None
        result = conexion.get_data(consult)
        result = int(result[0][0])
        return result

    # Se consulta en la base de datos de SQLSERVER los documentos marcados como no a importar por el modulo conector
    def getter_cancelled(self, name):
        Config = Pool().get('conector.configuration')
        conexion, = Config.search([], order=[('id', 'DESC')], limit=1)
        fecha = conexion.date.strftime('%Y-%m-%d %H:%M:%S')
        consult = "SET DATEFORMAT ymd SELECT COUNT(*) FROM dbo.Documentos WHERE fecha_hora >= CAST('"+fecha+"' AS datetime) AND exportado = 'X'"
        if self.name == 'VENTAS':
            consult += " AND (sw = 1 or sw = 2)"
        elif self.name == 'COMPRAS':
            consult += " AND (sw = 3 or sw = 4)"
        elif self.name == 'COMPROBANTES DE INGRESO':
            consult += " AND sw = 5"
        elif self.name == 'COMPROBANTES DE EGRESO':
            consult += " AND sw = 6"
        elif self.name == 'PRODUCCION':
            consult += " AND sw = 12"
        else:
            return None
        result = conexion.get_data(consult)
        result = int(result[0][0])
        return result

    # Se consulta en la base de datos de SQLSERVER los documentos que faltan por ser importados
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
        elif self.name == 'PRODUCCION':
            consult += " AND sw = 12 AND ("
            parametro = Config.get_data_parametros('177')
            valor_parametro = parametro[0].Valor.split(',')
            for tipo in valor_parametro:
                consult += "tipo = "+str(tipo)
                if (valor_parametro.index(tipo)+1) < len(valor_parametro):
                    consult += " OR "
            consult += ")"
        else:
            return None
        result = conexion.get_data(consult)
        result = int(result[0][0])
        return result

    # Se revisa los documentos existentes en Tryton vs SqlServer (TecnoCarnes) para marcarlos como pendientes por importar.
    # Se solicita el nombre de la tabla en tryton (table), la lista de sw según el documento y el nombre de la actualizacion
    @classmethod
    def revisa_secuencia_imp(cls, name):
        pool = Pool()
        Config = pool.get('conector.configuration')
        Actualizacion = pool.get('conector.actualizacion')
        cursor = Transaction().connection.cursor()
        # Se procede primero a buscar los documentos importados en Tryton
        result = None
        result_tryton = []
        cond = None
        if name == 'VENTAS':
            consultv = "SELECT id_tecno FROM sale_sale WHERE id_tecno is not null"
            cursor.execute(consultv)
            result = cursor.fetchall()
            cond = "(sw=1 OR sw=2)"
        if name == 'COMPRAS':
            consultv = "SELECT id_tecno FROM purchase_purchase WHERE id_tecno is not null"
            cursor.execute(consultv)
            result = cursor.fetchall()
            cond = "(sw=3 OR sw=4)"
        if name == 'COMPROBANTES DE INGRESO':
            consult1 = "SELECT id_tecno FROM account_voucher WHERE id_tecno LIKE '5-%'"
            cursor.execute(consult1)
            result = cursor.fetchall()
            result_tryton = [r[0] for r in result]
            consult2 = "SELECT id_tecno FROM account_multirevenue WHERE id_tecno is not null"
            cursor.execute(consult2)
            result = cursor.fetchall()
            cond = "sw=5"
        if name == 'COMPROBANTES DE EGRESO':
            consultv = "SELECT id_tecno FROM account_voucher WHERE id_tecno  LIKE '6-%'"
            cursor.execute(consultv)
            result = cursor.fetchall()
            cond = "sw=6"
        if name == 'PRODUCCION':
            consultv = "SELECT id_tecno FROM production WHERE id_tecno is not null"
            cursor.execute(consultv)
            result = cursor.fetchall()
            cond = "sw=12 AND ("
            parametro = Config.get_data_parametros('177')
            valor_parametro = parametro[0].Valor.split(',')
            for tipo in valor_parametro:
                cond += "tipo="+tipo.strip()
                if valor_parametro.index(tipo) != (len(valor_parametro)-1):
                    cond += " OR "
            cond += ")"
        if name == 'NOTAS DE CREDITO':
            consultv = "SELECT id_tecno FROM account_invoice WHERE id_tecno  LIKE '32-%'"
            cursor.execute(consultv)
            result = cursor.fetchall()
            cond = "sw=32"
        if name == 'NOTAS DE DEBITO':
            consultv = "SELECT id_tecno FROM account_voucher WHERE id_tecno  LIKE '31-%'"
            cursor.execute(consultv)
            result = cursor.fetchall()
            cond = "sw=31"
        # Se almacena el resultado de la busqueda en una lista
        if not result_tryton and result:
            result_tryton = [r[0] for r in result]
        elif result_tryton and result:
            for r in result:
                result_tryton.append(r[0])
        # Si no entró a ningún documento no hace nada
        if not cond:
            return
        config, = Config.search([], order=[('id', 'DESC')], limit=1)
        fecha = config.date.strftime('%Y-%m-%d %H:%M:%S')
        consultc = f"SELECT CONCAT(sw,'-',tipo,'-',numero_documento) FROM Documentos WHERE {cond} AND fecha_hora >= CAST('"+fecha+"' AS datetime) AND exportado = 'T' AND tipo<>0 ORDER BY tipo,numero_documento"
        result_tecno = Config.get_data(consultc)
        result_tecno = [r[0] for r in result_tecno]
        list_difference = [r for r in result_tecno if r not in result_tryton]
        # Se guarda el registro y se marcan los documentos para ser importados de nuevo
        logs = []
        for falt in list_difference:
            lid = falt.split('-')
            Config.set_data(f"UPDATE dbo.Documentos SET exportado = 'N' WHERE sw = {lid[0]} AND tipo = {lid[1]} AND Numero_documento = {lid[2]}")
            logs.append(f"DOCUMENTO FALTANTE: {falt}")
        actualizacion, = Actualizacion.search([('name', '=', name)])
        cls.add_logs(actualizacion, logs) 