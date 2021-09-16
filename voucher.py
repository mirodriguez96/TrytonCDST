from trytond.model import ModelView, ModelSQL, fields
from trytond.pool import Pool, PoolMeta
from trytond.exceptions import UserError
import datetime


__all__ = [
    'Voucher',
    'Cron',
    ]


class Cron(metaclass=PoolMeta):
    'Cron'
    __name__ = 'ir.cron'

    @classmethod
    def __setup__(cls):
        super().__setup__()
        cls.method.selection.append(
            ('account.voucher|import_voucher', "Update vouchers"),
            )


#Heredamos del modelo sale.sale para agregar el campo id_tecno
class Voucher(ModelSQL, ModelView):
    'Voucher'
    __name__ = 'account.voucher'
    id_tecno = fields.Char('Id Tabla Sqlserver', required=False)

    @classmethod
    def import_voucher(cls):
        print("--------------RUN VOUCHER--------------")
        documentos_db = cls.last_update()
        cls.create_actualizacion(False)
        if documentos_db:
            columns_doc = cls.get_columns_db_tecno('Documentos')
            columns_rec = cls.get_columns_db_tecno('Documentos_Cruce')
            #pool = Pool()
            #Invoice = pool.get('account.invoice')
            for doc in documentos_db:
                tipo = str(doc[columns_doc.index('tipo')].strip)
                nro = str(doc[columns_doc.index('Numero_documento')])
                recibos = cls.get_recibos(tipo, nro)
                for rec in recibos:
                    print(rec[columns_rec.index('tipo_aplica')], rec[columns_rec.index('numero_aplica')])


    #Función encargada de consultar las columnas pertenecientes a 'x' tabla de la bd de TecnoCarnes
    @classmethod
    def get_columns_db_tecno(cls, table):
        columns = []
        try:
            Config = Pool().get('conector.configuration')
            conexion = Config.conexion()
            with conexion.cursor() as cursor:
                query = cursor.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = '"+table+"' ORDER BY ORDINAL_POSITION")
                for q in query.fetchall():
                    columns.append(q[0])
        except Exception as e:
            print("ERROR QUERY "+table+": ", e)
        return columns

    #Esta función se encarga de traer todos los datos de una tabla dada de acuerdo al rango de fecha dada de la bd TecnoCarnes
    @classmethod
    def get_data_where_tecno(cls, table, date):
        data = []
        try:
            Config = Pool().get('conector.configuration')
            conexion = Config.conexion()
            with conexion.cursor() as cursor:
                query = cursor.execute("SELECT TOP(20) * FROM dbo."+table+" WHERE fecha_hora >= CAST('"+date+"' AS datetime) AND sw = 5")
                data = list(query.fetchall())
        except Exception as e:
            print("ERROR QUERY get_data_where_tecno: ", e)
        return data

    #Metodo encargado de obtener los recibos pagados de un documento dado
    @classmethod
    def get_recibos(cls, tipo, nro):
        data = []
        try:
            Config = Pool().get('conector.configuration')
            conexion = Config.conexion()
            with conexion.cursor() as cursor:
                query = cursor.execute("SELECT * FROM dbo.Documentos_Cruce WHERE sw = 5 AND tipo = "+tipo+" AND numero ="+nro)
                data = list(query.fetchall())
        except Exception as e:
            print("ERROR QUERY get_recibos: ", e)
        return data

    #Función encargada de traer los datos de la bd TecnoCarnes con una fecha dada.
    @classmethod
    def last_update(cls):
        Actualizacion = Pool().get('conector.actualizacion')
        #Se consulta la ultima actualización realizada para los terceros
        ultima_actualizacion = Actualizacion.search([('name', '=','RECIBOS')])
        if ultima_actualizacion:
            #Se calcula la fecha restando la diferencia de horas que tiene el servidor con respecto al clienete
            if ultima_actualizacion[0].write_date:
                fecha = (ultima_actualizacion[0].write_date - datetime.timedelta(hours=5))
            else:
                fecha = (ultima_actualizacion[0].create_date - datetime.timedelta(hours=5))
        else:
            fecha = datetime.date(2021,1,1)
            cls.create_actualizacion(True)
        fecha = fecha.strftime('%Y-%d-%m %H:%M:%S')
        data = cls.get_data_where_tecno('Documentos', fecha)
        return data

    #Crea o actualiza un registro de la tabla actualización en caso de ser necesario
    @classmethod
    def create_actualizacion(cls, create):
        Actualizacion = Pool().get('conector.actualizacion')
        if create:
            #Se crea un registro con la actualización realizada
            actualizar = Actualizacion()
            actualizar.name = 'RECIBOS'
            actualizar.save()
        else:
            #Se busca un registro con la actualización realizada
            actualizacion, = Actualizacion.search([('name', '=','RECIBOS')])
            actualizacion.name = 'RECIBOS'
            actualizacion.save()

