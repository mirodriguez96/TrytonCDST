from trytond.model import ModelView, ModelSQL, fields
from trytond.pool import Pool, PoolMeta
from trytond.exceptions import UserError
from trytond.transaction import Transaction
from trytond.wizard import Wizard, StateTransition
from decimal import Decimal
import logging
from sql import Table

import datetime

__all__ = [
    'Voucher',
    'Cron',
    'MultiRevenue',
    'VoucherConfiguration',
    'Delete Voucher Tecno'
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

    #Funcion encargada de crear los comprobantes ingresos y egresos
    @classmethod
    def import_voucher(cls):
        logging.warning("RUN COMPROBANTES")
        documentos_db = cls.last_update()
        #Se crea o actualiza la fecha de importación
        actualizacion = cls.create_or_update()
        if not documentos_db:
            actualizacion.save()
            logging.warning("FINISH COMPROBANTES")
            return

        pool = Pool()
        Voucher = pool.get('account.voucher')
        Line = pool.get('account.voucher.line')
        Party = pool.get('party.party')
        PayMode = pool.get('account.voucher.paymode')
        MultiRevenue = pool.get('account.multirevenue')
        Transaction = pool.get('account.multirevenue.transaction')

        logs = []
        #to_save = []
        created = []

        for doc in documentos_db:
            sw = str(doc.sw)
            tipo = doc.tipo
            nro = str(doc.Numero_documento)
            id_tecno = sw+'-'+tipo+'-'+nro
            existe = cls.find_voucher(sw+'-'+tipo+'-'+nro)
            if existe:
                cls.importado(id_tecno)
                continue
            fecha_date = cls.convert_fecha_tecno(doc.fecha_hora)
            nit_cedula = doc.nit_Cedula
            tercero, = Party.search([('id_number', '=', nit_cedula)])
            #Se obtiene las facturas a las que hace referencia el ingreso o egreso
            facturas = cls.get_dcto_cruce("sw="+sw+" and tipo="+tipo+" and numero="+nro)
            if not facturas:
                msg1 = f"No hay recibos para {id_tecno}"
                logging.warning(msg1)
                #logs.append(msg1)
                continue
            lineas_a_pagar = False
            #Se comprueba si el comprobante tiene facturas en el sistema Tryton
            for factura in facturas:
                ref = factura.tipo_aplica+'-'+str(factura.numero_aplica)
                move_line = cls.get_moveline(ref, tercero)
                if move_line:
                    lineas_a_pagar = True
                else:
                    msg1 = f"No se encontró la factura {ref} del comprobante {id_tecno}"
                    logging.warning(msg1)
                    logs.append(msg1)
            if not lineas_a_pagar:
                continue
            #print("Procesando...", id_tecno)
            #Se obtiene la forma de pago, según la tabla Documentos_Che de TecnoCarnes
            tipo_pago = cls.get_tipo_pago(sw, tipo, nro)
            if len(tipo_pago) > 1 and sw == '5':
                print('MULTI INGRESO:', id_tecno)
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
                        msg1 = f'Total de pago es mayor al que se debe pagar en comprobantes multingreso: {id_tecno}'
                        logs.append(msg1)
                msg1 = f'Revisar comprobantes multingreso: {id_tecno}'
                logs.append(msg1)
                created.append(id_tecno)
            elif len(tipo_pago) == 1:
                print('VOUCHER:', id_tecno)
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
                valor_aplicado = Decimal(doc.valor_aplicado)
                for rec in facturas:
                    ref = rec.tipo_aplica+'-'+str(rec.numero_aplica)
                    move_line = cls.get_moveline(ref, tercero)
                    if not move_line:
                        msg1 = f'No existe la factura: {ref}'
                        logging.warning(msg1)
                        logs.append(msg1)
                        continue
                    config_voucher = pool.get('account.voucher_configuration')(1)
                    line = Line()
                    line.voucher = voucher
                    valor_original, amount_to_pay, untaxed_amount = cls.get_amount_to_pay_moveline_tecno(move_line, voucher)
                    line.amount_original = valor_original
                    line.reference = ref
                    line.move_line = move_line
                    line.on_change_move_line()
                    valor = Decimal(rec.valor)
                    descuento = Decimal(rec.descuento)
                    retencion = Decimal(rec.retencion)
                    ajuste = Decimal(rec.ajuste)
                    retencion_iva = Decimal(rec.retencion_iva)
                    retencion_ica = Decimal(rec.retencion_ica)

                    valor_pagado = valor + descuento + (retencion) + (ajuste*-1) + (retencion_iva) + (retencion_ica)
                    valor_pagado = round(valor_pagado, 2)
                    if valor_pagado > amount_to_pay:
                        valor_pagado = amount_to_pay
                    line.amount = Decimal(valor_pagado)
                    line.save()
                    #
                    if descuento > 0:
                        line_discount = Line()
                        line_discount.voucher = voucher
                        line_discount.detail = 'DESCUENTO'
                        valor_descuento = round((descuento * -1), 2)
                        line_discount.amount = valor_descuento
                        line_discount.account = config_voucher.account_discount_tecno
                        line_discount.save()
                    if retencion > 0:
                        line_rete = Line()
                        line_rete.voucher = voucher
                        line_rete.detail = 'RETENCION - ('+str(retencion)+')'
                        line_rete.type = 'tax'
                        line_rete.untaxed_amount = untaxed_amount
                        line_rete.tax = config_voucher.account_rete_tecno
                        line_rete.on_change_tax()
                        line_rete.amount = round((retencion*-1), 2)
                        line_rete.save()
                    if retencion_iva > 0:
                        line_retiva = Line()
                        line_retiva.voucher = voucher
                        line_retiva.detail = 'RETENCION IVA - ('+str(retencion_iva)+')'
                        line_retiva.type = 'tax'
                        line_retiva.untaxed_amount = untaxed_amount
                        line_retiva.tax = config_voucher.account_retiva_tecno
                        line_retiva.on_change_tax()
                        line_retiva.amount = round((retencion_iva*-1), 2)
                        line_retiva.save()
                    if retencion_ica > 0:
                        line_retica = Line()
                        line_retica.voucher = voucher
                        line_retica.detail = 'RETENCION ICA - ('+str(retencion_ica)+')'
                        line_retica.type = 'tax'
                        line_retica.untaxed_amount = untaxed_amount
                        line_retica.tax = config_voucher.account_retica_tecno
                        line_retica.on_change_tax()
                        line_retica.amount = round((retencion_ica*-1), 2)
                        line_retica.save()
                    if ajuste > 0:
                        line_ajuste = Line()
                        line_ajuste.voucher = voucher
                        line_ajuste.detail = 'AJUSTE'
                        if Decimal(move_line.debit) > 0:
                            line_ajuste.account = config_voucher.account_adjust_income
                        elif Decimal(move_line.credit) > 0:
                            line_ajuste.account = config_voucher.account_adjust_expense
                        valor_ajuste = round(ajuste, 2)
                        line_ajuste.amount = valor_ajuste
                        line_ajuste.save()
                    voucher.on_change_lines()
                    voucher.save()
                        
                #Se verifica que el comprobante tenga lineas para ser procesado y contabilizado (doble verificación por error)
                if voucher.lines and voucher.amount_to_pay > 0:
                    Voucher.process([voucher])
                    diferencia = abs(voucher.amount_to_pay - valor_aplicado)
                    #print(diferencia, (diferencia < Decimal(6.0)))
                    if voucher.amount_to_pay == valor_aplicado or diferencia < Decimal(6.0):
                        Voucher.post([voucher])
                created.append(id_tecno)
            else:
                msg1 = f"Revisar el tipo de pago de {id_tecno}"
                logging.warning(msg1)
                logs.append(msg1)
                continue                
        actualizacion.add_logs(actualizacion, logs)
        for id in created:
            cls.importado(id)
        logging.warning("FINISH COMPROBANTES")


    #Se obtiene las lineas de la factura que se desea pagar
    @classmethod
    def get_moveline(cls, reference, party):
        print(reference)
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
        #Si no encuentra lineas a pagar... Se busca en saldos iniciales
        moveline = MoveLine.search([('reference', '=', reference), ('party', '=', party)])
        if moveline:
            if len(moveline) > 1:
                raise UserError("Error factura saldos iniciales", "Esperaba una linea de movimiento y obtuvo muchas !")
            moveline, = moveline
            return moveline
        else:
            return False


    @classmethod
    def get_amount_to_pay_moveline_tecno(cls, moveline, voucher):
        pool = Pool()
        #Model = pool.get('ir.model')
        Invoice = pool.get('account.invoice')

        amount = moveline.credit or moveline.debit
        if voucher.voucher_type == 'receipt':
            if moveline.credit > Decimal('0'):
                amount = -amount
        else:
            if moveline.debit > Decimal('0'):
                amount = -amount

        amount_to_pay = Decimal(0)
        untaxed_amount = Decimal(0)
        if moveline.move_origin and hasattr(moveline.move_origin, '__name__') and moveline.move_origin.__name__ == 'account.invoice':

            amount_to_pay = Invoice.get_amount_to_pay(
                [moveline.move_origin], 'amount_to_pay'
            )
            amount_to_pay = amount_to_pay[moveline.move_origin.id]
            untaxed_amount = moveline.move_origin.untaxed_amount
        elif not moveline.move_origin:
            amount_to_pay = amount
            untaxed_amount = amount

        return amount, amount_to_pay, untaxed_amount

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
            return voucher[0]
        else:
            multirevenue = MultiRevenue.search([('id_tecno', '=', idt)])
            if multirevenue:
                return True
            else:
                return False

    @classmethod
    def convert_fecha_tecno(cls, fecha_tecno):
        fecha = str(fecha_tecno).split()[0].split('-')
        fecha = datetime.date(int(fecha[0]), int(fecha[1]), int(fecha[2]))
        return fecha

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
        

    @classmethod
    def delete_imported_vouchers(cls, vouchers):
        #pool = Pool()
        #Move = pool.get('account.move')
        #Voucher = pool.get('account.voucher')
        bank_statement_line = Table('bank_statement_line_account_move_line')
        account_move = Table('account_move')
        voucher_table = Table('account_voucher')
        voucher_line_table = Table('account_voucher_line')
        reconciliation_table = Table('account_move_reconciliation')
        cursor = Transaction().connection.cursor()
        Conexion = Pool().get('conector.configuration')

        for voucher in vouchers:
            # Se marca en la base de datos de importación como no exportado y se elimina
            lista = voucher.id_tecno.split('-')
            consult = "UPDATE dbo.Documentos SET exportado = 'S' WHERE exportado = 'T' and sw ="+lista[0]+" and tipo = "+lista[1]+" and Numero_documento = "+lista[2]
            Conexion.set_data(consult)

            if voucher.move:
                #Se requiere desconciliar el asiento antes de eliminarlo
                if voucher.move.origin.state == 'paid':
                    cls.unreconcile_move(voucher.move)

                if voucher.move and voucher.move.lines:
                    for move_line in voucher.move.lines:
                        #if move_line.reconciliation:
                        #    cursor.execute(*reconciliation_table.delete(
                        #        where=reconciliation_table.id == move_line.reconciliation.id)
                        #    )
                        cursor.execute(*bank_statement_line.delete(
                            where=bank_statement_line.move_line == move_line.id)
                        )
                #Se elimina el asiento
                #Move.draft([voucher.move.id])
                #Move.delete([voucher.move])
                if voucher.move:
                    cursor.execute(*account_move.delete(
                                where=account_move.id == voucher.move.id)
                        )
            #Se elimina el comprobante
            #Voucher.draft([voucher])
            #Voucher.delete([voucher])
            cursor.execute(*voucher_line_table.delete(
                where=voucher_line_table.voucher == voucher.id)
            )
            cursor.execute(*voucher_table.delete(
                where=voucher_table.id == voucher.id)
            )
    
    @classmethod
    def unreconcile_move(cls, move):
        Reconciliation = Pool().get('account.move.reconciliation')
        reconciliations = [l.reconciliation for l in move.lines if l.reconciliation]
        if reconciliations:
            Reconciliation.delete(reconciliations)

class VoucherConfiguration(metaclass=PoolMeta):
    'Voucher Configuration'
    __name__ = 'account.voucher_configuration'
    account_discount_tecno = fields.Many2One('account.account',
        'Account Discount for Conector TecnoCarnes', domain=[
            ('type', '!=', None),
        ])
    account_rete_tecno = fields.Many2One('account.tax',
    'Account Retention for Conector TecnoCarnes', domain=[
        ('type', '!=', None),
    ])
    account_retiva_tecno = fields.Many2One('account.tax',
    'Account Retention IVA for Conector TecnoCarnes', domain=[
        ('type', '!=', None),
    ])
    account_retica_tecno = fields.Many2One('account.tax',
    'Account Retention ICA for Conector TecnoCarnes', domain=[
        ('type', '!=', None),
    ])


class MultiRevenue(metaclass=PoolMeta):
    'MultiRevenue'
    __name__ = 'account.multirevenue'
    id_tecno = fields.Char('Id Tabla Sqlserver', required=False)


class DeleteVoucherTecno(Wizard):
    'Delete Voucher Tecno'
    __name__ = 'account.voucher.delete_voucher_tecno'
    start_state = 'do_submit'
    do_submit = StateTransition()

    def transition_do_submit(self):
        pool = Pool()
        Voucher = pool.get('account.voucher')
        ids = Transaction().context['active_ids']

        to_delete = []
        for voucher in Voucher.browse(ids):
            rec_name = voucher.rec_name
            party_name = voucher.party.name
            rec_party = rec_name+' de '+party_name
            if voucher.number and '-' in voucher.number and voucher.id_tecno:
                to_delete.append(voucher)
            else:
                raise UserError("Revisa el número del comprobante (tipo-numero): ", rec_party)
        Voucher.delete_imported_vouchers(to_delete)
        return 'end'

    def end(self):
        return 'reload'