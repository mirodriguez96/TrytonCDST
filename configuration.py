from trytond.model import ModelSQL, ModelView, fields
from trytond.pool import Pool
from trytond.exceptions import UserError, UserWarning
from trytond.transaction import Transaction
from decimal import Decimal
import math
import datetime

try:
    import pyodbc
except:
    print("Warning: Does not possible import pyodbc module!")
    print("Please install it...!")


# Paso a paso recomendado para la importación
# 1. Crear la funcion que importa los datos y crea la actualización
# 2. Crear la funcion que valida los datos importados
#   2.1 Ya existe el registro?
#   2.2 Falta algún dato en Tryton?
# 3. Funcion que se encarga de crear los registros en Tryton
#   3.1 _create_model()
#   3.2 _create_lines()
#   3.3 Model.save([all])


TYPES_FILE = [
    ('parties', 'Parties'),
    ('products', 'Products'),
    ('balances', 'Balances'),
    ('accounts', 'Accounts'),
    ('update_accounts', 'Update Accounts'),
    ('product_costs', 'Product costs'),
    ('inventory', "Inventory"),
    ('bank_account', 'Bank Account'),
    ('loans', 'Loans'),
    ('access_biometric', 'Access biometric')
]

class Configuration(ModelSQL, ModelView):
    'Configuration'
    __name__ = 'conector.configuration'

    server = fields.Char('Server', required=True, help="Example: ip,port")
    db = fields.Char('Database', required=True, help="Enter the name of the database without leaving spaces")
    user = fields.Char('User', required=True, help="Enter the user of the database without leaving spaces")
    password = fields.Char('Password', required=True, help="Enter the password of the database without leaving spaces")
    date = fields.Date('Date', required=True, help="Enter the import start date")
    end_date = fields.Date('End Date', help="Enter the import end date" )
    file = fields.Binary('File', help="Enter the file to import with (;)")
    type_file = fields.Selection(TYPES_FILE, 'Type file')
    #doc_types = fields.Char('Doc types', help="Example: 101;120;103")
    order_type_production = fields.Char('Order types', help="Example: 101;202;303")
    access_enter_timestamp = fields.Char('Inicia a laborar', help="Example: Laborando")
    access_exit_timestamp = fields.Char('Finaliza de laborar', help="Example: Salir")
    access_start_rest = fields.Char('Inicia a descansar', help="Example: Descansando")
    access_end_rest = fields.Char('Finaliza de descansar', help="Example: Retornar")


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

    @classmethod
    def set_data_rollback(cls, queries):
        try:
            cnxn = cls.conexion()
            cnxn.autocommit = False
            for query in queries:
                cnxn.cursor().execute(query)
        except pyodbc.DatabaseError as err:
            cnxn.rollback()
            raise UserError('database error', err)
        else:
            cnxn.commit()
        finally:
            cnxn.autocommit = True


    #Se marca en la tabla dbo.Documentos como exportado a Tryton
    @classmethod
    def update_exportado(cls, id, e):
        lista = id.split('-')
        query = "UPDATE dbo.Documentos SET exportado = '"+e+"' WHERE sw ="+lista[0]+" and tipo = "+lista[1]+" and Numero_documento = "+lista[2]
        cls.set_data(query)


    @classmethod
    def get_tblproducto(cls, fecha):
        fecha = fecha.strftime('%Y-%m-%d %H:%M:%S')
        query = "SET DATEFORMAT ymd SELECT * FROM dbo.TblProducto WHERE fecha_creacion >= CAST('"+fecha+"' AS datetime) OR Ultimo_Cambio_Registro >= CAST('"+fecha+"' AS datetime)"
        data = cls.get_data(query)
        return data

    @classmethod
    def get_tblterceros(cls, fecha):
        fecha = fecha.strftime('%Y-%m-%d %H:%M:%S')
        query = "SET DATEFORMAT ymd SELECT * FROM dbo.TblTerceros WHERE fecha_creacion >= CAST('"+fecha+"' AS datetime) OR Ultimo_Cambio_Registro >= CAST('"+fecha+"' AS datetime)"
        data = cls.get_data(query)
        return data

    @classmethod
    def get_tercerosdir(cls, fecha):
        fecha = fecha.strftime('%Y-%m-%d %H:%M:%S')
        query = "SET DATEFORMAT ymd SELECT * FROM dbo.Terceros_Dir WHERE Ultimo_Cambio_Registro >= CAST('"+fecha+"' AS datetime)"
        data = cls.get_data(query)
        return data

    @classmethod
    def get_tercerosdir_nit(cls, nit):
        query = "SELECT * FROM dbo.Terceros_Dir WHERE nit = '"+nit+"'"
        data = cls.get_data(query)
        return data

    @classmethod
    def get_documentos_tecno(cls, sw):
        Config = Pool().get('conector.configuration')
        config, = Config.search([], order=[('id', 'DESC')], limit=1)
        fecha = config.date.strftime('%Y-%m-%d %H:%M:%S')
        # query = "SELECT * FROM dbo.Documentos WHERE tipo = null AND Numero_documento = null " #TEST
        query = "SET DATEFORMAT ymd SELECT TOP(50) * FROM dbo.Documentos "\
                f"WHERE fecha_hora >= CAST('{fecha}' AS datetime) AND "\
                f"sw = {sw} AND exportado != 'T' AND exportado != 'E' AND exportado != 'X' "
        # Se valida si en la configuración de la base de datos, añadieron un valor en la fecha final de importación
        if config.end_date:
            end_date = config.end_date.strftime('%Y-%m-%d %H:%M:%S')
            query += f" AND fecha_hora < CAST('{end_date}' AS datetime) "
        query += "ORDER BY fecha_hora ASC"
        data = cls.get_data(query)
        return data

    @classmethod
    def get_documentos_tipo(cls, sw, tipo):
        Config = Pool().get('conector.configuration')
        config, = Config.search([], order=[('id', 'DESC')], limit=1)
        fecha = config.date.strftime('%Y-%m-%d %H:%M:%S')
        # query = "SELECT * FROM dbo.Documentos WHERE tipo = null AND Numero_documento = null" #TEST
        if not sw:
            query = "SET DATEFORMAT ymd SELECT TOP(50) * FROM dbo.Documentos WHERE fecha_hora >= CAST('"+fecha+"' AS datetime) AND tipo = "+tipo+" AND exportado != 'T' AND exportado != 'E' AND exportado != 'X' "
        else:
            query = "SET DATEFORMAT ymd SELECT TOP(50) * FROM dbo.Documentos WHERE fecha_hora >= CAST('"+fecha+"' AS datetime) AND sw = "+sw+" AND tipo = "+tipo+" AND exportado != 'T' AND exportado != 'E' AND exportado != 'X' "
        if config.end_date:
            end_date = config.end_date.strftime('%Y-%m-%d %H:%M:%S')
            query += f" AND fecha_hora < CAST('{end_date}' AS datetime) "
        query += "ORDER BY fecha_hora ASC"
        data = cls.get_data(query)
        return data

    @classmethod
    def get_lineasd_tecno(cls, id):
        lista = id.split('-')
        query = "SELECT * FROM dbo.Documentos_Lin WHERE sw = "+lista[0]+" AND tipo = "+lista[1]+" AND Numero_Documento = "+lista[2]+" order by seq"
        data = cls.get_data(query)
        return data

    @classmethod
    def get_data_parametros(cls, id):
        query = "SELECT * FROM dbo.TblParametro WHERE IdParametro = "+id
        data = cls.get_data(query)
        return data

    @classmethod
    def get_tbltipodoctos(cls, id):
        query = "SELECT * FROM dbo.TblTipoDoctos WHERE idTipoDoctos = "+id
        data = cls.get_data(query)
        return data

    @classmethod
    def get_tbltipoproducto(cls, id):
        query = "SELECT * FROM dbo.TblTipoProducto WHERE IdTipoProducto = "+id
        data = cls.get_data(query)
        return data

    #Metodo encargado de obtener los recibos pagados de un documento dado
    @classmethod
    def get_dctos_cruce(cls, id):
        lista = id.split('-')
        query = "SELECT * FROM dbo.Documentos_Cruce WHERE sw="+lista[0]+" AND tipo="+lista[1]+" AND numero="+lista[2]
        data = cls.get_data(query)
        return data

    #Metodo encargado de obtener la forma en que se pago el comprobante (recibos)
    @classmethod
    def get_tipos_pago(cls, id):
        lista = id.split('-')
        query = "SELECT * FROM dbo.Documentos_Che WHERE sw="+lista[0]+" AND tipo="+lista[1]+" AND numero="+lista[2]
        data = cls.get_data(query)
        return data


    @classmethod
    def get_data_table(cls, table):
        query = "SELECT * FROM dbo."+table
        data = cls.get_data(query)
        return data
    
    @classmethod
    def get_documentos_orden(cls):
        Config = Pool().get('conector.configuration')
        config, = Config.search([], order=[('id', 'DESC')], limit=1)
        fecha = config.date.strftime('%Y-%m-%d %H:%M:%S')
        query = "SET DATEFORMAT ymd SELECT d.DescuentoOrdenVenta, l.* FROM dbo.Documentos_Lin l "\
                "INNER JOIN Documentos d ON d.sw=l.sw AND d.tipo=l.tipo AND d.Numero_documento=l.Numero_Documento "\
                f"WHERE d.DescuentoOrdenVenta like 'T-%' AND d.fecha_hora >= CAST('{fecha}' AS datetime) "\
                "AND d.sw = 12 AND d.exportado != 'T' AND d.exportado != 'E' AND d.exportado != 'X'"
        if config.end_date:
            end_date = config.end_date.strftime('%Y-%m-%d %H:%M:%S')
            query += f" AND fecha_hora < CAST('{end_date}' AS datetime) "
        data = cls.get_data(query)
        return data

    # Se solicita un archivo para ser codificado o descodificado
    @classmethod
    def encode_file(cls, file, process='encode'):
        if process == 'encode':
            file_decod = file.encode()
        else:
            file_decod = file.decode()
        return file_decod

    # Una vez cargado el archivo a importar, se envía a la función según el tipo de importación deseada
    @classmethod
    @ModelView.button
    def importfile(cls, records):
        Warning = Pool().get('res.user.warning')
        warning_name = 'warning_import_conector'
        if Warning.check(warning_name):
            raise UserWarning(warning_name, "Se procede a importar el archivo cargado.")
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
                elif config.type_file == "update_accounts":
                    cls.update_csv_accounts(lineas)
                elif config.type_file == "product_costs":
                    cls.import_csv_product_costs(lineas)
                elif config.type_file == "inventory":
                    cls.import_csv_inventory(lineas)
                elif config.type_file == "bank_account":
                    cls.import_csv_bank_account(lineas)
                elif config.type_file == "loans":
                    cls.import_csv_loans(lineas)
                elif config.type_file == "access_biometric":
                    cls.import_csv_access_biometric(lineas)
                else:
                    raise UserError('Importar archivo: ', 'Seleccione el tipo de importación')
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
        for linea in lineas:
            linea = linea.split(';')
            if len(linea) != 13:
                raise UserError('Error de plantilla',
                'type_document | id_number | name | address/party_name | address/name | address/street | address/country_code | address/department_code | address/city_code | address/phone | address/email | regime_tax | type_person')
            id_number = linea[1].strip()
            print(id_number)
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
            Party.create([to_save])
            Transaction().connection.commit()

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

    #Importar saldos iniciales
    @classmethod
    def import_csv_balances(cls, lineas):
        pool = Pool()
        Account = pool.get('account.account')
        Journal = pool.get('account.journal')
        Period = pool.get('account.period')
        Move = pool.get('account.move')
        Line = pool.get('account.move.line')
        Party = pool.get('party.party')
        
        parties = Party.search([()])
        partiesd = {}
        for party in parties:
            partiesd[party.id_number] = party.id

        accounts = Account.search([()])
        accountsd = {}
        for account in accounts:
            accountsd[account.code] = {
                1: account.id,
                2: account.party_required
            }
        cont = 0
        vlist = []
        not_party = []
        for linea in lineas:
            print(linea)
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
                move = Move()
                move.journal = journal
                move.period = period
                move.date = efective_date
                move.description = description_move
                move.save()
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
            line = {
                'move': move.id,
                'account': accountsd[account_line][1],
                'reference': reference_line,
                'debit': debit_line,
                'credit': credit_line,
                'description': description_line,
            }
            if maturity_date:
                line['maturity_date'] = cls.convert_str_date(maturity_date)
            if accountsd[account_line][2]:
                if not party_line in partiesd.keys():
                    if party_line not in not_party:
                        not_party.append(party_line)
                    continue
                line['party'] = partiesd[party_line]
            #lines.append(line)
            vlist.append(line)
            if len(vlist) > 1000:
                Line.create(vlist)
                vlist.clear()
        if not_party:
            raise UserError("Falta terceros", f"{not_party}")
        #Se verifica si hay lineas por crear
        if vlist:
            Line.create(vlist)
        print('FIN import_csv_balances')


    # Función encargada de importar y verificar las cuentas nuevas
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
        not_account = []
        for linea in ordered:
            code = linea[0].strip()
            account = Account.search([('code', '=', code)])
            if account:
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
                type = Type.search([('sequence', '=', type)])
                if not type:
                    raise UserError('Importación de archivo: ', f'Error en la búsqueda del tipo de cuenta de la cuenta {code} - {name}')
                account['type'] = type[0].id
            code_parent = cls.get_parent_account(code)
            if code_parent:
                parent_account = Account.search([('code', '=', code_parent)])
                if not parent_account:
                    not_account.append(code_parent)
                    continue
                account['parent'] = parent_account[0].id
            Account.create([account])
        if not_account:
            raise UserError('Importación de archivo: ', f'Error: Faltan las cuentas padres {not_account}')


    # Función encargada de actualizar las cuentas del PUC
    @classmethod
    def update_csv_accounts(cls, lineas):
        pool = Pool()
        Account = pool.get('account.account')
        Type = pool.get('account.account.type')
        for linea in lineas:
            linea = linea.strip()
            if not linea:
                continue            
            linea = linea.split(';')
            if linea[0] == 'code':
                continue
            if len(linea) != 5:
                raise UserError('Error plantilla', 'account | name | type | reconcile | party_required')
            # Se consulta y procesa la cuenta
            code = linea[0].strip()
            account = Account.search([('code', '=', code)])
            if not account:
                continue
            account, = account
            name = linea[1].strip().upper()
            if name:
                account.name = name
            reconcile = linea[3].strip().upper()
            if reconcile:
                if reconcile == 'TRUE':
                    account.reconcile = True
                if reconcile == 'FALSE':
                    account.reconcile = False
            party_required = linea[4].strip().upper()
            if party_required:
                if party_required == 'TRUE':
                    account.party_required = True
                if party_required == 'FALSE':
                    account.party_required = False
            type = linea[2].strip()
            if type:
                type = Type.search([('sequence', '=', type)])
                if not type:
                    raise UserError('Importación de archivo: ', f'Error en la búsqueda del tipo de cuenta, para la cuenta {code} - {name}')
                type, = type
                account.type = type
            Account.save([account])

    
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

    # Funcion encargada de actualizar los costos de los productos
    @classmethod
    def import_csv_product_costs(cls, lineas):
        pool = Pool()
        Product = pool.get('product.product')
        ProductTemplate = pool.get('product.template')
        ModifyCost = pool.get('product.modify_cost_price', type='wizard')
        _id, _, _ = ModifyCost.create()
        modify_cost = ModifyCost(_id)
        RecomputeCost = pool.get('product.recompute_cost_price', type='wizard')
        _id, _, _ = RecomputeCost.create()
        recompute_cost_price = RecomputeCost(_id)
        today = datetime.date.today()
        for linea in lineas:
            linea = linea.strip()
            if not linea:
                continue            
            linea = linea.split(';')
            if len(linea) != 3:
                raise UserError('Error plantilla', ' code_product | cost | date ')
            code_product = linea[0]
            template = ProductTemplate.search([('code', '=', code_product)])
            if not template:
                raise UserError("ERROR PRODUCTO", f"No se encontro el producto con código {code_product}")
            product, = Product.search([('template', '=', template[0])])
            cost = linea[1]
            if not cost or cost == 0:
                raise UserError("ERROR COSTO", f"No se encontro el costo para el producto con código {code_product}")
            date = cls.convert_str_date(linea[2])
            # Se procede a ejecutar el asistente
            modify_cost.model = Product
            modify_cost.records = [product]
            modify_cost.start.date = date
            modify_cost.start.cost_price = cost
            modify_cost.transition_modify()
            recompute_cost_price.model = Product
            recompute_cost_price.records = [product]
            recompute_cost_price.start.from_ = today
            recompute_cost_price.transition_recompute()

    # Funcion encargada de cargar el inventario
    @classmethod
    def import_csv_inventory(cls, lineas):
        pool = Pool()
        Inventory = pool.get('stock.inventory')
        Line = pool.get('stock.inventory.line')
        Location = pool.get('stock.location')
        Product = pool.get('product.product')
        ProductTemplate = pool.get('product.template')
        inventory = Inventory()
        to_lines = []
        first = True
        for linea in lineas:
            linea = linea.strip()
            if not linea:
                continue            
            linea = linea.split(';')
            if len(linea) != 4:
                raise UserError('Error plantilla', ' location | date | product | quantity ')
            # Se verifica que es la primera linea para crear el inventario
            if first:
                location, = Location.search([('name', '=', linea[0].strip())])
                inventory.location = location
                date = cls.convert_str_date(linea[1])
                inventory.date = date
                first = False
            line = Line()
            code_product = linea[2]
            template = ProductTemplate.search([('code', '=', code_product)])
            if not template:
                raise UserError("ERROR PRODUCTO", f"No se encontro el producto con código {code_product}")
            product = Product.search([('template', '=', template[0])])
            if not product:
                raise UserError("ERROR PRODUCTO", f"No se encontro La variante con código {code_product}")
            product, = product
            line.product = product
            line.quantity = Decimal(linea[3])
            to_lines.append(line)
        if to_lines:
            inventory.lines = to_lines
            inventory.save()
        print('FIN')

    # Funcion encargada de cargar las cuentas bancarias de los empleados
    @classmethod
    def import_csv_bank_account(cls, lineas):
        pool = Pool()
        BankAccount = pool.get('bank.account')
        Bank = pool.get('bank')
        Account = pool.get('account.account')
        Party = pool.get('party.party')
        Number = pool.get('bank.account.number')
        BankAccountParty = pool.get('bank.account-party.party')
        to_save = []
        first = True
        for linea in lineas:
            linea = linea.strip()
            if not linea:
                continue            
            linea = linea.split(';')
            if len(linea) != 5:
                raise UserError('Error plantilla', 'id_bank;account;parties;number;type')
            # Se verifica que es la primera linea (encabezado) para omitirla
            if first:
                first = False
                continue
            bank = linea[0].strip()
            bank = Bank(int(bank))
            account = linea[1].strip()
            account, = Account.search([('code', '=', account)])
            party = linea[2].strip()
            party, = Party.search([('id_number', '=', party)])
            number = linea[3].strip()
            type = linea[4].strip()
            bparty = BankAccountParty.search([('owner', '=', party)])
            domain = [
                ('bank', '=', bank),
                ('account', '=', account)
            ]
            if bparty:
                domain.append(('owners', '=', bparty))
            exist = BankAccount.search(domain)
            if exist and bparty:
                continue
            print("crear")
            baccount = BankAccount()
            baccount.bank = bank
            baccount.account = account
            baccount.owners = [party]
            numbers = Number()
            numbers.number = number
            numbers.type = type
            baccount.numbers = [numbers]
            to_save.append(baccount)
        BankAccount.save(to_save)
        print('FIN')

    # Funcion encargada de cargar los prestamos de los empleados
    @classmethod
    def import_csv_loans(cls, lineas):
        pool = Pool()
        Loan = pool.get('staff.loan')
        Party = pool.get('party.party')
        PayMode = pool.get('account.voucher.paymode')
        PaymentTerm  = pool.get('staff.loan.payment_term')
        PaymentTermLine  = pool.get('staff.loan.payment_term.line')
        Delta = pool.get('staff.loan.payment_term.line.delta')
        Currency = pool.get('currency.currency')
        to_save = []
        first = True
        for linea in lineas:
            linea = linea.strip()
            if not linea:
                continue            
            linea = linea.split(';')
            if len(linea) != 7:
                raise UserError('Error plantilla', 'party;date_effective;type;payment_mode;amount;amount_fee')
            # Se verifica que es la primera linea (encabezado) para omitirla
            if first:
                first = False
                continue
            party = linea[0].strip()
            date = cls.convert_str_date(linea[1].strip())
            party, = Party.search([('id_number', '=', party)])
            paymode = linea[3].strip()
            paymode, = PayMode.search([('name', '=', paymode)])
            amount = Decimal(linea[4].strip())
            amount_fee = Decimal(linea[5].strip())
            days = (linea[6].strip()).split('-')
            if not days:
                days = [linea[6].strip()]
            loan = Loan()
            loan.party = party
            loan.date_effective = date
            loan.type = linea[2].strip()
            loan.payment_mode = paymode
            loan.amount = amount
            #se procede a buscar y/o crear el plazo de pago
            cant = math.ceil(amount/amount_fee)
            name_payment_term  = f"{cant} CUOTAS DE {len(days)} VEZ/VECES AL MES DE ${amount_fee}"
            payment_term = PaymentTerm.search([('name', '=', name_payment_term)])
            if not payment_term:
                payment_term = PaymentTerm()
                payment_term.name = name_payment_term
                fee = (days*cant)
                months = 0
                cont = 0
                _lines = []
                for i in fee:
                    cont+=1
                    line = PaymentTermLine()
                    delta = Delta()
                    delta.months = months
                    delta.day = int(i)
                    line.relativedeltas = [delta]
                    if len(_lines) == cant-1:
                        line.type = 'remainder'
                        _lines.append(line)
                        break
                    line.type = 'fixed'
                    line.amount = amount_fee
                    line.currency = Currency(1)
                    _lines.append(line)
                    if cont == len(days):
                        cont = 0
                        months += 1
                payment_term.lines = _lines
            else:
                payment_term = payment_term[0]
            loan.payment_term = payment_term
            to_save.append(loan)
        Loan.save(to_save)
        Loan.calculate(to_save)
        print('FIN')

    # Funcion encargada de cargar los ingresos y salidas de los empleados (access biometric)
    @classmethod
    def import_csv_access_biometric(cls, lineas):
        print('INICIA')
        pool = Pool()
        Access = pool.get('staff.access')
        # Rest = pool.get('staff_access_extratime.rests')
        Employee = pool.get('company.employee')
        Config = pool.get('conector.configuration')
        configuration, = Config.search([], order=[('id', 'DESC')], limit=1)
        to_create = {}
        _events = {
            configuration.access_enter_timestamp: 'enter_timestamp',
            configuration.access_exit_timestamp: 'exit_timestamp',
            configuration.access_start_rest: 'start_rest',
            configuration.access_end_rest: 'end_rest',
        }
        first = True
        for linea in lineas:
            linea = linea.strip()
            if not linea:
                continue            
            linea = linea.split(';')
            if len(linea) != 14:
                raise UserError('Error template access_biometric', 'employee;datetime(d/m/y h:m);event')
            # Se verifica que es la primera linea (encabezado) para omitirla
            if first:
                first = False
                continue
            code = linea[2].strip()
            if not code or code == '':
                continue
            employee = Employee.search([('code', '=', code)])
            if not employee:
                continue
                # raise UserError('error employee_code', f'employee code {code} not found')
            employee, = employee
            if not employee.contract.position:
                raise UserError('employee', f'employee position {employee.rec_name} not found')
            if employee not in to_create.keys():
                to_create[employee] = {}
            _year = linea[5].strip()
            _month = linea[6].strip()
            _day = linea[7].strip()
            _hour = linea[8].strip()
            _minute = linea[9].strip()
            _date_time = _day+'/'+_month+'/'+_year+' '+_hour+':'+_minute
            try:
               _datetime = datetime.datetime.strptime(_date_time, '%d/%m/%Y %H:%M')
               _datetime = (_datetime + datetime.timedelta(hours=5))
               _date = datetime.date(_datetime.year, _datetime.month, _datetime.day)
            except Exception as e:
               raise UserError('error datetime', e)
            
            if _date not in to_create[employee].keys():
                to_create[employee][_date] = {}

            _event = linea[11].strip() 
            _event = _events.get(_event)
            # En caso de no existir el evento se registra como un inicio de descanso
            if not _event:
                _event = 'start_rest'

            if _event not in to_create[employee][_date].keys():
                to_create[employee][_date][_event] = []

            to_create[employee][_date][_event].append(_datetime)
            # to_create[employee][_date][_event].sort() #Se va ordenando la lista (FIX)

        # to_save = []
        for empleoyee in to_create.keys():
            for date in to_create[empleoyee].keys():
                start_time = datetime.datetime.combine(date, datetime.datetime.min.time())
                end_time = datetime.datetime.combine(date, datetime.time(23,59,59))
                rests = cls.get_access_rests(to_create[empleoyee][date])
                if 'enter_timestamp' not in to_create[empleoyee][date].keys():
                    if 'exit_timestamp' not in to_create[empleoyee][date].keys():
                        access = Access()
                        access.employee = empleoyee
                        access.enter_timestamp = start_time
                        access.exit_timestamp = end_time
                        access.rests = rests
                        access.state = 'open'
                        access.rest = access.on_change_with_rest()
                        access.save()
                        # to_save.append(access)
                        continue
                    # Si tiene exit_timestamp
                    to_create[empleoyee][date]['exit_timestamp'].sort()
                    for exit_timestamp in to_create[empleoyee][date]['exit_timestamp']:
                        access = Access()
                        access.employee = empleoyee
                        access.enter_timestamp = exit_timestamp
                        access.exit_timestamp = exit_timestamp
                        access.rests = cls.validate_access_rests(rests, access)
                        access.rest = access.on_change_with_rest()
                        access.state = 'open'
                        access.save()
                        # to_save.append(access)
                    continue
                to_create[empleoyee][date]['enter_timestamp'].sort()
                if 'exit_timestamp' in to_create[empleoyee][date].keys():
                    to_create[empleoyee][date]['exit_timestamp'].sort()
                for enter_timestamp in to_create[empleoyee][date]['enter_timestamp']:
                    access = Access()
                    access.employee = empleoyee
                    access.enter_timestamp = enter_timestamp
                    access.exit_timestamp = None
                    if 'exit_timestamp' in to_create[empleoyee][date].keys() and to_create[empleoyee][date]['exit_timestamp']:
                        i = 0
                        for exit_timestamp in to_create[empleoyee][date]['exit_timestamp']:
                            # Se valida que el registro a asignar como hora de salida sea mayor a la de entrada
                            if exit_timestamp >= enter_timestamp:
                                exit_timestamp = to_create[empleoyee][date]['exit_timestamp'].pop(i)
                                access.exit_timestamp = exit_timestamp
                                break
                            i += 1
                    access.rests = cls.validate_access_rests(rests, access)
                    cls.validate_access(access)
                    access.rest = access.on_change_with_rest()
                    access.save()
                    # to_save.append(access)
                if 'exit_timestamp' in to_create[empleoyee][date].keys() and to_create[empleoyee][date]['exit_timestamp']:
                    for exit_timestamp in to_create[empleoyee][date]['exit_timestamp']:
                        access = Access()
                        access.employee = empleoyee
                        # En caso de tener registro de salida pero no entrada, se asigna la misma hora de salida como entrada
                        access.enter_timestamp = exit_timestamp
                        access.exit_timestamp = exit_timestamp
                        access.rests = cls.validate_access_rests(rests, access)
                        cls.validate_access(access)
                        access.rest = access.on_change_with_rest()
                        access.save()
                        # to_save.append(access)
        # Access.save(to_save)
        print('FIN')


    @classmethod
    def get_access_rests(cls, events):
        Rest = Pool().get('staff_access_extratime.rests')
        rests = []
        if 'start_rest' not in events.keys():
            if 'end_rest' in events.keys():
                events['end_rest'].sort()
                for end_rest in events['end_rest']:
                    rest = Rest()
                    rest.start_rest = None
                    rest.end_rest = end_rest
                    rest.rest_paid = True
                    rest.rest = rest.on_change_with_rest()
                    rest.save()
                    rests.append(rest)
            return rests
        if 'end_rest' not in events.keys():
            events['start_rest'].sort()
            for start_rest in events['start_rest']:
                rest = Rest()
                rest.start_rest = start_rest
                rest.end_rest = None
                rest.rest_paid = True
                rest.rest = rest.on_change_with_rest()
                rest.save()
                rests.append(rest)
            return rests
        # SI tiene start_rest y end_rest
        events['start_rest'].sort()
        events['end_rest'].sort()
        for start_rest in events['start_rest']:
            rest = Rest()
            rest.start_rest = start_rest
            rest.end_rest = None
            if events['end_rest']:
                end_rest = events['end_rest'].pop(0)
                rest.end_rest = end_rest
            rest.rest_paid = True
            rest.rest = rest.on_change_with_rest()
            rest.save()
            rests.append(rest)
        for end_rest in events['end_rest']:
            rest = Rest()
            rest.start_rest = None
            rest.end_rest = end_rest
            rest.rest_paid = True
            rest.rest = rest.on_change_with_rest()
            rest.save()
            rests.append(rest)
        return rests

    @classmethod
    def validate_access_rests(cls, rests, access):
        result = []
        for rest in rests:
            if access.enter_timestamp and access.exit_timestamp and access.enter_timestamp == access.exit_timestamp:
                result.append(rest)
                continue
            if rest.start_rest and rest.end_rest:
                if access.exit_timestamp and rest.start_rest > access.enter_timestamp and rest.end_rest < access.exit_timestamp:
                    result.append(rest)
                elif not access.exit_timestamp and rest.start_rest > access.enter_timestamp:
                    result.append(rest)
            elif rest.start_rest:
                # No tiene end_rest
                if access.exit_timestamp and rest.start_rest > access.enter_timestamp and rest.start_rest < access.exit_timestamp:
                    result.append(rest)
                elif not access.exit_timestamp and rest.start_rest > access.enter_timestamp:
                    result.append(rest)
            else:
                # No tiene start_rest
                if access.exit_timestamp and rest.end_rest > access.enter_timestamp and rest.end_rest < access.exit_timestamp:
                    result.append(rest)
                elif not access.exit_timestamp and rest.end_rest > access.enter_timestamp:
                    result.append(rest)
        result_rests = []
        for rest in rests:
            if rest not in result:
                result_rests.append(rest)
        rests = result_rests
        return result


    @classmethod
    def validate_access(cls, access):
        state = 'close'
        if access.enter_timestamp and access.exit_timestamp and access.enter_timestamp != access.exit_timestamp:
            for rest in access.rests:
                if not rest.start_rest or not rest.end_rest:
                    state = 'open'
        else:
            state = 'open'
        access.state = state