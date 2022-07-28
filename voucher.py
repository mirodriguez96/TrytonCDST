from trytond.model import ModelView, ModelSQL, fields
from trytond.pool import Pool, PoolMeta
from trytond.exceptions import UserError
from decimal import Decimal
import logging
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
        Module = pool.get('ir.module')
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
                created.append(id_tecno)
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
                msg = f"NO SE ENCONTRO FORMA(S) DE PAGO EN TECNOCARNES (DOCUMENTOS_CHE) PARA EL DOCUMENTO {id_tecno}"
                logs.append(msg)
                logging.error(msg)
                continue
            #for pago in tipo_pago: 
            paymode = PayMode.search([('id_tecno', '=', tipo_pago[0].forma_pago)]) # REVISAR CRITICO ¿CUANDO HAY MAS DE 1 FORMA DE PAGO?
            if not paymode:
                msg = f"NO SE ENCONTRO LA FORMA DE PAGO {tipo_pago[0].forma_pago}"
                logs.append(msg)
                logging.error(msg)
                continue
            print('VOUCHER EGRESO:', id_tecno)
            fecha_date = cls.convert_fecha_tecno(doc.fecha_hora)
            voucher = Voucher()
            voucher.id_tecno = id_tecno
            voucher.number = tipo_numero
            voucher.reference = tipo_numero
            voucher.party = party
            voucher.payment_mode = paymode[0]
            voucher.on_change_payment_mode()
            voucher.voucher_type = 'payment'
            voucher.date = fecha_date
            nota = (doc.notas).replace('\n', ' ').replace('\r', '')
            if nota:
                voucher.description = nota
            if hasattr(voucher, 'operation_center'):
                operation_center = pool.get('company.operation_center')(1)
                voucher.operation_center = operation_center
            valor_aplicado = Decimal(doc.valor_aplicado)
            lines = cls.get_lines_vtecno(facturas, voucher, logs)
            if lines:
                voucher.lines = lines
                voucher.on_change_lines()
            #Se verifica que el comprobante tenga lineas para ser procesado y contabilizado (doble verificación por error)
            if voucher.lines and voucher.amount_to_pay > 0:
                Voucher.process([voucher])
                diferencia = abs(voucher.amount_to_pay - valor_aplicado)
                if voucher.amount_to_pay == valor_aplicado:
                    Voucher.post([voucher])
                elif diferencia < Decimal(60):
                    config_voucher = pool.get('account.voucher_configuration')(1)
                    line_ajuste = Line()
                    line_ajuste.voucher = voucher
                    line_ajuste.detail = 'AJUSTE'
                    line_ajuste.account = config_voucher.account_adjust_expense
                    line_ajuste.amount = diferencia
                    if hasattr(line_ajuste, 'operation_center'):
                        operation_center = pool.get('company.operation_center')(1)
                        line_ajuste.operation_center = operation_center
                    line_ajuste.save()
                    voucher.on_change_lines()
                    Voucher.post([voucher])
            voucher.save()
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
        Module = pool.get('ir.module')
        Voucher = pool.get('account.voucher')
        Line = pool.get('account.voucher.line')
        Party = pool.get('party.party')
        PayMode = pool.get('account.voucher.paymode')
        MultiRevenue = pool.get('account.multirevenue')
        MultiRevenueLine = pool.get('account.multirevenue.line')
        Transaction = pool.get('account.multirevenue.transaction')
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
                created.append(id_tecno)
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
                msg = f"NO SE ENCONTRO FORMA(S) DE PAGO EN TECNOCARNES (DOCUMENTOS_CHE) PARA EL DOCUMENTO {id_tecno}"
                logs.append(msg)
                logging.error(msg)
                continue            
            fecha_date = cls.convert_fecha_tecno(doc.fecha_hora)
            if len(tipo_pago) > 1:
                print('MULTI-INGRESO:', id_tecno)
                multingreso = MultiRevenue()
                multingreso.code = tipo+'-'+nro
                multingreso.party = tercero
                multingreso.date = fecha_date
                multingreso.id_tecno = id_tecno
                #Se ingresa las formas de pago (transacciones)
                to_transactions = []
                doble_fp = False
                for pago in tipo_pago:
                    paymode = PayMode.search([('id_tecno', '=', pago.forma_pago)])
                    if not paymode:
                        msg = f"NO SE ENCONTRO LA FORMA DE PAGO {pago.forma_pago}"
                        logs.append(msg)
                        logging.error(msg)
                        continue
                    for existr in to_transactions:
                        if existr.payment_mode == paymode[0]:
                            existr.amount += Decimal(pago.valor)
                            doble_fp = True
                            continue
                    if doble_fp:
                        doble_fp = False
                        continue
                    transaction = Transaction()
                    transaction.description = 'IMPORTACION TECNO'
                    transaction.amount = Decimal(pago.valor)
                    transaction.date = fecha_date
                    transaction.payment_mode = paymode[0]
                    to_transactions.append(transaction)
                if to_transactions:
                    multingreso.transactions = to_transactions
                #Se ingresa las lineas a pagar
                to_lines = []
                for rec in facturas:
                    ref = rec.tipo_aplica+'-'+str(rec.numero_aplica)
                    move_line = cls.get_moveline(ref, tercero, logs)
                    if move_line and rec.valor:
                        valor_pagado = Decimal(rec.valor + rec.descuento + rec.retencion + (rec.ajuste*-1) + rec.retencion_iva + rec.retencion_ica)
                        line = MultiRevenueLine()
                        line.move_line = move_line
                        amount_to_pay = Decimal(move_line.move.origin.amount_to_pay)
                        if valor_pagado > amount_to_pay:
                            valor_pagado = amount_to_pay
                        line.amount = valor_pagado
                        line.original_amount = amount_to_pay
                        line.is_prepayment = False
                        line.reference_document = ref
                        line.others_concepts = cls.get_others_tecno(rec, amount_to_pay)
                        to_lines.append(line)
                    else:
                        if doc.anulado == 'S':
                            msg = f'MULTI-INGRESO {id_tecno} ANULADO EN TECNOCARNES'
                            logging.warning(msg)
                            logs.append(msg)
                        else:
                            msg = f'NO SE ENCONTRO LA FACTURA {ref} EN TRYTON O REVISA SU VALOR {str(rec.valor)}. MULTI-INGRESO {id_tecno}'
                            logging.warning(msg)
                            logs.append(msg)
                if to_lines:
                    multingreso.lines = to_lines
                multingreso.save()
                if multingreso.transactions and multingreso.lines:
                    #device = SaleDevice.search([('id_tecno', '=', doc.pc)])
                    #if not device:
                    #    msg = f'NO SE ENCONTRO LA TERMINAL {doc.pc}'
                    #    logs.append(msg)
                    #    logging.error(msg)
                    #    continue
                    #MultiRevenue.add_statement(multingreso, device[0])
                    MultiRevenue.create_voucher_tecno(multingreso)
                else:
                    msg = f'REVISAR EL COMPROBANTE MULTI-INGRESO {id_tecno}'
                    logs.append(msg)
                created.append(id_tecno)
            elif len(tipo_pago) == 1:
                #continue
                print('VOUCHER:', id_tecno)
                forma_pago = tipo_pago[0].forma_pago
                paymode = PayMode.search([('id_tecno', '=', forma_pago)])
                if not paymode:
                    msg = f"NO SE ENCONTRO LA FORMA DE PAGO {forma_pago}"
                    logs.append(msg)
                    logging.error(msg)
                    continue
                voucher = Voucher()
                voucher.id_tecno = id_tecno
                voucher.number = tipo+'-'+nro
                voucher.reference = tipo+'-'+nro
                voucher.party = tercero
                voucher.payment_mode = paymode[0]
                voucher.on_change_payment_mode()
                voucher.voucher_type = 'receipt'
                voucher.date = fecha_date
                nota = (doc.notas).replace('\n', ' ').replace('\r', '')
                if nota:
                    voucher.description = nota
                company_operation = Module.search([('name', '=', 'company_operation'), ('state', '=', 'activated')])
                if company_operation:
                    operation_center = pool.get('company.operation_center')(1)
                    voucher.operation_center = operation_center
                valor_aplicado = Decimal(doc.valor_aplicado)
                lines = cls.get_lines_vtecno(facturas, voucher, logs)
                if lines:
                    voucher.lines = lines
                    voucher.on_change_lines()
                    #if company_operation:
                    #    voucher.on_change_operation_center()
                voucher.save()
                #Se verifica que el comprobante tenga lineas para ser procesado y contabilizado (doble verificación por error)
                if voucher.lines and voucher.amount_to_pay > 0:
                    Voucher.process([voucher])
                    diferencia = abs(voucher.amount_to_pay - valor_aplicado)
                    #print(diferencia, (diferencia < Decimal(6.0)))
                    if voucher.amount_to_pay == valor_aplicado:
                        Voucher.post([voucher])
                    elif diferencia < Decimal(60):
                        config_voucher = pool.get('account.voucher_configuration')(1)
                        line_ajuste = Line()
                        line_ajuste.voucher = voucher
                        line_ajuste.detail = 'AJUSTE'
                        line_ajuste.account = config_voucher.account_adjust_income
                        line_ajuste.amount = diferencia
                        if company_operation:
                            operation_center = pool.get('company.operation_center')(1)
                            line_ajuste.operation_center = operation_center
                        line_ajuste.save()
                        voucher.on_change_lines()
                        Voucher.post([voucher])
                    voucher.save()
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
    def get_moveline(cls, reference, party, logs):
        pool = Pool()
        Invoice = pool.get('account.invoice')
        MoveLine = pool.get('account.move.line')
        #A continuacion se consulta las lineas a pagar de la factura (reference)
        invoice = Invoice.search([('number', '=', reference),('state', '=', 'posted')])
        if invoice:
            # Se selecciona la primera linea pendiente por pagar
            return invoice[0].lines_to_pay[0]
        line_domain = ['AND',
            ('reference', '=', reference),
            ('party', '=', party),
            ['OR',
                ('account.type.payable', '=', True),
                ('account.type.receivable', '=', True),
            ]
        ]
        #Si no encuentra lineas a pagar... Se busca en saldos iniciales
        moveline = MoveLine.search(line_domain)
        if moveline:
            if len(moveline) > 1:
                msg = f"Esperaba unica referencia ({reference}) en linea de movimiento (saldos iniciales) y obtuvo muchas !"
                logs.append(msg)
                return False
            #print("SALDOS INICIALES")
            return moveline[0]
        else:
            return False

    @classmethod
    def get_amounts_to_pay(cls, moveline, voucher_type):
        amount = moveline.credit or moveline.debit
        if voucher_type == 'receipt':
            if moveline.credit > Decimal('0'):
                amount = -amount
        else:
            if moveline.debit > Decimal('0'):
                amount = -amount
        # Valor a pagar
        amount_to_pay = Decimal(0)
        untaxed_amount = Decimal(0)
        if moveline.move_origin and hasattr(moveline.move_origin, '__name__') and moveline.move_origin.__name__ == 'account.invoice':
            amount_to_pay = moveline.move.origin.amount_to_pay
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
                return multirevenue
            else:
                return False


    @classmethod
    def get_lines_vtecno(cls, facturas, voucher, logs):
        pool = Pool()
        Module = pool.get('ir.module')
        Line = pool.get('account.voucher.line')
        config_voucher = pool.get('account.voucher_configuration')(1)
        to_lines = []
        for rec in facturas:
            ref = rec.tipo_aplica+'-'+str(rec.numero_aplica)
            move_line = cls.get_moveline(ref, voucher.party, logs)
            if not move_line:
                msg = f'NO SE ENCONTRO LA FACTURA {ref} EN TRYTON'
                logging.warning(msg)
                logs.append(msg)
                continue
            #print(ref)
            valor_original, amount_to_pay, untaxed_amount = cls.get_amounts_to_pay(move_line, voucher.voucher_type)
            #print(valor_original, amount_to_pay, untaxed_amount)
            line = Line()
            line.amount_original = valor_original
            line.reference = ref
            line.move_line = move_line
            line.on_change_move_line()
            company_operation = Module.search([('name', '=', 'company_operation'), ('state', '=', 'activated')])
            if company_operation:
                operation_center = pool.get('company.operation_center')(1)
                line.operation_center = operation_center
            valor = Decimal(rec.valor)
            descuento = Decimal(rec.descuento)
            retencion = Decimal(rec.retencion)
            ajuste = Decimal(rec.ajuste)
            retencion_iva = Decimal(rec.retencion_iva)
            retencion_ica = Decimal(rec.retencion_ica)
            valor_pagado = valor + descuento + retencion + (ajuste*-1) + retencion_iva + retencion_ica
            valor_pagado = round(valor_pagado, 2)
            if valor_pagado > amount_to_pay:
                valor_pagado = amount_to_pay
            line.amount = Decimal(valor_pagado)
            to_lines.append(line)
            # Se crean lineas adicionales en el comprobante en caso de ser necesario
            if descuento > 0:
                line_discount = Line()
                line_discount.party = move_line.party
                line_discount.reference = ref
                line_discount.detail = 'DESCUENTO'
                line_discount.amount = round((descuento * -1), 2)
                line_discount.account = config_voucher.account_discount_tecno
                if company_operation:
                    operation_center = pool.get('company.operation_center')(1)
                    line_discount.operation_center = operation_center
                to_lines.append(line_discount)
            if retencion > 0:
                line_rete = Line()
                line_rete.party = move_line.party
                line_rete.reference = ref
                line_rete.detail = 'RETENCION - ('+str(retencion)+')'
                line_rete.type = 'tax'
                line_rete.untaxed_amount = untaxed_amount
                line_rete.tax = config_voucher.account_rete_tecno
                line_rete.on_change_tax()
                line_rete.amount = round((retencion*-1), 2)
                if company_operation:
                    operation_center = pool.get('company.operation_center')(1)
                    line_rete.operation_center = operation_center
                to_lines.append(line_rete)
            if retencion_iva > 0:
                line_retiva = Line()
                line_retiva.party = move_line.party
                line_retiva.reference = ref
                line_retiva.detail = 'RETENCION IVA - ('+str(retencion_iva)+')'
                line_retiva.type = 'tax'
                line_retiva.untaxed_amount = untaxed_amount
                line_retiva.tax = config_voucher.account_retiva_tecno
                line_retiva.on_change_tax()
                line_retiva.amount = round((retencion_iva*-1), 2)
                if company_operation:
                    operation_center = pool.get('company.operation_center')(1)
                    line_retiva.operation_center = operation_center
                to_lines.append(line_retiva)
            if retencion_ica > 0:
                line_retica = Line()
                line_retica.party = move_line.party
                line_retica.reference = ref
                line_retica.detail = 'RETENCION ICA - ('+str(retencion_ica)+')'
                line_retica.type = 'tax'
                line_retica.untaxed_amount = untaxed_amount
                line_retica.tax = config_voucher.account_retica_tecno
                line_retica.on_change_tax()
                line_retica.amount = round((retencion_ica*-1), 2)
                if company_operation:
                    operation_center = pool.get('company.operation_center')(1)
                    line_retica.operation_center = operation_center
                to_lines.append(line_retica)
            if ajuste > 0:
                line_ajuste = Line()
                line_ajuste.party = move_line.party
                line_ajuste.reference = ref
                line_ajuste.detail = 'AJUSTE'
                if Decimal(move_line.debit) > 0:
                    line_ajuste.account = config_voucher.account_adjust_income
                elif Decimal(move_line.credit) > 0:
                    line_ajuste.account = config_voucher.account_adjust_expense
                line_ajuste.amount = round(ajuste, 2)
                if company_operation:
                    operation_center = pool.get('company.operation_center')(1)
                    line_ajuste.operation_center = operation_center
                to_lines.append(line_ajuste)
        return to_lines


    @classmethod
    def get_others_tecno(cls, rec, original_amount):
        pool = Pool()
        OthersConcepts = pool.get('account.multirevenue.others_concepts')
        config_voucher = pool.get('account.voucher_configuration')(1)
        valor = Decimal(rec.valor)
        descuento = Decimal(rec.descuento)
        retencion = Decimal(rec.retencion)
        ajuste = Decimal(rec.ajuste)
        retencion_iva = Decimal(rec.retencion_iva)
        retencion_ica = Decimal(rec.retencion_ica)
        valor_pagado = valor + descuento + retencion + (ajuste*-1) + retencion_iva + retencion_ica
        to_others = []
        if descuento > 0:
            line_discount = OthersConcepts()
            line_discount.description = 'DESCUENTO'
            line_discount.amount = round((descuento * -1), 2)
            line_discount.account = config_voucher.account_discount_tecno
            to_others.append(line_discount)
            valor_pagado += line_discount.amount
        if retencion > 0:
            line_rete = OthersConcepts()
            line_rete.description = 'RETENCION'
            line_rete.account = config_voucher.account_adjust_income #se añade cualquier cuenta
            line_rete.amount = round((retencion*-1), 2)
            to_others.append(line_rete)
            valor_pagado += line_rete.amount
        if retencion_iva > 0:
            line_retiva = OthersConcepts()
            line_retiva.description = 'RETIVA:'
            line_retiva.account = config_voucher.account_adjust_income #se añade cualquier cuenta
            line_retiva.amount = round((retencion_iva*-1), 2)
            to_others.append(line_retiva)
            valor_pagado += line_retiva.amount
        if retencion_ica > 0:
            line_retica = OthersConcepts()
            line_retica.description = 'RETICA'
            line_retica.account = config_voucher.account_adjust_income #se añade cualquier cuenta
            line_retica.amount = round((retencion_ica*-1), 2)
            to_others.append(retencion_ica)
            valor_pagado += line_retica.amount
        if ajuste > 0:
            line_ajuste = OthersConcepts()
            line_ajuste.description = 'AJUSTE'
            line_ajuste.account = config_voucher.account_adjust_income
            line_ajuste.amount = round(ajuste, 2)
            to_others.append(line_ajuste)
            valor_pagado += line_ajuste.amount
        #Se verifica si la diferencia es minima para llevarla a un ajuste
        difference = (original_amount - valor_pagado)
        if difference != 0 and abs(difference) < 50:
            line_ajuste = OthersConcepts()
            line_ajuste.description = 'REDONDEO'
            line_ajuste.account = config_voucher.account_adjust_income
            line_ajuste.amount = Decimal(difference * -1)
            to_others.append(line_ajuste)
        return to_others

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
        #consult = "SELECT * FROM dbo.Documentos WHERE sw = 5 AND tipo = 117 AND Numero_documento = 3309" #TEST
        consult = "SET DATEFORMAT ymd SELECT TOP(10) * FROM dbo.Documentos WHERE sw = 5 AND fecha_hora >= CAST('"+fecha+"' AS datetime) AND exportado != 'T' ORDER BY fecha_hora ASC"
        data = Config.get_data(consult)
        return data

    #Esta función se encarga de traer todos los datos de una tabla dada de acuerdo al rango de fecha dada de la bd TecnoCarnes
    @classmethod
    def get_data_tecno_out(cls):
        Config = Pool().get('conector.configuration')
        config = Config(1)
        fecha = config.date.strftime('%Y-%m-%d %H:%M:%S')
        #consult = "SET DATEFORMAT ymd SELECT * FROM dbo.Documentos WHERE sw = 6 AND fecha_hora >= CAST('"+fecha+"' AS datetime) AND exportado != 'T' AND tipo = 149" #TEST
        consult = "SET DATEFORMAT ymd SELECT TOP(10) * FROM dbo.Documentos WHERE sw = 6 AND fecha_hora >= CAST('"+fecha+"' AS datetime) AND exportado != 'T' ORDER BY fecha_hora ASC"
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

    
    @classmethod
    def unreconcilie_move_voucher(cls, vouchers):
        pool = Pool()
        Reconciliation = pool.get('account.move.reconciliation')
        Move = pool.get('account.move')
        to_unreconcilie = []
        for voucher in vouchers:
            if voucher.move:
                to_unreconcilie.append(voucher.move)
        for move in to_unreconcilie:
            reconciliations = [l.reconciliation for l in move.lines if l.reconciliation]
            if reconciliations:
                Reconciliation.delete(reconciliations)
            Move.draft([move.id])

    @classmethod
    def force_draft_voucher(cls, vouchers):
        pool = Pool()
        Voucher = pool.get('account.voucher')
        Move = pool.get('account.move')
        for voucher in vouchers:
            if voucher.move:
                Move.draft([voucher.move.id])
                Move.delete([voucher.move])
            voucher.number = None
        Voucher.draft(vouchers)
        Voucher.save(vouchers)
        

    @classmethod
    def delete_imported_vouchers(cls, vouchers):
        pool = Pool()
        Voucher = pool.get('account.voucher')
        Conexion = pool.get('conector.configuration')
        ids_tecno = []
        for voucher in vouchers:
            ids_tecno.append(voucher.id_tecno)
            cls.force_draft_voucher([voucher])
        Voucher.delete(vouchers)
        # Se marca en la base de datos de importación como NO exportado y se elimina
        for idt in ids_tecno:
            Conexion.update_exportado(idt, 'S')


