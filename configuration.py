from trytond.model import ModelSQL, ModelView, fields
from trytond.pool import Pool
from trytond.exceptions import UserError
from decimal import Decimal
import datetime

try:
    import pyodbc
except:
    print("Warning: Does not possible import pyodbc module!")
    print("Please install it...!")


__all__ = [
    'Configuration',
    ]

TYPES_FILE = [
    ('parties', 'Parties'),
    ('products', 'Products'),
    ('balances', 'Balances'),
    ('accounts', 'Accounts'),
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
    type_file = fields.Selection(TYPES_FILE, 'Type file')
    #doc_types = fields.Char('Doc types', help="Example: 101;120;103")


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
            raise UserError('Error: ', 'Ingrese por favor todos los datos de configuracion de la base de datos')


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

    #Se marca en la tabla dbo.Documentos como exportado a Tryton
    @classmethod
    def mark_imported(cls, id):
        lista = id.split('-')
        query = "UPDATE dbo.Documentos SET exportado = 'T' WHERE sw ="+lista[0]+" and tipo = "+lista[1]+" and Numero_documento = "+lista[2]
        cls.set_data(query)

    #
    @classmethod
    def encode_file(cls, file, process='encode'):
        if process == 'encode':
            file_decod = file.encode()
        else:
            file_decod = file.decode()
        return file_decod

    # Boton de importaciones
    @classmethod
    @ModelView.button
    def importfile(cls, records):
        for config in records:
            if config.file:
                file_decode = cls.encode_file(config.file, 'decode')
                lineas = file_decode.split('\n')
                if config.type_file == "parties":
                    cls.import_csv_parties(lineas)
                elif config.type_file == "products":
                    cls.import_csv_products(lineas)
                elif config.type_file == "balances":
                    cls.import_csv_balances(lineas)
                elif config.type_file == "accounts":
                    cls.import_csv_accounts(lineas)
                else:
                    raise UserError('Importación de archivo: ', 'Seleccione el tipo de importación')
            else:
                raise UserError('Importación de archivo: ', 'Agregue un archivo para importar')

    #Importar terceros
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
                if len(linea) != 13:
                    raise UserError('Error de plantilla',
                    'type_document | id_number | name | address/party_name | address/name | address/street | address/country_code | address/department_code | address/city_code | address/phone | address/email | regime_tax | type_person')
                id_number = linea[1].strip()
                party = Party.search([('id_number', '=', id_number)])
                if party:
                    continue
                to_save = {
                    'type_document': linea[0].strip(),
                    'id_number': id_number,
                    'name': linea[2].strip().upper(),
                    'regime_tax': linea[11].strip(),
                    'type_person': linea[12].strip()
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
                phone = linea[9].strip()
                if phone:
                    phone = {
                        'type': 'phone',
                        'value': phone
                    }
                    contacts.append(phone)
                email = linea[10].strip()
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

    #Importar productos
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
                if len(linea) != 13:
                    raise UserError('Error de plantilla', 'code | name | list_price | sale_price_w_tax | account_category | name_uom | salable | purchasable | producible | consumable | type | depreciable | cost_price')
                code = linea[0].strip()
                product = Product.search([('code', '=', code)])
                if product:
                    not_products.append(code)
                    continue
                salable = cls.get_boolean(linea[6].strip())
                purchasable = cls.get_boolean(linea[7].strip())
                producible = cls.get_boolean(linea[8].strip())
                consumable = cls.get_boolean(linea[9].strip())
                depreciable = cls.get_boolean(linea[11].strip())
                prod = {
                    'code': code,
                    'name': linea[1].strip(),
                    'list_price': linea[2].strip(),
                    'sale_price_w_tax': linea[3].strip(),
                    'salable': salable,
                    'purchasable': purchasable,
                    'producible': producible,
                    'consumable': consumable,
                    'depreciable': depreciable,
                    'type': linea[10].strip(),
                }
                name_category = linea[4].strip()
                account_category = Category.search([('name', '=', name_category)])
                if not account_category:
                    print(name_category)
                    raise UserError("Error Categoria Producto", f"No se encontro la categoria: {name_category}")
                account_category, = account_category
                prod['account_category'] = account_category.id
                name_uom = linea[5].strip()
                uom = Uom.search([('name', '=', name_uom)])
                if not uom:
                    print(name_uom)
                    raise UserError("Error UDM Producto", f"No se encontro la unidad de medida: {name_uom}")
                uom, = uom
                prod['default_uom'] = uom.id
                prod['sale_uom'] = uom.id
                prod['purchase_uom'] = uom.id
                prod['products'] = [('create', [{
                        'cost_price': int(linea[12].strip()),
                    }])]
                products.append(prod)
        print(len(products))
        Product.create(products)
        print(not_products)

    #Importador de saldos iniciales
    @classmethod
    def import_csv_balances(cls, lineas):
        pool = Pool()
        Account = pool.get('account.account')
        Journal = pool.get('account.journal')
        Period = pool.get('account.period')
        Move = pool.get('account.move')
        Party = pool.get('party.party')
        cont = 0
        move = {}
        lines = []
        not_party = []
        for linea in lineas:
            linea = linea.strip()
            if not linea:
                continue
            linea = linea.split(';')
            if len(linea) != 11:
                raise UserError('Error de plantilla',
                'libro diario | periodo | fecha efectiva | descripcion | linea/cuenta | linea/debito | linea/credito | linea/tercero | linea/descripcion | linea/fecha vencimiento | linea/referencia')
            if cont == 0:
                name_journal = linea[0].strip()
                name_period = linea[1].strip()
                efective_date = cls.convert_str_date(linea[2])
                description_move = linea[3].strip()
                journal = Journal.search([('name', '=', name_journal)])
                if not journal:
                    raise UserError('Error diario', f'No se encontró el diario {name_journal}')
                journal, = journal
                period = Period.search([('name', '=', name_period)])
                if not period:
                    raise UserError('Error periodo', f'No se encontró el diario {name_period}')
                period, = period
                move = {
                    'journal': journal.id,
                    'period': period.id,
                    'date': efective_date,
                    'description': description_move,
                }
            cont += 1
            
            account_line = linea[4].strip()
            debit_line = linea[5].strip()
            if debit_line:
                debit_line = Decimal(debit_line)
            else:
                debit_line = Decimal(0)
            credit_line = linea[6].strip()
            if credit_line:
                credit_line = Decimal(credit_line)
            else:
                credit_line = Decimal(0)
            party_line = linea[7].strip()
            description_line = linea[8].strip()
            maturity_date = linea[9].strip()
            reference_line = linea[10].strip()
            account = Account.search([('code', '=', account_line)])
            if not account:
                raise UserError("Error de cuenta", f"No se encontro la cuenta: {account_line}")
            account, = account
            line = {
                'account': account.id,
                'reference': reference_line,
                'debit': debit_line,
                'credit': credit_line,
                'description': description_line,
            }
            if maturity_date:
                line['maturity_date'] = cls.convert_str_date(maturity_date)
            if account.party_required:
                party = Party.search([('id_number', '=', party_line)])
                if not party:
                    msg = f"No se encontro el tercero: {party_line} requerido para la cuenta {account_line}"
                    not_party.append(msg)
                    continue
                line['party'] = party[0].id
            lines.append(line)
        if not_party:
            result = "\n".join(not_party)
            raise UserError("Error terceros", result)
        #Se verifica si hay lineas por crear
        if lines:
            move['lines'] = [('create', lines)]
        Move.create([move])


    #Función encargada de verificar las cuentas nuevas a importar
    @classmethod
    def import_csv_accounts(cls, lineas):
        pool = Pool()
        Account = pool.get('account.account')
        Type = pool.get('account.account.type')
        ordered = []
        for linea in lineas:
            linea = linea.strip()
            if not linea:
                continue            
            linea = linea.split(';')
            if linea[0] == 'code':
                continue
            if len(linea) != 5:
                raise UserError('Error plantilla', 'account | name | type | reconcile | party_required')
            ordered.append(linea)
        ordered = sorted(ordered, key=lambda item:len(item[0]))
        #to_create = []
        not_account = []
        for linea in ordered:
            #print(linea)
            code = linea[0].strip()
            account = Account.search([('code', '=', code)])
            if account:
                #print(account)
                continue
            name = linea[1].strip().upper()
            type = linea[2].strip()
            reconcile = linea[3].strip().upper()
            if reconcile and reconcile == 'TRUE':
                reconcile = True
            else:
                reconcile = False
            party_required = linea[4].strip().upper()
            if party_required and party_required == 'TRUE':
                party_required = True
            else:
                party_required = False
            account = {
                'code': code,
                'name': name,
                'reconcile': reconcile,
                'party_required': party_required,
                'type': None
            }
            if type:
                #print(type)
                type = Type.search([('sequence', '=', type)])
                if not type:
                    raise UserError('Importación de archivo: ', f'Error en la búsqueda del tipo de cuenta de la cuenta {code} - {name}')
                type, = type
                account['type'] = type.id
            #else:
            #    raise UserError('Importación de archivo: ', f'Error falata el tipo de cuenta de la cuenta {code} - {name}')
            parent = cls.get_parent_account(code)
            if parent:
                #print(parent)
                account_s = Account.search([('code', '=', parent)])
                if not account_s:
                    not_account.append(parent)
                    continue
                    #raise UserError('Importación de archivo: ', f'Error al buscar la cuenta padre {parent}')
                account['parent'] = account_s[0].id
            #to_create.append(account)
            Account.create([account])
        if not_account:
            raise UserError('Importación de archivo: ', f'Error: Faltan las cuentas padres {not_account}')

    
    @classmethod
    def get_parent_account(cls, code):
        if len(code) < 2:
            return
        elif len(code) == 2:
            return code[0]
        elif len(code) > 2:
            if (len(code) % 2) != 0:
                raise UserError('Importación de archivo: ', f'Error de código {code}')
            return code[:-2]

    @classmethod
    def convert_str_date(cls, fecha):
        try:
            result = fecha.strip().split()[0].split('-')
            result = datetime.date(int(result[0]), int(result[1]), int(result[2]))
        except:
            raise UserError(f"Error fecha {fecha}", "Recuerde que la fecha debe estar con el siguiente formato YY-MM-DD")
        return result

    #
    @classmethod
    def get_boolean(cls, val):
        if int(val) == 0:
            return False
        if int(val) == 1:
            return True