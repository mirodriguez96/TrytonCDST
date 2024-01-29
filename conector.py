"""CONECTOR MODULE"""

from decimal import Decimal
import datetime
from sql import Table
from trytond.model import ModelSQL, ModelView, fields
from trytond.transaction import Transaction
from trytond.pool import Pool
from trytond.wizard import Wizard, StateTransition, StateView, Button
from trytond.exceptions import UserError

TYPES_FILE = [
    ('parties', 'Parties'),
    ('products', 'Products'),
    ('balances', 'Balances'),
    ('accounts', 'Accounts'),
    ('update_accounts', 'Update Accounts'),
    ('product_costs', 'Product costs'),
    ('inventory', "Inventory"),
    ('bank_account', 'Bank Account'),
    # ('loans', 'Loans'),
]

STATE_LOG = [
    ('pending', 'Pending'),
    ('in_progress', 'In progress'),
    ('done', 'Done'),
]


class Actualizacion(ModelSQL, ModelView):
    'Actualizacion'
    __name__ = 'conector.actualizacion'

    name = fields.Char('Update', required=True, readonly=True)
    quantity = fields.Function(fields.Integer('Quantity'), 'getter_quantity')
    imported = fields.Function(fields.Integer('Imported'), 'getter_imported')
    exceptions = fields.Function(fields.Integer('Exceptions'),
                                 'getter_exceptions')
    cancelled = fields.Function(fields.Integer('Cancelled'),
                                'getter_cancelled')
    not_imported = fields.Function(fields.Integer('Not imported'),
                                   'getter_not_imported')
    logs = fields.Text("Logs", readonly=True)
    log = fields.One2Many('conector.log', 'actualizacion', 'Log')

    @classmethod
    def create_or_update(cls, name):
        """Function that Create or update a data of conector.actualizacion"""

        updates = Pool().get('conector.actualizacion')
        update = updates.search([('name', '=', name)])
        if update:
            update, = update
        else:
            # A new record is created
            update = updates()
            update.name = name
            update.save()
        return update

    @classmethod
    def get_fecha_actualizacion(cls, actualizacion):
        """Function that get the last date of updated conector.actualizacion"""
        fecha = datetime.date(1, 1, 1)
        if actualizacion.write_date:
            fecha = actualizacion.write_date - datetime.timedelta(hours=6)
        elif actualizacion.create_date:
            date = Pool().get('ir.date')
            create_date = actualizacion.create_date.date()
            if create_date != date.today():
                fecha = (actualizacion.create_date -
                         datetime.timedelta(hours=6))
        return fecha

    def add_logs(self, logs):
        """Function that get and update a dictionary with logs in imports"""

        now = datetime.datetime.now()  # - datetime.timedelta(hours=5)
        if not logs:
            self.write([self], {'write_date': now})
            return
        to_create = []
        for id_tecno, message in logs.items():
            create = {
                'event_time': now,
                'id_tecno': id_tecno,
                'message': message,
                'state': 'pending'
            }
            to_create.append(create)
        self.write([self], {'log': [('create', to_create)]})

    def getter_quantity(self, name):
        """Function that query DB SQLSERVER with the docts imported"""
        #CHECKING

        conector_configurations = Pool().get('conector.configuration')
        connection, = conector_configurations.search([],
                                                     order=[('id', 'DESC')],
                                                     limit=1)
        data = connection.date
        data = data.strftime('%Y-%m-%d %H:%M:%S')
        consult = "SET DATEFORMAT ymd SELECT COUNT(*) FROM dbo.Documentos "\
            f"WHERE fecha_hora >= CAST('{data}' AS datetime)"
        if connection.end_date:
            end_date = connection.end_date.strftime('%Y-%m-%d %H:%M:%S')
            consult += f" AND fecha_hora < CAST('{end_date}' AS datetime) "
        if self.name == 'VENTAS':
            consult += " AND (sw = 1 or sw = 2)"
        elif self.name == 'COMPRAS':
            consult += " AND (sw = 3 or sw = 4)"
        elif self.name == 'COMPROBANTES DE INGRESO':
            consult += " AND sw = 5"
        elif self.name == 'COMPROBANTES DE EGRESO':
            consult += " AND sw = 6"
        elif self.name == 'PRODUCCION':
            consult += " AND ("
            parametro = conector_configurations.get_data_parametros('177')
            valor_parametro = parametro[0].Valor.split(',')
            for tipo in valor_parametro:
                consult += f"tipo = {tipo}"
                if (valor_parametro.index(tipo) + 1) < len(valor_parametro):
                    consult += " OR "
            consult += ")"

        else:
            return None
        result = connection.get_data(consult)
        result = int(result[0][0])
        return result

    def getter_imported(self, name):
        """Function that query the save records in Tryton that was imported by conector"""

        conector_configuration = Pool().get('conector.configuration')
        connection, = conector_configuration.search([],
                                                    order=[('id', 'DESC')],
                                                    limit=1)

        query = "SELECT COUNT(*) FROM "
        quantity = None
        cursor = Transaction().connection.cursor()

        if self.name == 'VENTAS':
            query += f"sale_sale WHERE sale_date >= '{connection.date}' "\
                "AND (id_tecno LIKE '1-%' OR id_tecno LIKE '2-%') "
            if connection.end_date:
                query += f" AND sale_date < '{connection.end_date}' "
            cursor.execute(query)

        elif self.name == 'COMPRAS':
            query += f"purchase_purchase WHERE purchase_date >= '{connection.date}' "\
                    "AND (id_tecno LIKE '3-%' OR id_tecno LIKE '4-%') "
            if connection.end_date:
                query += f" AND purchase_date < '{connection.end_date}' "
            cursor.execute(query)

        elif self.name == 'COMPROBANTES DE INGRESO':
            query = "SELECT COUNT(*) FROM account_voucher "\
                    f"WHERE date >= '{connection.date}' AND id_tecno LIKE '5-%' "
            if connection.end_date:
                query += f" AND date < '{connection.end_date}' "
            cursor.execute(query)
            quantity = int(cursor.fetchone()[0])
            query = "SELECT COUNT(*) FROM account_multirevenue "\
                    f"WHERE date >= '{connection.date}' AND id_tecno LIKE '5-%' "
            if connection.end_date:
                query += f" AND date < '{connection.end_date}' "
            cursor.execute(query)
            quantity2 = int(cursor.fetchone()[0])
            quantity += quantity2
            return quantity

        elif self.name == 'COMPROBANTES DE EGRESO':
            query += f"account_voucher WHERE date >= '{connection.date}' "\
                "AND id_tecno LIKE '6-%' "
            if connection.end_date:
                query += f" AND date < '{connection.end_date}' "
            cursor.execute(query)

        elif self.name == 'PRODUCCION':
            query += f"production WHERE planned_date >= '{connection.date}' "\
                "AND id_tecno LIKE '12-%' "
            if connection.end_date:
                query += f" AND planned_date < '{connection.end_date}' "
            cursor.execute(query)
        else:
            return quantity

        result = cursor.fetchone()
        if result:
            quantity = int(result[0])
        return quantity

    def getter_exceptions(self, name):
        """Function that query DB SQLSERVER records with exceptions"""

        conector_configuration = Pool().get('conector.configuration')
        connection, = conector_configuration.search([],
                                                    order=[('id', 'DESC')],
                                                    limit=1)
        data = connection.date.strftime('%Y-%m-%d %H:%M:%S')
        consult = "SET DATEFORMAT ymd SELECT COUNT(*) FROM dbo.Documentos "\
            f"WHERE fecha_hora >= CAST('{data}' AS datetime) AND exportado = 'E'"

        if connection.end_date:
            end_date = connection.end_date.strftime('%Y-%m-%d %H:%M:%S')
            consult += f" AND fecha_hora < CAST('{end_date}' AS datetime) "
        if self.name == 'VENTAS':
            consult += " AND (sw = 1 or sw = 2)"
        elif self.name == 'COMPRAS':
            consult += " AND (sw = 3 or sw = 4)"
        elif self.name == 'COMPROBANTES DE INGRESO':
            consult += " AND sw = 5"
        elif self.name == 'COMPROBANTES DE EGRESO':
            consult += " AND sw = 6"
        elif self.name == 'PRODUCCION':
            consult += " AND ("
            conector_parameters = conector_configuration.get_data_parametros(
                '177')
            parameters = conector_parameters[0].Valor.split(',')

            for parameter in parameters:
                consult += f"tipo = {parameter}"
                if (parameters.index(parameter) + 1) < len(parameters):
                    consult += " OR "
            consult += ")"
        else:
            return None
        result = connection.get_data(consult)
        result = int(result[0][0])
        return result

    def getter_cancelled(self, name):
        """Function that query DB SQLSERVER records that was not imported"""

        conector_configuration = Pool().get('conector.configuration')
        connection, = conector_configuration.search([],
                                                    order=[('id', 'DESC')],
                                                    limit=1)
        data = connection.date.strftime('%Y-%m-%d %H:%M:%S')
        consult = "SET DATEFORMAT ymd SELECT COUNT(*) FROM dbo.Documentos "\
            f"WHERE fecha_hora >= CAST('{data}' AS datetime) AND exportado = 'X'"

        if connection.end_date:
            end_date = connection.end_date.strftime('%Y-%m-%d %H:%M:%S')
            consult += f" AND fecha_hora < CAST('{end_date}' AS datetime) "
        if self.name == 'VENTAS':
            consult += " AND (sw = 1 or sw = 2)"
        elif self.name == 'COMPRAS':
            consult += " AND (sw = 3 or sw = 4)"
        elif self.name == 'COMPROBANTES DE INGRESO':
            consult += " AND sw = 5"
        elif self.name == 'COMPROBANTES DE EGRESO':
            consult += " AND sw = 6"
        elif self.name == 'PRODUCCION':
            consult += " AND ("
            conector_parameters = conector_configuration.get_data_parametros(
                '177')
            parameters = conector_parameters[0].Valor.split(',')

            for parameter in parameters:
                consult += f"tipo = {parameter}"
                if (parameters.index(parameter) + 1) < len(parameters):
                    consult += " OR "
            consult += ")"
        else:
            return None
        result = connection.get_data(consult)
        result = int(result[0][0])
        return result

    def getter_not_imported(self, name):
        """Function that query DB SQLSERVER the records that have to be imported"""

        conector_configuration = Pool().get('conector.configuration')
        connection, = conector_configuration.search([],
                                                    order=[('id', 'DESC')],
                                                    limit=1)
        data = connection.date
        data = data.strftime('%Y-%m-%d %H:%M:%S')
        consult = "SET DATEFORMAT ymd SELECT COUNT(*) FROM dbo.Documentos "\
            f"WHERE fecha_hora >= CAST('{data}' AS datetime) "\
            "AND exportado != 'T' AND exportado != 'E' AND exportado != 'X'"

        if connection.end_date:
            end_date = connection.end_date.strftime('%Y-%m-%d %H:%M:%S')
            consult += f" AND fecha_hora < CAST('{end_date}' AS datetime) "
        if self.name == 'VENTAS':
            consult += " AND (sw = 1 or sw = 2)"
        elif self.name == 'COMPRAS':
            consult += " AND (sw = 3 or sw = 4)"
        elif self.name == 'COMPROBANTES DE INGRESO':
            consult += " AND sw = 5"
        elif self.name == 'COMPROBANTES DE EGRESO':
            consult += " AND sw = 6"
        elif self.name == 'PRODUCCION':
            consult += " AND ("
            conector_parameters = conector_configuration.get_data_parametros(
                '177')
            parameters = conector_parameters[0].Valor.split(',')

            for parameter in parameters:
                consult += "tipo = " + str(parameter)
                if (parameters.index(parameter) + 1) < len(parameters):
                    consult += " OR "
            consult += ")"
        else:
            return None
        result = connection.get_data(consult)
        result = int(result[0][0])
        return result

    @classmethod
    def revisa_secuencia_imp(cls, name):
        """Function that compare Tryton records with TecnoCarnes records 
            and markup if will be imported"""

        result = None
        result_tryton = []
        condition = None
        logs = {}

        pool = Pool()
        conector_configuration = pool.get('conector.configuration')
        conector_updates = pool.get('conector.actualizacion')
        cursor = Transaction().connection.cursor()

        if name == 'VENTAS':
            consultv = "SELECT id_tecno FROM sale_sale WHERE id_tecno is not null"
            cursor.execute(consultv)
            result = cursor.fetchall()
            condition = "(sw=1 OR sw=2)"

        if name == 'COMPRAS':
            consultv = "SELECT id_tecno FROM purchase_purchase WHERE id_tecno is not null"
            cursor.execute(consultv)
            result = cursor.fetchall()
            condition = "(sw=3 OR sw=4)"

        if name == 'COMPROBANTES DE INGRESO':
            consult1 = "SELECT id_tecno FROM account_voucher WHERE id_tecno LIKE '5-%'"
            cursor.execute(consult1)
            result = cursor.fetchall()
            result_tryton = [r[0] for r in result]
            consult2 = "SELECT id_tecno FROM account_multirevenue WHERE id_tecno is not null"
            cursor.execute(consult2)
            result = cursor.fetchall()
            condition = "sw=5"

        if name == 'COMPROBANTES DE EGRESO':
            consultv = "SELECT id_tecno FROM account_voucher WHERE id_tecno  LIKE '6-%'"
            cursor.execute(consultv)
            result = cursor.fetchall()
            condition = "sw=6"

        if name == 'PRODUCCION':
            consultv = "SELECT id_tecno FROM production WHERE id_tecno is not null"
            cursor.execute(consultv)
            result = cursor.fetchall()
            condition = "("
            parametro = conector_configuration.get_data_parametros('177')
            valor_parametro = parametro[0].Valor.split(',')
            for tipo in valor_parametro:
                condition += "tipo=" + tipo.strip()
                if valor_parametro.index(tipo) != (len(valor_parametro) - 1):
                    condition += " OR "
            condition += ")"

        if name == 'NOTAS DE CREDITO':
            consultv = "SELECT id_tecno FROM account_invoice WHERE id_tecno  LIKE '32-%'"
            cursor.execute(consultv)
            result = cursor.fetchall()
            condition = "sw=32"

        if name == 'NOTAS DE DEBITO':
            consultv = "SELECT id_tecno FROM account_voucher WHERE id_tecno  LIKE '31-%'"
            cursor.execute(consultv)
            result = cursor.fetchall()
            condition = "sw=31"

        #Save records in a list
        if not result_tryton and result:
            result_tryton = [r[0] for r in result]
        elif result_tryton and result:
            for r in result:
                result_tryton.append(r[0])
        if not condition:
            return

        config, = conector_configuration.search([],
                                                order=[('id', 'DESC')],
                                                limit=1)
        data = config.date.strftime('%Y-%m-%d %H:%M:%S')
        consultc = "SET DATEFORMAT ymd SELECT CONCAT(sw,'-',tipo,'-',numero_documento) FROM Documentos "\
            f"WHERE {condition} AND fecha_hora >= CAST('{data}' AS datetime) "\
            "AND exportado = 'T' AND tipo<>0 ORDER BY tipo,numero_documento"

        result_tecno = conector_configuration.get_data(consultc)
        result_tecno = [r[0] for r in result_tecno]
        list_difference = [r for r in result_tecno if r not in result_tryton]

        #Records are saved and marked for import again
        for falt in list_difference:
            lid = falt.split('-')
            query = "UPDATE dbo.Documentos SET exportado = 'N' "\
                f"WHERE sw = {lid[0]} AND tipo = {lid[1]} AND Numero_documento = {lid[2]}"
            conector_configuration.set_data(query)
            logs[falt] = "EL DOCUMENTO ESTABA MARCADO COMO IMPORTADO (T) SIN ESTARLO. "\
                "AHORA FUE MARACADO COMO PENDIENTE PARA IMPOTAR (N)"
        connector_update, = conector_updates.search([('name', '=', name)])
        connector_update.add_logs(logs)

    @classmethod
    def _missing_documents(cls):
        print("RUN missing documents")
        cursor = Transaction().connection.cursor()
        cursor.execute("SELECT name FROM conector_actualizacion")
        result = cursor.fetchall()
        for r in result:
            cls.revisa_secuencia_imp(r[0])
        print("FINISH missing documents")

    @classmethod
    def import_biometric_access(cls, event_time=None):
        """Function that acces to briometic"""

        to_save = {}
        to_rest = {}
        start_work = None
        pool = Pool()
        conector_configuration = pool.get('conector.configuration')
        staff_access = pool.get('staff.access')
        staff_access_rests = pool.get('staff.access.rests')
        company_employees = pool.get('company.employee')
        configuration = conector_configuration.get_configuration()

        if not configuration:
            return
        if not event_time:
            yesterday = datetime.date.today() - datetime.timedelta(days=1)
            event_time = datetime.datetime(yesterday.year, yesterday.month,
                                           yesterday.day, 0, 0, 0)
        data = configuration.get_biometric_access_transactions(event_time)

        for d in data:
            if d.Nit_cedula not in to_save:
                employee = company_employees.search([('party.id_number', '=',
                                                      d.Nit_cedula)])
                if not employee:
                    continue

                employee, = employee
                start_work = None
                to_save[d.Nit_cedula] = staff_access()
                to_save[d.Nit_cedula].employee = employee
                to_save[d.Nit_cedula].payment_method = 'extratime'
                to_save[d.Nit_cedula].enter_timestamp = None
                to_save[d.Nit_cedula].exit_timestamp = None
                to_rest[d.Nit_cedula] = []
            access = to_save[d.Nit_cedula]

            datetime_record = d.Fecha_Hora_Marcacion + datetime.timedelta(
                hours=5)
            if d.TipoEventoEntraoSale.upper() == 'SALIDA':
                if not access.enter_timestamp:
                    access.enter_timestamp = datetime_record
                    continue

            if d.TipoEventoEntraoSale.upper() == 'ENTRADA':
                #First input to "ENTRADA" is ignored, because is the work start
                if not start_work:
                    start_work = datetime_record
                    continue
                access.exit_timestamp = datetime_record  # 'ultima entrada

            rests = to_rest[d.Nit_cedula]

            #Start of breakfast
            if d.TipoEventoEntraoSale.upper() == 'ENTRADA':
                rest = staff_access_rests()
                rest.start = datetime_record
                rest.end = None
                continue

            if d.TipoEventoEntraoSale.upper() == 'SALIDA':
                if not access.enter_timestamp:
                    continue

                #punishment if register input a "SALIDA" without input "ENTRADA" before
                if not 'rest' in locals():
                    rest = staff_access_rests()
                    rest.start = datetime_record - datetime.timedelta(
                        minutes=45)
                    rest.end = datetime_record
                    rests.append(rest)
                    continue

                if not rest.start:
                    rest = staff_access_rests()
                    rest.end = datetime_record
                    rests.append(rest)
                    continue

                if not rest.end:
                    rest.end = datetime_record
                    rests.append(rest)
                    continue

        #Search the records of the same day
        tomorrow = event_time + datetime.timedelta(days=1)
        access_search = list(
            staff_access.search([('enter_timestamp', '>=', event_time),
                                 ('enter_timestamp', '<', tomorrow)]))

        for nit, acess in to_save.items():
            exists = False
            for acces_search in access_search:
                if acess.employee == acces_search.employee:
                    access_search.remove(acces_search)
                    exists = True
                    break
            if exists:
                continue
            if not acess.enter_timestamp:
                continue
            if acess.exit_timestamp \
                and acess.enter_timestamp >= acess.exit_timestamp:
                continue
            if to_rest[nit]:
                to_rest[nit].pop()
                for rest in to_rest[nit]:
                    rest.access = acess
                    if rest.start >= rest.end:
                        rest.start = rest.end - datetime.timedelta(minutes=45)
                staff_access_rests.save(to_rest[nit])
                acess.rests = to_rest[nit]
            acess.on_change_rests()
            acess.save()

    @classmethod
    def biometric_access_dom(cls):
        """Function that get biometric access sunday"""

        pool = Pool()
        ir_crons = pool.get('ir.cron')
        staff_access = pool.get('staff.access')
        company_employees = pool.get('company.employee')
        access_table = Table('staff_access')
        cursor = Transaction().connection.cursor()
        time, = ir_crons.search([('access_register', '=', True)])

        date = [int(i) for i in str(datetime.date.today()).split('-')]

        time_enter = [int(i) for i in str(time.enter_timestamp).split(':')]

        time_exit = [int(i) for i in str(time.exit_timestamp).split(':')]

        enter_employee = datetime.datetime(*date, *time_enter)
        exit_employee = datetime.datetime(*date, *time_exit)

        employees = company_employees.search([
            ('active', '=', 'active'),
            ('contracting_state', '=', 'active'),
        ])

        for employee in employees:
            if enter_employee and exit_employee:
                is_access = staff_access.search([
                    ('enter_timestamp', '<=',
                     enter_employee + datetime.timedelta(hours=5)),
                    ('exit_timestamp', '>=',
                     exit_employee + datetime.timedelta(hours=5)),
                    ('employee', '=', employee)
                ])

                if not is_access:
                    to_save = staff_access()
                    to_save.employee = employee
                    to_save.payment_method = 'extratime'
                    to_save.enter_timestamp = enter_employee + datetime.timedelta(
                        hours=5)
                    to_save.exit_timestamp = exit_employee + datetime.timedelta(
                        hours=5)
                    to_save.line_event = time
                    to_save.save()

                    cursor.execute(*access_table.update(
                        columns=[
                            access_table.ttt,
                            access_table.hedo,
                            access_table.heno,
                            access_table.hedf,
                            access_table.henf,
                            access_table.reco,
                            access_table.recf,
                            access_table.dom,
                        ],
                        values=[Decimal(7.83), 0, 0, 0, 0, 0, 0, 0],
                        where=access_table.id.in_([to_save.id])))

    @classmethod
    def holidays_access_fes(cls):
        """Function that get biometric access holidays"""
        staff_holidays = Pool().get('staff.holidays')
        validate = datetime.date.today() + datetime.timedelta(hours=5)
        holidays = staff_holidays.search([('holiday', '=', validate)])

        if holidays:
            cls.biometric_access_dom()


