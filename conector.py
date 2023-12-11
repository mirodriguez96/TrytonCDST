import math
from trytond.model import ModelSQL, ModelView, fields
from trytond.transaction import Transaction
from trytond.pool import Pool
from trytond.exceptions import UserError
# from conexion import Conexion
from trytond.wizard import Wizard, StateTransition, StateView, Button
# from sql import Table
from decimal import Decimal
import datetime
from sql import Table
from trytond.exceptions import UserError, UserWarning


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
    exceptions = fields.Function(fields.Integer('Exceptions'), 'getter_exceptions')
    cancelled = fields.Function(fields.Integer('Cancelled'), 'getter_cancelled')
    not_imported = fields.Function(fields.Integer('Not imported'), 'getter_not_imported')
    logs = fields.Text("Logs", readonly=True)
    log = fields.One2Many('conector.log', 'actualizacion', 'Log')


    #Crea o actualiza un registro de la tabla actualización en caso de ser necesario
    @classmethod
    def create_or_update(cls, name):
        Actualizacion = Pool().get('conector.actualizacion')
        actualizacion = Actualizacion.search([('name', '=', name)])
        if actualizacion:
            #Se busca un registro con la actualización
            actualizacion, = actualizacion
        else:
            #Se crea un registro con la actualización
            actualizacion = Actualizacion()
            actualizacion.name = name
            actualizacion.save()
        return actualizacion


    # se obtiene la fecha de la ultima actualizacion (modificacion) de un registro del modelo conector.actualizacion
    # pero la fecha del registro debe ser diferente a la del dia de hoy
    @classmethod
    def get_fecha_actualizacion(cls, actualizacion):
        fecha = datetime.date(1,1,1)
        if actualizacion.write_date:
            fecha = (actualizacion.write_date - datetime.timedelta(hours=6))
        elif actualizacion.create_date:
            Date = Pool().get('ir.date')
            create_date = actualizacion.create_date.date()
            if create_date != Date.today():
                fecha = (actualizacion.create_date - datetime.timedelta(hours=6))
        return fecha

    # Se recibe un dicionario con los mensajes arrojados en la importacion
    def add_logs(self, logs):
        now = datetime.datetime.now()# - datetime.timedelta(hours=5)
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

    
    # Se consulta en la base de datos de SQLSERVER por la cantidad de documentos
    # que se van a importar
    def getter_quantity(self, name):
        Config = Pool().get('conector.configuration')
        conexion, = Config.search([], order=[('id', 'DESC')], limit=1)
        fecha = conexion.date
        fecha = fecha.strftime('%Y-%m-%d %H:%M:%S')
        consult = "SET DATEFORMAT ymd SELECT COUNT(*) FROM dbo.Documentos "\
            f"WHERE fecha_hora >= CAST('{fecha}' AS datetime)"
        if conexion.end_date:
            end_date = conexion.end_date.strftime('%Y-%m-%d %H:%M:%S')
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
                if (valor_parametro.index(tipo)+1) < len(valor_parametro):
                    consult += " OR "
            consult += ")"
        # elif self.name == "TERCEROS":

        #     consult = "select tt.nit_cedula  \
        #                 from TblTerceros tt" 
        else:
            return None
        result = conexion.get_data(consult)
        result = int(result[0][0])
        return result
        
    # Se consulta la cantidad de documentos (registros) que hay almacenados en Tryton
    # que han sido importados por el modulo conector
    def getter_imported(self, name):
        Config = Pool().get('conector.configuration')
        config, = Config.search([], order=[('id', 'DESC')], limit=1)
        # fecha = config.date
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
            query += f"purchase_purchase WHERE purchase_date >= '{config.date}' "\
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

    # Se consulta en la base de datos de SQLSERVER los documentos marcados como excepcion
    def getter_exceptions(self, name):
        Config = Pool().get('conector.configuration')
        conexion, = Config.search([], order=[('id', 'DESC')], limit=1)
        fecha = conexion.date.strftime('%Y-%m-%d %H:%M:%S')
        consult = "SET DATEFORMAT ymd SELECT COUNT(*) FROM dbo.Documentos "\
            f"WHERE fecha_hora >= CAST('{fecha}' AS datetime) AND exportado = 'E'"
        if conexion.end_date:
            end_date = conexion.end_date.strftime('%Y-%m-%d %H:%M:%S')
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
                if (valor_parametro.index(tipo)+1) < len(valor_parametro):
                    consult += " OR "
            consult += ")"
        else:
            return None
        result = conexion.get_data(consult)
        result = int(result[0][0])
        return result

    # Se consulta en la base de datos de SQLSERVER los documentos marcados como no a importar por el modulo conector
    def getter_cancelled(self, name):
        Config = Pool().get('conector.configuration')
        conexion, = Config.search([], order=[('id', 'DESC')], limit=1)
        fecha = conexion.date.strftime('%Y-%m-%d %H:%M:%S')
        consult = "SET DATEFORMAT ymd SELECT COUNT(*) FROM dbo.Documentos "\
            f"WHERE fecha_hora >= CAST('{fecha}' AS datetime) AND exportado = 'X'"
        if conexion.end_date:
            end_date = conexion.end_date.strftime('%Y-%m-%d %H:%M:%S')
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
                if (valor_parametro.index(tipo)+1) < len(valor_parametro):
                    consult += " OR "
            consult += ")"
        else:
            return None
        result = conexion.get_data(consult)
        result = int(result[0][0])
        return result

    # Se consulta en la base de datos de SQLSERVER los documentos que faltan por ser importados
    def getter_not_imported(self, name):
        Config = Pool().get('conector.configuration')
        conexion, = Config.search([], order=[('id', 'DESC')], limit=1)
        fecha = conexion.date
        fecha = fecha.strftime('%Y-%m-%d %H:%M:%S')
        consult = "SET DATEFORMAT ymd SELECT COUNT(*) FROM dbo.Documentos "\
            f"WHERE fecha_hora >= CAST('{fecha}' AS datetime) "\
            "AND exportado != 'T' AND exportado != 'E' AND exportado != 'X'"
        if conexion.end_date:
            end_date = conexion.end_date.strftime('%Y-%m-%d %H:%M:%S')
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
                consult += "tipo = "+str(tipo)
                if (valor_parametro.index(tipo)+1) < len(valor_parametro):
                    consult += " OR "
            consult += ")"
        else:
            return None
        result = conexion.get_data(consult)
        result = int(result[0][0])
        return result

    # Se revisa los documentos existentes en Tryton vs SqlServer (TecnoCarnes) para marcarlos como pendientes por importar.
    # Se solicita el nombre de la tabla en tryton (table), la lista de sw según el documento y el nombre de la actualizacion
    @classmethod
    def revisa_secuencia_imp(cls, name):
        pool = Pool()
        Config = pool.get('conector.configuration')
        Actualizacion = pool.get('conector.actualizacion')
        cursor = Transaction().connection.cursor()
        # Se procede primero a buscar los documentos importados en Tryton
        result = None
        result_tryton = []
        cond = None
        if name == 'VENTAS':
            consultv = "SELECT id_tecno FROM sale_sale WHERE id_tecno is not null"
            cursor.execute(consultv)
            result = cursor.fetchall()
            cond = "(sw=1 OR sw=2)"
        if name == 'COMPRAS':
            consultv = "SELECT id_tecno FROM purchase_purchase WHERE id_tecno is not null"
            cursor.execute(consultv)
            result = cursor.fetchall()
            cond = "(sw=3 OR sw=4)"
        if name == 'COMPROBANTES DE INGRESO':
            consult1 = "SELECT id_tecno FROM account_voucher WHERE id_tecno LIKE '5-%'"
            cursor.execute(consult1)
            result = cursor.fetchall()
            result_tryton = [r[0] for r in result]
            consult2 = "SELECT id_tecno FROM account_multirevenue WHERE id_tecno is not null"
            cursor.execute(consult2)
            result = cursor.fetchall()
            cond = "sw=5"
        if name == 'COMPROBANTES DE EGRESO':
            consultv = "SELECT id_tecno FROM account_voucher WHERE id_tecno  LIKE '6-%'"
            cursor.execute(consultv)
            result = cursor.fetchall()
            cond = "sw=6"
        if name == 'PRODUCCION':
            consultv = "SELECT id_tecno FROM production WHERE id_tecno is not null"
            cursor.execute(consultv)
            result = cursor.fetchall()
            cond = "("
            parametro = Config.get_data_parametros('177')
            valor_parametro = parametro[0].Valor.split(',')
            for tipo in valor_parametro:
                cond += "tipo="+tipo.strip()
                if valor_parametro.index(tipo) != (len(valor_parametro)-1):
                    cond += " OR "
            cond += ")"
        if name == 'NOTAS DE CREDITO':
            consultv = "SELECT id_tecno FROM account_invoice WHERE id_tecno  LIKE '32-%'"
            cursor.execute(consultv)
            result = cursor.fetchall()
            cond = "sw=32"
        if name == 'NOTAS DE DEBITO':
            consultv = "SELECT id_tecno FROM account_voucher WHERE id_tecno  LIKE '31-%'"
            cursor.execute(consultv)
            result = cursor.fetchall()
            cond = "sw=31"
        # Se almacena el resultado de la busqueda en una lista
        if not result_tryton and result:
            result_tryton = [r[0] for r in result]
        elif result_tryton and result:
            for r in result:
                result_tryton.append(r[0])
        # Si no entró a ningún documento no hace nada
        if not cond:
            return
        config, = Config.search([], order=[('id', 'DESC')], limit=1)
        fecha = config.date.strftime('%Y-%m-%d %H:%M:%S')
        consultc = "SET DATEFORMAT ymd SELECT CONCAT(sw,'-',tipo,'-',numero_documento) FROM Documentos "\
            f"WHERE {cond} AND fecha_hora >= CAST('{fecha}' AS datetime) "\
            "AND exportado = 'T' AND tipo<>0 ORDER BY tipo,numero_documento"
        result_tecno = Config.get_data(consultc)
        result_tecno = [r[0] for r in result_tecno]
        list_difference = [r for r in result_tecno if r not in result_tryton]
        # Se guarda el registro y se marcan los documentos para ser importados de nuevo
        logs = {}
        for falt in list_difference:
            lid = falt.split('-')
            query = "UPDATE dbo.Documentos SET exportado = 'N' "\
                f"WHERE sw = {lid[0]} AND tipo = {lid[1]} AND Numero_documento = {lid[2]}"
            Config.set_data(query)
            logs[falt] = "EL DOCUMENTO ESTABA MARCADO COMO IMPORTADO (T) SIN ESTARLO. "\
                "AHORA FUE MARACADO COMO PENDIENTE PARA IMPOTAR (N)"
        actualizacion, = Actualizacion.search([('name', '=', name)])
        actualizacion.add_logs(logs)


    @classmethod
    def _missing_documents(cls):
        print("RUN missing documents")
        cursor = Transaction().connection.cursor()
        cursor.execute("SELECT name FROM conector_actualizacion")
        result = cursor.fetchall()
        for r in result:
            cls.revisa_secuencia_imp(r[0])
        print("FINISH missing documents")


    # Biometric access
    @classmethod
    def import_biometric_access(cls, event_time=None):
        print("RUN import_biometric_access")
        pool = Pool()
        Configuration = pool.get('conector.configuration')
        configuration = Configuration.get_configuration()
        if not configuration:
            return
        if not event_time:
            yesterday = datetime.date.today() - datetime.timedelta(days=1)
            event_time = datetime.datetime(yesterday.year, yesterday.month, yesterday.day, 0, 0, 0)
        data = configuration.get_biometric_access_transactions(event_time)
        Access = pool.get('staff.access')
        Rest = pool.get('staff.access.rests')
        Employee = pool.get('company.employee')
        to_save = {}
        to_rest = {}
        start_work = None
        for d in data:
            if d.Nit_cedula not in to_save:
                employee = Employee.search([('party.id_number', '=', d.Nit_cedula)])
                if not employee:
                    continue
                    # raise UserError(f'Could not find employee with id_number = {d.Nit_cedula}')
                employee, = employee
                start_work = None
                to_save[d.Nit_cedula] = Access()
                to_save[d.Nit_cedula].employee = employee
                to_save[d.Nit_cedula].payment_method = 'extratime'
                to_save[d.Nit_cedula].enter_timestamp = None
                to_save[d.Nit_cedula].exit_timestamp = None
                to_rest[d.Nit_cedula] = []
                # rest = Rest()
                # rest.start = None
                # rest.end = None
            access = to_save[d.Nit_cedula]

            #Primera  entrada debe ignorarse porque es hora de ingreso a las instalaciones 	ok
            #Pimera  salida es entrada a trabajar						ok
            #Ultima entrada es salida de trabajar						
            #Ultima salida debe ignorararse porque es hora de salida de las instalaciones
            #Salida a descanso sin entrada se castiga con entrada= fecha-45, debe valida que no coincida con Entrada a Trabajar
            #Es salida a descanso si hay entrada a trabajar 

            #entro 7 'debe ignorarse  ok
            #salio 710 'en access.enter_timestamp ok
            #entro 10 'rest.start ok
            #salio 1030'  rest.end ok
            #entro 6 ' access.exit_timestamp ok
            #salio 610'debe ignorarse

            datetime_record = d.Fecha_Hora_Marcacion + datetime.timedelta(hours=5)
            if d.TipoEventoEntraoSale.upper() == 'SALIDA':
                if not access.enter_timestamp:
                    access.enter_timestamp = datetime_record # 'Primera Salida es Entrada a Trabajar 
                    continue

            if d.TipoEventoEntraoSale.upper() == 'ENTRADA':
                if not start_work: # 'Primera entrada se Ignora, Es ingreso a instalaciones
                    start_work = datetime_record
                    continue 
                else:
                    access.exit_timestamp = datetime_record # 'ultima entrada 
            
            rests = to_rest[d.Nit_cedula]

            if d.TipoEventoEntraoSale.upper() == 'ENTRADA':
                rest = Rest()
                rest.start = datetime_record #inicio descanso
                rest.end = None
                # rests.append(rest)
                continue

            if d.TipoEventoEntraoSale.upper() == 'SALIDA':
                if not access.enter_timestamp:
                   continue
                if not 'rest' in locals():
                    # Si se registra una salida sin una entrada previa, se castiga
                    rest = Rest()
                    rest.start = datetime_record - datetime.timedelta(minutes=45)
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
        # Se busca los registros del mismo día
        tomorrow = event_time + datetime.timedelta(days=1)
        access_search = list(Access.search([
            ('enter_timestamp', '>=', event_time),
            ('enter_timestamp', '<', tomorrow)
            ]))
        # to_create = []
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
                Rest.save(to_rest[nit])
                acess.rests = to_rest[nit]
            # to_create.append(acess)
            acess.on_change_rests()
            acess.save()
        # Access.save(to_create)



    # Biometric access
    @classmethod
    def biometric_access_dom(cls):
        print("RUN biometric_access_dom")
        pool = Pool()
        Config = pool.get('ir.cron')
        Access = pool.get('staff.access')
        Employee = pool.get('company.employee')
        access_table = Table('staff_access')
        cursor = Transaction().connection.cursor()
        time, = Config.search([('access_register', '=', True)])
        
        date = [int(i) for i in str(datetime.date.today()).split('-')]

        time_enter = [int(i) for i in str(time.enter_timestamp).split(':')]

        time_exit = [int(i) for i in str(time.exit_timestamp).split(':')]


        enter = datetime.datetime(*date,*time_enter)
        exit = datetime.datetime(*date,*time_exit)

        employees = Employee.search([('active', '=', 'active'),
                                    ('contracting_state', '=', 'active'),])

        for employee in employees:
            if enter and exit:
                    is_access = Access.search([
                        ('enter_timestamp', '<=', enter + datetime.timedelta(hours=5)),
                        ('exit_timestamp', '>=', exit + datetime.timedelta(hours=5)),
                        ('employee', '=', employee)])

                    if not is_access:
                        to_save = Access()
                        to_save.employee = employee
                        to_save.payment_method = 'extratime'
                        to_save.enter_timestamp = enter + datetime.timedelta(hours=5)
                        to_save.exit_timestamp = exit + datetime.timedelta(hours=5)
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
                        values=[Decimal(7.83),0,0,0,0,0,0,0],
                        where=access_table.id.in_([to_save.id]))
                    )
                        
    # Biometric access
    @classmethod
    def holidays_access_fes(cls):
        print("RUN holidays_access_fes")        
        Holiday = Pool().get('staff.holidays')
        validate = datetime.date.today() + datetime.timedelta(hours=5)
        holidays = Holiday.search([
            ('holiday', '=', validate)])

        if holidays:
            cls.biometric_access_dom()


