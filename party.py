import datetime
from trytond.model import ModelSQL, ModelView, fields
from trytond.pool import Pool, PoolMeta
from trytond.exceptions import UserError
import logging


__all__ = [
    'Party',
    'PartyAddress',
    'ContactMechanism',
    'Cron',
    ]


class Cron(metaclass=PoolMeta):
    'Cron'
    __name__ = 'ir.cron'

    @classmethod
    def __setup__(cls):
        super().__setup__()
        cls.method.selection.append(
            ('party.party|update_parties', "Importar terceros"),
            )


#Herencia del party.party e insercción de la función actualizar terceros
class Party(ModelSQL, ModelView):
    'Party'
    __name__ = 'party.party'

    # Función encargada de crear o actualizar los terceros de db TecnoCarnes teniendo en cuenta la ultima fecha de actualizacion y si existe.
    @classmethod
    def update_parties(cls):
        logging.warning("RUN TERCEROS")
        pool = Pool()
        Config = pool.get('conector.configuration')
        Actualizacion = pool.get('conector.actualizacion')
        actualizacion = Actualizacion.create_or_update("TERCEROS")
        # Se trae los terceros que cumplan con la fecha establecida
        fecha = datetime.date(1,1,1)
        if actualizacion.write_date:
            print(actualizacion.write_date)
            fecha = actualizacion.write_date.strftime('%Y-%m-%d %H:%M:%S')
        elif actualizacion.create_date:
            print(actualizacion.create_date)
            fecha = actualizacion.create_date.strftime('%Y-%m-%d %H:%M:%S')
        terceros_db = Config.get_tblterceros(fecha)
        if not terceros_db:
            actualizacion.save()
            logging.warning("FINISH TERCEROS")
            return
        pool = Pool()
        Party = pool.get('party.party')
        Address = pool.get('party.address')
        Lang = pool.get('ir.lang')
        es, = Lang.search([('code', '=', 'es_419')])
        Country = pool.get('party.country_code')
        Department = pool.get('party.department_code')
        City = pool.get('party.city_code')

        # Comenzamos a recorrer los terceros traidos por la consulta
        for ter in terceros_db:
            nit_cedula = ter.nit_cedula
            tipo_identificacion = cls.id_type(ter.tipo_identificacion)
            nombre = cls.delete_caracter(ter.nombre.strip()).upper()
            PrimerNombre = cls.delete_caracter(ter.PrimerNombre.strip()).upper()
            SegundoNombre = cls.delete_caracter(ter.SegundoNombre.strip()).upper()
            PrimerApellido = cls.delete_caracter(ter.PrimerApellido.strip()).upper()
            SegundoApellido = cls.delete_caracter(ter.SegundoApellido.strip()).upper()
            mail = ter.mail.strip()
            telefono = ter.telefono.strip()
            TipoPersona = cls.person_type(ter.TipoPersona.strip())
            ciiu = ter.IdActividadEconomica
            TipoContribuyente = cls.tax_regime(ter.IdTipoContribuyente)
            exists = cls.find_party(nit_cedula)
            #Ahora verificamos si el tercero existe en la bd de tryton
            if exists:
                ultimo_cambiop = ter.Ultimo_Cambio_Registro
                create_date = None
                write_date = None
                #LA HORA DEL SISTEMA DE TRYTON TIENE UNA DIFERENCIA HORARIA DE 5 HORAS CON LA DE TECNO
                if exists.write_date:
                    write_date = (exists.write_date - datetime.timedelta(hours=5, minutes=5))
                elif exists.create_date:
                    create_date = (exists.create_date - datetime.timedelta(hours=5, minutes=5))
                #Ahora vamos a verificar si el cambio más reciente fue hecho en la bd sqlserver para actualizarlo
                if (ultimo_cambiop and write_date and ultimo_cambiop > write_date) or (ultimo_cambiop and not write_date and ultimo_cambiop > create_date):
                    exists.type_document = tipo_identificacion
                    exists.name = nombre
                    exists.first_name = PrimerNombre
                    exists.second_name = SegundoNombre
                    exists.first_family_name = PrimerApellido
                    exists.second_family_name = SegundoApellido
                    exists.type_person = TipoPersona
                    if exists.type_person == 'persona_juridica':
                        exists.declarante = True
                    #Verificación e inserción codigo ciiu
                    if ciiu and ciiu != 0:
                        exists.ciiu_code = ciiu
                    exists.regime_tax = TipoContribuyente
                    exists.lang = es
                    exists.save()
                #Actualización de los 2 metodos de contactos principales
                cls.update_contact(exists, ultimo_cambiop, mail, 'email')
                cls.update_contact(exists, ultimo_cambiop, telefono, 'phone')
            else:
                #Creando tercero junto con sus direcciones y metodos de contactos
                tercero = Party()
                tercero.type_document = tipo_identificacion
                tercero.id_number = nit_cedula
                tercero.name = nombre
                tercero.first_name = PrimerNombre
                tercero.second_name = SegundoNombre
                tercero.first_family_name = PrimerApellido
                tercero.second_family_name = SegundoApellido
                #Equivalencia tipo de persona y asignación True en declarante
                tercero.type_person = TipoPersona
                if tercero.type_person == 'persona_juridica':
                    tercero.declarante = True
                #Verificación e inserción codigo ciiu
                if ciiu and ciiu != 0:
                    tercero.ciiu_code = ciiu
                #Equivalencia regimen de impuestos
                tercero.regime_tax = TipoContribuyente
                tercero.lang = es
                tercero.save()
                #Creamos las direcciones pertenecientes al tercero
                direcciones_tecno = Config.get_tercerosdir_nit(nit_cedula)
                for direccion in direcciones_tecno:
                    cls.create_address_new(tercero, direccion)
                #Metodos de contactos
                cls.create_contact_type(tercero, mail, 'email')
                cls.create_contact_type(tercero, telefono, 'phone')

        # Actualización de direcciones
        direcciones_db = Config.get_tercerosdir(fecha)
        for dir in direcciones_db:
            nit = dir.nit
            tercero = Party.search([('id_number', '=', nit)])
            if not tercero:
                continue
            id_tecno = nit+'-'+str(dir.codigo_direccion)
            address = Address.search([('id_tecno', '=', id_tecno)])
            if address:
                address = address[0]
                ultimo_cambiod = dir.Ultimo_Cambio_Registro
                create_date = None
                write_date = None
                if address.write_date:
                    write_date = (address.write_date - datetime.timedelta(hours=5, minutes=5))
                elif address.create_date:
                    create_date = (address.create_date - datetime.timedelta(hours=5, minutes=5))
                if (ultimo_cambiod and write_date and ultimo_cambiod > write_date) or (ultimo_cambiod and not write_date and ultimo_cambiod > create_date):
                    region = list(dir.CodigoSucursal.strip())
                    try:
                        country_code, = Country.search([('code', '=', '169')])
                        if len(region) > 4:
                            department_code = Department.search([('code', '=', region[0]+region[1])])
                            if department_code:
                                address.department_code = department_code[0]
                                city_code = City.search([
                                    ('code', '=', region[2]+region[3]+region[4]),
                                    ('department', '=', department_code[0])
                                    ])
                                if city_code:
                                    address.city_code = city_code[0]
                    except Exception as e:
                        print(e)
                        raise UserError("ERROR REGION", f"Error: {e}")
                    address.country_code = country_code
                    barrio = dir.Barrio.strip()
                    if barrio and len(barrio) > 2:
                        address.name = barrio
                    address.party_name = tercero[0].name
                    street = dir.direccion.strip()
                    if len(street) > 2:
                        address.street = street
                    address.save()
            else:
                cls.create_address_new(tercero[0], dir)
        logging.warning("FINISH TERCEROS")


    @classmethod
    def create_address_new(cls, party, data):
        Address = Pool().get('party.address')
        Country = Pool().get('party.country_code')
        Department = Pool().get('party.department_code')
        City = Pool().get('party.city_code')
        if data.codigo_direccion == 1:
            comercial_name = cls.delete_caracter(data.NombreSucursal.strip()).upper()
            if len(comercial_name) > 2:
                party.commercial_name = comercial_name
        direccion = Address()
        direccion.id_tecno = data.nit+'-'+str(data.codigo_direccion)
        region = list(data.CodigoSucursal.strip())
        try:
            country_code, = Country.search([('code', '=', '169')])
            if len(region) > 4:
                department_code = Department.search([('code', '=', region[0]+region[1])])
                if department_code:
                    direccion.department_code = department_code[0]
                    city_code = City.search([
                        ('code', '=', region[2]+region[3]+region[4]),
                        ('department', '=', department_code[0])
                        ])
                    if city_code:
                        direccion.city_code = city_code[0]
        except Exception as e:
            print(e)
            raise UserError("ERROR REGION", f"Error: {e}")
        direccion.country_code = country_code
        barrio = data.Barrio.strip()
        if barrio and len(barrio) > 2:
            direccion.name = barrio
        direccion.party = party
        direccion.party_name = party.name
        street = data.direccion.strip()
        if len(street) > 2:
            direccion.street = street
        direccion.save()

    #Función encargada de verificar, actualizar e insertar los metodos de contacto pertenecientes a un tercero dado
    @classmethod
    def update_contact(cls, party, ultimo_cambio, value, type):
        if len(value) > 4:
            Mcontact = Pool().get('party.contact_mechanism')
            #Buscamos y validamos el contacto
            id_t = party.id_number+'-tel'
            if type == 'email':
                id_t = party.id_number+'-mail'
            contact = Mcontact.search([('id_tecno', '=', id_t)])
            if contact:
                contact = contact[0]
                create_date = None
                write_date = None
                if contact.write_date:
                    write_date = (contact.write_date - datetime.timedelta(hours=5, minutes=5))
                else:
                    create_date = (contact.create_date - datetime.timedelta(hours=5, minutes=5))
                if (ultimo_cambio and write_date and ultimo_cambio > write_date) or (ultimo_cambio and not write_date and ultimo_cambio > create_date):
                    contact.value = value
                    contact.save()
            else:
                cls.create_contact_type(party, value, type)

    @classmethod
    def create_contact_type(cls, party, value, type):
        Mcontact = Pool().get('party.contact_mechanism')
        Lang = Pool().get('ir.lang')
        es, = Lang.search([('code', '=', 'es_419')])
        if len(value) > 4:
            contacto = Mcontact()
            if type == 'phone':
                contacto.id_tecno = party.id_number+'-tel'
                contacto.name = 'telefono'
            elif type == 'email':
                contacto.id_tecno = party.id_number+'-mail'
                contacto.name = 'correo'
            contacto.type = type
            contacto.value = value
            contacto.language = es
            contacto.party = party
            contacto.save()

    #Función encargada de eliminar caracteres especiales y convertir string en alfanumerico
    @classmethod
    def delete_caracter(cls, word):
        list_word = word.split(" ")
        result = ''
        for word in list_word:
            res = ''.join(filter(str.isalnum, word))
            if result != '':
                result = result+' '+res
            else:
                result = res
        return result

    #Función encargada de retornar el tercero de acuerdo a su id_number
    @classmethod
    def find_party(cls, id):
        Party = Pool().get('party.party')
        try:
            party, = Party.search([('id_number', '=', id)])
            return party
        except Exception as e:
            return False

    #Función encargada de realizar la equivalencia entre los tipo de documentos de la db
    #y los tipos de documentos del modulo account_col de presik
    @classmethod
    def id_type(cls, type):
        #Equivalencia tipo de identificacion
        if type == '1':
            return '13'
        elif type == '2':
            return '22'
        elif type == '3':
            return '31'
        elif type == '4':
            return '41'
        elif type == '6':
            return '12'
        else:
            return None

    #Función encargada de realizar la equivalencia entre los tipos de personas de la db TecnoCarnes
    # y los tipos del modulo account_col de presik
    @classmethod
    def person_type(cls, type):
        #Equivalencia tipo de persona y asignación True en declarante
        if type == 'Natural':
            return 'persona_natural'
        elif type == 'Juridica':
            return 'persona_juridica'

    #Función encargada de realizar la equivalencia entre los regimen de impuestos de la db TecnoCarnes
    # y los regimen de impuestos del modulo account_col de presik
    @classmethod
    def tax_regime(cls, regime):
        #Equivalencia regimen de impuestos
        if regime == 1 or regime == 4:
            return 'gran_contribuyente'
        elif regime == 2 or regime == 5 or regime == 6 or regime == 7 or regime == 8:
            return 'regimen_responsable'
        elif regime == 3 or regime == 0:
            return'regimen_no_responsable'
        else:
            return None

#Herencia del party.address e insercción del campo id_tecno
class PartyAddress(ModelSQL, ModelView):
    'PartyAddress'
    __name__ = 'party.address'
    id_tecno = fields.Char('Id TecnoCarnes', required=False)


#Herencia del party.contact_mechanism e insercción del campo id_tecno
class ContactMechanism(ModelSQL, ModelView):
    'ContactMechanism'
    __name__ = 'party.contact_mechanism'
    id_tecno = fields.Char('Id TecnoCarnes', required=False)