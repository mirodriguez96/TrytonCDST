from trytond.model import ModelSQL, ModelView, fields
from trytond.pool import Pool
from trytond.exceptions import UserError
#from trytond.bus import notify

try:
    import pyodbc
except:
    print("Warning: Does not possible import pyodbc module!")
    print("Please install it...!")


__all__ = [
    'Configuration',
    ]

class Configuration(ModelSQL, ModelView):
    'Configuration'
    __name__ = 'conector.configuration'

    server = fields.Char('Server', required=True, help="Example: tcp:ip,port")
    db = fields.Char('Database', required=True, help="Enter the name of the database without leaving spaces")
    user = fields.Char('User', required=True, help="Enter the user of the database without leaving spaces")
    password = fields.Char('Password', required=True, help="Enter the password of the database without leaving spaces")

    @classmethod
    def __setup__(cls):
        super(Configuration, cls).__setup__()
        cls._buttons.update({
                'test_conexion': {},
                })

    #Función que se activa al pulsar el botón test_conexion
    @classmethod
    @ModelView.button
    def test_conexion(cls, records):
        for record in records:
            try:
                conexion = pyodbc.connect('DRIVER={ODBC Driver 17 for SQL Server};SERVER='+str(record.server)+';DATABASE='+str(record.db)+';UID='+str(record.user)+';PWD='+str(record.password))
                print("Conexion sqlserver exitosa !")
                #notify('Conexion sqlserver exitosa !', priority=3)
                raise UserError('Conexión sqlserver: ', 'Exitosa !')
            except Exception as e:
                print('Error sql server: ', e)
                raise UserError('Conexión sqlserver: ', str(e))
            finally:
                conexion.close()

    #Función encargada de enviar la conexión configurada con los datos del primer registro
    @classmethod
    def conexion(cls):
        Config = Pool().get('conector.configuration')
        last_record = Config.search([], order=[('id', 'DESC')], limit=1)
        if last_record:
            record = last_record[0]
            try:
                conexion = pyodbc.connect('DRIVER={ODBC Driver 17 for SQL Server};SERVER='+str(record.server)+';DATABASE='+str(record.db)+';UID='+str(record.user)+';PWD='+str(record.password))
                return conexion
            except Exception as e:
                print('Error sql server: ', e)
                raise UserError('Error al conectarse a la base de datos (SQL Server): ', str(e))
        else:
            raise UserError('Error: ', 'Ingrese por favor los datos de configuracion de la base de datos')