# Vista para mportancion de documentos tryton 
class ImportedDocument(ModelView):

    'Imported Document'
    __name__ = 'conector.actualizacion.imported_document'

    file = fields.Binary('File', help="Enter the file to import with (;)")
    type_file = fields.Selection(TYPES_FILE, 'Type file')

# Asistente para mportancion de documentos tryton 
class ImportedDocumentWizard(Wizard):

    __name__ = 'conector.actualizacion.imported_document_asistend'

    start = StateView('conector.actualizacion.imported_document',
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
            raise UserWarning(warning_name, "Se procede a importar el archivo cargado.")
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
                raise UserError('Importar archivo: ', 'Seleccione el tipo de importación')
        else:
            raise UserError('Importación de archivo: ', 'Agregue un archivo para importar')
                
        return 'end'

#     imported = fields.Function(fields.Integer('Imported'), 'getter_imported')


    @classmethod
    def import_csv_parties(cls, lineas):
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
                raise UserError('Error de plantilla',
                'type_document | id_number | name | address/party_name | address/name | address/street | address/country_code | address/department_code | address/city_code | address/phone | address/email | regime_tax | type_person')
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
            print(contacts)
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
        first = True
        for linea in lineas:
            linea = linea.strip()
            if linea:
                linea = linea.split(';')
                if len(linea) != 13:
                    raise UserError('Error de plantilla', 'code | name | list_price | sale_price_w_tax | account_category | name_uom | salable | purchasable | producible | consumable | type | depreciable | cost_price')
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
        first = True
        for linea in lineas:
            print(linea)
            linea = linea.strip()
            if not linea:
                continue
            linea = linea.split(';')
            if len(linea) != 11:
                raise UserError('Error de plantilla',
                'libro diario | periodo | fecha efectiva | descripcion | linea/cuenta | linea/debito | linea/credito | linea/tercero | linea/descripcion | linea/fecha vencimiento | linea/referencia')
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
        firts = True
        for linea in lineas:
            linea = linea.strip()
            if not linea:
                continue            
            linea = linea.split(';')
            if linea[0] == 'code':
                continue
            if len(linea) != 5:
                raise UserError('Error plantilla', 'account | name | type | reconcile | party_required')
            if firts:
                firts = False
                continue
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
        firts = True
        item = []

        columns = [
            'account','name','type','reconcile','party_required'
        ]
        
        for linea in lineas:

            if firts:
                firts = False
                continue

            linea = linea.strip()

            item = [i  for i in linea.split(';')]
            
            if item == ['']:
                continue

            if len(item) != 5:
                raise UserError('Error plantilla', 'account | name | type | reconcile | party_required')
            

            
            
            if not firts:
                dicAccount = {}
                dicAccount = dict(zip(columns, item))

            if not item:
                continue            


            # Se consulta y procesa la cuenta
            code = dicAccount['account']

            account = Account.search([('code', '=', code)])
            print(account)
            if not account:
                continue
            account, = account
            name = dicAccount['name'].upper()
            if name:
                account.name = name
            reconcile = dicAccount['reconcile'].upper()
            if reconcile:
                if reconcile == 'TRUE':
                    account.reconcile = True
                if reconcile == 'FALSE':
                    account.reconcile = False
            party_required = dicAccount['party_required'].upper()
            if party_required:
                if party_required == 'TRUE':
                    account.party_required = True
                if party_required == 'FALSE':
                    account.party_required = False
            type = dicAccount['type']

            if type:
                type = Type.search([('sequence', '=', type)])
                if not type:
                    raise UserError('Importación de archivo: ', f'Error en la búsqueda del tipo de cuenta, para la cuenta {code} - {name}')
                type, = type
                account.type = type

            if account.type and type == '':
                account.type = None

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
        Revision = pool.get('product.cost_price.revision')
        AverageCost = Pool().get('product.average_cost')
        company = Transaction().context.get('company')
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
                raise UserError('Error plantilla', ' code_product | cost | date ')
            if firts:
                firts = False
                continue
            code_product = linea[0]
            product = Product.search([('template', '=', code_product)])
            if not product:
                raise UserError("ERROR PRODUCTO", f"No se encontro el producto con código {code_product}")
            product, = product
            cost = linea[1]
            if not cost or cost == 0:
                raise UserError("ERROR COSTO", f"No se encontro el costo para el producto con código {code_product}")
            date = cls.convert_str_date(linea[2])
            # Revision
            revision = {
                "company": company,
                "product": product.id,
                "template": product.template.id,
                "cost_price": cost,
                "date": date,
            }
            revisions.append(revision)
            # Se procede a crear el AverageCost
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
                # start = min((r.date for r in products), default=None)
            Product.recompute_cost_price(products, start=datetime.date.today())

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
                raise UserError('Error plantilla', 'id_bank | account | parties | number | type')
            # Se verifica que es la primera linea (encabezado) para omitirla
            if first:
                first = False
                continue
            bank = linea[0].strip()
            print (bank)
            bank = Bank(int(bank))
            account = linea[1].strip()
            account, = Account.search([('code', '=', account)])
            print(account.id)
            party = linea[2].strip()
            party, = Party.search([('id_number', '=', party)])
            number = linea[3].strip()
            type = linea[4].strip()
            bparty = BankAccountParty.search([('owner', '=', party)])
            print(bparty)
            domain = [
                ('bank', '=', bank),
                ('account', '=', account.id)
            ]
            if bparty:
                domain.append(('owners', 'in', bparty))
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

    
class ConectorLog(ModelSQL, ModelView):
    'Conector Log'
    __name__ = 'conector.log'

    actualizacion = fields.Many2One('conector.actualizacion', 'log', 'Actualizacion', required=True)
    event_time = fields.DateTime('Event time', required=True)
    id_tecno = fields.Char('Id TecnoCarnes', help='For documents sw-tipo-numero', required=True)
    message = fields.Char('Message', required=True)
    state = fields.Selection(STATE_LOG, 'State', required=True)

    @staticmethod
    def default_state():
        return 'pending'