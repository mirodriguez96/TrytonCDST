import pprint
from trytond.model import ModelSQL, ModelView, fields
from trytond.pool import Pool
from trytond.exceptions import UserError
import base64

from party import Party

try:
    import pyodbc
except:
    print("Warning: Does not possible import pyodbc module!")
    print("Please install it...!")


__all__ = [
    'Configuration',
    ]

class Configuration(ModelSQL, ModelView):
    'Configuration'
    __name__ = 'conector.configuration'

    server = fields.Char('Server', required=True, help="Example: ip,port")
    db = fields.Char('Database', required=True, help="Enter the name of the database without leaving spaces")
    user = fields.Char('User', required=True, help="Enter the user of the database without leaving spaces")
    password = fields.Char('Password', required=True, help="Enter the password of the database without leaving spaces")
    date = fields.Date('Date', required=True, help="Enter the import start date")
    file = fields.Binary('File', help="Enter the file to import with (;)")


    @classmethod
    def __setup__(cls):
        super(Configuration, cls).__setup__()
        cls._buttons.update({
                'test_conexion': {},
                'importfile': {},
                })


    #Función que prueba la conexión a la base de datos sqlserver
    @classmethod
    @ModelView.button
    def test_conexion(cls, records):
        cnxn = cls.conexion()
        cnxn.close()
        raise UserError('Conexión sqlserver: ', 'Exitosa !')

    #Función encargada de establecer conexión con respecto a la configuración
    @classmethod
    def conexion(cls):
        Config = Pool().get('conector.configuration')
        last_record = Config.search([], order=[('id', 'DESC')], limit=1)
        if last_record:
            record, = last_record
            #Las conexiones utilizadas en un bloque with se confirmarán al final del bloque si no se generan errores y se revertirán de lo contrario
            with pyodbc.connect('DRIVER={ODBC Driver 17 for SQL Server};SERVER='+record.server+';DATABASE='+record.db+';UID='+record.user+';PWD='+record.password) as cnxn:
                return cnxn
        else:
            raise UserError('Error: ', 'Ingrese por favor los datos de configuracion de la base de datos')


    #Función encargada de enviar la conexión configurada con los datos del primer registro
    @classmethod
    def get_data(cls, query):
        data = []
        cnxn = cls.conexion()
        with cnxn.cursor() as cursor:
            cursor.execute(query)
            data = cursor.fetchall()
        cnxn.close()
        return data


    #
    @classmethod
    def set_data(cls, query):
        cnxn = cls.conexion()
        with cnxn.cursor() as cursor:
            cursor.execute(query)
        cnxn.close()

    #
    @classmethod
    def encode_file(cls, file, process='encode'):
        if process == 'encode':
            file64_decod = file.encode()
        else:
            file64_decod = file.decode()

        return file64_decod

    # Boton de importaciones
    @classmethod
    @ModelView.button
    def importfile(cls, records):
        for config in records:
            if config.file:
                file_decode = cls.encode_file(config.file, 'decode')
                lineas = file_decode.split('\n')
                #cls.import_csv_parties(lineas)
                cls.import_csv_products(lineas)
            else:
                raise UserError('Importación de archivo: ', 'Error: agregue un archivo para importar !')

    @classmethod
    def import_csv_parties(cls, lineas):
        pool = Pool()
        Party = pool.get('party.party')
        City = pool.get('party.city_code')
        Department = pool.get('party.department_code')
        Country = pool.get('party.country_code')
        parties = []
        for linea in lineas:
            linea = linea.strip()
            if linea:
                linea = linea.split(';')
                if len(linea) != 15:
                    raise UserError('Importación de archivo: ', 'Error de plantilla !')
                id_number = linea[1].strip()
                party = Party.search([('id_number', '=', id_number)])
                if party:
                    continue
                to_save = {
                    'type_document': linea[0].strip(),
                    'id_number': id_number,
                    'name': linea[2].strip().upper(),
                    'regime_tax': linea[13].strip(),
                    'type_person': linea[14].strip()
                }
                adress = {
                    'party_name': linea[3].strip().upper(),
                    'name': linea[4].strip(),
                    'street': linea[5].strip()
                }
                country_code = linea[6].strip()
                country = Country.search([
                    ('code', '=', country_code),
                ])
                department_code = linea[7].strip()
                department = Department.search([
                    ('code',  '=', department_code),
                ])
                city_code = linea[8].strip()
                city = City.search([
                    ('code', '=', city_code),
                    ('department.code',  '=', department_code),
                ])
                if country:
                    adress['country_code'] = country[0].id
                if department:
                    adress['department_code'] = department[0].id
                if city:
                    adress['city_code'] = city[0].id
                to_save['addresses'] = [('create', [adress])]
                contacts = []
                phone = linea[10].strip()
                if phone:
                    phone = {
                        'type': 'phone',
                        'value': phone
                    }
                    contacts.append(phone)
                email = linea[12].strip()
                if email:
                    email = {
                        'type': 'email',
                        'value': email
                    }
                    contacts.append(email)
                if contacts:
                    to_save['contact_mechanisms'] = [('create', contacts)]
                parties.append(to_save)
        print(len(parties))
        Party.create(parties)


    @classmethod
    def import_csv_products(cls, lineas):
        pool = Pool()
        Product = pool.get('product.template')
        Category = pool.get('product.category')
        Uom = pool.get('product.uom')
        products = []
        not_products = []
        for linea in lineas:
            linea = linea.strip()
            if linea:
                linea = linea.split(';')
                if len(linea) != 15:
                    raise UserError('Importación de archivo: ', 'Error de plantilla !')
                code = linea[0].strip()
                product = Product.search([('code', '=', code)])
                if product:
                    not_products.append(code)
                    continue
                salable = cls.get_boolean(linea[6].strip())
                purchasable = cls.get_boolean(linea[7].strip())
                producible = cls.get_boolean(linea[8].strip())
                consumable = cls.get_boolean(linea[9].strip())
                depreciable = cls.get_boolean(linea[13].strip())
                prod = {
                    #'code': code,
                    'name': linea[1].strip(),
                    'sale_price_w_tax': linea[3].strip(),
                    'salable': salable,
                    'purchasable': purchasable,
                    'producible': producible,
                    'consumable': consumable,
                    'depreciable': depreciable,
                    'type': linea[10].strip(),
                }
                account_category = linea[4].strip()
                account_category, = Category.search([('name', '=', account_category)])
                prod['account_category'] = account_category.id
                uom = linea[5].strip()
                uom, = Uom.search([('name', '=', uom)])
                prod['default_uom'] = uom.id
                prod['sale_uom'] = uom.id
                prod['purchase_uom'] = uom.id
                prod['products'] = [('create', [{
                        'cost_price': int(linea[14].strip()),
                        #'sale_price_uom': linea[2].strip(),
                    }])]
                products.append(prod)
        print(len(products))
        Product.create(products)
        print(not_products)

    @classmethod
    def get_boolean(cls, val):
        if int(val) == 0:
            return False
        if int(val) == 1:
            return True