# Se añaden campos relacionados con las retenciones aplicadas en TecnoCarnes
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

    @classmethod
    def create_voucher_tecno(cls, multirevenue):
        voucher_to_create = {}
        pool = Pool()
        Voucher = pool.get('account.voucher')
        operation_center = pool.get('company.operation_center')(1)
        config_voucher = pool.get('account.voucher_configuration')(1)
        line_paid = []
        concept_ids = []
        for transaction in multirevenue.transactions:
            payment_mode = transaction.payment_mode
            amount_tr = transaction.amount
            for line in multirevenue.lines:
                if line.id in line_paid or not line.amount:
                    continue
                # Se crea el diccionario de los vouchers por crear
                if transaction.id not in voucher_to_create.keys():
                    voucher_to_create[transaction.id] = {}
                if line.id not in voucher_to_create[transaction.id].keys():
                    voucher_to_create[transaction.id][line.id] = {
                        'party': line.origin.party.id,
                        'company': multirevenue.company.id,
                        'voucher_type': 'receipt',
                        'date': transaction.date,
                        'description': f"MULTI-INGRESO FACTURA {line.origin.number}",
                        'reference': multirevenue.code,
                        'payment_mode': payment_mode.id,
                        'state': 'draft',
                        'account': payment_mode.account.id,
                        'journal': payment_mode.journal.id,
                        'lines': [('create', [])],
                        'method_counterpart': 'one_line',
                        'operation_center': operation_center.id,
                    }
                # Se procede a comparar el total de cada factura
                concept_amounts = 0
                for concept in line.others_concepts:
                    if concept.id in concept_ids:
                        continue
                    c_line = {
                        'party': line.origin.party.id,
                        'reference': line.origin.reference,
                        'detail': concept.description,
                        'amount': concept.amount,
                        'operation_center': operation_center.id
                    }
                    if concept.description == 'RETENCION':
                        c_line['untaxed_amount'] = line.original_amount
                        c_line['type'] = 'tax'
                        c_line['tax'] = config_voucher.account_rete_tecno.id
                        c_line['account'] = config_voucher.account_rete_tecno.invoice_account.id
                    elif concept.description == 'RETIVA':
                        c_line['untaxed_amount'] = line.original_amount
                        c_line['type'] = 'tax'
                        c_line['tax'] = config_voucher.account_retiva_tecno.id
                        c_line['account'] = config_voucher.account_retiva_tecno.invoice_account.id
                    elif concept.description == 'RETICA':
                        c_line['untaxed_amount'] = line.original_amount
                        c_line['type'] = 'tax'
                        c_line['tax'] = config_voucher.account_retica_tecno.id
                        c_line['account'] = config_voucher.account_retica_tecno.invoice_account.id
                    else:
                        c_line['account'] = concept.account.id
                    voucher_to_create[transaction.id][line.id]['lines'][0][1].append(c_line)
                    concept_amounts += concept.amount
                    concept_ids.append(concept.id)
                net_payment = line.amount + concept_amounts
                if net_payment < amount_tr:
                    _line_amount = line.amount
                    amount_tr -= net_payment
                    line_paid.append(line.id)
                else:
                    _line_amount = amount_tr + abs(concept_amounts)
                    line.amount = line.amount - _line_amount
                    amount_tr = 0
                if line.move_line:
                    move_line = line.move_line
                    origin_number = line.origin.number if line.origin else None
                    total_amount = line.origin.total_amount if line.origin and line.origin.__name__ == 'account.invoice' else move_line.amount
                    if _line_amount > total_amount: # Se valida que el pago no sea mayor
                        _line_amount = total_amount
                    voucher_to_create[transaction.id][line.id]['lines'][0][1].append({
                        'detail': origin_number or move_line.reference or move_line.description,
                        'amount': _line_amount,
                        'amount_original': total_amount,
                        'move_line': move_line.id,
                        'account': move_line.account.id,
                        'operation_center': operation_center.id
                    })
                else:
                    detail_ = line.reference_document
                    account_id = line.account.id if line.account else None
                    if not account_id:
                        raise UserError('account_voucher.msg_without_account')
                    if line.is_prepayment:
                        detail_ = 'ANTICIPO'
                    voucher_to_create[transaction.id][line.id]['lines'][0][1].append({
                        'detail': detail_,
                        'amount': _line_amount,
                        'account':  account_id,
                    })
                if amount_tr == 0:
                    break
        for key in voucher_to_create.keys():
            for line_id in voucher_to_create[key]:
                voucher, = Voucher.create([voucher_to_create[key][line_id]])
                voucher.on_change_lines()
                Voucher.process([voucher])
                if voucher.amount_to_pay > Decimal("0.0"):
                    Voucher.post([voucher])


    #Reimportar multi-ingresos
    @classmethod
    def mark_rimport(cls, multirevenue):
        pool = Pool()
        Conexion = pool.get('conector.configuration')
        MultiRevenue = pool.get('account.multirevenue')
        Line = pool.get('account.multirevenue.line')
        OthersConcepts = pool.get('account.multirevenue.others_concepts')
        Transaction = pool.get('account.multirevenue.transaction')
        Voucher = pool.get('account.voucher')
        ids_tecno = []
        for multi in multirevenue:
            ids_tecno.append(multi.id_tecno)
            vouchers = Voucher.search([('reference', '=', multi.code)])
            Voucher.force_draft_voucher(vouchers)
            Voucher.delete(vouchers)
            for line in multi.lines:
                OthersConcepts.delete(line.others_concepts)
            Line.delete(multi.lines)
            Transaction.delete(multi.transactions)
        MultiRevenue.delete(multirevenue)
        for idt in ids_tecno:
            Conexion.update_exportado(idt, 'S')