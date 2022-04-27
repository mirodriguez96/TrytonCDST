from trytond.model import ModelView, ModelSQL, fields
from trytond.pool import Pool, PoolMeta
from trytond.exceptions import UserError
from trytond.transaction import Transaction
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
            ('account.voucher|import_voucher', "Importar comprobantes de ingreso"),
            )
        cls.method.selection.append(
            ('account.voucher|import_voucher_payment', "Importar comprobantes de egreso"),
            )


#Heredamos del modelo sale.sale para agregar el campo id_tecno
class Voucher(ModelSQL, ModelView):
    'Voucher'
    __name__ = 'account.voucher'
    id_tecno = fields.Char('Id Tabla Sqlserver', required=False)


    @classmethod
    def import_voucher_payment(cls):
        logging.warning("RUN COMPROBANTES DE EGRESO")
        pool = Pool()
        Actualizacion = pool.get('conector.actualizacion')
        actualizacion = Actualizacion.create_or_update('COMPROBANTES DE EGRESO')
        # Obtenemos los comprobantes de egreso de TecnoCarnes
        documentos = cls.get_data_tecno_out()
        if not documentos:
            actualizacion.save()
            logging.warning("FINISH COMPROBANTES DE EGRESO")
            return
        Voucher = pool.get('account.voucher')
        Line = pool.get('account.voucher.line')
        Party = pool.get('party.party')
        PayMode = pool.get('account.voucher.paymode')
        logs = []
        created = []
        # Comenzamos a recorrer los documentos a procesar y almacenamos los registros y creados en una lista
        for doc in documentos:
            sw = str(doc.sw)
            nro = str(doc.Numero_documento)
            tipo_numero = doc.tipo+'-'+nro
            id_tecno = sw+'-'+tipo_numero
            # Buscamos si ya existe el comprobante
            comprobante = Voucher.search([('id_tecno', '=', id_tecno)])
            if comprobante:
                msg = f"EL DOCUMENTO {id_tecno} YA EXISTIA EN TRYTON"
                logs.append(msg)
                continue
            facturas = cls.get_dcto_cruce("sw="+sw+" and tipo="+doc.tipo+" and numero="+nro)
            if not facturas:
                msg1 = f"NO HAY FACTURAS EN TECNOCARNES PARA EL RECIBO {id_tecno}"
                logging.warning(msg1)
                logs.append(msg1)
                continue
            nit_cedula = doc.nit_Cedula
            party = Party.search([('id_number', '=', nit_cedula)])
            if not party:
                msg = f"EL TERCERO {nit_cedula} NO EXISTE EN TRYTON"
                logs.append(msg)
                logging.error(msg)
                continue
            party, = party
            tipo_pago = cls.get_tipo_pago(sw, doc.tipo, nro)
            if not tipo_pago:
                msg = f"NO SE ENCONTRO LA FORMA DE PAGO EN LA TABLA DOCUMENTOS_CHE {id_tecno}"
                logs.append(msg)
                logging.error(msg)
                continue
            forma_pago = tipo_pago[0].forma_pago
            paymode = PayMode.search([('id_tecno', '=', forma_pago)])
            if not paymode:
                msg = f"NO SE ENCONTRO LA FORMA DE PAGO {forma_pago}"
                logs.append(msg)
                logging.error(msg)
                continue
            paymode, = paymode
            print('VOUCHER:', id_tecno)
            fecha_date = cls.convert_fecha_tecno(doc.fecha_hora)
            voucher = Voucher()
            voucher.id_tecno = id_tecno
            voucher.number = tipo_numero
            voucher.party = party
            voucher.payment_mode = paymode
            voucher.on_change_payment_mode()
            voucher.voucher_type = 'payment'
            voucher.date = fecha_date
            nota = (doc.notas).replace('\n', ' ').replace('\r', '')
            if nota:
                voucher.description = nota
            voucher.reference = tipo_numero
            voucher.save()
            valor_aplicado = Decimal(doc.valor_aplicado)
            
            for rec in facturas:
                ref = rec.tipo_aplica+'-'+str(rec.numero_aplica)
                move_line = cls.get_moveline(ref, party)
                if not move_line:
                    msg1 = f'NO SE ENCONTRO LA FACTURA {ref} EN TRYTON'
                    logging.warning(msg1)
                    logs.append(msg1)
                    continue
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
                config_voucher = pool.get('account.voucher_configuration')(1)
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
                if voucher.amount_to_pay == valor_aplicado:
                    Voucher.post([voucher])
                elif diferencia < Decimal(600.0):
                    line_ajuste = Line()
                    line_ajuste.voucher = voucher
                    line_ajuste.detail = 'AJUSTE'
                    line_ajuste.account = config_voucher.account_adjust_expense
                    line_ajuste.amount = diferencia
                    line_ajuste.save()
                    voucher.on_change_lines()
                    Voucher.post([voucher])
            created.append(id_tecno)
        Actualizacion.add_logs(actualizacion, logs)
        for id in created:
            cls.importado(id)
            #print(id)
        logging.warning("FINISH COMPROBANTES DE EGRESO")


    #Funcion encargada de crear los comprobantes de ingreso
    @classmethod
    def import_voucher(cls):
        logging.warning("RUN COMPROBANTES DE INGRESO")
        pool = Pool()
        Actualizacion = pool.get('conector.actualizacion')
        actualizacion = Actualizacion.create_or_update('COMPROBANTES DE INGRESO')
        documentos_db = cls.get_data_tecno()
        if not documentos_db:
            actualizacion.save()
            logging.warning("FINISH COMPROBANTES DE INGRESO")
            return
        Voucher = pool.get('account.voucher')
        Line = pool.get('account.voucher.line')
        Party = pool.get('party.party')
        PayMode = pool.get('account.voucher.paymode')
        MultiRevenue = pool.get('account.multirevenue')
        MultiRevenueLine = pool.get('account.multirevenue.line')
        Transaction = pool.get('account.multirevenue.transaction')
        SaleDevice = pool.get('sale.device')
        logs = []
        created = []
        for doc in documentos_db:
            sw = str(doc.sw)
            tipo = doc.tipo
            nro = str(doc.Numero_documento)
            id_tecno = sw+'-'+tipo+'-'+nro
            comprobante = cls.find_voucher(sw+'-'+tipo+'-'+nro)
            if comprobante:
                msg = f"EL DOCUMENTO {id_tecno} YA EXISTIA EN TRYTON"
                logs.append(msg)
                continue
            facturas = cls.get_dcto_cruce("sw="+sw+" and tipo="+doc.tipo+" and numero="+nro)
            if not facturas:
                msg1 = f"NO HAY FACTURAS EN TECNOCARNES PARA EL RECIBO {id_tecno}"
                logging.warning(msg1)
                logs.append(msg1)
                continue
            tercero = Party.search([('id_number', '=', doc.nit_Cedula)])
            if not tercero:
                msg = f"EL TERCERO {doc.nit_Cedula} NO EXISTE EN TRYTON"
                logs.append(msg)
                logging.error(msg)
                continue
            tercero, = tercero
            #Se obtiene la forma de pago, según la tabla Documentos_Che de TecnoCarnes
            tipo_pago = cls.get_tipo_pago(sw, doc.tipo, nro)
            if not tipo_pago:
                msg = f"NO SE ENCONTRO LA FORMA DE PAGO EN LA TABLA DOCUMENTOS_CHE {id_tecno}"
                logs.append(msg)
                logging.error(msg)
                continue
            forma_pago = tipo_pago[0].forma_pago
            
            fecha_date = cls.convert_fecha_tecno(doc.fecha_hora)
            if len(tipo_pago) > 1:
                #continue
                print('MULTI-INGRESO:', id_tecno)
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
                    if move_line and rec.valor:
                        #valor pagado x la factura
                        valor = Decimal(rec.valor)
                        create_line = {
                            'multirevenue': multingreso.id,
                            'move_line': move_line.id,
                            'amount': valor,
                            'original_amount': move_line.debit,
                            'is_prepayment': False,
                            'reference_document': ref,
                        }
                        line, = MultiRevenueLine.create([create_line])
                        to_lines.append(line)
                    else:
                        msg = f'NO SE ENCONTRO LA FACTURA {ref} EN TRYTON'
                        logging.warning(msg)
                        logs.append(msg)
                if to_lines:
                    multingreso.lines = to_lines
                    multingreso.save()
                if multingreso.total_transaction and multingreso.total_lines_to_pay:
                    #if multingreso.total_transaction <= multingreso.total_lines_to_pay:
                        device = SaleDevice.search([('id_tecno', '=', doc.pc)])
                        if not device:
                            msg = f'NO SE ENCONTRO LA TERMINAL {doc.pc}'
                            logs.append(msg)
                            logging.error(msg)
                            continue
                        MultiRevenue.add_statement(multingreso, device[0])
                    #else:
                    #    msg1 = f'Total de pago es mayor al total a pagar en el multi-ingreso: {id_tecno}'
                    #    logs.append(msg1)
                else:
                    msg = f'REVISAR EL COMPROBANTE MULTI-INGRESO {id_tecno}'
                    logs.append(msg)
                created.append(id_tecno)
            elif len(tipo_pago) == 1:
                paymode = PayMode.search([('id_tecno', '=', forma_pago)])
                if not paymode:
                    msg = f"NO SE ENCONTRO LA FORMA DE PAGO {forma_pago}"
                    logs.append(msg)
                    logging.error(msg)
                    continue
                paymode, = paymode
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
                        msg = f'NO SE ENCONTRO LA FACTURA {ref} EN TRYTON'
                        logging.warning(msg)
                        logs.append(msg)
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
                    if voucher.amount_to_pay == valor_aplicado:
                        Voucher.post([voucher])
                    elif diferencia < Decimal(60.0):
                        line_ajuste = Line()
                        line_ajuste.voucher = voucher
                        line_ajuste.detail = 'AJUSTE'
                        line_ajuste.account = config_voucher.account_adjust_income
                        line_ajuste.amount = diferencia
                        line_ajuste.save()
                        voucher.on_change_lines()
                        Voucher.post([voucher])
                created.append(id_tecno)
            else:
                msg1 = f"EL DOCUMENTO {id_tecno} NO ENCONTRO FORMA DE PAGO EN TECNOCARNES"
                logging.warning(msg1)
                logs.append(msg1)
                continue
        Actualizacion.add_logs(actualizacion, logs)
        for id in created:
            cls.importado(id)
            #print('CREADO...', id) #TEST
        logging.warning("FINISH COMPROBANTES DE INGRESO")


    #Se obtiene las lineas de la factura que se desea pagar
    @classmethod
    def get_moveline(cls, reference, party):
        #print(reference)
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
                raise UserError("Error factura en saldos iniciales", "Esperaba una (reference) linea de movimiento y obtuvo muchas !")
            print("SALDOS INICIALES")
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
        Config.mark_imported(id)

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
    def get_data_tecno(cls):
        Config = Pool().get('conector.configuration')
        config = Config(1)
        fecha = config.date.strftime('%Y-%m-%d %H:%M:%S')
        #consult = "SET DATEFORMAT ymd SELECT TOP(50) * FROM dbo.Documentos WHERE sw = 5 AND fecha_hora >= CAST('"+fecha+"' AS datetime) AND exportado != 'T' ORDER BY fecha_hora ASC" #TEST
        consult = "SET DATEFORMAT ymd SELECT TOP(200) * FROM dbo.Documentos WHERE sw = 5 AND fecha_hora >= CAST('"+fecha+"' AS datetime) AND exportado != 'T' ORDER BY fecha_hora ASC"
        data = Config.get_data(consult)
        return data

    #Esta función se encarga de traer todos los datos de una tabla dada de acuerdo al rango de fecha dada de la bd TecnoCarnes
    @classmethod
    def get_data_tecno_out(cls):
        Config = Pool().get('conector.configuration')
        config = Config(1)
        fecha = config.date.strftime('%Y-%m-%d %H:%M:%S')
        #consult = "SET DATEFORMAT ymd SELECT * FROM dbo.Documentos WHERE sw = 6 AND fecha_hora >= CAST('"+fecha+"' AS datetime) AND exportado != 'T' AND tipo = 149" #TEST
        consult = "SET DATEFORMAT ymd SELECT TOP(200) * FROM dbo.Documentos WHERE sw = 6 AND fecha_hora >= CAST('"+fecha+"' AS datetime) AND exportado != 'T' ORDER BY fecha_hora ASC"
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
        
    #
    @classmethod
    def delete_imported_vouchers(cls, vouchers):
        bank_statement_line = Table('bank_statement_line_account_move_line')
        account_move = Table('account_move')
        voucher_table = Table('account_voucher')
        voucher_line_table = Table('account_voucher_line')
        cursor = Transaction().connection.cursor()
        Conexion = Pool().get('conector.configuration')

        for voucher in vouchers:
            # Se marca en la base de datos de importación como no exportado y se elimina
            lista = voucher.id_tecno.split('-')
            consult = "UPDATE dbo.Documentos SET exportado = 'S' WHERE exportado = 'T' and sw ="+lista[0]+" and tipo = "+lista[1]+" and Numero_documento = "+lista[2]
            Conexion.set_data(consult)

            if voucher.move:
                #Se requiere desconciliar el asiento antes de eliminarlo
                #cls.unreconcile_move(voucher.move)
                #Se verifica si hay lineas y se eliminan sus relaciones con la tabla bank_statement_line_account_move_line
                if voucher.move.lines:
                    for move_line in voucher.move.lines:
                        cursor.execute(*bank_statement_line.delete(
                            where=bank_statement_line.move_line == move_line.id)
                        )
                #Se elimina el asiento
                cursor.execute(*account_move.delete(
                            where=account_move.id == voucher.move.id)
                    )
            #Se elimina el comprobante y sus lineas
            cursor.execute(*voucher_line_table.delete(
                where=voucher_line_table.voucher == voucher.id)
            )
            cursor.execute(*voucher_table.delete(
                where=voucher_table.id == voucher.id)
            )


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

    #Función encargada de enviar las facturas a ser pagadas con su respectivo pago al estado de cuenta
    @classmethod
    def add_statement(cls, multirevenue, device):
        lines_to_add = {}
        pool = Pool()
        Sale = pool.get('sale.sale')
        #Statement = pool.get('account.statement')
        StatementeJournal = pool.get('account.statement.journal')
        lines_created = {}
        line_paid = []
        for transaction in multirevenue.transactions:
            statement_journal, = StatementeJournal.search([('id_tecno', '=', transaction.payment_mode.id_tecno)])
            args_statement = {
                'device': device,
                'date': transaction.date,
                'journal': statement_journal
            }
            statement, = Sale.search_or_create_statement(args_statement)
            amount_tr = transaction.amount
            lines_created[transaction.id] = {'ids': []}
            for line in multirevenue.lines:
                #Se valida que la linea no se haya 'pagado' o tenga un 'valor pagado'
                if line.id in line_paid or not line.amount:
                    continue
                if transaction.id not in lines_to_add.keys():
                    lines_to_add[transaction.id] = {'sales': {}}
                    lines_to_add[transaction.id]['statement'] = statement.id
                    lines_to_add[transaction.id]['date'] = transaction.date
                net_payment = line.amount
                if net_payment < amount_tr:
                    _line_amount = line.amount
                    amount_tr -= net_payment
                    line_paid.append(line.id)
                else:
                    _line_amount = amount_tr
                    line.amount = line.amount - _line_amount
                    amount_tr = 0
                if line.move_line:
                    sale, = line.origin.sales
                    lines_to_add[transaction.id]['sales'][sale] = _line_amount
                else:
                    raise UserError('multirevenue.msg_without_invoice')
                    lines_to_add[transaction.id]['sales'][line.origin.sales[0].id] = _line_amount
                lines_created[transaction.id]['ids'].append(line.id)
                if amount_tr == 0:
                    break
        for key in lines_to_add.keys():
            Sale.multipayment_invoices_statement(lines_to_add[key])
