from trytond.model import ModelSQL, ModelView, fields
from trytond.pool import Pool
from trytond.exceptions import UserError
import datetime
from .additional import list_to_tuple

try:
    import pyodbc
except:
    print("Warning: Does not possible import pyodbc module!")
    print("Please install it...!")


# Paso a paso recomendado para la importación
# 1. Crear la funcion que importa los datos y crea la actualización
# 2. Crear la funcion que valida los datos importados
#   2.1 Ya existe el registro?
#   2.2 Falta algún dato en Tryton?
# 3. Funcion que se encarga de crear los registros en Tryton
#   3.1 _create_model()
#   3.2 _create_lines()
#   3.3 Model.save([all])


# TYPES_FILE = [
#     ('parties', 'Parties'),
#     ('products', 'Products'),
#     ('balances', 'Balances'),
#     ('accounts', 'Accounts'),
#     ('update_accounts', 'Update Accounts'),
#     ('product_costs', 'Product costs'),
#     ('inventory', "Inventory"),
#     ('bank_account', 'Bank Account'),
#     ('loans', 'Loans'),
#     ('access_biometric', 'Access biometric')
# ]

class Configuration(ModelSQL, ModelView):
    'Configuration'
    __name__ = 'conector.configuration'

    server = fields.Char('Server', required=True, help="Example: ip,port")
    db = fields.Char('Database', required=True, help="Enter the name of the database without leaving spaces")
    user = fields.Char('User', required=True, help="Enter the user of the database without leaving spaces")
    password = fields.Char('Password', required=True, help="Enter the password of the database without leaving spaces")
    date = fields.Date('Date', required=True, help="Enter the import start date")
    end_date = fields.Date('End Date', help="Enter the import end date" )
    # file = fields.Binary('File', help="Enter the file to import with (;)")
    # type_file = fields.Selection(TYPES_FILE, 'Type file')
    #doc_types = fields.Char('Doc types', help="Example: 101;120;103")
    order_type_production = fields.Char('Order types', help="Example: 101;202;303")
    access_enter_timestamp = fields.Char('Inicia a laborar', help="Example: Laborando")
    access_exit_timestamp = fields.Char('Finaliza de laborar', help="Example: Salir")
    access_start_rest = fields.Char('Inicia a descansar', help="Example: Descansando")
    access_end_rest = fields.Char('Finaliza de descansar', help="Example: Retornar")
    enhabled = fields.Function(fields.Boolean('Enhabled'), 'get_enhabled')


    @classmethod
    def __setup__(cls):
        super(Configuration, cls).__setup__()
        cls._buttons.update({
                'test_conexion': {},
                'importfile': {},
                })

    # Se retorna la configuracion a trabajar
    @classmethod
    def get_configuration(cls):
        configuration = None
        last_record = cls.search([], order=[('id', 'DESC')], limit=1)
        if last_record and last_record[0].enhabled:
            configuration, = last_record
        return configuration

    # Se valida si esta habilitada la conexión para importar datos
    def get_enhabled(self, name):
        try:
            parametro = self.get_data_parametros("181")
            if parametro:
                if parametro[0].Valor.strip() == 'S':
                    return False
            return True
        except Exception as e:
            print(e)
            return False

    #Función que prueba la conexión a la base de datos sqlserver
    @classmethod
    @ModelView.button
    def test_conexion(cls, records):
        cnxn = cls.conexion()
        cnxn.close()
        raise UserError('Conexión sqlserver: ', 'Exitosa !')

    #Función encargada de establecer conexión con respecto a la configuración
    @classmethod
    def conexion(cls):
        last_record = cls.search([], order=[('id', 'DESC')], limit=1)
        if last_record:
            record, = last_record
            #Las conexiones utilizadas en un bloque with se confirmarán al final del bloque si no se generan errores y se revertirán de lo contrario
            with pyodbc.connect('DRIVER={ODBC Driver 17 for SQL Server};SERVER='+record.server+';DATABASE='+record.db+';UID='+record.user+';PWD='+record.password) as cnxn:
                return cnxn
        else:
            raise UserError('Error: ', 'Ingrese por favor todos los datos de configuracion de la base de datos')


    #Función encargada de enviar la conexión configurada con los datos del primer registro
    @classmethod
    def get_data(cls, query):
        data = []
        cnxn = cls.conexion()
        with cnxn.cursor() as cursor:
            cursor.execute(query)
            data = cursor.fetchall()
        cnxn.close()
        return data

    #
    @classmethod
    def set_data(cls, query):
        cnxn = cls.conexion()
        with cnxn.cursor() as cursor:
            cursor.execute(query)
        cnxn.close()

    @classmethod
    def set_data_rollback(cls, queries):
        try:
            cnxn = cls.conexion()
            cnxn.autocommit = False
            for query in queries:
                cnxn.cursor().execute(query)
        except pyodbc.DatabaseError as err:
            cnxn.rollback()
            raise UserError('database error', err)
        else:
            cnxn.commit()
        finally:
            cnxn.autocommit = True


    #Se marca en la tabla dbo.Documentos como exportado a Tryton
    @classmethod
    def update_exportado(cls, id, e):
        lista = id.split('-')
        query = "UPDATE dbo.Documentos SET exportado = '"+e+"' WHERE sw ="+lista[0]+" and tipo = "+lista[1]+" and Numero_documento = "+lista[2]
        cls.set_data(query)

    @classmethod
    def update_exportado_list(cls, idt, e):
        ids = list_to_tuple(idt, string=True)
        query = f"UPDATE dbo.Documentos SET exportado = '{e}' WHERE CONCAT(sw,'-',tipo,'-',Numero_Documento) IN {ids}"
        print(query)
        cls.set_data(query)

    @classmethod
    def get_tblproducto(cls, fecha):
        fecha = fecha.strftime('%Y-%m-%d %H:%M:%S')
        query = "SET DATEFORMAT ymd SELECT * FROM dbo.TblProducto WHERE fecha_creacion >= CAST('"+fecha+"' AS datetime) OR Ultimo_Cambio_Registro >= CAST('"+fecha+"' AS datetime)"
        data = cls.get_data(query)
        return data

    @classmethod
    def get_tblterceros(cls, fecha):
        fecha = fecha.strftime('%Y-%m-%d %H:%M:%S')
        query = "SET DATEFORMAT ymd SELECT * FROM dbo.TblTerceros WHERE fecha_creacion >= CAST('"+fecha+"' AS datetime) OR Ultimo_Cambio_Registro >= CAST('"+fecha+"' AS datetime)"
        data = cls.get_data(query)
        return data

    @classmethod
    def get_tercerosdir(cls, fecha):
        fecha = fecha.strftime('%Y-%m-%d %H:%M:%S')
        query = "SET DATEFORMAT ymd SELECT * FROM dbo.Terceros_Dir WHERE Ultimo_Cambio_Registro >= CAST('"+fecha+"' AS datetime)"
        data = cls.get_data(query)
        return data

    @classmethod
    def get_tercerosdir_nit(cls, nit):
        query = "SELECT * FROM dbo.Terceros_Dir WHERE nit = '"+nit+"'"
        data = cls.get_data(query)
        return data

    @classmethod
    def get_documentos_tecno(cls, sw):
        Config = Pool().get('conector.configuration')
        config, = Config.search([], order=[('id', 'DESC')], limit=1)
        fecha = config.date.strftime('%Y-%m-%d %H:%M:%S')
        # query = "SELECT * FROM dbo.Documentos WHERE tipo = null AND Numero_documento = null " #TEST
        query = "SET DATEFORMAT ymd SELECT TOP(50) * FROM dbo.Documentos "\
                f"WHERE fecha_hora >= CAST('{fecha}' AS datetime) AND "\
                f"sw = {sw} AND exportado != 'T' AND exportado != 'E' AND exportado != 'X' "
        # Se valida si en la configuración de la base de datos, añadieron un valor en la fecha final de importación
        if config.end_date:
            end_date = config.end_date.strftime('%Y-%m-%d %H:%M:%S')
            query += f" AND fecha_hora < CAST('{end_date}' AS datetime) "
        query += "ORDER BY fecha_hora ASC"
        data = cls.get_data(query)
        return data

    @classmethod
    def get_documentos_tipo(cls, sw, tipo):
        Config = Pool().get('conector.configuration')
        config, = Config.search([], order=[('id', 'DESC')], limit=1)
        fecha = config.date.strftime('%Y-%m-%d %H:%M:%S')
        # query = "SELECT * FROM dbo.Documentos WHERE tipo = null AND Numero_documento = null" #TEST
        if not sw:
            query = "SET DATEFORMAT ymd SELECT TOP(50) * FROM dbo.Documentos WHERE Fecha_Hora_Factura >= CAST('"+fecha+"' AS datetime) AND tipo = "+tipo+" AND exportado != 'T' AND exportado != 'E' AND exportado != 'X' "
        else:
            query = "SET DATEFORMAT ymd SELECT TOP(50) * FROM dbo.Documentos WHERE Fecha_Hora_Factura >= CAST('"+fecha+"' AS datetime) AND sw = "+sw+" AND tipo = "+tipo+" AND exportado != 'T' AND exportado != 'E' AND exportado != 'X' "
        if config.end_date:
            end_date = config.end_date.strftime('%Y-%m-%d %H:%M:%S')
            query += f" AND Fecha_Hora_Factura < CAST('{end_date}' AS datetime) "
        query += "ORDER BY Fecha_Hora_Factura ASC"
        data = cls.get_data(query)
        return data

    @classmethod
    def get_lineasd_tecno(cls, id):
        lista = id.split('-')
        query = "SELECT * FROM dbo.Documentos_Lin WHERE sw = "+lista[0]+" AND tipo = "+lista[1]+" AND Numero_Documento = "+lista[2]+" order by seq"
        data = cls.get_data(query)
        return data
    
    @classmethod
    def get_documentos_lin(cls, ids):
        cond = "IN"
        if len(ids) == 1:
            ids = f"'{ids[0]}'"
            cond = "="
        query = "SELECT * FROM dbo.Documentos_Lin "\
            f"WHERE CONCAT(sw,'-',tipo,'-',Numero_Documento) {cond} {ids} order by seq"
        data = cls.get_data(query)
        return data

    @classmethod
    def get_data_parametros(cls, id):
        query = "SELECT * FROM dbo.TblParametro WHERE IdParametro = "+id
        data = cls.get_data(query)
        return data

    @classmethod
    def get_tbltipodoctos(cls, id):
        query = "SELECT * FROM dbo.TblTipoDoctos WHERE idTipoDoctos = "+id
        data = cls.get_data(query)
        return data
    
    @classmethod
    def get_tbltipodoctos_encabezado(cls, ids):
        query = "SELECT idTipoDoctos, Encabezado FROM dbo.TblTipoDoctos WHERE idTipoDoctos in "+ids
        data = cls.get_data(query)
        return data

    @classmethod
    def get_tbltipoproducto(cls, id):
        query = "SELECT * FROM dbo.TblTipoProducto WHERE IdTipoProducto = "+id
        data = cls.get_data(query)
        return data

    #Metodo encargado de obtener los recibos pagados de un documento dado
    @classmethod
    def get_dctos_cruce(cls, id):
        lista = id.split('-')
        query = "SELECT * FROM dbo.Documentos_Cruce WHERE sw="+lista[0]+" AND tipo="+lista[1]+" AND numero="+lista[2]
        data = cls.get_data(query)
        return data

    #Metodo encargado de obtener la forma en que se pago el comprobante (recibos)
    @classmethod
    def get_tipos_pago(cls, id):
        lista = id.split('-')
        query = "SELECT * FROM dbo.Documentos_Che WHERE sw="+lista[0]+" AND tipo="+lista[1]+" AND numero="+lista[2]
        data = cls.get_data(query)
        return data


    @classmethod
    def get_data_table(cls, table):
        query = "SELECT * FROM dbo."+table
        data = cls.get_data(query)
        return data
    
    @classmethod
    def get_documentos_orden(cls):
        Config = Pool().get('conector.configuration')
        config, = Config.search([], order=[('id', 'DESC')], limit=1)
        fecha = config.date.strftime('%Y-%m-%d %H:%M:%S')
        query = "SET DATEFORMAT ymd SELECT d.DescuentoOrdenVenta, l.* FROM dbo.Documentos_Lin l "\
                "INNER JOIN Documentos d ON d.sw=l.sw AND d.tipo=l.tipo AND d.Numero_documento=l.Numero_Documento "\
                f"WHERE d.DescuentoOrdenVenta like 'T-%' AND d.fecha_hora >= CAST('{fecha}' AS datetime) "\
                "AND d.sw = 12 AND d.exportado != 'T' AND d.exportado != 'E' AND d.exportado != 'X'"
        if config.end_date:
            end_date = config.end_date.strftime('%Y-%m-%d %H:%M:%S')
            query += f" AND fecha_hora < CAST('{end_date}' AS datetime) "
        data = cls.get_data(query)
        return data

    @classmethod
    def get_documentos_traslados(cls):
        Config = Pool().get('conector.configuration')
        config, = Config.search([], order=[('id', 'DESC')], limit=1)
        fecha = config.date.strftime('%Y-%m-%d %H:%M:%S')
        # Consulta T-SQL mejorada
        subquery = f"""SELECT TOP 50 sw, tipo, Numero_documento, bodega 
                    FROM dbo.Documentos 
                    WHERE sw = 16 
                    AND Fecha_Hora_Factura >= CAST('{fecha}' AS datetime)
                    AND anulado != 'S' 
                    AND exportado NOT IN ('T', 'E', 'X')
                    """
        if config.end_date:
            end_date = config.end_date.strftime('%Y-%m-%d %H:%M:%S')
            subquery += f"AND Fecha_Hora_Factura < CAST('{end_date}' AS datetime) "
        subquery += "ORDER BY Fecha_Hora_Factura ASC"
        query = f"""
                SET DATEFORMAT ymd 
                SELECT d.bodega from_location, l.* 
                FROM dbo.Documentos_Lin AS l
                INNER JOIN (
                {subquery}
                ) AS d
                ON d.sw = l.sw AND d.tipo = l.tipo AND d.Numero_documento = l.Numero_Documento
                """
        data = cls.get_data(query)
        return data

    @classmethod
    def get_biometric_access_transactions(cls, event_time=None):
        if event_time:
            tomorrow = event_time + datetime.timedelta(days=1)
            # event_time = datetime.datetime(1111, 1, 1, 1, 1, 1)
            query = f"SET DATEFORMAT ymd SELECT * FROM TblDatosBiometrico "\
                f"WHERE Fecha_Hora_Marcacion >= '{event_time}' AND Fecha_Hora_Marcacion < '{tomorrow}' "\
                "ORDER BY Nit_cedula, Fecha_Hora_Marcacion ASC"
        else:
            query = "SELECT * FROM TblDatosBiometrico ORDER BY Nit_cedula, Fecha_Hora_Marcacion ASC"
        data = cls.get_data(query)
        return data
    
    @classmethod
    def get_tblproducto_parent(cls):
        query = """
                SELECT
                    IdProducto,
                    IdResponsable,
                    tiempo_del_ciclo
                FROM
                    dbo.TblProducto
                WHERE
                    IdResponsable <> 0
                """
        data = cls.get_data(query)
        return data
