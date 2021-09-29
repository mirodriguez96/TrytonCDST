from trytond.model import ModelView, ModelSQL, fields
from trytond.pool import Pool, PoolMeta
from trytond.exceptions import UserError
from trytond.transaction import Transaction
from decimal import Decimal

import datetime


__all__ = [
    'Voucher',
    'Cron',
    'VoucherPayMode',
    ]


class Cron(metaclass=PoolMeta):
    'Cron'
    __name__ = 'ir.cron'

    @classmethod
    def __setup__(cls):
        super().__setup__()
        cls.method.selection.append(
            ('account.voucher|import_voucher', "Update vouchers"),
            )


#Heredamos del modelo sale.sale para agregar el campo id_tecno
class Voucher(ModelSQL, ModelView):
    'Voucher'
    __name__ = 'account.voucher'
    id_tecno = fields.Char('Id Tabla Sqlserver', required=False)

    @classmethod
    def import_voucher(cls):
        print("--------------RUN VOUCHER--------------")
        documentos_db = cls.last_update()
        cls.create_or_update()
        if documentos_db:
            cls.update_paymode()
            columns_doc = cls.get_columns_db('Documentos')
            columns_rec = cls.get_columns_db('Documentos_Cruce')
            columns_tip = cls.get_columns_db('Documentos_Che')
            pool = Pool()
            Account = pool.get('account.account')
            Invoice = pool.get('account.invoice')
            Voucher = pool.get('account.voucher')
            Line = pool.get('account.voucher.line')
            MoveLine = pool.get('account.move.line')
            Party = pool.get('party.party')
            PayMode = pool.get('account.voucher.paymode')
            Tax = pool.get('account.tax')
            for doc in documentos_db:
                sw = str(doc[columns_doc.index('sw')])
                tipo = doc[columns_doc.index('tipo')].strip()
                nro = str(doc[columns_doc.index('Numero_documento')])
                existe = cls.find_voucher(sw+'-'+tipo+'-'+nro)
                if not existe:
                    nit_cedula = doc[columns_doc.index('nit_Cedula')].strip()
                    tercero, = Party.search([('id_number', '=', nit_cedula)])
                    recibos = cls.get_recibos(tipo, nro)
                    if recibos:
                        voucher = Voucher()
                        voucher.id_tecno = sw+'-'+tipo+'-'+nro
                        voucher.party = tercero
                        tipo_pago, = cls.get_tipo_pago(tipo, nro)
                        idt = tipo_pago[columns_tip.index('forma_pago')]
                        paym, = PayMode.search([('id_tecno', '=', idt)])
                        voucher.payment_mode = paym
                        voucher.on_change_payment_mode()
                        voucher.voucher_type = 'receipt'
                        fecha = str(doc[columns_doc.index('fecha_hora')]).split()[0].split('-')
                        fecha_date = datetime.date(int(fecha[0]), int(fecha[1]), int(fecha[2]))
                        voucher.date = fecha_date
                        nota = doc[columns_doc.index('notas')].replace('\n', ' ').replace('\r', '')
                        if nota:
                            voucher.description = nota
                        voucher.reference = tipo+'-'+nro
                        for rec in recibos:
                            ref = str(rec[columns_rec.index('tipo_aplica')])+'-'+str(rec[columns_rec.index('numero_aplica')])
                            move_line = MoveLine.search([('reference', '=', ref), ('party', '=', tercero.id)])
                            if move_line:
                                line = Line()
                                line.voucher = voucher
                                line.amount_original = move_line[0].debit
                                line.reference = ref
                                line.move_line = move_line[0]
                                line.on_change_move_line()
                                line.amount = Decimal(rec[columns_rec.index('valor')])
                                line.save()
                                #Descuentos
                                if rec[columns_rec.index('descuento')] > 0:
                                    account, = Account.search([('code', '=', '530535')])
                                    line = Line()
                                    line.party = tercero
                                    line.account = account
                                    line.voucher = voucher
                                    line.detail = 'DESCUENTO'
                                    line.reference = ref
                                    line.amount = Decimal(rec[columns_rec.index('descuento')])
                                    line.save()
                                #Retenciones
                                if rec[columns_rec.index('retencion')] > 0:
                                    retencion, = Tax.search([('name', '=', 'RET. RENTA 0,4%')])
                                    line = Line()
                                    line.party = tercero
                                    line.account = 547 #RET
                                    line.detail = 'RETENCION'
                                    line.voucher = voucher
                                    line.type = 'tax'
                                    line.tax = retencion
                                    line.amount = Decimal(rec[columns_rec.index('retencion')])
                                    line.reference = ref
                                    line.save()
                                if rec[columns_rec.index('retencion_iva')] > 0:
                                    retencion, = Tax.search([('name', '=', 'RET. RENTA 0,4%')])
                                    line = Line()
                                    line.party = tercero
                                    line.account = 547 #RET
                                    line.detail = 'RETENCION'
                                    line.voucher = voucher
                                    line.type = 'tax'
                                    line.tax = retencion
                                    line.amount = Decimal(rec[columns_rec.index('retencion')])
                                    line.reference = ref
                                    line.save()
                                if rec[columns_rec.index('retencion_ica')] > 0:
                                    retencion, = Tax.search([('name', '=', 'RET. RENTA 0,4%')])
                                    line = Line()
                                    line.party = tercero
                                    line.account = 547 #RET
                                    line.detail = 'RETENCION'
                                    line.voucher = voucher
                                    line.type = 'tax'
                                    line.tax = retencion
                                    line.amount = Decimal(rec[columns_rec.index('retencion')])
                                    line.reference = ref
                                    line.save()
                                if rec[columns_rec.index('retencion2')] > 0:
                                    retencion, = Tax.search([('name', '=', 'RET. RENTA 0,4%')])
                                    line = Line()
                                    line.party = tercero
                                    line.account = 547 #RET
                                    line.detail = 'RETENCION'
                                    line.voucher = voucher
                                    line.type = 'tax'
                                    line.tax = retencion
                                    line.amount = Decimal(rec[columns_rec.index('retencion')])
                                    line.reference = ref
                                    line.save()
                                if rec[columns_rec.index('retencion3')] > 0:
                                    retencion, = Tax.search([('name', '=', 'RET. RENTA 0,4%')])
                                    line = Line()
                                    line.party = tercero
                                    line.account = 547 #RET
                                    line.detail = 'RETENCION'
                                    line.voucher = voucher
                                    line.type = 'tax'
                                    line.tax = retencion
                                    line.amount = Decimal(rec[columns_rec.index('retencion')])
                                    line.reference = ref
                                    line.save()
                                #Se procede a comparar los totales
                                voucher.on_change_lines()
                                invoice, = Invoice.search([('reference', '=', ref)])
                                if Decimal(invoice.untaxed_amount) == Decimal(voucher.amount_to_pay):
                                    voucher.process()
                            else:
                                print('OJO NO ENCONTRO LINEA: ', ref)
                        voucher.save()


    @classmethod
    def update_paymode(cls):
        columns_fp = cls.get_columns_db('TblFormaPago')
        forma_pago = cls.get_formapago()
        PayMode = Pool().get('account.voucher.paymode')
        Journal = Pool().get('account.journal')
        Account = Pool().get('account.account')
        for fp in forma_pago:
            idt = str(fp[columns_fp.index('IdFormaPago')])
            paym = PayMode.search([('id_tecno', '=', idt)])
            if paym:
                for pm in paym:
                    pm.name = fp[columns_fp.index('FormaPago')].strip()
                    PayMode.save(paym)
            else:
                journal, = Journal.search([('code', '=', 'REV')])
                paym = PayMode()
                paym.id_tecno = idt
                paym.name = fp[columns_fp.index('FormaPago')].strip()
                paym.payment_type = 'cash'
                paym.kind = 'both'
                paym.journal = journal
                sequence_payment = cls.find_seq('Voucher Payment')
                sequence_multipayment = cls.find_seq('Voucher Multipayment')
                sequence_receipt = cls.find_seq('Voucher Receipt')
                paym.sequence_payment = sequence_payment[0]
                paym.sequence_multipayment = sequence_multipayment[0]
                paym.sequence_receipt = sequence_receipt[0]
                #Se busca la cuenta de caja general para asignarle al paymode
                account, = Account.search([('code', '=', '110505')])
                paym.account = account
                #Codigo clasificacion tipo de pago ('10' => 'Efectivo')
                paym.payment_means_code = 10
                paym.save()


    #Metodo encargado de consultar y verificar si existe un voucher con la id de la BD
    @classmethod
    def find_voucher(cls, idt):
        Voucher = Pool().get('account.voucher')
        voucher = Voucher.search([('id_tecno', '=', idt)])
        if voucher:
            return voucher[0]
        else:
            return False

    #Función encargada de consultar las columnas pertenecientes a 'x' tabla de la bd de TecnoCarnes
    @classmethod
    def get_columns_db(cls, table):
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

    @classmethod
    def get_formapago(cls):
        data = []
        try:
            Config = Pool().get('conector.configuration')
            conexion = Config.conexion()
            with conexion.cursor() as cursor:
                query = cursor.execute("SELECT * FROM dbo.TblFormaPago")
                data = list(query.fetchall())
        except Exception as e:
            print("ERROR QUERY get_formapago: ", e)
        return data

    #Esta función se encarga de traer todos los datos de una tabla dada de acuerdo al rango de fecha dada de la bd TecnoCarnes
    @classmethod
    def get_data(cls, table, date):
        data = []
        try:
            Config = Pool().get('conector.configuration')
            conexion = Config.conexion()
            with conexion.cursor() as cursor:
                query = cursor.execute("SELECT * FROM dbo."+table+" WHERE sw = 5 AND fecha_hora >= CAST('"+date+"' AS datetime)")
                data = list(query.fetchall())
        except Exception as e:
            print("ERROR QUERY get_data: ", e)
        return data

    #Metodo encargado de obtener los recibos pagados de un documento dado
    @classmethod
    def get_recibos(cls, tipo, nro):
        data = []
        try:
            Config = Pool().get('conector.configuration')
            conexion = Config.conexion()
            with conexion.cursor() as cursor:
                query = cursor.execute("SELECT * FROM dbo.Documentos_Cruce WHERE sw = 5 AND tipo = "+tipo+" AND numero ="+nro)
                data = list(query.fetchall())
        except Exception as e:
            print("ERROR QUERY get_recibos: ", e)
        return data

    #Metodo encargado de obtener la forma en que se pago el comprobante (recibos)
    @classmethod
    def get_tipo_pago(cls, tipo, nro):
        data = []
        try:
            Config = Pool().get('conector.configuration')
            conexion = Config.conexion()
            with conexion.cursor() as cursor:
                query = cursor.execute("SELECT * FROM dbo.Documentos_Che WHERE sw = 5 AND tipo = "+tipo+" AND numero ="+nro)
                data = list(query.fetchall())
        except Exception as e:
            print("ERROR QUERY get_recibos: ", e)
        return data

    #Función encargada de traer los datos de la bd TecnoCarnes con una fecha dada.
    @classmethod
    def last_update(cls):
        Actualizacion = Pool().get('conector.actualizacion')
        #Se consulta la ultima actualización realizada para los terceros
        ultima_actualizacion = Actualizacion.search([('name', '=','RECIBOS')])
        if ultima_actualizacion:
            #Se calcula la fecha restando la diferencia de horas que tiene el servidor con respecto al clienete
            if ultima_actualizacion[0].write_date:
                fecha = (ultima_actualizacion[0].write_date - datetime.timedelta(hours=5))
            else:
                fecha = (ultima_actualizacion[0].create_date - datetime.timedelta(hours=5))
        else:
            fecha = datetime.date(2021,1,1)
        fecha = fecha.strftime('%Y-%d-%m %H:%M:%S')
        data = cls.get_data('Documentos', fecha)
        return data

    #Crea o actualiza un registro de la tabla actualización en caso de ser necesario
    @classmethod
    def create_or_update(cls):
        Actualizacion = Pool().get('conector.actualizacion')
        actualizacion = Actualizacion.search([('name', '=','RECIBOS')])
        if actualizacion:
            #Se busca un registro con la actualización
            actualizacion, = Actualizacion.search([('name', '=','RECIBOS')])
            actualizacion.name = 'RECIBOS'
            actualizacion.save()
        else:
            #Se crea un registro con la actualización
            actualizar = Actualizacion()
            actualizar.name = 'RECIBOS'
            actualizar.save()

#Función encargada de consultar la secuencia de un voucher dado
    @classmethod
    def find_seq(cls, name):
        Sequence = Pool().get('ir.sequence')
        seq = Sequence.__table__()
        cursor = Transaction().connection.cursor()
        cursor.execute(*seq.select(where=(seq.name == name)))
        result = cursor.fetchall()
        return result[0]

class VoucherPayMode(ModelSQL, ModelView):
    'Voucher Pay Mode'
    __name__ = 'account.voucher.paymode'
    id_tecno = fields.Char('Id Tabla Sqlserver', required=False)