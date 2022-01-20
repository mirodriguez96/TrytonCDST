from audioop import mul
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

    """
    #Se importa los comprobantes de las facturas existentes en Tryton
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
                    valor = data[0][columns_rec.index('valor')]
                    id_recibo = sw+'-'+tipo+'-'+nro
                    if id_recibo not in to_create.keys():
                        to_create[id_recibo] = []
                    to_create[id_recibo].append([invoice, valor])

            for rec in to_create:
                print(rec)
                #Se traen las lineas a pagar
                to_line = []
                for factura in to_create[rec]:
                    val = factura[0].lines_to_pay
                    if val:
                        to_line.append([val[0], factura[1]])
                tipo_numero = rec.split('-')
                tipo_pago = cls.get_tipo_pago(tipo_numero[0], tipo_numero[1], tipo_numero[2])
                for pago in tipo_pago:
                    #Se procede a crear el comprobante de pago
                    comprobante = Voucher()
                    comprobante.id_tecno = rec
                    comprobante.party = to_create[rec][0].party
                    idt = pago[columns_tip.index('forma_pago')]
                    paym, = PayMode.search([('id_tecno', '=', idt)])
                    comprobante.payment_mode = paym
                    comprobante.on_change_payment_mode()
                    #SE LE INDICA SI EL COMPROBANTE ES DE TIPO INGRESO O EGRESO
                    comprobante.voucher_type = 'receipt'
                    if tipo_numero[0] == '6':
                        comprobante.voucher_type = 'payment'
                    fecha = str(pago[columns_tip.index('fecha')]).split()[0].split('-')
                    fecha_date = datetime.date(int(fecha[0]), int(fecha[1]), int(fecha[2]))
                    comprobante.date = fecha_date
                    comprobante.reference = tipo_numero[1]+'-'+tipo_numero[2]
                    comprobante.description = 'IMPORTACION TECNO'
                    #valor_tecno = Decimal(pago[columns_tip.index('valor')])
                    for move_line in to_line:
                        line = Line()
                        line.voucher = comprobante
                        #line.amount = move_line.debit
                        line.reference = move_line[0].reference
                        line.move_line = move_line[0]
                        line.on_change_move_line()
                        line.amount = move_line[1]
                        line.save()
                        #Se procede a comparar los totales
                        comprobante.on_change_lines()
                    Voucher.process([comprobante])
                    Voucher.post([comprobante])
                    #diferencia_total = valor_tecno - Decimal(comprobante.amount_to_pay)
                    #if diferencia_total <= 0.5:
                    #    Voucher.post([comprobante]) 
                    comprobante.save()
        logging.warning('FINISH VOUCHER !')
    """

    #Funcion encargada de crear los comprobantes ingresos y egresos
    @classmethod
    def import_voucher(cls):
        logging.warning("RUN COMPROBANTES")
        documentos_db = cls.last_update()
        #Se crea o actualiza la fecha de importación
        actualizacion = cls.create_or_update()
        logs = actualizacion.logs
        if not logs:
            logs = 'logs...'
        if documentos_db:
            columns_doc = cls.get_columns_db('Documentos')
            columns_rec = cls.get_columns_db('Documentos_Cruce')
            columns_tip = cls.get_columns_db('Documentos_Che')
            pool = Pool()
            Invoice = pool.get('account.invoice')
            Voucher = pool.get('account.voucher')
            Line = pool.get('account.voucher.line')
            Party = pool.get('party.party')
            PayMode = pool.get('account.voucher.paymode')
            MultiRevenue = pool.get('account.multirevenue')
            Transaction = pool.get('account.multirevenue.transaction')
            for doc in documentos_db:
                fecha = str(doc[columns_doc.index('fecha_hora')]).split()[0].split('-')
                fecha_date = datetime.date(int(fecha[0]), int(fecha[1]), int(fecha[2]))
                sw = str(doc[columns_doc.index('sw')])
                tipo = doc[columns_doc.index('tipo')].strip()
                nro = str(doc[columns_doc.index('Numero_documento')])
                id_tecno = sw+'-'+tipo+'-'+nro
                print(id_tecno)
                existe = cls.find_voucher(sw+'-'+tipo+'-'+nro)
                if not existe:
                    nit_cedula = doc[columns_doc.index('nit_Cedula')].strip()
                    tercero, = Party.search([('id_number', '=', nit_cedula)])
                    consult = "sw="+sw+" and tipo="+tipo+" and numero="+nro
                    #Se obtiene los recibos y las facturas a las que hace referencia el ingreso o egreso
                    recibos = cls.get_recibos(consult)
                    if recibos:
                        facturas_a_pagar = False
                        #Se comprueba si el comprobante tiene facturas en el sistema Tryton
                        for recibo in recibos:
                            ref = str(recibo[columns_rec.index('tipo_aplica')])+'-'+str(recibo[columns_rec.index('numero_aplica')])
                            moveline = cls.get_moveline(ref, tercero)
                            if moveline:
                                facturas_a_pagar = True
                        if not facturas_a_pagar:
                            continue
                        #Se obtiene la forma de pago, según la tabla Documentos_Che de TecnoCarnes
                        tipo_pago = cls.get_tipo_pago(sw, tipo, nro)
                        if len(tipo_pago) > 1 and sw == '5':
                            multingreso = MultiRevenue()
                            multingreso.party = tercero
                            multingreso.date = fecha_date
                            multingreso.save()
                            cont = 0
                            for pago in tipo_pago:
                                forma_pago = tipo_pago[cont][columns_tip.index('forma_pago')]
                                paymode, = PayMode.search([('id_tecno', '=', forma_pago)])
                                valor = pago[columns_tip.index('valor')]
                                transaction = Transaction()
                                transaction.multirevenue = multingreso
                                transaction.description = 'IMPORTACION TECNO'
                                transaction.amount = Decimal(valor)
                                transaction.date = fecha_date
                                transaction.payment_mode = paymode
                                transaction.save()
                                cont += 1
                            to_lines = []
                            for rec in recibos:
                                ref = str(rec[columns_rec.index('tipo_aplica')])+'-'+str(rec[columns_rec.index('numero_aplica')])
                                move = cls.get_moveline(ref, tercero)
                                if move:
                                    #valor pagado x la factura
                                    valor = Decimal(rec[columns_rec.index('valor')])
                                    line = multingreso.create_new_line(move, valor, Decimal(valor), multingreso.transactions)
                                    if line:
                                        to_lines.append(line)
                            if to_lines:
                                multingreso.lines = to_lines
                                multingreso.save()
                            if multingreso.total_transaction and multingreso.total_lines_to_pay and multingreso.total_transaction <= multingreso.total_lines_to_pay:
                                MultiRevenue.process([multingreso])
                                MultiRevenue.generate_vouchers([multingreso])
                        elif len(tipo_pago) == 1:
                            forma_pago = tipo_pago[0][columns_tip.index('forma_pago')]
                            paymode, = PayMode.search([('id_tecno', '=', forma_pago)])
                            voucher = Voucher()
                            voucher.id_tecno = id_tecno
                            voucher.party = tercero
                            voucher.payment_mode = paymode
                            voucher.on_change_payment_mode()
                            voucher.voucher_type = 'receipt'
                            if sw == '6':
                                voucher.voucher_type = 'payment'
                            voucher.date = fecha_date
                            nota = doc[columns_doc.index('notas')].replace('\n', ' ').replace('\r', '')
                            if nota:
                                voucher.description = nota
                            voucher.reference = tipo+'-'+nro
                            for rec in recibos:
                                ref = str(rec[columns_rec.index('tipo_aplica')])+'-'+str(rec[columns_rec.index('numero_aplica')])
                                move_line = cls.get_moveline(ref, tercero)
                                if move_line:
                                    line = Line()
                                    line.voucher = voucher
                                    line.amount_original = move_line.debit
                                    line.reference = ref
                                    line.move_line = move_line
                                    line.on_change_move_line()
                                    valor = Decimal(rec[columns_rec.index('valor')])
                                    if valor > line.amount_original:
                                        valor = line.amount_original
                                    line.amount = valor
                                    line.save()
                                    #Se procede a comparar los totales
                                    voucher.on_change_lines()
                                    invoice, = Invoice.search([('reference', '=', ref)])
                                    diferencia = Decimal(invoice.untaxed_amount) - Decimal(voucher.amount_to_pay)
                                    if diferencia <= 1.0:
                                        Voucher.process([voucher])
                                        Voucher.post([voucher])
                                else:
                                    logging.warning('NO SE ENCONTRO LA LINEA: '+ref)
                                    continue
                            voucher.save()
                        else:
                            continue
                    else:
                        pass
                cls.importado(id_tecno)
        actualizacion.logs = logs
        actualizacion.save()
        logging.warning("FINISH COMPROBANTES")


    #Se obtiene las lineas de la factura
    @classmethod
    def get_moveline(cls, reference, party):
        MoveLine = Pool().get('account.move.line')
        moveline = MoveLine.search([('reference', '=', reference), ('party', '=', party)])
        if moveline:
            return moveline[0]
        else:
            return None

    #Se marca como importado
    @classmethod
    def importado(cls, id):
        lista = id.split('-')
        try:
            Config = Pool().get('conector.configuration')
            conexion = Config.conexion()
            with conexion.cursor() as cursor:
                cursor.execute("UPDATE dbo.Documentos SET exportado = 'T' WHERE sw ="+lista[0]+" and tipo = "+lista[1]+" and Numero_documento = "+lista[2])
        except Exception as e:
            print(e)
            raise logging.error('Error al actualizar como importado: ', e)

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

    #Esta función se encarga de traer todos los datos de una tabla dada de acuerdo al rango de fecha dada de la bd TecnoCarnes
    @classmethod
    def get_data(cls, table, date):
        data = []
        try:
            Config = Pool().get('conector.configuration')
            conexion = Config.conexion()
            with conexion.cursor() as cursor:
                query = cursor.execute("SELECT TOP(100) * FROM dbo."+table+" WHERE (sw = 5 OR sw = 6) AND fecha_hora >= CAST('"+date+"' AS datetime) AND exportado != 'T' ")
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
        #Actualizacion = Pool().get('conector.actualizacion')
        #Se consulta la ultima actualización realizada para los terceros
        #ultima_actualizacion = Actualizacion.search([('name', '=','COMPROBANTES')])
        #if ultima_actualizacion:
        #    #Se calcula la fecha restando la diferencia de horas que tiene el servidor con respecto al clienete
        #    if ultima_actualizacion[0].write_date:
        #        fecha = (ultima_actualizacion[0].write_date - datetime.timedelta(hours=5))
        #    else:
        #        fecha = (ultima_actualizacion[0].create_date - datetime.timedelta(hours=5))
        #else:
        #    fecha = datetime.date(1,1,1)
        Config = Pool().get('conector.configuration')
        config, = Config.search([], order=[('id', 'DESC')], limit=1)
        fecha = config.date
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
            actualizacion.logs = 'logs...'
            actualizacion.save()
        else:
            #Se crea un registro con la actualización
            actualizacion = Actualizacion()
            actualizacion.name = 'COMPROBANTES'
            actualizacion.save()
        return actualizacion
