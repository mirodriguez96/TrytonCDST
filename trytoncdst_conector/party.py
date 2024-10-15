"""PARTY MODULE"""

import datetime

import requests

from trytond.model import fields
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Eval
from trytond.transaction import Transaction

RECEIVABLE_PAYABLE_TECNO = {}

TYPE_DOCUMENT = [
    ('11', 'Registro Civil de Nacimiento'),
    ('12', 'Tarjeta de Identidad'),
    ('13', 'Cedula de Ciudadania'),
    ('21', 'Tarjeta de Extranjeria'),
    ('22', 'Cedula de Extranjeria'),
    ('31', 'NIT'),
    ('41', 'Pasaporte'),
    ('42', 'Tipo de Documento Extranjero'),
    ('47', 'PEP'),
    ('50', 'NIT de otro pais'),
    ('91', 'NUIP'),
    ('43', 'Cuantías menores'),
    ('', ''),
]


# Herencia del party.party e insercción de la función actualizar terceros
class Party(metaclass=PoolMeta):
    'Party'
    __name__ = 'party.party'
    receivable_tecno = fields.Function(
        fields.Numeric('Receivable Tecno',
                       digits=(16, Eval('currency_digits', 2)),
                       depends=['currency_digits']),
        'get_receivable_payable_tecno')
    payable_tecno = fields.Function(
        fields.Numeric('Payable Tecno',
                       digits=(16, Eval('currency_digits', 2)),
                       depends=['currency_digits']),
        'get_receivable_payable_tecno')
    number_pay_payroll = fields.Char(
        'number_payroll',
        size=5,
        states={'invisible': Eval('type_document') != '41'})

    validate_dian = fields.Boolean('Validate DIAN', states={'invisible': True})

    @classmethod
    def __setup__(cls):
        super(Party, cls).__setup__()
        cls.type_document = fields.Selection(TYPE_DOCUMENT,
                                             'Tipo de Documento',
                                             required=True)

    # Funcion encargada de consultar en TecnoCarnes el saldo por pagar y cobrar de los terceros
    def get_receivable_payable_tecno(self, name):
        '''
        Function to compute receivable, payable (today) for parties.
        '''
        pool = Pool()
        Config = pool.get('conector.configuration')
        configuration = Config.get_configuration()
        if not configuration:
            return None
        value = 0
        now = datetime.datetime.now()
        date_time = datetime.datetime(now.year, now.month, now.day, now.hour,
                                      now.minute)

        global RECEIVABLE_PAYABLE_TECNO
        if not RECEIVABLE_PAYABLE_TECNO or (
                RECEIVABLE_PAYABLE_TECNO
                and RECEIVABLE_PAYABLE_TECNO['date_time'] < date_time):
            query = "SELECT nit_cedula, sum(porcobrar), sum(porpagar) from VIEWCTASPORPAGARYCOBRAR GROUP BY nit_cedula"
            result = Config.get_data(query)
            for val in result:
                RECEIVABLE_PAYABLE_TECNO[val[0]] = {
                    'receivable': val[1],
                    'payable': val[2]
                }
            RECEIVABLE_PAYABLE_TECNO['date_time'] = date_time
        if name == 'receivable_tecno':
            if self.id_number in RECEIVABLE_PAYABLE_TECNO.keys():
                value = RECEIVABLE_PAYABLE_TECNO[self.id_number]['receivable']
        elif name == 'payable_tecno':
            if self.id_number in RECEIVABLE_PAYABLE_TECNO.keys():
                value = RECEIVABLE_PAYABLE_TECNO[self.id_number]['payable']
        return value

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
        fecha_actualizacion = Actualizacion.get_fecha_actualizacion(
            actualizacion)
        terceros_db = Config.get_tblterceros(fecha_actualizacion)
        if not terceros_db:
            return
        values = {
            'to_create': [],
            'logs': {},
        }

        print('Obteniendo los terceros')
        parties = cls._get_party_documentos(terceros_db, 'nit_cedula')

        print('Recorriendo los terceros')
        for tercero in terceros_db:
            try:
                nit_cedula = tercero.nit_cedula.replace('\n', "")
                print(f'Obteniendo datos {nit_cedula}')
                tipo_identificacion = cls.id_type(
                    tercero.tipo_identificacion)
                nombre = cls.delete_caracter(
                    tercero.nombre.strip()).upper()
                PrimerNombre = cls.delete_caracter(
                    tercero.PrimerNombre.strip()).upper()
                SegundoNombre = cls.delete_caracter(
                    tercero.SegundoNombre.strip()).upper()
                PrimerApellido = cls.delete_caracter(
                    tercero.PrimerApellido.strip()).upper()
                SegundoApellido = cls.delete_caracter(
                    tercero.SegundoApellido.strip()).upper()
                mail = tercero.mail.strip()
                telefono = tercero.telefono.strip()
                TipoPersona = cls.person_type(tercero.TipoPersona.strip())
                ciiu = tercero.IdActividadEconomica
                regime_tax = cls.tax_regime(tercero)
                party = None
                if nit_cedula in parties['active']:
                    party = parties['active'][nit_cedula]
                elif nit_cedula in parties['inactive']:
                    values['logs'][
                        nit_cedula] = "El tercero esta marcado como inactivo"
                    continue
                # Ahora verificamos si el tercero existe en tryton
                if party:
                    print('Tercero existe en tryton')
                    ultimo_cambio = tercero.Ultimo_Cambio_Registro
                    if not ultimo_cambio:
                        continue
                    create_date = None
                    write_date = None
                    # LA HORA DEL SISTEMA DE TRYTON TIENE UNA DIFERENCIA HORARIA DE 5 HORAS CON LA DE TECNO
                    if party.write_date:
                        write_date = (party.write_date -
                                      datetime.timedelta(hours=5))
                    else:
                        create_date = (party.create_date -
                                       datetime.timedelta(hours=5))
                    # Ahora vamos a verificar si el cambio más reciente fue hecho en la bd sqlserver para actualizarlo

                    if (write_date and ultimo_cambio > write_date) or (
                            not write_date and ultimo_cambio > create_date):
                        print('Se actualiza el tercero con info nueva')
                        if not party.validate_dian:
                            party.name = nombre
                            party.first_name = PrimerNombre
                            party.second_name = SegundoNombre
                            party.first_family_name = PrimerApellido
                            party.second_family_name = SegundoApellido

                        party.type_document = tipo_identificacion
                        party.type_person = TipoPersona
                        if party.type_person == 'persona_juridica':
                            party.declarante = True
                        # Verificación e inserción codigo ciiu
                        if ciiu and ciiu != 0:
                            party.ciiu_code = ciiu
                        party.regime_tax = regime_tax
                        contact_mail = Mcontact.search([
                            ('id_tecno', '=', nit_cedula + '-mail')
                        ])
                        if contact_mail:
                            contact_mail, = contact_mail
                            contact_mail.value = mail
                            contact_mail.save()
                        elif len(mail) > 4:
                            contact_mail = Mcontact()
                            contact_mail.type = 'email'
                            contact_mail.value = mail
                            contact_mail.party = party
                            contact_mail.save()
                        contact_tel = Mcontact.search([('id_tecno', '=',
                                                        nit_cedula + '-tel')])
                        if contact_tel:
                            contact_tel, = contact_tel
                            contact_tel.type = 'other'
                            contact_tel.value = telefono
                            contact_tel.name = 'telefono'
                            if len(telefono) == 10:
                                contact_tel.type = 'phone'
                                contact_tel.value = '+57' + telefono
                            contact_tel.save()
                        elif len(telefono) > 4:
                            contact_tel = Mcontact()
                            contact_tel.type = 'other'
                            contact_tel.value = telefono
                            contact_tel.name = 'telefono'
                            contact_tel.party = party
                            if len(telefono) == 10:
                                contact_tel.type = 'phone'
                                contact_tel.value = '+57' + telefono
                            contact_tel.save()
                        party.save()
                        print('Tercero actualizado')
                else:
                    print('Creando tercero')
                    party = {
                        'type_document': tipo_identificacion,
                        'id_number': nit_cedula,
                        'name': nombre,
                        'first_name': PrimerNombre,
                        'second_name': SegundoNombre,
                        'first_family_name': PrimerApellido,
                        'second_family_name': SegundoApellido,
                        'regime_tax': regime_tax,
                        'type_person': TipoPersona,
                    }
                    # Equivalencia tipo de persona y asignación True en declarante
                    if TipoPersona == 'persona_juridica':
                        party['declarante'] = True
                    # Verificación e inserción codigo ciiu
                    if ciiu and ciiu != 0:
                        party['ciiu_code'] = ciiu
                    # Creamos las direcciones pertenecientes al tercero
                    direcciones_tecno = Config.get_tercerosdir_nit(
                        nit_cedula)
                    addresses = []
                    for direccion in direcciones_tecno:
                        address = cls.create_address_new(party, direccion)
                        addresses.append(address)
                    party['addresses'] = [('create', addresses)]
                    # Metodos de contactos
                    contacts = []
                    if len(telefono) > 4:
                        phone = {
                            'id_tecno': nit_cedula + '-tel',
                            'type': 'other',
                            'name': 'telefono',
                            'value': telefono
                        }
                        if len(telefono) == 10:
                            phone['type'] = 'phone'
                            phone['value'] = '+57' + telefono
                        contacts.append(phone)
                    if len(mail) > 4:
                        email = {
                            'id_tecno': nit_cedula + '-mail',
                            'type': 'email',
                            'name': 'mail',
                            'value': mail
                        }
                        contacts.append(email)
                    if contacts:
                        party['contact_mechanisms'] = [
                            ('create', contacts)]
                    Party.create([party])
                    print('Tercero creado')
            except Exception as error:
                values['logs'][nit_cedula] = f"EXCEPCION: {str(error)}"
        actualizacion.add_logs(values['logs'])
        print("FINISH TERCEROS")

    @classmethod
    def import_addresses_tecno(cls):
        print("RUN DIRECCION TERCEROS")
        pool = Pool()
        Actualizacion = pool.get('conector.actualizacion')
        Department = pool.get('party.department_code')
        Config = pool.get('conector.configuration')
        Country = pool.get('party.country_code')
        Address = pool.get('party.address')
        City = pool.get('party.city_code')
        Party = pool.get('party.party')

        actualizacion = Actualizacion.create_or_update("DIRECCION TERCEROS")

        # Se trae los terceros que cumplan con la fecha establecida
        fecha_actualizacion = Actualizacion.get_fecha_actualizacion(
            actualizacion)

        # Actualización de direcciones
        print('Obteniendo direcciones de terceros')
        direcciones_db = Config.get_tercerosdir(fecha_actualizacion)
        if not direcciones_db:
            actualizacion.save()
            print("No se encontro informacion")
            return
        values = {
            'to_create': [],
            'logs': {},
        }
        country_code, = Country.search([('code', '=', '169')])

        print("Recorriendo direcciones")
        for dir in direcciones_db:
            try:
                nit = (dir.nit).replace('\n', "")
                print(f"Tercero {nit}")
                party = Party.search([('id_number', '=', nit)])
                if not party:
                    print("No se encontro el tercero asociado")
                    values['logs'][nit] = "NO SE ENCONTRO EL TERCERO"
                    continue
                id_tecno = nit + '-' + str(dir.codigo_direccion)
                address = Address.search([('id_tecno', '=', id_tecno)])
                if address:
                    print("Actualizando direccion")
                    address = address[0]
                    ultimo_cambiod = dir.Ultimo_Cambio_Registro
                    create_date = None
                    write_date = None
                    if address.write_date:
                        write_date = (address.write_date -
                                      datetime.timedelta(hours=5))
                    elif address.create_date:
                        create_date = (address.create_date -
                                       datetime.timedelta(hours=5))
                    if (ultimo_cambiod and write_date and ultimo_cambiod > write_date) or \
                            (ultimo_cambiod and not write_date and ultimo_cambiod > create_date):
                        print("Actualizando direccion con cambios nuevos")
                        region = list(dir.CodigoSucursal.strip())
                        if len(region) > 4:
                            department_code = Department.search([
                                ('code', '=', region[0] + region[1])
                            ])
                            if department_code:
                                address.department_code = department_code[0]
                                city_code = City.search([
                                    ('code', '=',
                                     region[2] + region[3] + region[4]),
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
                        print("Direccion actualizada")
                else:
                    print('Creando direccion')
                    tercero = {
                        'name': party[0].name,
                    }
                    addressn = cls.create_address_new(tercero, dir)
                    addressn['party'] = party[0].id
                    Address.create([addressn])
                    print('Direccion creada')
            except Exception as e:
                values['logs'][id_tecno] = f"EXCEPCION: {str(e)}"
        actualizacion.add_logs(values['logs'])
        print("FINISH DIRECCION TERCEROS")

    @classmethod
    def create_address_new(cls, party, data):
        Country = Pool().get('party.country_code')
        Department = Pool().get('party.department_code')
        City = Pool().get('party.city_code')
        if data.codigo_direccion == 1:
            comercial_name = cls.delete_caracter(
                data.NombreSucursal.strip()).upper()
            if len(comercial_name) > 2:
                party['commercial_name'] = comercial_name
        country_code, = Country.search([('code', '=', '169')])
        nit = (data.nit).replace('\n', "")
        adress = {
            'id_tecno': nit + '-' + str(data.codigo_direccion),
            'country_code': country_code,
            'party_name': party['name'],
        }
        region = list(data.CodigoSucursal.strip())
        if len(region) > 4:
            department_code = Department.search([('code', '=',
                                                  region[0] + region[1])])
            if department_code:
                adress['department_code'] = department_code[0].id
                city_code = City.search([
                    ('code', '=', region[2] + region[3] + region[4]),
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

    # Función encargada de eliminar caracteres especiales y convertir string en alfanumerico
    @classmethod
    def delete_caracter(cls, word):
        list_word = word.split(" ")
        result = ''
        for word in list_word:
            res = ''.join(filter(str.isalnum, word))
            if result != '':
                result = result + ' ' + res
            else:
                result = res
        return result

    # Función encargada de realizar la equivalencia entre los tipo de documentos de la db
    # y los tipos de documentos del modulo account_col de presik
    @classmethod
    def id_type(cls, type):
        # Equivalencia tipo de identificacion
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

    # Función encargada de realizar la equivalencia entre los tipos de personas de la db TecnoCarnes
    # y los tipos del modulo account_col de presik
    @classmethod
    def person_type(cls, type):
        # Equivalencia tipo de persona y asignación True en declarante
        if type == 'Natural':
            return 'persona_natural'
        elif type == 'Juridica':
            return 'persona_juridica'

    # Función encargada de realizar la equivalencia entre los regimen de impuestos de la db TecnoCarnes
    # y los regimen de impuestos del modulo account_col de presik
    @classmethod
    def tax_regime(cls, tercero):
        regime_tax = None
        # Equivalencia regimen de impuestos
        if tercero.IdRegimen_Fiscal == 48:
            regime_tax = 'regimen_responsable'
        elif tercero.IdRegimen_Fiscal == 49:
            regime_tax = 'regimen_no_responsable'
        elif tercero.IdTipoContribuyente == 1 or tercero.IdTipoContribuyente == 4:
            regime_tax = 'gran_contribuyente'
        return regime_tax

    @classmethod
    def _get_party_documentos(cls, documentos, nombre_variable):
        if not documentos:
            return None
        Party = Pool().get('party.party')
        cursor = Transaction().connection.cursor()
        # Se procede a validar los terceros existentes y activos
        ids_number = []
        for obj in documentos:
            nit_cedula = getattr(obj, nombre_variable)
            nit_cedula = nit_cedula.replace('\n', "")
            ids_number.append(nit_cedula)
        if len(ids_number) > 1:
            ids_number = tuple(ids_number)
            query = f"SELECT id, id_number, active FROM party_party WHERE id_number in {ids_number}"
        else:
            id_number, = ids_number
            query = f"SELECT id, id_number, active FROM party_party WHERE id_number = '{id_number}'"
        cursor.execute(query)
        result = cursor.fetchall()
        """ 
        Se crea un diccionario dónde se almacenara los terceros existentes
        de acuerdo a su estado correspondiente activo o inactivo
        """
        parties = {'active': {}, 'inactive': []}
        for r in result:
            if r[2]:
                parties['active'][r[1]] = Party(r[0])
            else:
                if nombre_variable == 'nit_Cedula':
                    cursor.execute(
                        f"UPDATE party_party SET active = True WHERE id = {r[0]}"
                    )
                parties['inactive'].append(r[1])
        return parties


# Herencia del party.address e insercción del campo id_tecno
class PartyAddress(metaclass=PoolMeta):
    'PartyAddress'
    __name__ = 'party.address'
    id_tecno = fields.Char('Id TecnoCarnes', required=False)


# Herencia del party.contact_mechanism e insercción del campo id_tecno
class ContactMechanism(metaclass=PoolMeta):
    'ContactMechanism'
    __name__ = 'party.contact_mechanism'
    id_tecno = fields.Char('Id TecnoCarnes', required=False)


class CheckVIESResult(metaclass=PoolMeta):
    'Check VIES'
    __name__ = 'party.check_vies.result'

    parties_succeed = fields.Many2Many('party.party',
                                       None,
                                       None,
                                       'Parties Succeed',
                                       readonly=True,
                                       states={
                                           'invisible':
                                           ~Eval('parties_succeed'),
                                       })

    parties_failed = fields.Many2Many('party.party',
                                      None,
                                      None,
                                      'Parties Failed',
                                      readonly=True,
                                      states={
                                          'invisible': ~Eval('parties_failed'),
                                      })


class CheckVIES(metaclass=PoolMeta):
    'Check VIES'
    __name__ = 'party.check_vies'

    def transition_check(self):
        """Function that consult document in DIAN and update data"""
        # pylint: disable=no-member

        parties_succeed = []
        parties_failed = []

        if self.records:
            for party in self.records:
                party_id = party.id_number
                try:
                    report = self.report_dian(party_id)
                    if report:
                        if not report['success']:
                            parties_failed.append(party.id)
                        else:
                            info = report["result"]

                            if info["estado"] == "REGISTRO ACTIVO":
                                if "razon_social" in info:
                                    party.name = info["razon_social"]
                                else:
                                    first_name = info["primer_nombre"]
                                    second_name = info["otros_nombres"]
                                    first_family_name = info["primer_apellido"]
                                    second_family_name = info[
                                        "segundo_apellido"]

                                    if len(second_name) > 0:
                                        party_name = f'{first_name} {second_name} {first_family_name} {second_family_name}'
                                    else:
                                        party_name = f'{first_name} {first_family_name} {second_family_name}'

                                    party.first_name = first_name
                                    party.second_name = second_name
                                    party.first_family_name = first_family_name
                                    party.second_family_name = second_family_name
                                    party.name = party_name

                                party.validate_dian = True
                                parties_succeed.append(party.id)
                                party.save()

                except Exception as e:
                    print(f"no entro {e}")

            self.result.parties_succeed = parties_succeed
            self.result.parties_failed = parties_failed
            return 'result'

    @classmethod
    def report_dian(cls, nit):
        """Function that consult document in DIAN"""

        api_url = "http://api.consulta.fenix-erp.net/v1/82e414d56b9d4243c3efc98025685f4a/dian/"
        params = {'nit': nit}

        try:
            response = requests.get(api_url, params=params, timeout=10)
            response.raise_for_status(
            )  # Lanza una excepción para errores HTTP

            if response.status_code == 200:
                data = response.json()
                return data
            else:
                print(f"Error en la respuesta HTTP: {response.status_code}")
                return None
        except requests.exceptions.RequestException as e:
            print(f"Error en la solicitud: {e}")
            return None
