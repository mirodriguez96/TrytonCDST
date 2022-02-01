from audioop import mul
from trytond.model import ModelView, ModelSQL, fields
from trytond.pool import Pool, PoolMeta
from trytond.exceptions import UserError
#from trytond.transaction import Transaction
from decimal import Decimal
import logging

import datetime

__all__ = [
    'Voucher',
    'Cron',
    'MultiRevenue',
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
        logs = []
        if documentos_db:

            pool = Pool()
            Voucher = pool.get('account.voucher')
            Line = pool.get('account.voucher.line')
            Party = pool.get('party.party')
            PayMode = pool.get('account.voucher.paymode')
            MultiRevenue = pool.get('account.multirevenue')
            Transaction = pool.get('account.multirevenue.transaction')

            for doc in documentos_db:
                fecha = str(doc.fecha_hora).split()[0].split('-')
                fecha_date = datetime.date(int(fecha[0]), int(fecha[1]), int(fecha[2]))
                sw = str(doc.sw)
                tipo = doc.tipo.strip()
                nro = str(doc.Numero_documento)
                id_tecno = sw+'-'+tipo+'-'+nro
                #print(id_tecno)
                existe = cls.find_voucher(sw+'-'+tipo+'-'+nro)
                if not existe:
                    #print(id_tecno)
                    nit_cedula = doc.nit_Cedula.strip()
                    tercero, = Party.search([('id_number', '=', nit_cedula)])
                    consult = "sw="+sw+" and tipo="+tipo+" and numero="+nro
                    #Se obtiene las facturas a las que hace referencia el ingreso o egreso
                    facturas = cls.get_dcto_cruce(consult)
                    if facturas:
                        #print(id_tecno)
                        lineas_a_pagar = False
                        #Se comprueba si el comprobante tiene facturas en el sistema Tryton
                        for factura in facturas:
                            ref = factura.tipo_aplica+'-'+str(factura.numero_aplica)
                            move_line = cls.get_moveline(ref, tercero)
                            if move_line:
                                lineas_a_pagar = True
                        if not lineas_a_pagar:
                            continue
                        #Se obtiene la forma de pago, según la tabla Documentos_Che de TecnoCarnes
                        tipo_pago = cls.get_tipo_pago(sw, tipo, nro)
                        if len(tipo_pago) > 1 and sw == '5':
                            #print('MULTI INGRESO')
                            multingreso = MultiRevenue()
                            multingreso.code = tipo+'-'+nro
                            multingreso.party = tercero
                            multingreso.date = fecha_date
                            multingreso.id_tecno = id_tecno
                            multingreso.save()
                            #Se ingresa las formas de pago
                            for pago in tipo_pago:
                                forma_pago = pago.forma_pago
                                paymode, = PayMode.search([('id_tecno', '=', forma_pago)])
                                valor = pago.valor
                                transaction = Transaction()
                                transaction.multirevenue = multingreso
                                transaction.description = 'IMPORTACION TECNO'
                                transaction.amount = Decimal(valor)
                                transaction.date = fecha_date
                                transaction.payment_mode = paymode
                                transaction.save()
                            to_lines = []
                            #Se ingresa las lineas a pagar
                            for rec in facturas:
                                ref = rec.tipo_aplica+'-'+str(rec.numero_aplica)
                                move_line = cls.get_moveline(ref, tercero)
                                if move_line:
                                    #valor pagado x la factura
                                    valor = Decimal(rec.valor)
                                    line = multingreso.create_new_line(move_line, valor, Decimal(valor), multingreso.transactions)
                                    if line:
                                        to_lines.append(line)
                                else:
                                    msg1 = f'No existe la factura: {ref}'
                                    logging.warning(msg1)
                                    logs.append(msg1)
                            if to_lines:
                                multingreso.lines = to_lines
                                multingreso.save()
                            if multingreso.total_transaction and multingreso.total_lines_to_pay:
                                if multingreso.total_transaction <= multingreso.total_lines_to_pay:
                                    MultiRevenue.process([multingreso])
                                    MultiRevenue.generate_vouchers([multingreso])
                                else:
                                    pass
                        elif len(tipo_pago) == 1:
                            #print('VOUCHER')
                            forma_pago = tipo_pago[0].forma_pago
                            paymode, = PayMode.search([('id_tecno', '=', forma_pago)])
                            voucher = Voucher()
                            voucher.id_tecno = id_tecno
                            voucher.number = tipo+'-'+nro
                            voucher.party = tercero
                            voucher.payment_mode = paymode
                            voucher.on_change_payment_mode()
                            voucher.voucher_type = 'receipt'
                            if sw == '6':
                                voucher.voucher_type = 'payment'
                            voucher.date = fecha_date
                            nota = (doc.notas).replace('\n', ' ').replace('\r', '')
                            if nota:
                                voucher.description = nota
                            voucher.reference = tipo+'-'+nro
                            voucher.save()
                            for rec in facturas:
                                ref = rec.tipo_aplica+'-'+str(rec.numero_aplica)
                                move_line = cls.get_moveline(ref, tercero)
                                #print(move_line)
                                if move_line:
                                    line = Line()
                                    line.voucher = voucher
                                    valor_original = Decimal(0)
                                    if sw == '5':
                                        valor_original = Decimal(move_line.debit)
                                        #print(move_line.debit)
                                    elif sw == '6':
                                        valor_original = Decimal(move_line.credit)
                                        #print(move_line.credit)
                                    line.amount_original = valor_original
                                    line.reference = ref
                                    line.move_line = move_line
                                    line.on_change_move_line()
                                    valor = Decimal(rec.valor)
                                    
                                    if valor > valor_original:
                                        valor = valor_original
                                    line.amount = Decimal(valor)
                                    line.save()
                                    #Se procede a comparar los totales
                                    voucher.on_change_lines()
                                else:
                                    msg1 = f'No existe la factura: {ref}'
                                    logging.warning(msg1)
                                    logs.append(msg1)
                            #Se verifica que el comprobante tenga lineas para ser contabilizado
                            if voucher.lines:
                                Voucher.process([voucher])
                                Voucher.post([voucher])
                            voucher.save()
                        else:
                            msg1 = f"Revisar el tipo de pago de {id_tecno}"
                            logging.warning(msg1)
                            logs.append(msg1)
                            continue
                    else:
                        msg1 = f"No hay recibos para {id_tecno}"
                        logging.warning(msg1)
                        logs.append(msg1)
                        continue
                cls.importado(id_tecno)
        actualizacion.add_logs(actualizacion, logs)
        logging.warning("FINISH COMPROBANTES")


    #Se obtiene las lineas de la factura que se desea pagar
    @classmethod
    def get_moveline(cls, reference, party):
        pool = Pool()
        Invoice = pool.get('account.invoice')
        MoveLine = pool.get('account.move.line')
        #A continuacion se consulta las lineas a pagar de la factura (reference)
        linea = False
        invoice = Invoice.search([('number', '=', reference)])
        
        if invoice:
            invoice, = invoice
            if invoice.state != 'posted':
                return False
            lines_to_pay = Invoice.get_lines_to_pay([invoice], 'None')
            if lines_to_pay:
                #Se selecciona la primera linea. Pero si hay más?
                linea = lines_to_pay[invoice.id][0]
        if linea:
            moveline, = MoveLine.search([('id', '=', linea)])
            return moveline
        #Si no encuentra lineas a pagar...
        moveline = MoveLine.search([('reference', '=', reference), ('party', '=', party)])
        if moveline:
            moveline, = moveline
            return moveline
        else:
            return False

    #Se marca como importado
    @classmethod
    def importado(cls, id):
        Config = Pool().get('conector.configuration')
        lista = id.split('-')
        consult = "UPDATE dbo.Documentos SET exportado = 'T' WHERE sw ="+lista[0]+" and tipo = "+lista[1]+" and Numero_documento = "+lista[2]
        Config.set_data(consult)

    #Metodo encargado de consultar y verificar si existe un voucher con la id de la BD
    @classmethod
    def find_voucher(cls, idt):
        pool = Pool()
        Voucher = pool.get('account.voucher')
        MultiRevenue = pool.get('account.multirevenue')
        voucher = Voucher.search([('id_tecno', '=', idt)])
        if voucher:
            return True
        else:
            multirevenue = MultiRevenue.search([('id_tecno', '=', idt)])
            if multirevenue:
                return True
            else:
                return False

    #Esta función se encarga de traer todos los datos de una tabla dada de acuerdo al rango de fecha dada de la bd TecnoCarnes
    @classmethod
    def get_data_tecno(cls, date):
        Config = Pool().get('conector.configuration')
        #consult = "SELECT TOP(5) * FROM dbo.Documentos WHERE (sw = 5 OR sw = 6) AND fecha_hora >= CAST('"+date+"' AS datetime) AND exportado != 'T'" #TEST
        consult = "SET DATEFORMAT ymd SELECT TOP(500) * FROM dbo.Documentos WHERE (sw = 5 OR sw = 6) AND fecha_hora >= CAST('"+date+"' AS datetime) AND exportado != 'T'"
        data = Config.get_data(consult)
        return data

    #Metodo encargado de obtener los recibos pagados de un documento dado
    @classmethod
    def get_dcto_cruce(cls, consult):
        Config = Pool().get('conector.configuration')
        query = "SELECT * FROM dbo.Documentos_Cruce WHERE "+consult
        data = Config.get_data(query)
        return data

    #Metodo encargado de obtener la forma en que se pago el comprobante (recibos)
    @classmethod
    def get_tipo_pago(cls, sw, tipo, nro):
        Config = Pool().get('conector.configuration')
        consult = "SELECT * FROM dbo.Documentos_Che WHERE sw="+sw+" AND tipo="+tipo+" AND numero="+nro
        data = Config.get_data(consult)
        return data

    #Función encargada de traer los datos de la bd TecnoCarnes con una fecha dada.
    @classmethod
    def last_update(cls):
        Config = Pool().get('conector.configuration')
        config, = Config.search([], order=[('id', 'DESC')], limit=1)
        fecha = config.date
        fecha = fecha.strftime('%Y-%m-%d %H:%M:%S')
        data = cls.get_data_tecno(fecha)
        return data

    #Crea o actualiza un registro de la tabla actualización en caso de ser necesario
    @classmethod
    def create_or_update(cls):
        Actualizacion = Pool().get('conector.actualizacion')
        actualizacion = Actualizacion.search([('name', '=','COMPROBANTES')])
        if actualizacion:
            #Se busca un registro con la actualización
            actualizacion, = actualizacion
        else:
            #Se crea un registro con la actualización
            actualizacion = Actualizacion()
            actualizacion.name = 'COMPROBANTES'
            actualizacion.logs = 'logs...'
            actualizacion.save()
        return actualizacion


class MultiRevenue(metaclass=PoolMeta):
    'MultiRevenue'
    __name__ = 'account.multirevenue'
    id_tecno = fields.Char('Id Tabla Sqlserver', required=False)