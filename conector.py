
from conexion import conexion
from trytond.model import ModelSQL, ModelView, fields
from trytond.pool import Pool
import datetime
import json

__all__ = [
    'Terceros',
    ]

class Terceros(ModelSQL, ModelView):
    'Terceros'
    __name__ = 'conector.terceros'

    actualizacion = fields.Char('Actualizacion', required=True)
    fecha = fields.DateTime('Fecha y hora', format="%H:%M:%S", required=True)


    @classmethod
    def __setup__(cls):
        super().__setup__()
        cls._buttons.update({
                'cargar_datos': {},
                })
        cls._error_messages.update({
            'invalid_insert': 'Actualizacion erronea',
        })

    """
    @classmethod
    def validate(cls, books):
        for book in books:
            if not book.isbn:
                continue
            try:
                if int(book.isbn) < 0:
                    raise ValueError
            except ValueError:
                cls.raise_user_error('invalid_isbn')
    """

    @classmethod
    def default_fecha(cls):
        return datetime.datetime.now()

    @classmethod
    @ModelView.button
    def cargar_datos(cls, fecha = None):
        
        terceros_tecno = None
        try:
            with conexion.cursor() as cursor:
                columnas = cursor.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'dbo.TblTerceros'")
                print(columnas.fetchall())
                query = cursor.execute("SELECT TOP(1) * FROM dbo.TblTerceros")
                #print(query.fetchall()[0][0])
                #terceros_tecno = json.loads(query.fetchall()[0][0])
                print(query.fetchall())
        except Exception as e:
            print("ERROR consulta terceros_tecno: ", e)
        finally:
            cursor.close()
            conexion.close()

"""
        direcciones_tecno = None
        try:
            with conexion.cursor() as cursor:
                query2 = cursor.execute("SELECT TOP(1) * FROM dbo.Terceros_Dir FOR JSON PATH")
                direcciones_tecno = json.loads(query2.fetchall()[0][0])
        except Exception as e:
            print("ERROR consulta direcciones_tecno: ", e)
        finally:
            cursor.close()
            conexion.close()

        pool = Pool()
        Party = pool.get('party.party')
        Address = pool.get('party.address')
        Lang = pool.get('ir.lang')
        es, = Lang.search([('code', '=', 'es_419')])
        Mcontact = pool.get('party.contact_mechanism')
        to_create = []
        for ter in terceros_tecno:
            tercero = Party()
            tercero.code = ter['nit_cedula']
            tercero.name = ter['nombre']
            tercero.lang = es
            for dir in direcciones_tecno:
                if dir['nit'] == ter['nit_cedula']:
                    if dir['telefono_1']:
                        #Creacion e inserccion de metodos de contacto
                        contacto = Mcontact()
                        contacto.type = 'phone'
                        contacto.value = dir['telefono_1']
                        contacto.party = tercero
                        contacto.save()
                    if dir['telefono_2']:
                        #Creacion e inserccion de metodos de contacto
                        contacto = Mcontact()
                        contacto.type = 'phone'
                        contacto.value = dir['telefono_2']
                        contacto.party = tercero
                        contacto.save()
                    if ter['mail']:
                        #Creacion e inserccion de metodos de contacto
                        contacto = Mcontact()
                        contacto.type = 'email'
                        contacto.value = ter['mail']
                        contacto.party = tercero
                        contacto.save()
                    #Creacion e inserccion de direcciones
                    direccion = Address()
                    direccion.city = dir['ciudad']
                    direccion.country = 50
                    direccion.name = dir['Barrio']
                    direccion.party = tercero
                    direccion.party_name = tercero.name
                    direccion.street = dir['direccion']
                    direccion.save()
            to_create.append(tercero)
        Party.save(to_create)
        return None
"""
"""
    @classmethod
    @ModelView.button
    def btn_prueba(cls, fecha = None):
        return None
"""