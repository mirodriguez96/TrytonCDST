import pyodbc
import datetime


class Conexion:

    def __init__(self, data):
        self.server = data['server']
        self.database = data['database']
        self.user = data['user']
        self.password = data['password']

    # Metodo encargado de realizar la conexion a la base de datos externa
    def conexion(self):
        """
        Las conexiones utilizadas en un bloque with se confirmarán al final del bloque
        si no se generan errores, y se revertirán de lo contrario
        """
        driver = "DRIVER={ODBC Driver 17 for SQL Server};"\
                f"SERVER={self.server};DATABASE={self.database};"\
                f"UID={self.user};PWD={self.password}"
        with pyodbc.connect(driver) as cnxn:
            return cnxn
    
    # Se prueba la conexión y retorna booleano
    def test_conexion(self):
        try:
            self.conexion()
            return True
        except pyodbc.DatabaseError as error:
            print(error)
            return False

    # 
    def get_data(self, query):
        data = []
        cnxn = self.conexion()
        with cnxn.cursor() as cursor:
            cursor.execute(query)
            data = cursor.fetchall()
        cnxn.close()
        return data

    # 
    def set_data(self, query):
        cnxn = self.conexion()
        with cnxn.cursor() as cursor:
            cursor.execute(query)
        cnxn.close()