class ImportedDocument(ModelView):
    'Imported Document Tryton View'
    __name__ = 'conector.actualizacion.imported_document'

    file = fields.Binary('File', help="Enter the file to import with (;)")
    type_file = fields.Selection(TYPES_FILE, 'Type file')


class ImportedDocumentWizard(Wizard):
    'Imported Document Tryton Wizard'
    __name__ = 'conector.actualizacion.imported_document_asistend'

    start = StateView(
        'conector.actualizacion.imported_document',
        'conector.view_imported_document', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Import', 'importfile', 'tryton-ok', default=True),
        ])

    importfile = StateTransition()

    @classmethod
    def encode_file(cls, file, process='encode'):
        """Get file decoded or encode"""

        if process == 'encode':
            file_decod = file.encode()
        else:
            file_decod = file.decode()
        return file_decod

    def transition_importfile(self):
        """Function that identify file types that are imported"""
        # pylint: disable=no-member

        config = self.start
        user_warnings = Pool().get('res.user.warning')
        warning_name = 'warning_import_conector'

        if user_warnings.check(warning_name):
            raise UserError(warning_name,
                            "Se procede a importar el archivo cargado.")
        if config.file:
            file_decode = self.encode_file(config.file, 'decode')
            lineas = file_decode.split('\n')
            if config.type_file == "parties":
                self.import_csv_parties(lineas)
            elif config.type_file == "products":
                self.import_csv_products(lineas)
            elif config.type_file == "balances":
                self.import_csv_balances(lineas)
            elif config.type_file == "accounts":
                self.import_csv_accounts(lineas)
            elif config.type_file == "update_accounts":
                self.update_csv_accounts(lineas)
            elif config.type_file == "product_costs":
                self.import_csv_product_costs(lineas)
            elif config.type_file == "inventory":
                self.import_csv_inventory(lineas)
            elif config.type_file == "bank_account":
                self.import_csv_bank_account(lineas)
            elif config.type_file == "loans":
                self.import_csv_loans(lineas)
            elif config.type_file == "access_biometric":
                self.import_csv_access_biometric(lineas)
            else:
                raise UserError('Importar archivo: ',
                                'Seleccione el tipo de importación')
        else:
            raise UserError('Importación de archivo: ',
                            'Agregue un archivo para importar')

        return 'end'

    @classmethod
    def import_csv_parties(cls, lineas):
        """Function that import parties in file csv"""

        pool = Pool()
        parties = pool.get('party.party')
        parties_city = pool.get('party.city_code')
        parties_department = pool.get('party.department_code')
        parties_country = pool.get('party.country_code')
        firts = True
        for linea in lineas:
            linea = linea.strip()
            if not linea:
                continue
            linea = linea.split(';')
            if len(linea) != 13:
                raise UserError(
                    'Error de plantilla',
                    'type_document | id_number | name | address/party_name | address/name | '
                    'address/street | address/country_code | address/department_code | '
                    'address/city_code | address/phone |address/email | regime_tax | type_person'
                )

            if firts:
                firts = False
                continue

            id_number = linea[1].strip()
            party = parties.search([('id_number', '=', id_number)])
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
            country = parties_country.search([
                ('code', '=', country_code),
            ])
            department_code = linea[7].strip()
            department = parties_department.search([
                ('code', '=', department_code),
            ])
            city_code = linea[8].strip()
            city = parties_city.search([
                ('code', '=', city_code),
                ('department.code', '=', department_code),
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
                phone = {'type': 'phone', 'value': phone}
                contacts.append(phone)
            email = linea[10].strip()
            if email:
                email = {'type': 'email', 'value': email}
                contacts.append(email)
            if contacts:
                to_save['contact_mechanisms'] = [('create', contacts)]
            parties.create([to_save])
            print(contacts)
            Transaction().connection.commit()

    @classmethod
    def import_csv_products(cls, lineas):
        """Function that import products in file csv"""

        pool = Pool()
        product_template = pool.get('product.template')
        product_categories = pool.get('product.category')
        product_oum = pool.get('product.uom')
        products = []
        not_products = []
        first = True
        for linea in lineas:
            linea = linea.strip()
            if linea:
                linea = linea.split(';')
                if len(linea) != 13:
                    raise UserError(
                        'Error de plantilla',
                        'code | name | list_price | sale_price_w_tax | account_category | '
                        'name_uom | salable | purchasable | producible | consumable | type | '
                        'depreciable | cost_price')

                if first:
                    first = False
                    continue
                code = linea[0].strip()
                product = product_template.search([('code', '=', code)])
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
                account_category = product_categories.search([('name', '=',
                                                               name_category)])
                if not account_category:
                    print(name_category)
                    raise UserError(
                        "Error Categoria Producto",
                        f"No se encontro la categoria: {name_category}")

                account_category, = account_category
                prod['account_category'] = account_category.id
                name_uom = linea[5].strip()
                uom = product_oum.search([('name', '=', name_uom)])

                if not uom:
                    raise UserError(
                        "Error UDM Producto",
                        f"No se encontro la unidad de medida: {name_uom}")

                uom, = uom
                prod['default_uom'] = uom.id
                prod['sale_uom'] = uom.id
                prod['purchase_uom'] = uom.id
                prod['products'] = [('create', [{
                    'cost_price':
                    int(linea[12].strip()),
                }])]
                products.append(prod)

        product_template.create(products)

    @classmethod
    def import_csv_balances(cls, lineas):
        """Function that import account balances in file csv"""

        pool = Pool()
        account = pool.get('account.account')
        account_journals = pool.get('account.journal')
        account_periods = pool.get('account.period')
        account_moves = pool.get('account.move')
        account_move_line = pool.get('account.move.line')
        parties = pool.get('party.party')

        parties = parties.search([()])
        accounts_records = {}
        parties_records = {}
        cont = 0
        vlist = []
        not_party = []
        first = True

        for party in parties:
            parties_records[party.id_number] = party.id

        accounts = account.search([()])
        for account in accounts:
            accounts_records[account.code] = {
                1: account.id,
                2: account.party_required
            }

        for linea in lineas:
            print(linea)
            linea = linea.strip()
            if not linea:
                continue
            linea = linea.split(';')
            if len(linea) != 11:
                raise UserError(
                    'Error de plantilla',
                    'libro diario | periodo | fecha efectiva | descripcion | linea/cuenta | '
                    'linea/debito | linea/credito | linea/tercero | linea/descripcion | '
                    'linea/fecha vencimiento | linea/referencia')

            if first:
                first = False
                continue
            if cont == 0:
                name_journal = linea[0].strip()
                name_period = linea[1].strip()
                efective_date = cls.convert_str_date(linea[2])
                description_move = linea[3].strip()
                journal = account_journals.search([('name', '=', name_journal)
                                                   ])

                if not journal:
                    raise UserError(
                        'Error diario',
                        f'No se encontró el diario {name_journal}')

                journal, = journal
                period = account_periods.search([('name', '=', name_period)])
                if not period:
                    raise UserError('Error periodo',
                                    f'No se encontró el diario {name_period}')
                period, = period
                move = account_moves()
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
                'account': accounts_records[account_line][1],
                'reference': reference_line,
                'debit': debit_line,
                'credit': credit_line,
                'description': description_line,
            }
            if maturity_date:
                line['maturity_date'] = cls.convert_str_date(maturity_date)

            if accounts_records[account_line][2]:
                if not party_line in parties_records:
                    if party_line not in not_party:
                        not_party.append(party_line)
                    continue
                line['party'] = parties_records[party_line]

            vlist.append(line)

            if len(vlist) > 1000:
                account_move_line.create(vlist)
                vlist.clear()

        if not_party:
            raise UserError("Falta terceros", f"{not_party}")

        if vlist:
            account_move_line.create(vlist)

    @classmethod
    def import_csv_accounts(cls, lineas):
        """Function that verify and import new accounts"""

        pool = Pool()
        accounts = pool.get('account.account')
        account_types = pool.get('account.account.type')

        ordered = []
        firts = True

        for linea in lineas:
            linea = linea.strip()
            if not linea:
                continue
            linea = linea.split(';')
            if linea[0] == 'code':
                continue
            if len(linea) != 5:
                raise UserError(
                    'Error plantilla',
                    'account | name | type | reconcile | party_required')
            if firts:
                firts = False
                continue
            ordered.append(linea)
        ordered = sorted(ordered, key=lambda item: len(item[0]))
        not_account = []
        for linea in ordered:
            code = linea[0].strip()
            account = accounts.search([('code', '=', code)])
            if account:
                continue
            name = linea[1].strip().upper()
            type_account = linea[2].strip()
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
            if type_account:
                type_account = account_types.search([('sequence', '=',
                                                      type_account)])
                if not type_account:
                    raise UserError(
                        'Importación de archivo: ',
                        f'Error en la búsqueda del tipo de cuenta de la cuenta {code} - {name}'
                    )
                account['type'] = type_account[0].id

            code_parent = cls.get_parent_account(code)
            if code_parent:
                parent_account = accounts.search([('code', '=', code_parent)])
                if not parent_account:
                    not_account.append(code_parent)
                    continue
                account['parent'] = parent_account[0].id

            accounts.create([account])

        if not_account:
            raise UserError('Importación de archivo: ',
                            f'Error: Faltan las cuentas padres {not_account}')

    @classmethod
    def update_csv_accounts(cls, lineas):
        """Function that update PUC accounts"""

        pool = Pool()
        accounts = pool.get('account.account')
        account_types = pool.get('account.account.type')
        columns = ['account', 'name', 'type', 'reconcile', 'party_required']

        firts = True
        item = []
        account_dictionary = {}

        for linea in lineas:

            if firts:
                firts = False
                continue

            linea = linea.strip()

            item = [i for i in linea.split(';')]

            if item == ['']:
                continue

            if len(item) != 5:
                raise UserError(
                    'Error plantilla',
                    'account | name | type | reconcile | party_required')

            if not firts:
                account_dictionary = dict(zip(columns, item))

            if not item:
                continue

            # Se consulta y procesa la cuenta
            code = account_dictionary['account']

            account = accounts.search([('code', '=', code)])

            if not account:
                continue
            account, = account
            name = account_dictionary['name'].upper()
            if name:
                account.name = name
            reconcile = account_dictionary['reconcile'].upper()
            if reconcile:
                if reconcile == 'TRUE':
                    account.reconcile = True
                if reconcile == 'FALSE':
                    account.reconcile = False
            party_required = account_dictionary['party_required'].upper()
            if party_required:
                if party_required == 'TRUE':
                    account.party_required = True
                if party_required == 'FALSE':
                    account.party_required = False

            account_type = account_dictionary['type']

            if account_type:
                account_type = account_types.search([('sequence', '=',
                                                      account_type)])
                if not account_type:
                    raise UserError(
                        'Importación de archivo: ',
                        f'Error en la búsqueda del tipo de cuenta, para la cuenta {code} - {name}'
                    )

                account_type, = account_type
                account.type = account_type

            if account.type and account_type == '':
                account.type = None

            accounts.save([account])

    @classmethod
    def get_parent_account(cls, code):
        """Function that return parent account"""
        if len(code) < 2 or (len(code) % 2) != 0:
            raise UserError('Importación de archivo:',
                            f'Error de código {code}')

        return code[:-2] if len(code) > 2 else code[0]

    @classmethod
    def convert_str_date(cls, fecha):
        """Function that convert string in date"""
        try:
            result = fecha.strip().split()[0].split('-')
            result = datetime.date(int(result[0]), int(result[1]),
                                   int(result[2]))
        except ValueError as error:
            raise UserError(
                f"Error fecha {fecha}",
                "Recuerde que la fecha debe estar con el siguiente formato YY-MM-DD"
            ) from error
        return result

    @classmethod
    def get_boolean(cls, val):
        """Function that convert an integer to boolean"""
        if int(val) == 0:
            return False
        if int(val) == 1:
            return True

    @classmethod
    def import_csv_product_costs(cls, lineas):
        """Function that update product costs"""
        pool = Pool()
        products = pool.get('product.product')
        product_cost_revision = pool.get('product.cost_price.revision')
        product_average_costs = Pool().get('product.average_cost')
        company = Transaction().context.get('company')

        product_cost_revision_list = []
        to_create = []
        product_list = []
        firts = True
        for linea in lineas:
            linea = linea.strip()
            if not linea:
                continue
            linea = linea.split(';')
            if len(linea) != 3:
                raise UserError('Error plantilla',
                                ' code_product | cost | date ')
            if firts:
                firts = False
                continue
            code_product = linea[0]
            product = products.search([('template', '=', code_product)])
            if not product:
                raise UserError(
                    "ERROR PRODUCTO",
                    f"No se encontro el producto con código {code_product}")
            product, = product
            cost = linea[1]
            if not cost or cost == 0:
                raise UserError(
                    "ERROR COSTO",
                    f"No se encontro el costo para el producto con código {code_product}"
                )
            date = cls.convert_str_date(linea[2])

            revision = {
                "company": company,
                "product": product.id,
                "template": product.template.id,
                "cost_price": cost,
                "date": date,
            }
            product_cost_revision_list.append(revision)
            average_cost = {
                "product": product.id,
                "effective_date": date,
                "cost_price": cost,
            }
            to_create.append(average_cost)
            product_list.append(product)

        records = product_cost_revision.create(product_cost_revision_list)
        product_average_costs.create(to_create)

        if records:
            products.recompute_cost_price(product_list,
                                          start=datetime.date.today())

    @classmethod
    def import_csv_inventory(cls, lineas):
        """Function to load the inventory """

        pool = Pool()
        stock_inventories = pool.get('stock.inventory')
        stock_inventory_lines = pool.get('stock.inventory.line')
        stock_location = pool.get('stock.location')
        products = pool.get('product.product')
        product_template = pool.get('product.template')

        to_lines = []
        first = True
        inventory = stock_inventories()

        for linea in lineas:
            linea = linea.strip()
            if not linea:
                continue
            linea = linea.split(';')
            if len(linea) != 4:
                raise UserError('Error plantilla',
                                ' location | date | product | quantity ')

            #Create a inventory
            if first:
                location, = stock_location.search([('name', '=',
                                                    linea[0].strip())])
                inventory.location = location
                date = cls.convert_str_date(linea[1])
                inventory.date = date
                first = False
            line = stock_inventory_lines()
            code_product = linea[2]
            template = product_template.search([('code', '=', code_product)])
            if not template:
                raise UserError(
                    "ERROR PRODUCTO",
                    f"No se encontro el producto con código {code_product}")
            product = products.search([('template', '=', template[0])])
            if not product:
                raise UserError(
                    "ERROR PRODUCTO",
                    f"No se encontro La variante con código {code_product}")
            product, = product
            line.product = product
            line.quantity = Decimal(linea[3])
            to_lines.append(line)

        if to_lines:
            inventory.lines = to_lines
            inventory.save()

    @classmethod
    def import_csv_bank_account(cls, lineas):
        """Function that load account bank of parties"""

        pool = Pool()
        bank_accounts = pool.get('bank.account')
        banks = pool.get('bank')
        accounts = pool.get('account.account')
        parties = pool.get('party.party')
        bank_account_numbers = pool.get('bank.account.number')
        bank_account_parties = pool.get('bank.account-party.party')

        to_save = []
        first = True

        for linea in lineas:
            linea = linea.strip()
            if not linea:
                continue
            linea = linea.split(';')
            if len(linea) != 5:
                raise UserError('Error plantilla',
                                'id_bank | account | parties | number | type')

            if first:
                first = False
                continue

            bank = linea[0].strip()
            bank = banks(int(bank))

            account = linea[1].strip()
            account, = accounts.search([('code', '=', account)])

            party = linea[2].strip()
            party, = parties.search([('id_number', '=', party)])

            number_account = linea[3].strip()
            type_account_number = linea[4].strip()
            bparty = bank_account_parties.search([('owner', '=', party)])
            domain = [('bank', '=', bank), ('account', '=', account.id)]

            if bparty:
                domain.append(('owners', 'in', bparty))
            exist = bank_accounts.search(domain)
            if exist and bparty:
                continue

            baccount = bank_accounts()
            baccount.bank = bank
            baccount.account = account
            baccount.owners = [party]
            numbers = bank_account_numbers()
            numbers.number = number_account
            numbers.type = type_account_number
            baccount.numbers = [numbers]
            to_save.append(baccount)

        bank_accounts.save(to_save)


class ConectorLog(ModelSQL, ModelView):
    'Conector Log'
    __name__ = 'conector.log'

    actualizacion = fields.Many2One('conector.actualizacion',
                                    'log',
                                    'Actualizacion',
                                    required=True)
    event_time = fields.DateTime('Event time', required=True)
    id_tecno = fields.Char('Id TecnoCarnes',
                           help='For documents sw-tipo-numero',
                           required=True)
    message = fields.Char('Message', required=True)
    state = fields.Selection(STATE_LOG, 'State', required=True)

    @staticmethod
    def default_state():
        """Function that return default state"""
        return 'pending'
