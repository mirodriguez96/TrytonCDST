from trytond.model import ModelView, ModelSQL, fields
from trytond.pool import Pool, PoolMeta
from trytond.exceptions import UserError
from trytond.transaction import Transaction
from decimal import Decimal
import datetime
from sql import Table

_ZERO = Decimal('0.0')

#Heredamos del modelo sale.sale para agregar el campo id_tecno
class Voucher(ModelSQL, ModelView):
    'Voucher'
    __name__ = 'account.voucher'
    id_tecno = fields.Char('Id Tabla Sqlserver', required=False)
    # to_reconcile = fields.Function(fields.Boolean('To Reconcile'), 'getter_to_reconcile')

    # def getter_to_reconcile(self, name):
    #     if self.voucher_type != 'multipayment'\
    #         or self.state != 'posted'\
    #         or not self.move or len(self.lines) < 200:
    #         return False
    #     for line in self.move.lines:
    #         if line.account != self.account\
    #             and line.reconciliation:
    #             return False
    #     return True

    # Función encargada de importar los recibos (comprobantes) de egreso
    @classmethod
    def import_voucher_payment(cls):
        print("RUN COMPROBANTES DE EGRESO")
        pool = Pool()
        Config = pool.get('conector.configuration')
        configuration = Config.get_configuration()
        if not configuration:
            return
        Actualizacion = pool.get('conector.actualizacion')
        Voucher = pool.get('account.voucher')
        Line = pool.get('account.voucher.line')
        Party = pool.get('party.party')
        PayMode = pool.get('account.voucher.paymode')
        actualizacion = Actualizacion.create_or_update('COMPROBANTES DE EGRESO')
        logs = {}
        created = []
        exceptions = []
        not_import = []
        account_type = 'account.type.payable'
        # Obtenemos los comprobantes de egreso de TecnoCarnes
        documentos = Config.get_documentos_tecno('6')
        # Comenzamos a recorrer los documentos a procesar y almacenamos los registros y creados en una lista

        # tecno = {}
        # vouchers = {}
        # to_delete = []
        # for doc in documentos:
        #     id_tecno = f"{doc.sw}-{doc.tipo}-{doc.Numero_documento}"
        #     tecno[id_tecno] = doc
        # tryton_vouchers = Voucher.search([('id_tecno', 'in', tecno.keys())])
        # for tryton_voucher in tryton_vouchers:
        #     vouchers[tryton_voucher.id_tecno] = tryton_voucher
        # for id_tecno, doc in tecno.items():
        #     if id_tecno in vouchers and doc.anulado == 'S':
        #         to_delete.append(vouchers[id_tecno])
        #         msg = f"El documento {id_tecno} fue eliminado de tryton porque fue anulado en TecnoCarnes"
        #         logs[id_tecno] = msg
        #         not_import.append(id_tecno)
        #         continue
        #     elif id_tecno in vouchers and doc.anulado == 'N':
        #         created.append(id_tecno)
        #         continue
        # cls.unreconcilie_move_voucher(to_delete)
        # cls.force_draft_voucher(to_delete)
        # Voucher.delete(to_delete)

        parties = Party._get_party_documentos(documentos, 'nit_Cedula')
        for doc in documentos:
            try:
                tipo_numero = f"{doc.tipo}-{doc.Numero_documento}"
                id_tecno = f"{doc.sw}-{tipo_numero}"
                # Buscamos si ya existe el comprobante
                comprobante = cls.find_voucher(id_tecno)
                if comprobante:
                    if doc.anulado == 'S':
                        if comprobante.__name__ == 'account.voucher':
                            cls.unreconcilie_move_voucher([comprobante])
                            cls.force_draft_voucher([comprobante])
                            Voucher.delete([comprobante])
                            logs[id_tecno] = "El documento fue eliminado de tryton porque fue anulado en TecnoCarnes"
                            not_import.append(id_tecno)
                            continue
                    logs[id_tecno] = "EL DOCUMENTO YA EXISTE EN TRYTON"
                    created.append(id_tecno)
                    continue
                if doc.anulado == 'S':
                    logs[id_tecno] = "Documento ANULADO EN TECNOCARNES"
                    not_import.append(id_tecno)
                    continue
                facturas = Config.get_dctos_cruce(id_tecno)
                if not facturas:
                    exceptions.append(id_tecno)
                    logs[id_tecno] = "EXCEPCION: NO SE ENCONTRARON FACTURAS PARA EL PAGO (CRUCE)"
                    continue
                nit_cedula = doc.nit_Cedula.replace('\n',"")
                party = None
                if nit_cedula in parties['active']:
                    party = parties['active'][nit_cedula]
                if not party:
                    if nit_cedula not in parties['inactive']:
                        logs[id_tecno] = f"EXCEPCION: El tercero {nit_cedula} no existe en tryton"
                        exceptions.append(id_tecno)
                    continue
                tipo_pago = Config.get_tipos_pago(id_tecno)
                if not tipo_pago:
                    logs[id_tecno] = "EXCEPCION: NO SE ENCONTRO FORMA(S) DE PAGO EN TECNOCARNES (DOCUMENTOS_CHE)"
                    exceptions.append(id_tecno)
                    continue
                # REVISAR ¿CUANDO HAY MAS DE 1 FORMA DE PAGO?
                if len(tipo_pago) != 1:
                    msg = f"EXCEPCION {id_tecno} - se esperaba 1 forma de pago y se obtuvo {len(tipo_pago)}"
                    logs[id_tecno] = msg
                    exceptions.append(id_tecno)
                    continue
                #for pago in tipo_pago: 
                paymode = PayMode.search([('id_tecno', '=', tipo_pago[0].forma_pago)])
                if not paymode:
                    msg = f"EXCEPCION: NO SE ENCONTRO LA FORMA DE PAGO {tipo_pago[0].forma_pago}"
                    logs[id_tecno] = msg
                    exceptions.append(id_tecno)
                    continue
                print('VOUCHER EGRESO:', id_tecno)
                # fecha_date = cls.convert_fecha_tecno(doc.fecha_hora)
                fecha_date = cls.convert_fecha_tecno(tipo_pago[0].fecha)
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
                if hasattr(Voucher, 'operation_center'):
                    OperationCenter = pool.get('company.operation_center')
                    operation_center, = OperationCenter.search([], order=[('id', 'DESC')], limit=1)
                    voucher.operation_center = operation_center
                valor_aplicado = Decimal(doc.valor_aplicado)
                lines = cls.get_lines_vtecno(facturas, voucher, logs, account_type)
                if lines:
                    voucher.lines = lines
                    voucher.on_change_lines()
                else:
                    exceptions.append(id_tecno)
                    continue
                voucher.save()
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
                        if hasattr(Line, 'operation_center'):
                            OperationCenter = pool.get('company.operation_center')
                            operation_center, = OperationCenter.search([], order=[('id', 'DESC')], limit=1)
                            line_ajuste.operation_center = operation_center
                        line_ajuste.save()
                        voucher.on_change_lines()
                        Voucher.post([voucher])
                    voucher.save()
                created.append(id_tecno)
            except Exception as e:
                logs[id_tecno] = f"EXCEPCION: {str(e)}"
                exceptions.append(id_tecno)
        actualizacion.add_logs(logs)
        for idt in exceptions:
            Config.update_exportado(idt, 'E')
        for idt in created:
            Config.update_exportado(idt, 'T')
            #print(id)
        for idt in not_import:
            Config.update_exportado(idt, 'X')
            # print('not_import...', idt) #TEST
        print("FINISH COMPROBANTES DE EGRESO")


    # Funcion encargada de importar los recibos (comprobantes) de ingreso
    @classmethod
    def import_voucher(cls):
        print("RUN COMPROBANTES DE INGRESO")
        pool = Pool()
        Config = pool.get('conector.configuration')
        configuration = Config.get_configuration()
        if not configuration:
            return
        Actualizacion = pool.get('conector.actualizacion')
        #Module = pool.get('ir.module')
        Voucher = pool.get('account.voucher')
        Line = pool.get('account.voucher.line')
        Party = pool.get('party.party')
        PayMode = pool.get('account.voucher.paymode')
        MultiRevenue = pool.get('account.multirevenue')
        MultiRevenueLine = pool.get('account.multirevenue.line')
        Transaction = pool.get('account.multirevenue.transaction')
        OthersConcepts = pool.get('account.multirevenue.others_concepts')
        logs = {}
        created = []
        exceptions = []
        not_import = []
        actualizacion = Actualizacion.create_or_update('COMPROBANTES DE INGRESO')
        documentos_db = Config.get_documentos_tecno('5')
        account_type = 'account.type.receivable'
        parties = Party._get_party_documentos(documentos_db, 'nit_Cedula')
        for doc in documentos_db:
            try:
                sw = str(doc.sw)
                tipo = doc.tipo
                nro = str(doc.Numero_documento)
                id_tecno = sw+'-'+tipo+'-'+nro
                comprobante = cls.find_voucher(id_tecno)
                if comprobante:
                    if doc.anulado == 'S':
                        if comprobante.__name__ == 'account.voucher':
                            cls.unreconcilie_move_voucher([comprobante])
                            cls.force_draft_voucher([comprobante])
                            Voucher.delete([comprobante])
                        if comprobante.__name__ == 'account.multirevenue':
                            vouchers = Voucher.search([('reference', '=', comprobante.code)])
                            cls.unreconcilie_move_voucher(vouchers)
                            cls.force_draft_voucher(vouchers)
                            Voucher.delete(vouchers)
                            for line in comprobante.lines:
                                OthersConcepts.delete(line.others_concepts)
                            MultiRevenueLine.delete(comprobante.lines)
                            Transaction.delete(comprobante.transactions)
                            MultiRevenue.delete([comprobante])
                        logs[id_tecno] = "El documento fue eliminado de tryton porque fue anulado en TecnoCarnes"
                        not_import.append(id_tecno)
                        continue
                    logs[id_tecno] = "EL DOCUMENTO YA EXISTE EN TRYTON"
                    created.append(id_tecno)
                    continue
                if doc.anulado == 'S':
                    logs[id_tecno] = "Documento ANULADO EN TECNOCARNES"
                    not_import.append(id_tecno)
                    continue
                facturas = Config.get_dctos_cruce(id_tecno)
                if not facturas:
                    logs[id_tecno] = "EXCEPCION: NO HAY FACTURAS EN TECNOCARNES PARA EL RECIBO"
                    exceptions.append(id_tecno)
                    continue
                nit_cedula = doc.nit_Cedula.replace('\n',"")
                party = None
                if nit_cedula in parties['active']:
                    party = parties['active'][nit_cedula]
                if not party:
                    if nit_cedula not in parties['inactive']:
                        msg = f"EXCEPCION: El tercero {nit_cedula} no existe en tryton"
                        logs[id_tecno] = msg
                        exceptions.append(id_tecno)
                    continue
                #Se obtiene la forma de pago, según la tabla Documentos_Che de TecnoCarnes
                tipo_pago = Config.get_tipos_pago(id_tecno)
                if not tipo_pago:
                    logs[id_tecno] = "EXCEPCION: NO SE ENCONTRO FORMA(S) DE PAGO EN TECNOCARNES (DOCUMENTOS_CHE) PARA EL DOCUMENTO"
                    exceptions.append(id_tecno)
                    continue            
                # Comprobante con mas de 1 forma de pago (MULTI-INGRESO)
                if len(tipo_pago) > 1:
                    print('MULTI-INGRESO:', id_tecno)
                    fecha_date = cls.convert_fecha_tecno(doc.fecha_hora)
                    multingreso = MultiRevenue()
                    multingreso.code = tipo+'-'+nro
                    multingreso.party = party
                    multingreso.date = fecha_date
                    multingreso.id_tecno = id_tecno
                    # Se crea una lista con las formas de pago (transacciones)
                    to_transactions = []
                    # doble_fp = False
                    for pago in tipo_pago:
                        paymode = PayMode.search([('id_tecno', '=', pago.forma_pago)])
                        if not paymode:
                            msg = f"EXCEPCION: MULTI-INGRESO - NO SE ENCONTRO LA FORMA DE PAGO {pago.forma_pago}"
                            logs[id_tecno] = msg
                            exceptions.append(id_tecno)
                            break
                        # for existr in to_transactions:
                        #     if existr.payment_mode == paymode[0]:
                        #         existr.amount += Decimal(pago.valor) #
                        #         doble_fp = True
                        #         continue
                        # if doble_fp:
                        #     doble_fp = False
                        #     continue
                        fecha_date = cls.convert_fecha_tecno(pago.fecha)
                        transaction = Transaction()
                        transaction.description = 'IMPORTACION TECNO'
                        transaction.amount = Decimal(pago.valor)
                        transaction.date = fecha_date
                        transaction.payment_mode = paymode[0]
                        to_transactions.append(transaction)
                    if id_tecno in exceptions:
                        continue
                    multingreso.transactions = to_transactions
                    # Se crea una lista con las lineas (facturas) a pagar
                    to_lines = []
                    for factura in facturas:
                        reference = factura.tipo_aplica+'-'+str(factura.numero_aplica)
                        move_line = cls.get_moveline(reference, party, logs, account_type)
                        if move_line:
                            valor_pagado = Decimal(factura.valor + factura.descuento + factura.retencion + (factura.ajuste*-1) + factura.retencion_iva + factura.retencion_ica)
                            if valor_pagado and valor_pagado > 0:
                                line = MultiRevenueLine()
                                line.move_line = move_line
                                amount_to_pay = move_line.debit
                                if move_line.move.origin and move_line.move.origin.amount_to_pay:
                                    amount_to_pay = move_line.move.origin.amount_to_pay
                                if valor_pagado > amount_to_pay:
                                    valor_pagado = amount_to_pay
                                line.amount = valor_pagado
                                line.original_amount = amount_to_pay
                                line.is_prepayment = False
                                line.reference_document = reference
                                line.others_concepts = cls.get_others_tecno(factura, amount_to_pay)
                                to_lines.append(line)
                            else:
                                msg = f'EXCEPCION: MULTI-INGRESO - Valor erroneo ({factura.valor}) de la factura {reference}'
                                logs[id_tecno] = msg
                                exceptions.append(id_tecno)
                                break
                        else:
                            msg = f'EXCEPCION: MULTI-INGRESO - No se encontro la factura {reference} en Tryton'
                            logs[id_tecno] = msg
                            exceptions.append(id_tecno)
                            break
                    if id_tecno in exceptions:
                        continue
                    multingreso.lines = to_lines
                    multingreso.save()
                    MultiRevenue.create_voucher_tecno(multingreso)
                    created.append(id_tecno)
                # Comprobantes de ingreso (UNA SOLA FORMA DE PAGO)
                elif len(tipo_pago) == 1:
                    print('VOUCHER:', id_tecno)
                    forma_pago = tipo_pago[0].forma_pago
                    paymode = PayMode.search([('id_tecno', '=', forma_pago)])
                    if not paymode:
                        msg = f"EXCEPCION: NO SE ENCONTRO LA FORMA DE PAGO {forma_pago}"
                        logs[id_tecno] = msg
                        exceptions.append(id_tecno)
                        continue
                    fecha_date = cls.convert_fecha_tecno(tipo_pago[0].fecha)
                    voucher = Voucher()
                    voucher.id_tecno = id_tecno
                    voucher.number = tipo+'-'+nro
                    voucher.reference = tipo+'-'+nro
                    voucher.party = party
                    voucher.payment_mode = paymode[0]
                    voucher.on_change_payment_mode()
                    voucher.voucher_type = 'receipt'
                    voucher.date = fecha_date
                    nota = (doc.notas).replace('\n', ' ').replace('\r', '')
                    if nota:
                        voucher.description = nota
                    if hasattr(Voucher, 'operation_center'):
                        OperationCenter = pool.get('company.operation_center')
                        operation_center, = OperationCenter.search([], order=[('id', 'DESC')], limit=1)
                        voucher.operation_center = operation_center
                    valor_aplicado = Decimal(doc.valor_aplicado)
                    lines = cls.get_lines_vtecno(facturas, voucher, logs, account_type)
                    if lines:
                        voucher.lines = lines
                        voucher.on_change_lines()
                    else:
                        exceptions.append(id_tecno)
                        continue                    
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
                            if hasattr(Line, 'operation_center'):
                                OperationCenter = pool.get('company.operation_center')
                                operation_center, = OperationCenter.search([], order=[('id', 'DESC')], limit=1)
                                line_ajuste.operation_center = operation_center
                            line_ajuste.save()
                            voucher.on_change_lines()
                            Voucher.post([voucher])
                        voucher.save()
                    created.append(id_tecno)
                else:
                    exceptions.append(id_tecno)
                    logs[id_tecno] = "EXCEPCION: NO ENCONTRO FORMA DE PAGO EN TECNOCARNES"
                    continue
            except Exception as e:
                msg = f"EXCEPCION RECIBO {id_tecno} : {str(e)}"
                logs[id_tecno] = msg
                exceptions.append(id_tecno)
        actualizacion.add_logs(logs)
        for idt in exceptions:
            #print('EXCEPCIONES...', idt) #TEST
            Config.update_exportado(idt, 'E')
        for idt in created:
            Config.update_exportado(idt, 'T')
            #print('CREADO...', idt) #TEST
        for idt in not_import:
            Config.update_exportado(idt, 'X')
            # print('not_import...', idt) #TEST
        print("FINISH COMPROBANTES DE INGRESO")


    #Se obtiene las lineas de la factura que se desea pagar
    @classmethod
    def get_moveline(cls, reference, party, logs, account_type):
        pool = Pool()
        Invoice = pool.get('account.invoice')
        MoveLine = pool.get('account.move.line')
        #A continuacion se consulta las lineas a pagar de la factura (reference)
        invoice = Invoice.search([('number', '=', reference),('state', '=', 'posted')])
        if invoice:
            # Se selecciona la primera linea pendiente por pagar
            return invoice[0].lines_to_pay[0]
        line_domain = [
            ('reference', '=', reference),
            ('party', '=', party),
            (account_type, '=', True),
            ('reconciliation', '=', None),
            ('move.state', '=', 'posted')
        ]
        if account_type == 'account.type.receivable':
            line_domain.append(('debit', '>', 0))
        elif account_type == 'account.type.payable':
            line_domain.append(('credit', '>', 0))
        #Si no encuentra lineas a pagar... Se busca en saldos iniciales
        moveline = MoveLine.search(line_domain)
        if moveline:
            if len(moveline) > 1:
                msg = f"Esperaba unica referencia ({reference}) en linea de movimiento (saldos iniciales) y obtuvo muchas !"
                logs[reference] = msg
                return False
            if moveline[0].reconciliation:
                logs[reference] = f"REVISAR FACTURA ({reference}) CONCILIADA"
                return False
            return moveline[0]
        else:
            return False

    # Se obtiene el valor total a pagar de a cuerdo a línea de asiento
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


    #Metodo encargado de consultar y verificar si existe un comprobante de multi-ingreso con la id de la BD
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
                return multirevenue[0]
            else:
                return False

    # Función encargada de crear las diferentes líneas del comprobante
    @classmethod
    def get_lines_vtecno(cls, invoices, voucher, logs, account_type):
        pool = Pool()
        #Module = pool.get('ir.module')
        Line = pool.get('account.voucher.line')
        config_voucher = pool.get('account.voucher_configuration')(1)
        to_lines = []
        for inv in invoices:
            ref = inv.tipo_aplica+'-'+str(inv.numero_aplica)
            move_line = cls.get_moveline(ref, voucher.party, logs, account_type)
            if not move_line:
                msg = f"EXCEPCION: NO SE ENCONTRO LA FACTURA {ref} o REVISAR SI NO ESTA CONTABILIZADA EN TRYTON"
                logs[voucher.id_tecno] = msg
                return None
            #print(ref)
            valor_original, amount_to_pay, untaxed_amount = cls.get_amounts_to_pay(move_line, voucher.voucher_type)
            line = Line()
            line.amount_original = valor_original
            line.reference = ref
            line.move_line = move_line
            line.on_change_move_line()
            if hasattr(Line, 'operation_center'):
                OperationCenter = pool.get('company.operation_center')
                operation_center, = OperationCenter.search([], order=[('id', 'DESC')], limit=1)
                line.operation_center = operation_center
            valor = Decimal(inv.valor)
            descuento = Decimal(inv.descuento)
            retencion = Decimal(inv.retencion)
            ajuste = Decimal(inv.ajuste)
            retencion_iva = Decimal(inv.retencion_iva)
            retencion_ica = Decimal(inv.retencion_ica)
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
                if hasattr(Line, 'operation_center'):
                    OperationCenter = pool.get('company.operation_center')
                    operation_center, = OperationCenter.search([], order=[('id', 'DESC')], limit=1)
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
                if hasattr(Line, 'operation_center'):
                    OperationCenter = pool.get('company.operation_center')
                    operation_center, = OperationCenter.search([], order=[('id', 'DESC')], limit=1)
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
                if hasattr(Line, 'operation_center'):
                    OperationCenter = pool.get('company.operation_center')
                    operation_center, = OperationCenter.search([], order=[('id', 'DESC')], limit=1)
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
                if hasattr(Line, 'operation_center'):
                    OperationCenter = pool.get('company.operation_center')
                    operation_center, = OperationCenter.search([], order=[('id', 'DESC')], limit=1)
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
                if hasattr(Line, 'operation_center'):
                    OperationCenter = pool.get('company.operation_center')
                    operation_center, = OperationCenter.search([], order=[('id', 'DESC')], limit=1)
                    line_ajuste.operation_center = operation_center
                to_lines.append(line_ajuste)
        return to_lines

    # Función encargada de crear lineas de descuento, retencion, etc para los MULTI-INGRESOS
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
            to_others.append(line_retica)
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

    # Función encargada de desconciliar los asientos de los comprobantes
    @classmethod
    def unreconcilie_move_voucher(cls, vouchers):
        pool = Pool()
        Reconciliation = pool.get('account.move.reconciliation')
        moves = []
        reconciliations = None
        for voucher in vouchers:
            if voucher.move:
                moves.append(voucher.move)
        for move in moves:
            reconciliations = [l.reconciliation for l in move.lines if l.reconciliation]
            if reconciliations:
                Reconciliation.delete(reconciliations)
        return reconciliations

    # Función que se encarga de forzar a borrador los comprobantes
    @classmethod
    def force_draft_voucher(cls, vouchers):
        pool = Pool()
        Voucher = pool.get('account.voucher')
        move_table = Table('account_move')
        cursor = Transaction().connection.cursor()
        move_ids = []
        for voucher in vouchers:
            if voucher.move:
                move_ids.append(voucher.move.id)
            voucher.number = None
        if move_ids:
            cursor.execute(*move_table.update(
                columns=[move_table.state],
                values=['draft'],
                where=move_table.id.in_(move_ids)
            ))
            cursor.execute(*move_table.delete(
                where=move_table.id.in_(move_ids)
            ))
        Voucher.draft(vouchers)
        Voucher.save(vouchers)
        
    # Función encargada de reimportar los comprobantes que fueron previamente desconciliado
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
            Conexion.update_exportado(idt, 'N')


    @staticmethod
    def _check_cross_vouchers():
        print('RUN validar cruce de comprobantes')
        pool = Pool()
        Line = pool.get('account.voucher.line')
        Invoice = pool.get('account.invoice')
        MoveLine = pool.get('account.move.line')
        Reconciliation = pool.get('account.move.reconciliation')
        Actualizacion = pool.get('conector.actualizacion')
        actualizacion = Actualizacion.create_or_update(f'CRUCE DE COMPROBANTES')
        """
        Se realiza la búsqueda de las líneas de comprobantes que no tengan
        factura (línea de asiento) asociada para asignarse y luego conciliar
        """
        lines = Line.search([
            ('voucher.state', '=', 'posted'),
            ('reference', 'like', '%-%'),
            ('move_line', '=', None),
            [
                'OR',
                ('account.type.receivable', '=', True),
                ('account.type.payable', '=', True)
            ]
        ])
        """
        funcion encargada de obtener en las líneas del asiento 
        la perteneciente la línea del comprobante
        """
        def _get_move_line(line):
            for move_line in line.voucher.move.lines:
                if move_line.reference == line.reference and \
                    (move_line.account.type.receivable or move_line.account.type.payable):
                    return move_line
        logs = {}
        lines_invoice = {}
        for line in lines:
            if line.reference in lines_invoice:
                move_line = _get_move_line(line)
                lines_invoice[line.reference]['lines'].append(line)
                lines_invoice[line.reference]['move_lines'].append(move_line)
            else:
                move_line = _get_move_line(line)
                lines_invoice[line.reference] = {
                    'lines': [line],
                    'move_lines': [move_line]
                }
        invoices = Invoice.search([
            ('number', 'in', lines_invoice.keys()),
            ('state', '=', 'posted'),
        ])

        to_save = []
        for invoice in invoices:
            lines_to_pay = invoice.lines_to_pay
            # Se añade a las líneas del comprobante la línea de asienton de la factura
            lines = lines_invoice[invoice.number]['lines']
            Line.write(lines, {'move_line': lines_to_pay[0].id})
            # Se procede a agregar las líneas del comprobante junto con las líneas de pago de la factura
            move_lines = lines_invoice[invoice.number]['move_lines']
            payment_lines = list(invoice.payment_lines)
            for line in move_lines:
                if line and line not in payment_lines:
                    payment_lines.append(line)
            if len(payment_lines) > len(invoice.payment_lines):
                all_lines = list(lines_to_pay) + payment_lines
                # print(invoice, payment_lines)
                reconciliations = []
                amount = _ZERO
                for line in all_lines:
                    if line.reconciliation:
                        reconciliations.append(line.reconciliation)
                    amount += line.debit - line.credit
                # Se procede a validar si el total a pagar de la factura es valido
                if amount >= _ZERO:
                    invoice.payment_lines = payment_lines
                    to_save.append(invoice)
                    if amount == _ZERO:
                        Reconciliation.delete(reconciliations)
                        MoveLine.reconcile(all_lines)
                else:
                    msg = f"LA FACTURA CON ID {invoice} TIENE UN PAGO MAYOR "\
                        f"AL INTENTAR AGREGAR LA(S) LINEA(S) CRUCE {move_lines}"
                    logs[invoice.number] = msg
        Invoice.save(to_save)
        actualizacion.add_logs(logs)
        print('FINISH validar cruce de comprobantes')


    # def _reconcile_lines(self, to_reconcile):
    #     if self.voucher_type == 'multipayment' and\
    #         len(self.lines) > 200:
    #         return
    #     super(Voucher, self)._reconcile_lines(to_reconcile)


    # @classmethod
    # def _reconcile_multipayment(cls):
    #     MoveLine = Pool().get('account.move.line')
    #     multipayments = cls.search([
    #         ('voucher_type', '=', 'multipayment'),
    #         ('state', '=', 'posted')
    #     ])
    #     print(multipayments)
    #     for m in multipayments:
    #         if not m.to_reconcile:
    #             continue
    #         print(m.number)
    #         for line in m.lines:
    #             if not line.move_line:
    #                 continue
    #             sl = line.move_line
    #             if sl.reconciliation:
    #                 continue
    #             to_reconcile = []
    #             move_lines = MoveLine.search([
    #                 ('reconciliation', '=', None),
    #                 ('move', '=', m.move.id),
    #                 ('account', '=', sl.account.id),
    #                 ('party', '=', sl.party.id),
    #                 ('debit', '=', sl.credit),
    #             ])
    #             if move_lines:
    #                 to_reconcile = [sl, move_lines[0]]
    #             if to_reconcile:
    #                 print('to reconcile lines', to_reconcile)
    #                 MoveLine.reconcile(to_reconcile)


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
    adjustment_amount = fields.Numeric('Adjustment amount',
    digits=(16, 2),
    help="Enter the limit amount to make the adjustment of the invoices")


