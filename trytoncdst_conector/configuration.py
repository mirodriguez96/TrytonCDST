import datetime
import logging

from trytond.exceptions import UserError
from trytond.model import ModelSQL, ModelView, fields
from trytond.pool import Pool
from trytond.pyson import Eval, Not

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

    server = fields.Char(
        'Server',
        required=True,
        help="Example: ip,port",
        states={'invisible': ~Not(Eval('visibible'))},
        depends=['visibible'],
    )
    db = fields.Char(
        'Database',
        required=True,
        help="Enter the name of the database without leaving spaces",
        states={'invisible': ~Not(Eval('visibible'))},
        depends=['visibible'],
    )
    user = fields.Char(
        'User',
        required=True,
        help="Enter the user of the database without leaving spaces",
        states={'invisible': ~Not(Eval('visibible'))},
        depends=['visibible'],
    )
    password = fields.Char(
        'Password',
        required=True,
        help="Enter the password of the database without leaving spaces",
        states={'invisible': ~Not(Eval('visibible'))},
        depends=['visibible'],
    )
    date = fields.Date(
        'Date',
        required=True,
        help="Enter the import start date",
        states={'invisible': ~Not(Eval('visibible'))},
        depends=['visibible'],
    )
    end_date = fields.Date(
        'End Date',
        help="Enter the import end date",
        states={'invisible': ~Not(Eval('visibible'))},
        depends=['visibible'],
    )

    enhabled = fields.Function(fields.Boolean('Enhabled'), 'get_enhabled')
    visibible = fields.Boolean('Visible')

    @staticmethod
    def default_visibible():
        return True

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

    # Función que prueba la conexión a la base de datos sqlserver
    @classmethod
    @ModelView.button
    def test_conexion(cls, records):
        cnxn = cls.conexion()
        cnxn.close()
        raise UserError('Conexión sqlserver: ', 'Exitosa !')

    @classmethod
    def conexion(cls):
        try:
            last_record = cls.search([], order=[('id', 'DESC')], limit=1)
            if last_record:
                record, = last_record
                driver_sql3 = "{ODBC Driver 17 for SQL Server}"

                driver = f"""DRIVER={driver_sql3};
                SERVER={record.server};
                DATABASE={record.db};
                UID={record.user};
                PWD={record.password};
                Connection Timeout=5;
                """

                with pyodbc.connect(driver) as cnxn:
                    with cnxn.cursor() as cursor:
                        cursor = cnxn.cursor()
                        cursor.execute("SELECT 1")
                        return cnxn
            else:
                raise UserError(
                    'Error: ',
                    'Ingrese por favor todos los datos de configuracion de la base de datos'
                )
        except Exception as error:
            logging.error(f'Error de conexión a SQL Server: {error}')

    @classmethod
    def get_data(cls, query):
        try:
            data = []
            with cls.conexion() as cnxn:
                with cnxn.cursor() as cursor:
                    cursor.execute(query)
                    data = cursor.fetchall()
            return data
        except (pyodbc.OperationalError, pyodbc.InterfaceError) as db_error:
            logging.error(
                f"Error de conexión con la base de datos: {db_error}")
        except Exception as error:
            logging.error(f"Error al obtener datos: {error}")
        finally:
            if cnxn and not cnxn.closed:
                cnxn.close()
                logging.info('Conexión cerrada correctamente.')

    @classmethod
    def set_data(cls, query):
        try:
            with cls.conexion() as cnxn:
                with cnxn.cursor() as cursor:
                    cursor.execute(query)
        except (pyodbc.OperationalError, pyodbc.InterfaceError) as db_error:
            logging.error(
                f"Error de conexión con la base de datos: {db_error}")
        except Exception as error:
            logging.error(f"Error al actualizar datos: {error}")
        finally:
            if cnxn and not cnxn.closed:
                cnxn.close()
                logging.info('Conexión cerrada correctamente.')

    @classmethod
    def set_data_rollback(cls, queries):
        try:
            with cls.conexion() as cnxn:
                with cnxn.cursor() as cursor:
                    cnxn.autocommit = False
                    for query in queries:
                        cursor.execute(query)
                cnxn.commit()
        except pyodbc.DatabaseError as err:
            cnxn.rollback()
            raise UserError('database error', err)
        finally:
            cnxn.autocommit = True

    # Se marca en la tabla dbo.Documentos como exportado a Tryton
    @classmethod
    def update_exportado(cls, id, e):
        success = False
        try:
            lista = id.split('-')
            query = "UPDATE dbo.Documentos SET exportado = '" + e + "' WHERE sw =" + lista[
                0] + " and tipo = " + lista[
                    1] + " and Numero_documento = " + lista[2]
            cls.set_data(query)
            success = True
        except (pyodbc.OperationalError, pyodbc.InterfaceError) as db_error:
            logging.error(
                f"Error de conexión con la base de datos: {db_error}")
        except Exception as error:
            logging.error(f'Error al actualizar datos: {error}')
        finally:
            return success

    @classmethod
    def update_exportado_list(cls, idt, e):
        try:
            ids = list_to_tuple(idt, string=True)
            query = f"UPDATE dbo.Documentos SET exportado = '{e}' WHERE CONCAT(sw,'-',tipo,'-',Numero_Documento) IN {ids}"
            cls.set_data(query)
        except (pyodbc.OperationalError, pyodbc.InterfaceError) as db_error:
            logging.error(
                f"Error de conexión con la base de datos: {db_error}")
        except Exception as error:
            logging.error(f'Error al enviar datos en lista: {error}')

    @classmethod
    def get_tblproducto(cls, fecha):
        data = None
        try:
            fecha = fecha.strftime('%Y-%m-%d %H:%M:%S')
            query = "SET DATEFORMAT ymd SELECT * FROM dbo.TblProducto WHERE fecha_creacion >= CAST('" + \
                fecha + \
                    "' AS datetime) OR Ultimo_Cambio_Registro >= CAST('" + \
                fecha + "' AS datetime)"
            data = cls.get_data(query)
        except (pyodbc.OperationalError, pyodbc.InterfaceError) as db_error:
            logging.error(
                f"Error de conexión con la base de datos: {db_error}")
        except Exception as error:
            logging.error(f'Error al obtener datos TlbProducto: {error}')
        return data

    @classmethod
    def get_tblproducto_parent(cls):
        data = None
        try:
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
        except (pyodbc.OperationalError, pyodbc.InterfaceError) as db_error:
            logging.error(
                f"Error de conexión con la base de datos: {db_error}")
        except Exception as error:
            logging.error(
                f'Error al obtener datos TlbProducto parent: {error}')
        return data

    @classmethod
    def get_tblterceros(cls, fecha):
        data = None
        try:
            fecha = fecha.strftime('%Y-%m-%d %H:%M:%S')
            query = "SET DATEFORMAT ymd SELECT * FROM dbo.TblTerceros WHERE fecha_creacion >= CAST('" + \
                fecha + \
                    "' AS datetime) OR Ultimo_Cambio_Registro >= CAST('" + \
                fecha + "' AS datetime)"
            data = cls.get_data(query)
        except (pyodbc.OperationalError, pyodbc.InterfaceError) as db_error:
            logging.error(
                f"Error de conexión con la base de datos: {db_error}")
        except Exception as error:
            logging.error(
                f'Error al obtener datos TblTerceros: {error}')
        return data

    @classmethod
    def get_tercerosdir(cls, fecha):
        data = None
        try:
            fecha = fecha.strftime('%Y-%m-%d %H:%M:%S')
            query = "SET DATEFORMAT ymd SELECT * FROM dbo.Terceros_Dir WHERE Ultimo_Cambio_Registro >= CAST('" + \
                fecha + "' AS datetime)"
            data = cls.get_data(query)
        except (pyodbc.OperationalError, pyodbc.InterfaceError) as db_error:
            logging.error(
                f"Error de conexión con la base de datos: {db_error}")
        except Exception as error:
            logging.error(
                f'Error al obtener datos Terceros_Dir: {error}')
        return data

    @classmethod
    def get_tercerosdir_nit(cls, nit):
        data = None
        try:
            query = "SELECT * FROM dbo.Terceros_Dir WHERE nit = '" + nit + "'"
            data = cls.get_data(query)
        except (pyodbc.OperationalError, pyodbc.InterfaceError) as db_error:
            logging.error(
                f"Error de conexión con la base de datos: {db_error}")
        except Exception as error:
            logging.error(
                f'Error al obtener datos Terceros_Dir nit: {error}')
        return data

    @classmethod
    def get_documentos_tecno(cls, sw):
        data = None
        try:
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
        except (pyodbc.OperationalError, pyodbc.InterfaceError) as db_error:
            logging.error(
                f"Error de conexión con la base de datos: {db_error}")
        except Exception as error:
            logging.error(
                f'Error al obtener datos Documentos: {error}')
        finally:
            return data

    @classmethod
    def get_documentos_tipo(cls, sw, tipo):
        data = None
        try:
            Config = Pool().get('conector.configuration')
            config, = Config.search([], order=[('id', 'DESC')], limit=1)
            fecha = config.date.strftime('%Y-%m-%d %H:%M:%S')
            # query = "SELECT * FROM dbo.Documentos WHERE tipo = null AND Numero_documento = null" #TEST
            if not sw:
                query = "SET DATEFORMAT ymd SELECT TOP(50) * FROM dbo.Documentos WHERE Fecha_Hora_Factura >= CAST('" + fecha + \
                    "' AS datetime) AND tipo = " + tipo + \
                        " AND exportado != 'T' AND exportado != 'E' AND exportado != 'X' "
            else:
                query = "SET DATEFORMAT ymd SELECT TOP(50) * FROM dbo.Documentos WHERE Fecha_Hora_Factura >= CAST('" + fecha + \
                    "' AS datetime) AND sw = " + sw + " AND tipo = " + tipo + \
                        " AND exportado != 'T' AND exportado != 'E' AND exportado != 'X' "
            if config.end_date:
                end_date = config.end_date.strftime('%Y-%m-%d %H:%M:%S')
                query += f" AND Fecha_Hora_Factura < CAST('{end_date}' AS datetime) "
            query += "ORDER BY Fecha_Hora_Factura ASC"
            data = cls.get_data(query)
        except (pyodbc.OperationalError, pyodbc.InterfaceError) as db_error:
            logging.error(
                f"Error de conexión con la base de datos: {db_error}")
        except Exception as error:
            logging.error(
                f'Error al obtener datos Documentos tipo: {error}')
        return data

    @classmethod
    def get_lineasd_tecno(cls, id):
        data = None
        try:
            lista = id.split('-')
            query = "SELECT * FROM dbo.Documentos_Lin WHERE sw = " + lista[
                0] + " AND tipo = " + lista[
                    1] + " AND Numero_Documento = " + lista[2] + " order by seq"
            data = cls.get_data(query)
        except (pyodbc.OperationalError, pyodbc.InterfaceError) as db_error:
            logging.error(
                f"Error de conexión con la base de datos: {db_error}")
        except Exception as error:
            logging.error(
                f'Error al obtener datos Documentos_Lin: {error}')
        return data

    @classmethod
    def get_documentos_lin(cls, ids):
        data = None
        try:
            cond = "IN"
            if len(ids) == 1:
                ids = f"'{ids[0]}'"
                cond = "="
            query = "SELECT * FROM dbo.Documentos_Lin "\
                f"WHERE CONCAT(sw,'-',tipo,'-',Numero_Documento) {cond} {ids} order by seq"
            data = cls.get_data(query)
        except (pyodbc.OperationalError, pyodbc.InterfaceError) as db_error:
            logging.error(
                f"Error de conexión con la base de datos: {db_error}")
        except Exception as error:
            logging.error(
                f'Error al obtener datos Documentos_Lin 2: {error}')
        return data

    @classmethod
    def get_data_parametros(cls, id):
        data = None
        try:
            query = "SELECT * FROM dbo.TblParametro WHERE IdParametro = " + id
            data = cls.get_data(query)
        except (pyodbc.OperationalError, pyodbc.InterfaceError) as db_error:
            logging.error(
                f"Error de conexión con la base de datos: {db_error}")
        except Exception as error:
            logging.error(
                f'Error al obtener datos TblParametro: {error}')
        return data

    @classmethod
    def get_tbltipodoctos(cls, id):
        data = None
        try:
            query = "SELECT * FROM dbo.TblTipoDoctos WHERE idTipoDoctos = " + id
            data = cls.get_data(query)
        except (pyodbc.OperationalError, pyodbc.InterfaceError) as db_error:
            logging.error(
                f"Error de conexión con la base de datos: {db_error}")
        except Exception as error:
            logging.error(
                f'Error al obtener datos TblTipoDoctos: {error}')
        return data

    @classmethod
    def get_tbltipodoctos_encabezado(cls, ids):
        data = None
        try:
            query = "SELECT idTipoDoctos, Encabezado FROM dbo.TblTipoDoctos WHERE idTipoDoctos in " + ids
            data = cls.get_data(query)
        except (pyodbc.OperationalError, pyodbc.InterfaceError) as db_error:
            logging.error(
                f"Error de conexión con la base de datos: {db_error}")
        except Exception as error:
            logging.error(
                f'Error al obtener datos TblTipoDoctos encabezado: {error}')
        return data

    @classmethod
    def get_tbltipoproducto(cls, id):
        data = None
        try:
            query = "SELECT * FROM dbo.TblTipoProducto WHERE IdTipoProducto = " + id
            data = cls.get_data(query)
        except (pyodbc.OperationalError, pyodbc.InterfaceError) as db_error:
            logging.error(
                f"Error de conexión con la base de datos: {db_error}")
        except Exception as error:
            logging.error(
                f'Error al obtener datos TblTipoDoctos 2: {error}')
        return data

    # Metodo encargado de obtener los recibos pagados de un documento dado
    @classmethod
    def get_dctos_cruce(cls, id):
        data = None
        try:
            lista = id.split('-')
            query = "SELECT * FROM dbo.Documentos_Cruce WHERE sw=" + lista[
                0] + " AND tipo=" + lista[1] + " AND numero=" + lista[2]
            data = cls.get_data(query)
        except (pyodbc.OperationalError, pyodbc.InterfaceError) as db_error:
            logging.error(
                f"Error de conexión con la base de datos: {db_error}")
        except Exception as error:
            logging.error(
                f'Error al obtener datos Documentos_Cruce: {error}')
        return data

    # Metodo encargado de obtener la forma en que se pago el comprobante (recibos)
    @classmethod
    def get_tipos_pago(cls, id):
        data = None
        try:
            lista = id.split('-')
            query = "SELECT * FROM dbo.Documentos_Che WHERE sw=" + lista[
                0] + " AND tipo=" + lista[1] + " AND numero=" + lista[2]
            data = cls.get_data(query)
        except (pyodbc.OperationalError, pyodbc.InterfaceError) as db_error:
            logging.error(
                f"Error de conexión con la base de datos: {db_error}")
        except Exception as error:
            logging.error(
                f'Error al obtener datos Documentos_Che: {error}')
        return data

    @classmethod
    def get_data_table(cls, table):
        data = None
        try:
            query = "SELECT * FROM dbo." + table
            data = cls.get_data(query)
        except (pyodbc.OperationalError, pyodbc.InterfaceError) as db_error:
            logging.error(
                f"Error de conexión con la base de datos: {db_error}")
        except Exception as error:
            logging.error(
                f'Error al obtener datos table: {error}')
        return data

    @classmethod
    def get_documentos_orden(cls):
        data = None
        try:
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
        except (pyodbc.OperationalError, pyodbc.InterfaceError) as db_error:
            logging.error(
                f"Error de conexión con la base de datos: {db_error}")
        except Exception as error:
            logging.error(
                f'Error al obtener datos Documentos_Lin & Documentos: {error}')
        return data

    @classmethod
    def get_documentos_traslados(cls):
        data = None
        try:
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
        except (pyodbc.OperationalError, pyodbc.InterfaceError) as db_error:
            logging.error(
                f"Error de conexión con la base de datos: {db_error}")
        except Exception as error:
            logging.error(
                f'Error al obtener datos Documentos traslado: {error}')
        return data

    @classmethod
    def get_biometric_access_transactions(cls, event_time=None):
        data = None
        try:
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
        except (pyodbc.OperationalError, pyodbc.InterfaceError) as db_error:
            logging.error(
                f"Error de conexión con la base de datos: {db_error}")
        except Exception as error:
            logging.error(
                f'Error al obtener datos TblDatosBiometrico: {error}')
