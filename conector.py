from trytond.model import ModelSQL, ModelView, fields
from trytond.transaction import Transaction
from trytond.pool import Pool
from trytond.wizard import Wizard, StateTransition, StateView, Button
from trytond.exceptions import UserError, UserWarning

from decimal import Decimal
import datetime
from sql import Table

TYPES_FILE = [
    ('parties', 'Parties'),
    ('products', 'Products'),
    ('balances', 'Balances'),
    ('accounts', 'Accounts'),
    ('update_accounts', 'Update Accounts'),
    ('product_costs', 'Product costs'),
    ('inventory', "Inventory"),
    ('bank_account', 'Bank Account'),
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
        """Function to create or update data table"""
        Actualizacion = Pool().get('conector.actualizacion')
        actualizacion = Actualizacion.search([('name', '=', name)])

        if actualizacion:
            actualizacion, = actualizacion
        else:
            actualizacion = Actualizacion()
            actualizacion.name = name
            actualizacion.save()
        return actualizacion

    @classmethod
    def get_fecha_actualizacion(cls, actualizacion):
        """Function to get the last update diff to today"""
        date = datetime.date(1, 1, 1)
        if actualizacion.write_date:
            date = (actualizacion.write_date - datetime.timedelta(hours=6))
        elif actualizacion.create_date:
            Date = Pool().get('ir.date')
            create_date = actualizacion.create_date.date()
            if create_date != Date.today():
                date = (actualizacion.create_date -
                        datetime.timedelta(hours=6))
        return date

    def add_logs(self, logs):
        """Function to create log dictionay with message in imports"""
        to_create = []
        date_today = datetime.datetime.now()  # - datetime.timedelta(hours=5)
        if not logs:
            self.write([self], {'write_date': date_today})
            return
        for id_tecno, message in logs.items():
            create = {
                'event_time': date_today,
                'id_tecno': id_tecno,
                'message': message,
                'state': 'pending'
            }
            to_create.append(create)
        self.write([self], {'log': [('create', to_create)]})

    def getter_quantity(self, name):
        """Function to return data count to import"""
        Config = Pool().get('conector.configuration')
        connection, = Config.search([], order=[('id', 'DESC')], limit=1)
        connection_date = connection.date
        connection_date = connection_date.strftime('%Y-%m-%d %H:%M:%S')
        consult = "SET DATEFORMAT ymd SELECT COUNT(*) FROM dbo.Documentos "\
            f"WHERE fecha_hora >= CAST('{connection_date}' AS datetime)"
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
            parameter = Config.get_data_parametros('177')
            parameter_value = parameter[0].Valor.split(',')
            for tipo in parameter_value:
                consult += f"tipo = {tipo}"
                if (parameter_value.index(tipo) + 1) < len(parameter_value):
                    consult += " OR "
            consult += ")"
        else:
            return None
        result = connection.get_data(consult)
        result = int(result[0][0])
        return result

    def getter_imported(self, name):
        """Function to return data count to saved in Tryton
        that was imported by conector"""
        Config = Pool().get('conector.configuration')
        config, = Config.search([], order=[('id', 'DESC')], limit=1)
        query = "SELECT COUNT(*) FROM "
        quantity = None
        cursor = Transaction().connection.cursor()
        if self.name == 'VENTAS':
            query += f"sale_sale WHERE sale_date >= '{config.date}' "\
                "AND (id_tecno LIKE '1-%' OR id_tecno LIKE '2-%') "
            if config.end_date:
                query += f" AND sale_date < '{config.end_date}' "
            cursor.execute(query)
        elif self.name == 'COMPRAS':
            query += "purchase_purchase "\
                f"WHERE purchase_date >= '{config.date}' "\
                "AND (id_tecno LIKE '3-%' OR id_tecno LIKE '4-%') "
            if config.end_date:
                query += f" AND purchase_date < '{config.end_date}' "
            cursor.execute(query)
        elif self.name == 'COMPROBANTES DE INGRESO':
            query = "SELECT COUNT(*) FROM account_voucher "\
                    f"WHERE date >= '{config.date}' AND id_tecno LIKE '5-%' "
            if config.end_date:
                query += f" AND date < '{config.end_date}' "
            cursor.execute(query)
            quantity = int(cursor.fetchone()[0])
            query = "SELECT COUNT(*) FROM account_multirevenue "\
                    f"WHERE date >= '{config.date}' AND id_tecno LIKE '5-%' "
            if config.end_date:
                query += f" AND date < '{config.end_date}' "
            cursor.execute(query)
            quantity2 = int(cursor.fetchone()[0])
            quantity += quantity2
            return quantity
        elif self.name == 'COMPROBANTES DE EGRESO':
            query += f"account_voucher WHERE date >= '{config.date}' "\
                "AND id_tecno LIKE '6-%' "
            if config.end_date:
                query += f" AND date < '{config.end_date}' "
            cursor.execute(query)
        elif self.name == 'PRODUCCION':
            query += f"production WHERE planned_date >= '{config.date}' "\
                "AND id_tecno LIKE '12-%' "
            if config.end_date:
                query += f" AND planned_date < '{config.end_date}' "
            cursor.execute(query)
        else:
            return quantity
        result = cursor.fetchone()
        if result:
            quantity = int(result[0])
        return quantity

    def getter_exceptions(self, name):
        """Function to return SQLSERVER data that had exception"""
        Config = Pool().get('conector.configuration')
        connection, = Config.search([], order=[('id', 'DESC')], limit=1)
        connection_date = connection.date.strftime('%Y-%m-%d %H:%M:%S')
        consult = "SET DATEFORMAT ymd SELECT COUNT(*) FROM dbo.Documentos "\
            f"WHERE fecha_hora >= CAST('{connection_date}' AS datetime) "\
            "AND exportado = 'E'"
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
            parametro = Config.get_data_parametros('177')
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

    def getter_cancelled(self, name):
        """Function to return SQLSERVER data that was
        mark to no imported"""
        Config = Pool().get('conector.configuration')
        connection, = Config.search([], order=[('id', 'DESC')], limit=1)
        connection_date = connection.date.strftime('%Y-%m-%d %H:%M:%S')
        consult = "SET DATEFORMAT ymd SELECT COUNT(*) FROM dbo.Documentos "\
            f"WHERE fecha_hora >= CAST('{connection_date}' AS datetime) "\
            "AND exportado = 'X'"
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
            parametro = Config.get_data_parametros('177')
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

    def getter_not_imported(self, name):
        """Function to return SQLSERVER data to have to be import"""
        Config = Pool().get('conector.configuration')
        connection, = Config.search([], order=[('id', 'DESC')], limit=1)
        connection_date = connection.date
        connection_date = connection_date.strftime('%Y-%m-%d %H:%M:%S')
        consult = "SET DATEFORMAT ymd SELECT COUNT(*) FROM dbo.Documentos "\
            f"WHERE fecha_hora >= CAST('{connection_date}' AS datetime) "\
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
            parametro = Config.get_data_parametros('177')
            valor_parametro = parametro[0].Valor.split(',')
            for tipo in valor_parametro:
                consult += "tipo = " + str(tipo)
                if (valor_parametro.index(tipo) + 1) < len(valor_parametro):
                    consult += " OR "
            consult += ")"
        else:
            return None
        result = connection.get_data(consult)
        result = int(result[0][0])
        return result

    @classmethod
    def revisa_secuencia_imp(cls, name):
        """Function to check exist documents in Tryton and TecnoCarnes
        and to mark to be imported"""
        pool = Pool()
        Config = pool.get('conector.configuration')
        Sale = pool.get('sale.sale')
        Actualizacion = pool.get('conector.actualizacion')
        Log = pool.get('conector.log')
        cursor = Transaction().connection.cursor()
        results = None
        result_tryton = []
        condition = None
        logs = {}
        print(name)

        if name == 'VENTAS':
            consultv = "SELECT id_tecno FROM sale_sale "\
                "WHERE id_tecno is not null"
            cursor.execute(consultv)
            results = cursor.fetchall()
            condition = "(sw=1 OR sw=2)"
        if name == 'COMPRAS':
            consultv = "SELECT id_tecno FROM purchase_purchase "\
                "WHERE id_tecno is not null"
            cursor.execute(consultv)
            results = cursor.fetchall()
            condition = "(sw=3 OR sw=4)"
        if name == 'COMPROBANTES DE INGRESO':
            consult1 = "SELECT id_tecno FROM account_voucher "\
                "WHERE id_tecno LIKE '5-%'"
            cursor.execute(consult1)
            results = cursor.fetchall()
            result_tryton = [result[0] for result in results]
            consult2 = "SELECT id_tecno FROM account_multirevenue "\
                "WHERE id_tecno is not null"
            cursor.execute(consult2)
            results = cursor.fetchall()
            condition = "sw=5"
        if name == 'COMPROBANTES DE EGRESO':
            consultv = "SELECT id_tecno FROM account_voucher "\
                "WHERE id_tecno  LIKE '6-%'"
            cursor.execute(consultv)
            results = cursor.fetchall()
            condition = "sw=6"
        if name == 'PRODUCCION':
            consultv = "SELECT id_tecno FROM production "\
                "WHERE id_tecno is not null"
            cursor.execute(consultv)
            results = cursor.fetchall()
            condition = "("
            parametro = Config.get_data_parametros('177')
            valor_parametro = parametro[0].Valor.split(',')
            for tipo in valor_parametro:
                condition += "tipo=" + tipo.strip()
                if valor_parametro.index(tipo) != (len(valor_parametro) - 1):
                    condition += " OR "
            condition += ")"
        if name == 'NOTAS DE CREDITO':
            consultv = "SELECT id_tecno FROM account_invoice "\
                "WHERE id_tecno  LIKE '32-%'"
            cursor.execute(consultv)
            results = cursor.fetchall()
            condition = "sw=32"
        if name == 'NOTAS DE DEBITO':
            consultv = "SELECT id_tecno FROM account_voucher "\
                "WHERE id_tecno  LIKE '31-%'"
            cursor.execute(consultv)
            results = cursor.fetchall()
            condition = "sw=31"

        # save the results in a list
        if not result_tryton and results:
            result_tryton = [result[0] for result in results]
        elif result_tryton and results:
            for result in results:
                result_tryton.append(result[0])

        # If not data document condition, exit
        if not condition:
            return

        config, = Config.search([], order=[('id', 'DESC')], limit=1)
        connection_date = config.date.strftime('%Y-%m-%d %H:%M:%S')
        consultc = "SET DATEFORMAT ymd "\
            "SELECT CONCAT(sw,'-',tipo,'-',numero_documento), valor_total,"\
            "Valor_impuesto, Impuesto_Consumo, anulado FROM Documentos "\
            f"WHERE {condition} "\
            f"AND fecha_hora >= CAST('{connection_date}' AS datetime) "\
            "AND exportado = 'T' "\
            "AND tipo<>0 ORDER BY tipo,numero_documento"
        try:
            result_tecno = Config.get_data(consultc)
        except Exception as error:
            print(error)
            return

        if not result_tecno:
            return

        result_value = result_tecno
        result_tecno = [r[0] for r in result_tecno]

        if condition == "(sw=1 OR sw=2)":
            for value in result_value:
                id_tecno = value[0]
                invoice_amount = Decimal(value[1]).quantize(Decimal('0.00'))
                tax_ammount = Decimal(value[2]).quantize(Decimal('0.00'))
                tax_consumption = Decimal(value[3]).quantize(Decimal('0.00'))

                sale = Sale.search([("id_tecno", "=", id_tecno)])
                if sale:
                    tryton_value = sale[0].invoice_amount_tecno
                    if tryton_value != invoice_amount:
                        sale[0].invoice_amount_tecno = invoice_amount\
                            - tax_consumption
                        sale[0].tax_amount_tecno = tax_ammount
                        Sale.save(sale)

        list_difference = [r for r in result_tecno if r not in result_tryton]
        list_already_values = [r for r in result_tecno if r in result_tryton]
        list_canceled = [r[0] for r in result_value if r[4] == "S"]

        # Save the registry and mark the document to be imported
        for falt in list_difference:
            lid = falt.split('-')
            query = "UPDATE dbo.Documentos SET exportado = 'N' "\
                f"WHERE sw = {lid[0]} "\
                f"AND tipo = {lid[1]} "\
                f"AND Numero_documento = {lid[2]}"
            Config.set_data(query)
            logs[falt] = "EL DOCUMENTO ESTABA MARCADO COMO IMPORTADO "\
                "(T) SIN ESTARLO."\
                "AHORA FUE MARACADO COMO PENDIENTE PARA IMPOTAR (N)"
        """Update logs that was completed"""
        for values in list_already_values:
            id_tecno = values
            already_log = Log.search(["id_tecno", "=", id_tecno])
            if already_log:
                for log in already_log:
                    log.state = "done"
                    log.save()
        """Update logs of document that was canceled in Tecno"""
        for values in list_canceled:
            id_tecno = values
            already_log = Log.search(["id_tecno", "=", id_tecno])
            if already_log:
                for log in already_log:
                    log.state = "done"
                    log.save()

        actualizacion, = Actualizacion.search([('name', '=', name)])
        actualizacion.add_logs(logs)

    @classmethod
    def _missing_documents(cls):
        """Print to review missing documents"""
        cursor = Transaction().connection.cursor()
        cursor.execute("SELECT name FROM conector_actualizacion")
        results = cursor.fetchall()
        for r in results:
            cls.revisa_secuencia_imp(r[0])

    @classmethod
    def import_biometric_access(cls, event_time=None):
        """Function to import access of biometric"""

        """ ***Primera  entrada debe ignorarse porque es hora de ingreso
            ***Pimera  salida es entrada a trabajar
            ***Ultima entrada es salida de trabajar
            ***Ultima salida debe ignorararse porque es hora de salida
            ***Salida a descanso sin entrada se castiga,
                debe valida que no coincida con Entrada a Trabajar
            ***Es salida a descanso si hay entrada a trabajar
        """
        pool = Pool()
        Configuration = pool.get('conector.configuration')
        configuration = Configuration.get_configuration()
        Access = pool.get('staff.access')
        Rest = pool.get('staff.access.rests')
        Employee = pool.get('company.employee')
        Contract = pool.get('staff.contract')
        to_save = {}
        to_rest = {}
        start_work = None

        if not configuration:
            return
        if not event_time:
            yesterday = datetime.date.today() - datetime.timedelta(days=1)
            event_time = datetime.datetime(yesterday.year, yesterday.month,
                                           yesterday.day, 0, 0, 0)
        biometric_data = configuration.get_biometric_access_transactions(
            event_time)
        start_date = (event_time + datetime.timedelta(hours=5)).date()

        for data in biometric_data:
            if data.Nit_cedula not in to_save:
                employee = Employee.search([('party.id_number', '=',
                                             data.Nit_cedula)])

                if not employee:
                    continue
                employee, = employee
                contracts = Contract.search([
                    'OR',
                    [
                        ('employee', '=', employee.id),
                        ('start_date', '<=', start_date),
                        ('finished_date', '>=', start_date),
                    ],
                    [
                        ('employee', '=', employee.id),
                        ('start_date', '<=', start_date),
                        ('finished_date', '=', None),
                    ]
                ],
                    limit=1,
                    order=[('start_date', 'DESC')])

                if not contracts:
                    continue

                start_work = None
                to_save[data.Nit_cedula] = Access()
                to_save[data.Nit_cedula].employee = employee
                to_save[data.Nit_cedula].payment_method = 'extratime'
                to_save[data.Nit_cedula].enter_timestamp = None
                to_save[data.Nit_cedula].exit_timestamp = None
                to_rest[data.Nit_cedula] = []

            access = to_save[data.Nit_cedula]

            datetime_record = data.Fecha_Hora_Marcacion + datetime.timedelta(
                hours=5)
            if data.TipoEventoEntraoSale.upper() == 'SALIDA':
                if not access.enter_timestamp:
                    access.enter_timestamp = datetime_record
                    continue

            if data.TipoEventoEntraoSale.upper() == 'ENTRADA':
                if not start_work:
                    start_work = datetime_record
                    continue
                else:
                    access.exit_timestamp = datetime_record
            rests = to_rest[data.Nit_cedula]

            if data.TipoEventoEntraoSale.upper() == 'ENTRADA':
                rest = Rest()
                rest.start = datetime_record
                rest.end = None
                continue

            if data.TipoEventoEntraoSale.upper() == 'SALIDA':
                if not access.enter_timestamp:
                    continue
                if 'rest' not in locals():
                    rest = Rest()
                    rest.start = datetime_record - datetime.timedelta(
                        minutes=45)
                    rest.end = datetime_record
                    rests.append(rest)
                    continue
                if not rest.start:
                    rest = Rest()
                    rest.end = datetime_record
                    rests.append(rest)
                    continue
                else:
                    if not rest.end:
                        rest.end = datetime_record
                        rests.append(rest)
                    continue
        # Search records of the same day
        tomorrow = event_time + datetime.timedelta(days=1)
        access_search = list(
            Access.search([('enter_timestamp', '>=', event_time),
                           ('enter_timestamp', '<', tomorrow)]))

        for nit_cedula, acess in to_save.items():
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
            if acess.exit_timestamp\
                    and acess.enter_timestamp >= acess.exit_timestamp:
                continue
            if to_rest[nit_cedula]:
                to_rest[nit_cedula].pop()
                for rest in to_rest[nit_cedula]:
                    rest.access = acess
                    if rest.start >= rest.end:
                        rest.start = rest.end - datetime.timedelta(minutes=45)

                        # Validate if start is datetime type
                    if isinstance(rest.start, datetime.datetime):
                        start_time = rest.start
                    else:
                        start_time = datetime.datetime.strptime(
                            rest.start, "%Y-%m-%d %H:%M:%S")

                    # Validate if end is datetime type
                    if isinstance(rest.end, datetime.datetime):
                        end_time = rest.end
                    else:
                        end_time = datetime.datetime.strptime(
                            rest.end, "%Y-%m-%d %H:%M:%S")

                    # get difference in minutes
                    difference = end_time - start_time
                    difference_minutes = difference.total_seconds() / 60

                    if difference_minutes <= 5:
                        rest.pay = True

                Rest.save(to_rest[nit_cedula])
                acess.rests = to_rest[nit_cedula]
            acess.on_change_rests()
            acess.save()

    @classmethod
    def update_exception_documents(cls):
        """Function to check exist documents in Tryton and TecnoCarnes
        and to mark to be imported"""
        pool = Pool()
        Config = pool.get('conector.configuration')

        config, = Config.search([], order=[('id', 'DESC')], limit=1)
        connection_date = config.date.strftime('%Y-%m-%d %H:%M:%S')
        query = f"""
        SET DATEFORMAT ymd
        UPDATE Documentos
        SET exportado = 'N'
        WHERE fecha_hora >= CAST('{connection_date}' AS datetime)
        AND exportado = 'E';
        """

        try:
            Config.set_data(query)
        except Exception as error:
            print(error)
            return


class Email(ModelSQL, ModelView):
    'Email configuration'
    __name__ = 'conector.email'

    uri = fields.Char('Uri', required=True)
    from_to = fields.Char('From to', required=True)

    @classmethod
    def default_uri(cls):
        return 'smtps://notificaciones@cdstecno.com:98642443.Asd@mail.cdstecno.com:465'

    @classmethod
    def default_from_to(cls):
        return 'Notificaciones TecnoCarnes-Tryton <notificaciones@cdstecno.com>'


class ImportedDocument(ModelView):
    'Imported Document View'
    __name__ = 'conector.actualizacion.imported_document'

    file = fields.Binary('File', help="Enter the file to import with (;)")
    type_file = fields.Selection(TYPES_FILE, 'Type file')


class ImportedDocumentWizard(Wizard):
    'Imported Document Wizard'
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
        if process == 'encode':
            file_decod = file.encode()
        else:
            file_decod = file.decode()
        return file_decod

    def transition_importfile(self):
        config = self.start
        Warning = Pool().get('res.user.warning')
        warning_name = 'warning_import_conector'
        if Warning.check(warning_name):
            raise UserWarning(warning_name,
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
        """Function to import csv parties"""
        pool = Pool()
        Party = pool.get('party.party')
        City = pool.get('party.city_code')
        Department = pool.get('party.department_code')
        Country = pool.get('party.country_code')
        firts = True
        for linea in lineas:
            linea = linea.strip()
            if not linea:
                continue

            linea = linea.split(';')
            if len(linea) != 13:
                raise UserError(
                    'Error de plantilla',
                    'type_document | id_number | name | address/party_name | '
                    'address/name | address/street | address/country_code | '
                    'address/department_code | address/city_code |'
                    'address/phone | address/email | '
                    'regime_tax | type_person')

            if firts:
                firts = False
                continue

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
                ('code', '=', department_code),
            ])
            city_code = linea[8].strip()
            city = City.search([
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
            Party.create([to_save])
            print(contacts)
            Transaction().connection.commit()

    @classmethod
    def import_csv_products(cls, lineas):
        """Function to import csv products"""
        pool = Pool()
        Product = pool.get('product.template')
        Category = pool.get('product.category')
        Uom = pool.get('product.uom')
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
                        'code | name | list_price | sale_price_w_tax |'
                        'account_category | name_uom | salable | '
                        'purchasable | producible | consumable | '
                        'type | depreciable | cost_price')
                if first:
                    first = False
                    continue

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
                account_category = Category.search([('name', '=',
                                                     name_category)])
                if not account_category:
                    print(name_category)
                    raise UserError(
                        "Error Categoria Producto",
                        f"No se encontro la categoria: {name_category}")
                account_category, = account_category
                prod['account_category'] = account_category.id
                name_uom = linea[5].strip()
                uom = Uom.search([('name', '=', name_uom)])
                if not uom:
                    print(name_uom)
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
        Product.create(products)

    @classmethod
    def import_csv_balances(cls, lineas):
        """Function to import opening balances"""
        pool = Pool()
        Account = pool.get('account.account')
        Journal = pool.get('account.journal')
        Period = pool.get('account.period')
        Move = pool.get('account.move')
        Line = pool.get('account.move.line')
        Party = pool.get('party.party')
        partiesd = {}
        vlist = []
        not_party = []
        first = True
        cont = 0

        parties = Party.search([()])
        for party in parties:
            partiesd[party.id_number] = party.id

        accounts = Account.search([()])
        accountsd = {}
        for account in accounts:
            accountsd[account.code] = {
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
                    'libro diario | periodo | fecha efectiva | descripcion | '
                    'linea/cuenta | linea/debito | linea/credito | '
                    'linea/tercero | linea/descripcion | '
                    'linea/fecha vencimiento | linea/referencia')

            if first:
                first = False
                continue

            if cont == 0:
                name_journal = linea[0].strip()
                name_period = linea[1].strip()
                efective_date = cls.convert_str_date(linea[2])
                description_move = linea[3].strip()
                journal = Journal.search([('name', '=', name_journal)])

                if not journal:
                    raise UserError(
                        'Error diario',
                        f'No se encontró el diario {name_journal}')

                journal, = journal
                period = Period.search([('name', '=', name_period)])
                if not period:
                    raise UserError('Error periodo',
                                    f'No se encontró el diario {name_period}')

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
                if party_line not in partiesd.keys():
                    if party_line not in not_party:
                        not_party.append(party_line)
                    continue
                line['party'] = partiesd[party_line]

            vlist.append(line)
            if len(vlist) > 1000:
                Line.create(vlist)
                vlist.clear()

        if not_party:
            raise UserError("Falta terceros", f"{not_party}")

        if vlist:
            Line.create(vlist)

    @classmethod
    def import_csv_accounts(cls, lineas):
        """Function to review and import new accounts"""
        pool = Pool()
        Account = pool.get('account.account')
        Type = pool.get('account.account.type')
        not_account = []
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
                    raise UserError(
                        'Importación de archivo: ',
                        f'Error en la búsqueda del tipo de cuenta "\
                        "de la cuenta {code} - {name}')
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
            raise UserError('Importación de archivo: ',
                            f'Error: Faltan las cuentas padres {not_account}')

    @classmethod
    def update_csv_accounts(cls, lineas):
        """Function to update PUC accounts"""
        pool = Pool()
        Account = pool.get('account.account')
        Type = pool.get('account.account.type')
        dict_account = {}
        item = []
        firts = True
        columns = ['account', 'name', 'type', 'reconcile', 'party_required']

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
                dict_account = dict(zip(columns, item))

            if not item:
                continue

            code = dict_account['account']
            account = Account.search([('code', '=', code)])
            if not account:
                continue

            account, = account
            name = dict_account['name'].upper()
            if name:
                account.name = name

            reconcile = dict_account['reconcile'].upper()
            if reconcile:
                if reconcile == 'TRUE':
                    account.reconcile = True
                if reconcile == 'FALSE':
                    account.reconcile = False

            party_required = dict_account['party_required'].upper()
            if party_required:
                if party_required == 'TRUE':
                    account.party_required = True
                if party_required == 'FALSE':
                    account.party_required = False

            type = dict_account['type']
            if type:
                type = Type.search([('sequence', '=', type)])
                if not type:
                    raise UserError(
                        'Importación de archivo: ',
                        'Error en la búsqueda del tipo de cuenta,'
                        f'para la cuenta {code} - {name}')
                type, = type
                account.type = type

            if account.type and type == '':
                account.type = None

            Account.save([account])

    @classmethod
    def get_parent_account(cls, code):
        """Function to return parent account"""
        if len(code) < 2:
            return
        elif len(code) == 2:
            return code[0]
        elif len(code) > 2:
            if (len(code) % 2) != 0:
                raise UserError('Importación de archivo: ',
                                f'Error de código {code}')
            return code[:-2]

    @classmethod
    def convert_str_date(cls, date):
        """Function to convert string data to datetime data"""
        try:
            results = date.strip().split()[0].split('-')
            results = datetime.date(int(results[0]), int(results[1]),
                                    int(results[2]))
        except Exception as error:
            raise UserError(
                f"Error fecha {date}",
                "Recuerde que la fecha debe estar con el "
                "siguiente formato YY-MM-DD"
                f"{error}")
        return results

    @classmethod
    def get_boolean(cls, val):
        """Function to return boolean"""
        if int(val) == 0:
            return False
        if int(val) == 1:
            return True

    @classmethod
    def import_csv_product_costs(cls, lineas):
        """Function to update product costs"""
        pool = Pool()
        Product = pool.get('product.product')
        Revision = pool.get('product.cost_price.revision')
        AverageCost = Pool().get('product.average_cost')
        company = Transaction().context.get('company')
        StockPeriod = Pool().get('stock.period')

        revisions = []
        to_create = []
        products = []
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

            date = cls.convert_str_date(linea[2])
            date_period = StockPeriod.search(
                [('date', '=', date), ('state', '!=', 'closed')])
            if not date_period:
                raise UserError(
                    'ERROR', 'No se encontro un periodo abierto para '
                    'la fecha, la fecha debe coincidir con la fecha de '
                    'cierre del periodo')

            code_product = linea[0]
            product = Product.search([('template', '=', code_product)])
            if not product:
                raise UserError(
                    "ERROR PRODUCTO",
                    f"No se encontro el producto con código {code_product}")

            product, = product
            cost = linea[1]
            if not cost or cost == 0:
                raise UserError(
                    "ERROR COSTO",
                    f"No se encontro el costo para el producto {code_product}")

            revision = {
                "company": company,
                "product": product.id,
                "template": product.template.id,
                "cost_price": cost,
                "date": date,
            }
            revisions.append(revision)

            average_cost = {
                "product": product.id,
                "effective_date": date,
                "cost_price": cost,
            }
            to_create.append(average_cost)
            products.append(product)

        records = Revision.create(revisions)
        AverageCost.create(to_create)

        if records:
            Product.recompute_cost_price(products, start=datetime.date.today())

    @classmethod
    def import_csv_inventory(cls, lineas):
        """Function to load the inventory"""
        pool = Pool()
        Inventory = pool.get('stock.inventory')
        Line = pool.get('stock.inventory.line')
        Location = pool.get('stock.location')
        Product = pool.get('product.product')
        ProductTemplate = pool.get('product.template')
        Analytic_Account = pool.get('analytic_account.account')

        inventory = Inventory()
        to_lines = []
        first = True

        for linea in lineas:
            linea = linea.strip()
            if not linea:
                continue

            linea = linea.split(';')
            if len(linea) != 5:
                raise UserError(
                    'Error plantilla',
                    ' location | date | product | quantity | Analytic account')

            if first:
                location, = Location.search([('name', '=', linea[0].strip())])
                inventory.location = location
                date = cls.convert_str_date(linea[1])
                inventory.date = date
                inventory.analitic_account, = Analytic_Account.search([
                    ('code', '=', linea[4])
                ])
                first = False

            line = Line()
            code_product = linea[2]
            template = ProductTemplate.search([('code', '=', code_product)])
            if not template:
                raise UserError(
                    "ERROR PRODUCTO",
                    f"No se encontro el producto con código {code_product}")

            product = Product.search([('template', '=', template[0])])
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
        """Function to load bank accounts"""
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
                raise UserError('Error plantilla',
                                'id_bank | account | parties | number | type')

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
            domain = [('bank', '=', bank), ('account', '=', account.id)]
            if bparty:
                domain.append(('owners', 'in', bparty))

            exist = BankAccount.search(domain)
            if exist and bparty:
                continue

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
        return 'pending'