class MultiRevenue(metaclass=PoolMeta):
    'MultiRevenue'
    __name__ = 'account.multirevenue'
    id_tecno = fields.Char('Id Tabla Sqlserver', required=False)

    # Función encargada de crear los comprobantes de ingreso (idividuales) de acuerdo al multi-ingreso pasado por parametro
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
                        'party': line.move_line.party.id,
                        'company': multirevenue.company.id,
                        'voucher_type': 'receipt',
                        'date': transaction.date,
                        'description': f"MULTI-INGRESO FACTURA {line.reference_document}",
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
                        'party': line.move_line.party.id,
                        'reference': line.reference_document,
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
                voucher.save()
                Voucher.process([voucher])
                if voucher.amount_to_pay and voucher.amount_to_pay > 0:
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
            Conexion.update_exportado(idt, 'N')


class Note(metaclass=PoolMeta):
    __name__ = 'account.note'


    # Metodo encargado de crear notas contables para las facturas que requieren un ajuste para poder ser conciliadas
    @classmethod
    def create_adjustment_note (cls, data):
        pool = Pool()
        Period = pool.get('account.period')
        Config = pool.get('account.voucher_configuration')
        Note = pool.get('account.note')
        Line = pool.get('account.note.line')
        Invoice = pool.get('account.invoice')
        invoices = Invoice.search([('type', '=', data['invoice_type']), ('state', '=', 'posted'),('invoice_date', '>=',data['date_start']),('invoice_date', '<=', data['date_finish'])])
        # inv_adjustment = []
        inv_adjustment = [inv for inv in invoices if inv.amount_to_pay <= data['amount'] and inv.amount_to_pay > 0]
        # for inv in invoices:
        #     if inv.amount_to_pay <= data['amount'] and inv.amount_to_pay > 0:
        #         inv_adjustment.append(inv)
        if not inv_adjustment:
            return
        # Se procede a procesar las facturas que cumplen con la condicion
        config = Config.get_configuration()
        # print(len(new_inv_adjustment))
        print(len(inv_adjustment))
        for inv in inv_adjustment:
            lines_to_create = []
            print(inv)
            operation_center = None
            for ml in inv.move.lines:
                if ml.account == inv.account and (ml.account.type.payable or ml.account.type.receivable):
                    _line = Line()
                    _line.debit = ml.credit
                    _line.credit = ml.debit
                    _line.party = ml.party
                    _line.account = ml.account
                    _line.description = ml.description
                    _line.move_line = ml
                    if hasattr(ml, 'operation_center'):
                        if ml.operation_center:
                            operation_center = ml.operation_center
                            _line.operation_center = operation_center
                        else:
                            operation_center = pool.get('company.operation_center')(1)
                            _line.operation_center = operation_center
                    lines_to_create.append(_line)
            last_date = inv.invoice_date
            for pl in inv.payment_lines:
                _line = Line()
                _line.debit = pl.credit
                _line.credit = pl.debit
                _line.party = pl.party
                _line.account = pl.account
                _line.description = pl.description
                _line.move_line = pl
                if last_date:
                    if last_date < pl.date:
                        last_date = pl.date
                else:
                    last_date = pl.date
                if operation_center:
                    _line.operation_center = operation_center
                lines_to_create.append(_line)
            amount_to_pay = inv.amount_to_pay
            inv.payment_lines = []
            inv.save()
            # Se crea la línea del ajuste
            _line = Line()
            _line.party = inv.party
            _line.account = data['adjustment_account']
            _line.description = f"AJUSTE FACTURA {inv.number}"
            if data['invoice_type'] == 'out':
                _line.debit = amount_to_pay
                _line.credit = 0
            else:
                _line.debit = 0
                _line.credit = amount_to_pay
            if operation_center:
                _line.operation_center = operation_center
            if data['analytic_account']:
                _line.analytic_account = data['analytic_account']
            lines_to_create.append(_line)
            note = Note()
            # period = Period(Period.find(inv.company.id, date=last_date))
            period = Period.search([('state', '=', 'open'),('start_date', '>=', last_date),('end_date', '<=', last_date)])
            print(period)
            if period:
                note.date = last_date
            else:
                note.date = data['date']
            note.journal = config.default_journal_note
            note.description = f"AJUSTE FACTURA {inv.number}"
            note.lines = lines_to_create
            Note.save([note])
            Note.post([note])
            with Transaction().set_context(_skip_warnings=True):
                Invoice.process([inv])
            Transaction().connection.commit()