import pyodbc
import datetime
import logging


class Conexion:

    def __init__(self, data):
        self.server = data['server']
        self.database = data['database']
        self.user = data['user']
        self.password = data['password']

    def conexion(self):
        """
        Las conexiones utilizadas en un bloque with se confirmarán al final del bloque
        si no se generan errores, y se revertirán de lo contrario
        """
        try:
            driver = "DRIVER={ODBC Driver 17 for SQL Server};"\
                f"SERVER={self.server};DATABASE={self.database};"\
                f"UID={self.user};PWD={self.password}"\
                "Connection Timeout=5;"
            with pyodbc.connect(driver) as cnxn:
                cursor = cnxn.cursor()
                cursor.execute("SELECT 1")
                return cnxn
        except pyodbc.Error as error:
            logging.error(f'Error de conexión a SQL Server: {error}')
            print(f'ERROR DE CONEXION: {error}')

    def test_conexion(self):
        try:
            with self.conexion() as cnxn:
                with cnxn.cursor() as cursor:
                    cursor.execute("SELECT 1")
            return True
        except pyodbc.DatabaseError as error:
            logging.error(f'Error en la prueba de conexión: {error}')
            return False

    def get_data(self, query):
        try:
            data = []
            with self.conexion() as cnxn:
                with cnxn.cursor() as cursor:
                    cursor.execute(query)
                    data = cursor.fetchall()
            return data
        except Exception as error:
            logging.error(f'Error al obtener datos: {error}')

    def set_data(self, query):
        try:
            with self.conexion() as cnxn:
                with cnxn.cursor() as cursor:
                    cursor.execute(query)
        except Exception as error:
            logging.error(f'Error al ejecutar la consulta: {error}')
