
from conexion import conexion
from trytond.model import ModelSQL, ModelView, fields
from trytond.pool import Pool
import datetime

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
            'invalid_insert': 'Actualizacion erronea'
        })

    @classmethod
    def default_fecha(cls):
        return datetime.datetime.now()

    @classmethod
    @ModelView.button
    def cargar_datos(cls, fecha = None):
        """
        terceros_tecno = []
        try:
            with conexion.cursor() as cursor:
                query = cursor.execute("SELECT * FROM dbo.TblTerceros")
                for t in query.fetchall():
                    terceros_tecno.append([t['nit_cedula'], t['nombre']])
        except Exception as e:
            print("Error consulta 1: ", e)
        finally:
            cursor.close()
        """
        direcciones_tecno = []
        try:
            with conexion.cursor() as cursor:
                query2 = cursor.execute("SELECT TOP(3) * FROM dbo.Terceros_Dir FOR JSON AUTO")
                print(query2.fetchall()[1])
                """
                for d in query2.fetchall():
                    print('  ------------------------>  ')
                    print (d)
                    #direcciones_tecno.append(d)
                
                for ter in terceros_tecno:
                    result = query2.fetchall()[0]
                    if result:
                        direcciones_tecno.append([result['nit_cedula'], result[3], result[13], result[2], result[4]])
                        """
        except Exception as e:
            print("Error consulta 2: ", e)
        finally:
            cursor.close()
            conexion.close()
            #print (direcciones_tecno)
"""
        pool = Pool()
        Party = pool.get('party.party')
        Address = pool.get('party.address')
        Lang = pool.get('ir.lang')
        es, = Lang.search([('code', '=', 'es_419')])
        Mcontact = pool.get('party.contact_mechanism')
        to_create = []
        for ter in terceros_tecno:
            exemp = Party()
            exemp.code = ter[0]
            exemp.name = ter[1]
            exemp.lang = es
            for dir in direcciones_tecno:
                if dir[0] == ter[0]:
                    #Creacion e inserccion de metodos de contacto
                    contacto = Mcontact()
                    contacto.type = 'phone'
                    contacto.value = dir[4]
                    contacto.party = exemp
                    contacto.save()
                    #Creacion e inserccion de direcciones
                    exemd = Address()
                    exemd.city = dir[1]
                    exemd.country = 50
                    exemd.name = dir[2]
                    exemd.party = exemp
                    exemd.party_name = exemp.name
                    exemd.street = dir[3]
                    exemd.save()
            to_create.append(exemp)
        Party.save(to_create)
        return None


    @classmethod
    @ModelView.button
    def actualizar_datos(cls, fecha = None):
        pool = Pool()
        Acterceros = pool.get('conector.terceros')
        ultima_actualizacion = Acterceros.search([], order=[('id', 'DESC')], limit=1)
        print(ultima_actualizacion[0].fecha)

        return None

"""