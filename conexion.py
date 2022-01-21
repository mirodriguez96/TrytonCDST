import pyodbc


class Conexion:

    def __init__(self, data):
        #Atributos necesarios para la conexion
        self.server = data['server']
        self.db = data['db']
        self.user = data['user']
        self.password = data['password']

    #Metodo encargado de realizar la conexion a la base de datos externa
    def conexion(self):
        #Las conexiones utilizadas en un bloque with se confirmarán al final del bloque si no se generan errores y se revertirán de lo contrario
        with pyodbc.connect('DRIVER={ODBC Driver 17 for SQL Server};SERVER='+self.server+';DATABASE='+self.db+';UID='+self.user+';PWD='+self.password) as cnxn:
            return cnxn

    #
    def get_data(self, query):
        data = []
        cnxn = self.conexion()
        cursor = cnxn.cursor()
        cursor.execute(query)
        data = cursor.fetchall()
        cnxn.close()
        return data

    #
    def set_data(self, query):
        cnxn = self.conexion()
        cursor = cnxn.cursor()
        cursor.execute(query)
        cnxn.close()


"""
    @classmethod
    def conexion(cls):
        Config = Pool().get('conector.configuration')
        last_record = Config.search([], order=[('id', 'DESC')], limit=1)
        if last_record:
            record, = last_record
            #Las conexiones utilizadas en un bloque with se confirmarán al final del bloque si no se generan errores y se revertirán de lo contrario
            with pyodbc.connect('DRIVER={ODBC Driver 17 for SQL Server};SERVER='+record.server+';DATABASE='+record.db+';UID='+record.user+';PWD='+record.password) as cnxn:
                return cnxn
        else:
            raise UserError('Error: ', 'Ingrese por favor los datos de configuracion de la base de datos')


    #Función que se activa al pulsar el botón test_conexion
    @classmethod
    @ModelView.button
    def test_conexion(cls, record):
        cnxn = cls.conexion()
        cnxn.close()
        raise UserError('Conexión sqlserver: ', 'Exitosa !')


    #Función encargada de enviar la conexión configurada con los datos del primer registro
    @classmethod
    def get_data(cls, query):
        data = []
        cnxn = cls.conexion()
        cursor = cnxn.cursor()
        cursor.execute(query)
        data = cursor.fetchall()
        cnxn.close()
        return data


    #
    @classmethod
    def set_data(cls, query):
        cnxn = cls.conexion()
        cursor = cnxn.cursor()
        cursor.execute(query)
        cnxn.close()
"""