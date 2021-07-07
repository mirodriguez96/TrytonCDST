
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
        #cls.fecha = datetime.datetime.now()

        Acterceros = Pool().get('conector.terceros')
        ultima_actualizacion = Acterceros.search([], order=[('id', 'DESC')], limit=1)

        print(ultima_actualizacion[0])
        """
        terceros_tecno = []
        try:
            with conexion.cursor() as cursor:
                query = cursor.execute("SELECT * FROM dbo.TblTerceros WHERE fecha_creacion > ? OR Ultimo_CambioRegistro > ?")
                for t in query.fetchall():
                    terceros_tecno.append([t[2], t[1]])
        except Exception as e:
            print("Error consulta1: ", e)
        finally:
            conexion.cursor().close()
            #print(terceros_tecno)

        direcciones_tecno = []
        try:
            with conexion.cursor() as cursor:
                for ter in terceros_tecno:
                    query2 = cursor.execute("SELECT * FROM dbo.Terceros_Dir WHERE nit = ?", (ter[0]))
                    result = query2.fetchall()[0]
                    if result:
                        direcciones_tecno.append([result[0], result[3], result[13], result[2], result[4]])
        except Exception as e:
            print("Error consulta2: ", e)
        finally:
            cursor.close()
            conexion.close()
            #print(direcciones_tecno)

        Party = Pool().get('party.party')
        Address = Pool().get('party.address')
        Lang = Pool().get('ir.lang')
        es, = Lang.search([('code', '=', 'es')])
        Mcontact = Pool().get('party.contact_mechanism')
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
        """
        return None

    @classmethod
    def pruebacron(cls):
        print ("-----------Prueba CRON--------------")
        return None