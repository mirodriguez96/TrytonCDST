import datetime
from trytond.model import ModelSQL, ModelView, fields
from trytond.pool import Pool, PoolMeta
from trytond.transaction import Transaction
#from trytond.exceptions import UserError
#from conexion import conexion


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
            ('party.party|update_parties', "Update parties"),
            )


#Herencia del party.party e insercción de la función actualizar terceros
class Party(ModelSQL, ModelView):
    'Party'
    __name__ = 'party.party'

    #Función encargada de crear o actualizar los terceros de db TecnoCarnes,
    #teniendo en cuenta la ultima fecha de actualizacion y si existe o no.
    @classmethod
    def update_parties(cls):
        print("---------------RUN TERCEROS---------------")
        terceros_tecno = cls.last_update()
        cls.create_actualizacion(False)
        if terceros_tecno:
            columnas_terceros = cls.get_columns_db_tecno('TblTerceros')
            columnas_contactos = cls.get_columns_db_tecno('Terceros_Contactos')
            columna_direcciones = cls.get_columns_db_tecno('Terceros_Dir')
            pool = Pool()
            Party = pool.get('party.party')
            Address = pool.get('party.address')
            Lang = pool.get('ir.lang')
            es, = Lang.search([('code', '=', 'es_419')])
            Mcontact = pool.get('party.contact_mechanism')
            to_create = []
            create_address = []
            create_contact = []
            #Comenzamos a recorrer los terceros traidos por la consulta
            for ter in terceros_tecno:
                nit_cedula = ter[columnas_terceros.index('nit_cedula')].strip()
                tipo_identificacion = cls.id_type(ter[columnas_terceros.index('tipo_identificacion')])
                nombre = ter[columnas_terceros.index('nombre')].strip()
                PrimerNombre = ter[columnas_terceros.index('PrimerNombre')].strip()
                SegundoNombre = ter[columnas_terceros.index('SegundoNombre')].strip()
                PrimerApellido = ter[columnas_terceros.index('PrimerApellido')].strip()
                SegundoApellido = ter[columnas_terceros.index('SegundoApellido')].strip()
                TipoPersona = cls.person_type(ter[columnas_terceros.index('TipoPersona')].strip())
                ciiu = ter[columnas_terceros.index('IdActividadEconomica')]
                TipoContribuyente = cls.tax_regime(ter[columnas_terceros.index('IdTipoContribuyente')])
                exists = cls.find_party(nit_cedula)
                #Ahora verificamos si el tercero existe en la bd de tryton
                if exists:
                    ultimo_cambio = ter[columnas_terceros.index('Ultimo_Cambio_Registro')]
                    #Ahora vamos a verificar si el cambio más reciente fue hecho en la bd sqlserver para actualizarlo
                    if (ultimo_cambio and exists.write_date and ultimo_cambio > exists.write_date) or (ultimo_cambio and not exists.write_date and ultimo_cambio > exists.create_date):
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
                        #Actualización de la dirección y metodos de contacto
                        cls.update_address(exists)
                        cls.update_contact(exists)
                        exists.save()
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
                    direcciones_tecno = cls.get_address_db_tecno(nit_cedula)
                    if direcciones_tecno:
                        for direc in direcciones_tecno:
                            if direc[columna_direcciones.index('codigo_direccion')] == 1:
                                tercero.commercial_name = direc[columna_direcciones.index('NombreSucursal')].strip()
                            #Creacion e inserccion de direccion
                            direccion = Address()
                            direccion.id_tecno = direc[columna_direcciones.index('nit')].strip()+'-'+str(direc[columna_direcciones.index('codigo_direccion')])
                            direccion.city = direc[columna_direcciones.index('ciudad')].strip()
                            direccion.country = 50
                            barrio = direc[columna_direcciones.index('Barrio')].strip()
                            if barrio:
                                direccion.name = barrio
                            direccion.party = tercero
                            direccion.party_name = nombre
                            direccion.street = direc[columna_direcciones.index('direccion')].strip()
                            create_address.append(direccion)
                            #direccion.save()
                    contactos_tecno = cls.get_contacts_db_tecno(nit_cedula)
                    if contactos_tecno:
                        for cont in contactos_tecno:
                            #Creacion e inserccion de metodo de contacto phone
                            contacto = Mcontact()
                            contacto.id_tecno = str(cont[columnas_contactos.index('IdContacto')])+'-1'
                            contacto.type = 'phone'
                            contacto.value = cont[columnas_contactos.index('Telefono')].strip()
                            contacto.name = cont[columnas_contactos.index('Nombre')].strip()+' ('+cont[columnas_contactos.index('Cargo')].strip()+')'
                            contacto.language = es
                            contacto.party = tercero
                            create_contact.append(contacto)
                            #contacto.save()
                            #Creacion e inserccion de metodo de contacto email
                            contacto = Mcontact()
                            contacto.id_tecno = str(cont[columnas_contactos.index('IdContacto')])+'-2'
                            contacto.type = 'email'
                            contacto.value = cont[columnas_contactos.index('Email')].strip()
                            contacto.name = cont[columnas_contactos.index('Nombre')].strip()+' ('+cont[columnas_contactos.index('Cargo')].strip()+')'
                            contacto.language = es
                            contacto.party = tercero
                            create_contact.append(contacto)
                            #contacto.save()
                    to_create.append(tercero)
            Party.save(to_create)
            Address.save(create_address)
            Mcontact.save(create_contact)


    #Función encargada de verificar, actualizar e insertar las direcciones pertenecientes a un tercero dado
    @classmethod
    def update_address(cls, party):
        address_tecno = cls.get_address_db_tecno(party.id_number)
        #Consultamos si existen direcciones para el tercero
        if address_tecno:
            columna_direcciones = cls.get_columns_db_tecno('Terceros_Dir')
            Address = Pool().get('party.address')
            for add in address_tecno:
                id_tecno = add[columna_direcciones.index('nit')]+'-'+str(add[columna_direcciones.index('codigo_direccion')])
                address = Address.search([('id_tecno', '=', id_tecno)])
                if address:
                    if add[columna_direcciones.index('codigo_direccion')] == 1:
                        party.commercial_name = add[columna_direcciones.index('NombreSucursal')].strip()
                    address.city = add[columna_direcciones.index('ciudad')].strip()
                    barrio = add[columna_direcciones.index('Barrio')].strip()
                    if barrio:
                        address.name = barrio
                    address.street = add[columna_direcciones.index('direccion')].strip()
                    address.save()
                else:
                    if add[columna_direcciones.index('codigo_direccion')] == 1:
                        party.commercial_name = add[columna_direcciones.index('NombreSucursal')].strip()
                    address = Address()
                    address.id_tecno = id_tecno
                    address.city = add[columna_direcciones.index('ciudad')].strip()
                    address.country = 50
                    barrio = add[columna_direcciones.index('Barrio')].strip()
                    if barrio:
                        address.name = barrio
                    address.party = party
                    address.party_name = party.name
                    address.street = add[columna_direcciones.index('direccion')].strip()
                    address.save()


    #Función encargada de verificar, actualizar e insertar los metodos de contacto pertenecientes a un tercero dado
    @classmethod
    def update_contact(cls, party):
        contacts_tecno = cls.get_contacts_db_tecno(party.id_number)
        #Consultamos si existen contactos para el tercero
        if contacts_tecno:
            columns_contact = cls.get_columns_db_tecno('Terceros_Contactos')
            Contacts = Pool().get('party.contact_mechanism')
            for cont in contacts_tecno:
                id_tecno = str(cont[columns_contact.index('IdContacto')])
                nombre = cont[columns_contact.index('Nombre')].strip()+' ('+cont[columns_contact.index('Cargo')].strip()+')'
                contact1 = Contacts.search([('id_tecno', '=', id_tecno+'-1')])
                contact2 = Contacts.search([('id_tecno', '=', id_tecno+'-2')])
                Lang = Pool().get('ir.lang')
                es, = Lang.search([('code', '=', 'es_419')])
                #Verificamos y creamos el metodo de contacto phone, en caso de ser necesario
                if contact1:
                    contact1.value = cont[columns_contact.index('Telefono')].strip()
                    contact1.name = nombre
                    contact1.save()
                else:
                    #Creacion e inserccion de metodo de contacto phone
                    contacto = Contacts()
                    contacto.id_tecno = id_tecno+'-1'
                    contacto.type = 'phone'
                    contacto.value = cont[columns_contact.index('Telefono')].strip()
                    contacto.name = nombre
                    contacto.language = es
                    contacto.party = party
                    contacto.save()
                #Verificamos y creamos el metodo de contacto email, en caso de ser necesario
                if contact2:
                    contact2.value = cont[columns_contact.index('Email')].strip()
                    contact2.name = nombre
                    contact2.save()
                else:
                    #Creacion e inserccion de metodo de contacto email
                    contacto = Contacts()
                    contacto.id_tecno = id_tecno+'-2'
                    contacto.type = 'email'
                    contacto.value = cont[columns_contact.index('Email')].strip()
                    contacto.name = nombre
                    contacto.language = es
                    contacto.party = party
                    contacto.save()


    #Función encargada de retornar el tercero de acuerdo a su id_number
    @classmethod
    def find_party(cls, id):
        Party = Pool().get('party.party')
        party = Party.search([('id_number', '=', id)])
        if party:
            print('Encontro', id)
            return party[0]
        else:
            print('NO Se Encontro', id)
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

    #Función encargada de consultar la dirección de un tercero dado
    @classmethod
    def find_address(cls, party):
        Address = Pool().get('party.address')
        address = Address.__table__()
        cursor = Transaction().connection.cursor()
        cursor.execute(*address.select(where=(address.party == party.id)))
        result = cursor.fetchall()
        return result

    #Función encargada de consultar el metodo de contacto de un tercero dado
    @classmethod
    def find_contact_mechanism(cls, party):
        Contact = Pool().get('party.contact_mechanism')
        contact = Contact.__table__()
        cursor = Transaction().connection.cursor()
        cursor.execute(*contact.select(where=(contact.party == party.id)))
        result = cursor.fetchall()
        return result

    #Función encargada de consultar las columnas pertenecientes a 'x' tabla de la bd de TecnoCarnes
    @classmethod
    def get_columns_db_tecno(cls, table):
        columns = []
        try:
            Config = Pool().get('conector.configuration')
            conexion = Config.conexion()
            with conexion.cursor() as cursor:
                query = cursor.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = '"+table+"' ORDER BY ORDINAL_POSITION")
                for q in query.fetchall():
                    columns.append(q[0])
        except Exception as e:
            print("ERROR QUERY "+table+": ", e)
        return columns

    #Esta función se encarga de traer todos los datos de una tabla dada de la bd TecnoCarnes
    @classmethod
    def get_data_db_tecno(cls, table):
        data = []
        try:
            Config = Pool().get('conector.configuration')
            conexion = Config.conexion()
            with conexion.cursor() as cursor:
                query = cursor.execute("SELECT * FROM dbo."+table)
                data = list(query.fetchall())
        except Exception as e:
            print("ERROR QUERY "+table+": ", e)
        return data

    #Esta función se encarga de traer todos los datos de una tabla dada de acuerdo al rango de fecha dada de la bd TecnoCarnes
    @classmethod
    def get_data_where_tecno(cls, table, date):
        data = []
        try:
            Config = Pool().get('conector.configuration')
            conexion = Config.conexion()
            with conexion.cursor() as cursor:
                query = cursor.execute("SELECT * FROM dbo."+table+" WHERE fecha_creacion >= CAST('"+date+"' AS datetime) OR Ultimo_Cambio_Registro >= CAST('"+date+"' AS datetime)")
                data = list(query.fetchall())
        except Exception as e:
            print("ERROR QUERY get_data_where_tecno: ", e)
        return data

    #Función encargada de consultar las direcciones pertenecientes a un tercero en la bd TecnoCarnes
    @classmethod
    def get_address_db_tecno(cls, id):
        address = []
        try:
            Config = Pool().get('conector.configuration')
            conexion = Config.conexion()
            with conexion.cursor() as cursor:
                query = cursor.execute("SELECT * FROM dbo.Terceros_Dir WHERE nit = '"+id+"'")
                address = list(query.fetchall())
        except Exception as e:
            print("ERROR QUERY ADDRESS: ", e)
        return address

    #Función encargada de consultar los metodos de contactos pertenecientes a un tercero en la bd TecnoCarnes
    @classmethod
    def get_contacts_db_tecno(cls, id):
        contacts = []
        try:
            Config = Pool().get('conector.configuration')
            conexion = Config.conexion()
            with conexion.cursor() as cursor:
                query = cursor.execute("SELECT * FROM dbo.Terceros_Contactos WHERE Nit_Cedula = '"+id+"'")
                contacts = list(query.fetchall())
        except Exception as e:
            print("ERROR QUERY CONTACTS: ", e)
        return contacts

    #Función encargada de traer los datos de la bd TecnoCarnes con una fecha dada.
    @classmethod
    def last_update(cls):
        Actualizacion = Pool().get('conector.actualizacion')
        #Se consulta la ultima actualización realizada para los terceros
        ultima_actualizacion = Actualizacion.search([('name', '=','TERCEROS')])
        if ultima_actualizacion:
            #Se calcula la fecha restando la diferencia de horas que tiene el servidor con respecto al clienete
            if ultima_actualizacion[0].write_date:
                fecha = (ultima_actualizacion[0].write_date - datetime.timedelta(hours=5))
            else:
                fecha = (ultima_actualizacion[0].create_date - datetime.timedelta(hours=5))
        else:
            fecha = datetime.date(1,1,1)
            cls.create_actualizacion(True)
        fecha = fecha.strftime('%Y-%d-%m %H:%M:%S')
        data = cls.get_data_where_tecno('TblTerceros', fecha)
        return data

    #Crea o actualiza un registro de la tabla actualización en caso de ser necesario
    @classmethod
    def create_actualizacion(cls, create):
        Actualizacion = Pool().get('conector.actualizacion')
        if create:
            #Se crea un registro con la actualización realizada
            actualizar = Actualizacion()
            actualizar.name = 'TERCEROS'
            actualizar.save()
        else:
            #Se busca un registro con la actualización realizada
            actualizacion, = Actualizacion.search([('name', '=','TERCEROS')])
            actualizacion.name = 'TERCEROS'
            actualizacion.save()


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