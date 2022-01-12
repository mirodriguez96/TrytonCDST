from trytond.model import ModelView, ModelSQL, fields
from trytond.pool import Pool, PoolMeta
#from trytond.exceptions import UserError
#from trytond.transaction import Transaction
from decimal import Decimal
import logging

import datetime

__all__ = [
    'Voucher',
    'Cron',
    ]


class Cron(metaclass=PoolMeta):
    'Cron'
    __name__ = 'ir.cron'

    @classmethod
    def __setup__(cls):
        super().__setup__()
        cls.method.selection.append(
            ('account.voucher|import_voucher', "Importar comprobantes"),
            )


#Heredamos del modelo sale.sale para agregar el campo id_tecno
class Voucher(ModelSQL, ModelView):
    'Voucher'
    __name__ = 'account.voucher'
    id_tecno = fields.Char('Id Tabla Sqlserver', required=False)

    @classmethod
    def import_voucher(cls):
        logging.warning('RUN VOUCHER !')
        #documents = cls.last_update()
        cls.create_or_update()

        pool = Pool()
        Invoice = pool.get('account.invoice')
        Voucher = pool.get('account.voucher')
        Line = pool.get('account.voucher.line')
        PayMode = pool.get('account.voucher.paymode')
        columns_rec = cls.get_columns_db('Documentos_Cruce')
        columns_tip = cls.get_columns_db('Documentos_Che')

        invoices = Invoice.search([('state', '!=', 'paid')])

        if invoices:
            to_create = {}
            
            for invoice in invoices:
                if not invoice.number:
                    continue
                tipo_numero = invoice.number.split('-')
                if len(tipo_numero) != 2:
                    continue
                data = cls.get_recibos("(sw = 5 or sw = 6) AND tipo_aplica="+tipo_numero[0]+" AND numero_aplica="+tipo_numero[1])
                if data:
                    sw = str(data[0][columns_rec.index('sw')])
                    tipo = str(data[0][columns_rec.index('tipo')])
                    nro = str(data[0][columns_rec.index('numero')])
                    id_recibo = sw+'-'+tipo+'-'+nro
                    if id_recibo not in to_create.keys():
                        to_create[id_recibo] = []
                    to_create[id_recibo].append(invoice)
            """
            numbers = ['101-759084', '101-759085', '101-759086', '101-759087', '101-759088']
            to_create = {
                '5-107-19089': []
            }
            for num in numbers:
                invoice, = Invoice.search([('number', '=', num)])
                to_create['5-107-19089'].append(invoice)
            """
            for rec in to_create:
                #Se procede a crear el comprobante de pago
                comprobante = Voucher()
                comprobante.id_tecno = rec
                comprobante.party = to_create[rec][0].party
                #Se traen las lineas a pagar
                to_line = []
                for factura in to_create[rec]:
                    val = factura.lines_to_pay
                    if val:
                        to_line.append(val[0])
                tipo_numero = rec.split('-')
                tipo_pago, = cls.get_tipo_pago(tipo_numero[0], tipo_numero[1], tipo_numero[2])
                idt = tipo_pago[columns_tip.index('forma_pago')]
                paym, = PayMode.search([('id_tecno', '=', idt)])
                comprobante.payment_mode = paym
                comprobante.on_change_payment_mode()
                #SE LE INDICA SI EL COMPROBANTE ES DE TIPO INGRESO O EGRESO
                comprobante.voucher_type = 'receipt'
                if tipo_numero[0] == '6':
                    comprobante.voucher_type = 'payment'
                fecha = str(tipo_pago[columns_tip.index('fecha')]).split()[0].split('-')
                fecha_date = datetime.date(int(fecha[0]), int(fecha[1]), int(fecha[2]))
                comprobante.date = fecha_date
                comprobante.reference = tipo_numero[1]+'-'+tipo_numero[2]
                comprobante.description = 'IMPORTACION TECNO'

                for move_line in to_line:
                    line = Line()
                    line.voucher = comprobante
                    #line.amount_original = move_line.debit
                    line.reference = move_line.reference
                    line.move_line = move_line
                    line.on_change_move_line()
                    #line.amount = Decimal(rec[columns_rec.index('valor')])
                    line.save()
                    #Se procede a comparar los totales
                    comprobante.on_change_lines()
                Voucher.process([comprobante])
                diferencia_total = Decimal(tipo_pago[columns_tip.index('valor')]) - Decimal(comprobante.amount_to_pay)
                if diferencia_total <= 0.5:
                    Voucher.post([comprobante])
                comprobante.save()
        logging.warning('FINISH VOUCHER !')


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
                query = cursor.execute("SELECT TOP(10) * FROM dbo."+table+" WHERE (sw = 5 OR sw = 6) AND fecha_hora >= CAST('"+date+"' AS datetime)")
                data = list(query.fetchall())
        except Exception as e:
            print("ERROR QUERY get_data: ", e)
        return data

    #Metodo encargado de obtener los recibos pagados de un documento dado
    @classmethod
    def get_recibos(cls, consult):
        data = []
        try:
            Config = Pool().get('conector.configuration')
            conexion = Config.conexion()
            with conexion.cursor() as cursor:
                query = cursor.execute("SELECT * FROM dbo.Documentos_Cruce WHERE "+consult)
                data = list(query.fetchall())
        except Exception as e:
            print("ERROR QUERY get_recibos: ", e)
        return data

    #Metodo encargado de obtener la forma en que se pago el comprobante (recibos)
    @classmethod
    def get_tipo_pago(cls, sw, tipo, nro):
        data = []
        try:
            Config = Pool().get('conector.configuration')
            conexion = Config.conexion()
            with conexion.cursor() as cursor:
                query = cursor.execute("SELECT * FROM dbo.Documentos_Che WHERE sw="+sw+" AND tipo="+tipo+" AND numero="+nro)
                data = list(query.fetchall())
        except Exception as e:
            print("ERROR QUERY get_recibos: ", e)
        return data

    #Función encargada de traer los datos de la bd TecnoCarnes con una fecha dada.
    @classmethod
    def last_update(cls):
        Actualizacion = Pool().get('conector.actualizacion')
        #Se consulta la ultima actualización realizada para los terceros
        ultima_actualizacion = Actualizacion.search([('name', '=','COMPROBANTES')])
        if ultima_actualizacion:
            #Se calcula la fecha restando la diferencia de horas que tiene el servidor con respecto al clienete
            if ultima_actualizacion[0].write_date:
                fecha = (ultima_actualizacion[0].write_date - datetime.timedelta(hours=5))
            else:
                fecha = (ultima_actualizacion[0].create_date - datetime.timedelta(hours=5))
        else:
            Config = Pool().get('conector.configuration')
            config, = Config.search([], order=[('id', 'DESC')], limit=1)
            fecha = config.date
            #fecha = datetime.date(1,1,1)
        fecha = fecha.strftime('%Y-%d-%m %H:%M:%S')
        data = cls.get_data('Documentos', fecha)
        return data

    #Crea o actualiza un registro de la tabla actualización en caso de ser necesario
    @classmethod
    def create_or_update(cls):
        Actualizacion = Pool().get('conector.actualizacion')
        actualizacion = Actualizacion.search([('name', '=','COMPROBANTES')])
        if actualizacion:
            #Se busca un registro con la actualización
            actualizacion, = Actualizacion.search([('name', '=','COMPROBANTES')])
            actualizacion.name = 'COMPROBANTES'
            actualizacion.save()
        else:
            #Se crea un registro con la actualización
            actualizar = Actualizacion()
            actualizar.name = 'COMPROBANTES'
            actualizar.save()
