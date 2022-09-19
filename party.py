import datetime
from trytond.model import fields
from trytond.pool import Pool, PoolMeta


class Cron(metaclass=PoolMeta):
    'Cron'
    __name__ = 'ir.cron'

    @classmethod
    def __setup__(cls):
        super().__setup__()
        cls.method.selection.append(
            ('party.party|import_parties_tecno', "Importar terceros"),
            )
        cls.method.selection.append(
            ('party.party|import_addresses_tecno', "Importar direcciones de terceros"),
            )


#Herencia del party.party e insercción de la función actualizar terceros
class Party(metaclass=PoolMeta):
    'Party'
    __name__ = 'party.party'

    # Función encargada de crear o actualizar los terceros de db TecnoCarnes teniendo en cuenta la ultima fecha de actualizacion y si existe.
    @classmethod
    def import_parties_tecno(cls):
        print("RUN TERCEROS")
        pool = Pool()
        Config = pool.get('conector.configuration')
        Actualizacion = pool.get('conector.actualizacion')
        Party = pool.get('party.party')
        Mcontact = Pool().get('party.contact_mechanism')
        actualizacion = Actualizacion.create_or_update("TERCEROS")
        # Se trae los terceros que cumplan con la fecha establecida
        fecha_actualizacion = Actualizacion.get_fecha_actualizacion(actualizacion)
        terceros_db = Config.get_tblterceros(fecha_actualizacion)
        values = {
            'to_create': [],
            'logs': [],
        }
        # Comenzamos a recorrer los terceros traidos por la consulta
        for tercero in terceros_db:
            try:
                nit_cedula = tercero.nit_cedula.replace('\n',"")
                tipo_identificacion = cls.id_type(tercero.tipo_identificacion)
                nombre = cls.delete_caracter(tercero.nombre.strip()).upper()
                PrimerNombre = cls.delete_caracter(tercero.PrimerNombre.strip()).upper()
                SegundoNombre = cls.delete_caracter(tercero.SegundoNombre.strip()).upper()
                PrimerApellido = cls.delete_caracter(tercero.PrimerApellido.strip()).upper()
                SegundoApellido = cls.delete_caracter(tercero.SegundoApellido.strip()).upper()
                mail = tercero.mail.strip()
                telefono = tercero.telefono.strip()
                TipoPersona = cls.person_type(tercero.TipoPersona.strip())
                ciiu = tercero.IdActividadEconomica
                TipoContribuyente = cls.tax_regime(tercero.IdTipoContribuyente)
                exists = Party.search([('id_number', '=', nit_cedula)])
                #Ahora verificamos si el tercero existe en tryton
                if exists:
                    exists, = exists
                    ultimo_cambio = tercero.Ultimo_Cambio_Registro
                    if not ultimo_cambio:
                        continue
                    create_date = None
                    write_date = None
                    #LA HORA DEL SISTEMA DE TRYTON TIENE UNA DIFERENCIA HORARIA DE 5 HORAS CON LA DE TECNO
                    if exists.write_date:
                        write_date = (exists.write_date - datetime.timedelta(hours=5))
                    elif exists.create_date:
                        create_date = (exists.create_date - datetime.timedelta(hours=5))
                    #Ahora vamos a verificar si el cambio más reciente fue hecho en la bd sqlserver para actualizarlo
                    if (write_date and ultimo_cambio > write_date) or (not write_date and ultimo_cambio > create_date):
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
                        contact_mail = Mcontact.search([('id_tecno', '=', nit_cedula+'-mail')])
                        if contact_mail:
                            contact_mail, = contact_mail
                            contact_mail.value = mail
                            contact_mail.save()
                        elif len(mail) > 4:
                            contact_mail = Mcontact()
                            contact_mail.type = 'email'
                            contact_mail.value = mail
                            contact_mail.party = exists
                            contact_mail.save()
                        contact_tel = Mcontact.search([('id_tecno', '=', nit_cedula+'-tel')])
                        if contact_tel:
                            contact_tel, = contact_tel
                            contact_tel.value = telefono
                            contact_tel.save()
                        elif len(telefono) > 4:
                            contact_tel = Mcontact()
                            contact_tel.type = 'phone'
                            contact_tel.value = telefono
                            contact_tel.party = exists
                            contact_tel.save()
                        exists.save()
                else:
                    # Creando tercero junto con sus direcciones y metodos de contactos
                    party = {
                        'type_document': tipo_identificacion,
                        'id_number': nit_cedula,
                        'name': nombre,
                        'first_name': PrimerNombre,
                        'second_name': SegundoNombre,
                        'first_family_name': PrimerApellido,
                        'second_family_name': SegundoApellido,
                        'regime_tax': TipoContribuyente,
                        'type_person': TipoPersona,
                    }
                    # Equivalencia tipo de persona y asignación True en declarante
                    if TipoPersona== 'persona_juridica':
                        party['declarante'] = True
                    # Verificación e inserción codigo ciiu
                    if ciiu and ciiu != 0:
                        party['ciiu_code'] = ciiu
                    #Creamos las direcciones pertenecientes al tercero
                    direcciones_tecno = Config.get_tercerosdir_nit(nit_cedula)
                    addresses = []
                    for direccion in direcciones_tecno:
                        address = cls.create_address_new(party, direccion)
                        addresses.append(address)
                    party['addresses'] = [('create', addresses)]
                    # Metodos de contactos
                    contacts = []
                    if len(telefono) > 4:
                        phone = {
                            'id_tecno': nit_cedula+'-tel',
                            'type': 'phone',
                            'value': telefono
                        }
                        contacts.append(phone)
                    if len(mail) > 4:
                        email = {
                            'id_tecno': nit_cedula+'-mail',
                            'type': 'email',
                            'value': mail
                        }
                        contacts.append(email)
                    if contacts:
                        party['contact_mechanisms'] = [('create', contacts)]
                    values['to_create'].append(party)
            except Exception as e:
                msg = f"EXCEPCION TERCERO {nit_cedula} : {str(e)}"
                values['logs'].append(msg)
        Party.create(values['to_create'])
        #Se almacena los registros y finaliza el importe
        Actualizacion.add_logs(actualizacion, values['logs'])
        print("FINISH TERCEROS")


    @classmethod
    def import_addresses_tecno(cls):
        print("RUN DIRECCION TERCEROS")
        pool = Pool()
        Config = pool.get('conector.configuration')
        Actualizacion = pool.get('conector.actualizacion')
        Party = pool.get('party.party')
        Address = pool.get('party.address')
        Country = pool.get('party.country_code')
        Department = pool.get('party.department_code')
        City = pool.get('party.city_code')
        actualizacion = Actualizacion.create_or_update("DIRECCION TERCEROS")
        # Se trae los terceros que cumplan con la fecha establecida
        fecha_actualizacion = Actualizacion.get_fecha_actualizacion(actualizacion)
        # Actualización de direcciones
        direcciones_db = Config.get_tercerosdir(fecha_actualizacion)
        if not direcciones_db:
            actualizacion.save()
            print("FINISH DIRECCION TERCEROS")
            return
        values = {
            'to_create': [],
            'logs': [],
        }
        country_code, = Country.search([('code', '=', '169')])
        for dir in direcciones_db:
            try:
                nit = dir.nit
                party = Party.search([('id_number', '=', nit)])
                if not party:
                    msg = f"NO SE ENCONTRO EL TERCERO {nit}"
                    values['logs'].append(msg)
                    continue
                id_tecno = nit+'-'+str(dir.codigo_direccion)
                address = Address.search([('id_tecno', '=', id_tecno)])
                if address:
                    address = address[0]
                    ultimo_cambiod = dir.Ultimo_Cambio_Registro
                    create_date = None
                    write_date = None
                    if address.write_date:
                        write_date = (address.write_date - datetime.timedelta(hours=5))
                    elif address.create_date:
                        create_date = (address.create_date - datetime.timedelta(hours=5))
                    if (ultimo_cambiod and write_date and ultimo_cambiod > write_date) or (ultimo_cambiod and not write_date and ultimo_cambiod > create_date):
                        region = list(dir.CodigoSucursal.strip())
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
                        address.country_code = country_code
                        barrio = dir.Barrio.strip()
                        if barrio and len(barrio) > 2:
                            address.name = barrio
                        address.party_name = party[0].name
                        street = dir.direccion.strip()
                        if len(street) > 2:
                            address.street = street
                        address.save()
                else:
                    tercero = {
                        'name': party[0].name,
                    }
                    addressn = cls.create_address_new(tercero, dir)
                    addressn['party'] = party[0].id
                    values['to_create'].append(addressn)
            except Exception as e:
                msg = f"EXCEPCION {nit} : {str(e)}"
                values['logs'].append(msg)
        Address.create(values['to_create'])
        # Se almacena los registros y finaliza el importe
        Actualizacion.add_logs(actualizacion, values['logs'])
        print("FINISH DIRECCION TERCEROS")


    @classmethod
    def create_address_new(cls, party, data):
        Country = Pool().get('party.country_code')
        Department = Pool().get('party.department_code')
        City = Pool().get('party.city_code')
        if data.codigo_direccion == 1:
            comercial_name = cls.delete_caracter(data.NombreSucursal.strip()).upper()
            if len(comercial_name) > 2:
                party['commercial_name'] = comercial_name
        country_code, = Country.search([('code', '=', '169')])
        adress = {
            'id_tecno': data.nit+'-'+str(data.codigo_direccion),
            'country_code': country_code,
            'party_name': party['name'],
        }
        region = list(data.CodigoSucursal.strip())
        if len(region) > 4:
            department_code = Department.search([('code', '=', region[0]+region[1])])
            if department_code:
                adress['department_code'] = department_code[0].id
                city_code = City.search([
                    ('code', '=', region[2]+region[3]+region[4]),
                    ('department', '=', department_code[0])
                    ])
                if city_code:
                    adress['city_code'] = city_code[0].id
        barrio = data.Barrio.strip()
        if barrio and len(barrio) > 2:
            adress['name'] = barrio
        street = data.direccion.strip()
        if len(street) > 2:
            adress['street'] = street
        return adress


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
class PartyAddress(metaclass=PoolMeta):
    'PartyAddress'
    __name__ = 'party.address'
    id_tecno = fields.Char('Id TecnoCarnes', required=False)


#Herencia del party.contact_mechanism e insercción del campo id_tecno
class ContactMechanism(metaclass=PoolMeta):
    'ContactMechanism'
    __name__ = 'party.contact_mechanism'
    id_tecno = fields.Char('Id TecnoCarnes', required=False)