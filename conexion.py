import pyodbc

# Clase no utilizada
class Conexion:

    def __init__(self, data):
        #Atributos necesarios para la conexion
        self.server = data['server']
        self.db = data['db']
        self.user = data['user']
        self.password = data['password']

    # Metodo encargado de realizar la conexion a la base de datos externa
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