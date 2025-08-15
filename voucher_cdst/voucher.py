from datetime import date
from decimal import Decimal

from sql import Null, Table
from trytond.exceptions import UserError
from trytond.model import ModelSQL, ModelView, fields
from trytond.pool import Pool, PoolMeta
from trytond.transaction import Transaction

from . import fixes

_ZERO = Decimal('0.0')


# Heredamos del modelo sale.sale para agregar el campo id_tecno
class Voucher(ModelSQL, ModelView):
    'Voucher'
    __name__ = 'account.voucher'
    id_tecno = fields.Char('Id Tabla Sqlserver', required=False)

    @classmethod
    def import_voucher_payment(cls):
        """Function to import 'Comprobantes de egreso'
        """
        pool = Pool()
        Party = pool.get('party.party')
        Voucher = pool.get('account.voucher')
        Line = pool.get('account.voucher.line')
        Config = pool.get('conector.configuration')
        PayMode = pool.get('account.voucher.paymode')
        Actualizacion = pool.get('conector.actualizacion')

        import_name = "COMPROBANTES DE EGRESO"
        print(f"---------------RUN {import_name}---------------")

        actualizacion = Actualizacion.create_or_update(
            'COMPROBANTES DE EGRESO')
        logs = {}
        created = []
        exceptions = []
        not_import = []
        account_type = 'account.type.payable'
        # Obtenemos los comprobantes de egreso de TecnoCarnes
        documentos = Config.get_documentos_tecno('6')

        # Comenzamos a recorrer los documentos a procesar y almacenamos los registros y creados en una lista
        parties = Party._get_party_documentos(documentos, 'nit_Cedula')
        for doc in documentos:
            try:
                if not Config.get_configuration():
                    return
                tipo_numero = f"{doc.tipo}-{doc.Numero_documento}"
                id_tecno = f"{doc.sw}-{tipo_numero}"
                # Buscamos si ya existe el comprobante
                comprobante = cls.find_voucher(id_tecno)
                if comprobante:
                    if doc.anulado == 'S':
                        if comprobante.move.period.state == 'close':
                            exceptions.append(id_tecno)
                            logs[
                                id_tecno] = "EXCEPCION: EL PERIODO DEL DOCUMENTO SE ENCUENTRA CERRADO \
                            Y NO ES POSIBLE SU ELIMINACION O MODIFICACION"

                            continue

                        if comprobante.__name__ == 'account.voucher':
                            cls.unreconcilie_move_voucher([comprobante])
                            cls.force_draft_voucher([comprobante])
                            Voucher.delete([comprobante])
                            logs[
                                id_tecno] = "El documento fue eliminado de tryton porque fue anulado en TecnoCarnes"
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
                    logs[
                        id_tecno] = "EXCEPCION: NO SE ENCONTRARON FACTURAS PARA EL PAGO (CRUCE)"
                    continue
                nit_cedula = doc.nit_Cedula.replace('\n', "")
                party = None
                if nit_cedula in parties['active']:
                    party = parties['active'][nit_cedula]
                if not party:
                    if nit_cedula not in parties['inactive']:
                        logs[
                            id_tecno] = f"EXCEPCION: El tercero {nit_cedula} no existe en tryton"
                        exceptions.append(id_tecno)
                    continue
                tipo_pago = Config.get_tipos_pago(id_tecno)
                if not tipo_pago:
                    logs[
                        id_tecno] = "EXCEPCION: NO SE ENCONTRO FORMA(S) DE PAGO EN TECNOCARNES (DOCUMENTOS_CHE)"
                    exceptions.append(id_tecno)
                    continue
                # REVISAR ¿CUANDO HAY MAS DE 1 FORMA DE PAGO?
                if len(tipo_pago) != 1:
                    msg = f"EXCEPCION {id_tecno} - se esperaba 1 forma de pago y se obtuvo {len(tipo_pago)}"
                    logs[id_tecno] = msg
                    exceptions.append(id_tecno)
                    continue
                # for pago in tipo_pago:
                paymode = PayMode.search([('id_tecno', '=',
                                           tipo_pago[0].forma_pago)])
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
                    operation_center, = OperationCenter.search([],
                                                               order=[('id',
                                                                       'ASC')
                                                                      ],
                                                               limit=1)
                    voucher.operation_center = operation_center
                valor_aplicado = round(Decimal(doc.valor_aplicado), 2)
                lines = cls.get_lines_vtecno(facturas, voucher, logs,
                                             account_type)
                if lines:
                    voucher.lines = lines
                    voucher.on_change_lines()
                else:
                    exceptions.append(id_tecno)
                    continue
                voucher.save()
                # Se verifica que el comprobante tenga lineas para ser procesado y contabilizado (doble verificación por error)
                if voucher.lines and voucher.amount_to_pay > 0:
                    Voucher.process([voucher])
                    diferencia = round(
                        abs(voucher.amount_to_pay - valor_aplicado), 2)
                    if voucher.amount_to_pay == valor_aplicado:
                        Voucher.post([voucher])
                    elif diferencia < Decimal(60):
                        config_voucher = pool.get(
                            'account.voucher_configuration')(1)
                        line_ajuste = Line()
                        line_ajuste.voucher = voucher
                        line_ajuste.detail = 'AJUSTE'
                        line_ajuste.account = config_voucher.account_adjust_expense
                        line_ajuste.amount = diferencia
                        if hasattr(Line, 'operation_center'):
                            OperationCenter = pool.get(
                                'company.operation_center')
                            operation_center, = OperationCenter.search(
                                [], order=[('id', 'ASC')], limit=1)
                            line_ajuste.operation_center = operation_center
                        line_ajuste.save()
                        voucher.on_change_lines()
                        Voucher.post([voucher])
                    voucher.save()
                created.append(id_tecno)
            except Exception as error:
                Transaction().rollback()
                print(f"ROLLBACK-{import_name}: {error}")
                logs[id_tecno] = f"EXCEPCION: {error}"
                exceptions.append(id_tecno)
        actualizacion.add_logs(logs)
        for idt in exceptions:
            Config.update_exportado(idt, 'E')
        for idt in created:
            Config.update_exportado(idt, 'T')
        for idt in not_import:
            Config.update_exportado(idt, 'X')
        print(f"---------------FINISH {import_name}---------------")

    @classmethod
    def import_voucher(cls):
        """Function to import 'Comprobantes de Ingreso'
        """
        pool = Pool()
        BankStatementLines = pool.get('bank_statement.line-account.move.line')
        OthersConcepts = pool.get('account.multirevenue.others_concepts')
        MultirenevueTransaction = pool.get('account.multirevenue.transaction')
        MultiRevenueLine = pool.get('account.multirevenue.line')
        Actualizacion = pool.get('conector.actualizacion')
        MultiRevenue = pool.get('account.multirevenue')
        PayMode = pool.get('account.voucher.paymode')
        Config = pool.get('conector.configuration')
        MoveLine = pool.get('account.move.line')
        Line = pool.get('account.voucher.line')
        Voucher = pool.get('account.voucher')
        Party = pool.get('party.party')

        logs = {}
        created = []
        exceptions = []
        not_import = []

        import_name = "COMPROBANTES DE INGRESO"
        print(f"---------------RUN {import_name}---------------")
        configuration = Config.get_configuration()
        if not configuration:
            return
        documentos_db = Config.get_documentos_tecno('5')
        parties = Party._get_party_documentos(documentos_db, 'nit_Cedula')
        actualizacion = Actualizacion.create_or_update(
            'COMPROBANTES DE INGRESO')
        account_type = 'account.type.receivable'

        if documentos_db:
            for doc in documentos_db:
                try:
                    sw = str(doc.sw)
                    tipo = doc.tipo
                    nro = str(doc.Numero_documento)
                    id_tecno = sw + '-' + tipo + '-' + nro
                    comprobante = cls.find_voucher(id_tecno)
                    if comprobante:
                        if doc.anulado == 'S':
                            if comprobante.__name__ == 'account.voucher':
                                move_voucher = comprobante.move
                                move_lines_voucher = MoveLine.search(
                                    ['move', '=', move_voucher])
                                if move_lines_voucher:
                                    bank_statement = False
                                    for lines_voucher in move_lines_voucher:
                                        bank_statement_line = BankStatementLines.search(
                                            ['move_line', '=', lines_voucher])
                                        if bank_statement_line:
                                            bank_statement = True

                                    if bank_statement:
                                        exceptions.append(id_tecno)
                                        logs[
                                            id_tecno] = "EXCEPCION: El comprobante tiene extractos bancarios asociados"
                                        continue
                            if comprobante.__name__ == 'account.multirevenue':
                                move_lines_multi = MoveLine.search(
                                    ['reference', '=', comprobante.code])
                                if move_lines_multi:
                                    bank_statement = False
                                    for lines_multirevenue in move_lines_multi:
                                        bank_statement_line = BankStatementLines.search(
                                            ['move_line', '=', lines_multirevenue])
                                        if bank_statement_line:
                                            bank_statement = True
                                    if bank_statement:
                                        exceptions.append(id_tecno)
                                        msg = "EXCEPCION: El multi "\
                                            "ingreso tiene extractos bancarios "\
                                            "asociados."
                                        logs[id_tecno] = msg
                                        continue
                            if comprobante.__name__ == 'account.voucher':
                                if comprobante.move:
                                    if comprobante.move.period.state == 'close':
                                        exceptions.append(id_tecno)
                                        logs[
                                            id_tecno] = "EXCEPCION: EL PERIODO DEL DOCUMENTO SE ENCUENTRA CERRADO \
                                        Y NO ES POSIBLE SU ELIMINACION O MODIFICACION"

                                        continue
                            if comprobante.__name__ == 'account.voucher':
                                cls.delete_note([comprobante])
                                cls.unreconcilie_move_voucher([comprobante])
                                cls.force_draft_voucher([comprobante])
                                Voucher.delete([comprobante])
                            if comprobante.__name__ == 'account.multirevenue':
                                vouchers = Voucher.search([('reference', '=',
                                                            comprobante.code)])
                                cls.delete_note(vouchers)
                                cls.unreconcilie_move_voucher(vouchers)
                                cls.force_draft_voucher(vouchers)
                                Voucher.delete(vouchers)
                                for line in comprobante.lines:
                                    OthersConcepts.delete(line.others_concepts)
                                MultiRevenueLine.delete(comprobante.lines)
                                MultirenevueTransaction.delete(comprobante.transactions)
                                MultiRevenue.delete([comprobante])
                            logs[
                                id_tecno] = "El documento fue eliminado de tryton porque fue anulado en TecnoCarnes"
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
                        logs[
                            id_tecno] = "EXCEPCION: NO HAY FACTURAS EN TECNOCARNES PARA EL RECIBO"
                        exceptions.append(id_tecno)
                        continue
                    nit_cedula = doc.nit_Cedula.replace('\n', "")
                    party = None
                    if nit_cedula in parties['active']:
                        party = parties['active'][nit_cedula]
                    if not party:
                        if nit_cedula not in parties['inactive']:
                            msg = f"EXCEPCION: El tercero {nit_cedula} no existe en tryton"
                            logs[id_tecno] = msg
                            exceptions.append(id_tecno)
                        continue

                    # Se obtiene la forma de pago, según la tabla Documentos_Che de TecnoCarnes
                    tipo_pago = Config.get_tipos_pago(id_tecno)
                    if not tipo_pago:
                        logs[
                            id_tecno] = "EXCEPCION: NO SE ENCONTRO FORMA(S) DE PAGO EN TECNOCARNES (DOCUMENTOS_CHE) PARA EL DOCUMENTO"
                        exceptions.append(id_tecno)
                        continue

                    # Comprobante con mas de 1 forma de pago (MULTI-INGRESO)
                    if len(tipo_pago) > 1:
                        print('MULTI-INGRESO:', id_tecno)
                        fecha_date = cls.convert_fecha_tecno(doc.fecha_hora)
                        multingreso = MultiRevenue()
                        multingreso.code = tipo + '-' + nro
                        multingreso.party = party
                        multingreso.date = fecha_date
                        multingreso.id_tecno = id_tecno
                        # Se crea una lista con las formas de pago (transacciones)
                        to_transactions = []
                        for pago in tipo_pago:
                            paymode = PayMode.search([('id_tecno', '=',
                                                       pago.forma_pago)])
                            if not paymode:
                                msg = f"EXCEPCION: MULTI-INGRESO - NO SE ENCONTRO LA FORMA DE PAGO {pago.forma_pago}"
                                logs[id_tecno] = msg
                                exceptions.append(id_tecno)
                                break
                            amount_ = Decimal(str(round(pago.valor, 2)))
                            fecha_date = cls.convert_fecha_tecno(pago.fecha)
                            transaction = MultirenevueTransaction()
                            transaction.description = 'IMPORTACION TECNO'
                            transaction.amount = amount_
                            transaction.date = fecha_date
                            transaction.payment_mode = paymode[0]
                            to_transactions.append(transaction)
                        if id_tecno in exceptions:
                            continue
                        multingreso.transactions = to_transactions
                        # Se crea una lista con las lineas (facturas) a pagar
                        to_lines = []
                        for factura in facturas:
                            reference = factura.tipo_aplica + '-' + str(
                                factura.numero_aplica)
                            move_line = cls.get_moveline(reference, party, logs,
                                                         account_type)
                            if move_line:
                                valor_pagado = Decimal(factura.valor +
                                                       factura.descuento
                                                       + factura.retencion
                                                       + (factura.ajuste * -1)
                                                       + factura.retencion_iva
                                                       + factura.retencion_ica)
                                if valor_pagado and valor_pagado > 0:
                                    line = MultiRevenueLine()
                                    line.move_line = move_line
                                    amount_to_pay = move_line.debit
                                    if move_line.move.origin and move_line.move.origin.amount_to_pay:
                                        amount_to_pay = move_line.move.origin.amount_to_pay
                                    if valor_pagado > amount_to_pay:
                                        valor_pagado = amount_to_pay
                                    line.amount = Decimal(
                                        str(round(valor_pagado, 2)))
                                    line.original_amount = Decimal(
                                        str(round(amount_to_pay, 2)))
                                    line.is_prepayment = False
                                    line.reference_document = reference
                                    line.others_concepts = cls.get_others_tecno(
                                        factura, amount_to_pay)
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
                        paymode = PayMode.search(
                            [('id_tecno', '=', forma_pago)])
                        if not paymode:
                            msg = f"EXCEPCION: NO SE ENCONTRO LA FORMA DE PAGO {forma_pago}"
                            logs[id_tecno] = msg
                            exceptions.append(id_tecno)
                            continue
                        fecha_date = cls.convert_fecha_tecno(
                            tipo_pago[0].fecha)
                        voucher = Voucher()
                        voucher.id_tecno = id_tecno
                        voucher.number = tipo + '-' + nro
                        voucher.reference = tipo + '-' + nro
                        voucher.party = party
                        voucher.payment_mode = paymode[0]
                        voucher.on_change_payment_mode()
                        voucher.voucher_type = 'receipt'
                        voucher.date = fecha_date
                        nota = (doc.notas).replace('\n', ' ').replace('\r', '')
                        if nota:
                            voucher.description = nota
                        if hasattr(Voucher, 'operation_center'):
                            OperationCenter = pool.get(
                                'company.operation_center')
                            operation_center, = OperationCenter.search([],
                                                                       order=[
                                ('id',
                                 'ASC')
                            ],
                                limit=1)
                            voucher.operation_center = operation_center
                        valor_aplicado = Decimal(doc.valor_aplicado)
                        lines = cls.get_lines_vtecno(facturas, voucher, logs,
                                                     account_type)
                        if lines:
                            voucher.lines = lines
                            voucher.on_change_lines()
                        else:
                            exceptions.append(id_tecno)
                            logs[id_tecno] = "No se encontro lineas para el voucher"
                            continue
                        voucher.save()
                        # Se verifica que el comprobante tenga lineas para ser procesado y contabilizado (doble verificación por error)
                        if voucher.lines and voucher.amount_to_pay > 0:
                            Voucher.process([voucher])
                            diferencia = abs(
                                Decimal(
                                    str(
                                        round(
                                            voucher.amount_to_pay - valor_aplicado,
                                            2))))

                            # print(diferencia, (diferencia < Decimal(6.0)))
                            if voucher.amount_to_pay == valor_aplicado:
                                Voucher.post([voucher])
                            elif diferencia < Decimal(60):
                                config_voucher = pool.get(
                                    'account.voucher_configuration')(1)
                                line_ajuste = Line()
                                line_ajuste.voucher = voucher
                                line_ajuste.detail = 'AJUSTE'
                                line_ajuste.account = config_voucher.account_adjust_income
                                line_ajuste.amount = diferencia
                                if hasattr(Line, 'operation_center'):
                                    OperationCenter = pool.get(
                                        'company.operation_center')
                                    operation_center, = OperationCenter.search(
                                        [], order=[('id', 'ASC')], limit=1)
                                    line_ajuste.operation_center = operation_center
                                line_ajuste.save()
                                voucher.on_change_lines()
                                Voucher.post([voucher])
                            voucher.save()
                        created.append(id_tecno)
                    else:
                        exceptions.append(id_tecno)
                        logs[
                            id_tecno] = "EXCEPCION: NO ENCONTRO FORMA DE PAGO EN TECNOCARNES"
                        continue
                except Exception as error:
                    Transaction().rollback()
                    print(f"ROLLBACK-{import_name}: {error}")
                    exceptions.append(id_tecno)
                    logs[id_tecno] = f"EXCEPCION: {error}"

            actualizacion.add_logs(logs)

            for idt in exceptions:
                Config.update_exportado(idt, 'E')
            for idt in created:
                Config.update_exportado(idt, 'T')
            for idt in not_import:
                Config.update_exportado(idt, 'X')
        print(f"---------------FINISH {import_name}---------------")

    # Se obtiene las lineas de la factura que se desea pagar
    @classmethod
    def get_moveline(cls, invoice_number, party, logs, account_type):
        pool = Pool()
        Invoice = pool.get('account.invoice')
        MoveLine = pool.get('account.move.line')
        invoice = Invoice.search([('number', '=', invoice_number),
                                  ('state', '=', 'posted')])
        if invoice:
            return invoice[0].lines_to_pay[0]

        line_domain = [('reference', '=', invoice_number), ('party', '=', party),
                       (account_type, '=', True),
                       ('reconciliation', '=', None),
                       ('move.state', '=', 'posted')]
        if account_type == 'account.type.receivable':
            line_domain.append(('debit', '>', 0))
        elif account_type == 'account.type.payable':
            line_domain.append(('credit', '>', 0))
        # Si no encuentra lineas a pagar... Se busca en saldos iniciales
        moveline = MoveLine.search(line_domain)
        if moveline:
            if len(moveline) > 1:
                msg = f"Esperaba unica referencia ({invoice_number}) en linea de movimiento (saldos iniciales) y obtuvo muchas !"
                logs[invoice_number] = msg
                return False
            if moveline[0].reconciliation:
                logs[invoice_number] = f"REVISAR FACTURA ({invoice_number}) CONCILIADA"
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
        if moveline.move_origin and hasattr(
                moveline.move_origin, '__name__'
        ) and moveline.move_origin.__name__ == 'account.invoice':
            amount_to_pay = moveline.move.origin.amount_to_pay
            untaxed_amount = moveline.move_origin.untaxed_amount
        elif not moveline.move_origin:
            amount_to_pay = amount
            untaxed_amount = amount

        return amount, amount_to_pay, untaxed_amount

    # Metodo encargado de consultar y verificar si existe un comprobante de multi-ingreso con la id de la BD
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
        Line = pool.get('account.voucher.line')
        Invoice = pool.get('account.invoice')
        config_voucher = pool.get('account.voucher_configuration')(1)
        to_lines = []
        for inv in invoices:
            invoice_number = inv.tipo_aplica + '-' + str(inv.numero_aplica)
            invoice = Invoice.search([('number', '=', invoice_number)])
            if not invoice:
                msg = f"EXCEPCION: NO SE ENCONTRO LA FACTURA CON NUMERO {invoice_number}"
                logs[voucher.id_tecno] = msg
                return None

            invoice, = invoice
            move_line = cls.get_moveline(invoice_number, voucher.party, logs, account_type)
            reference = invoice.reference
            if not move_line:
                msg = f"EXCEPCION: REVISAR SI LA FACTURA CON NUMERO {invoice_number} NO ESTA CONTABILIZADA EN TRYTON"
                logs[voucher.id_tecno] = msg
                return None
            valor_original, amount_to_pay, untaxed_amount = cls.get_amounts_to_pay(
                move_line, voucher.voucher_type)
            line = Line()
            line.amount_original = valor_original
            line.reference = reference
            line.move_line = move_line
            line.on_change_move_line()
            if hasattr(Line, 'operation_center'):
                OperationCenter = pool.get('company.operation_center')
                operation_center, = OperationCenter.search([],
                                                           order=[('id',
                                                                   'ASC')],
                                                           limit=1)
                line.operation_center = operation_center
            valor = Decimal(inv.valor)
            descuento = Decimal(inv.descuento)
            retencion = Decimal(inv.retencion)
            ajuste = Decimal(inv.ajuste)
            retencion_iva = Decimal(inv.retencion_iva)
            retencion_ica = Decimal(inv.retencion_ica)
            valor_pagado = valor + descuento + retencion + (
                ajuste * -1) + retencion_iva + retencion_ica
            valor_pagado = round(valor_pagado, 2)
            if valor_pagado > amount_to_pay:
                valor_pagado = amount_to_pay
            line.amount = Decimal(str(round(valor_pagado, 2)))
            to_lines.append(line)
            # Se crean lineas adicionales en el comprobante en caso de ser necesario
            if descuento > 0:
                line_discount = Line()
                line_discount.party = move_line.party
                line_discount.reference = reference
                line_discount.detail = 'DESCUENTO'
                line_discount.amount = round((descuento * -1), 2)
                line_discount.account = config_voucher.account_discount_tecno
                if hasattr(Line, 'operation_center'):
                    OperationCenter = pool.get('company.operation_center')
                    operation_center, = OperationCenter.search([],
                                                               order=[('id',
                                                                       'ASC')
                                                                      ],
                                                               limit=1)
                    line_discount.operation_center = operation_center
                to_lines.append(line_discount)
            if retencion > 0:
                line_rete = Line()
                line_rete.party = move_line.party
                line_rete.reference = reference
                line_rete.detail = 'RETENCION - (' + str(retencion) + ')'
                line_rete.type = 'tax'
                line_rete.untaxed_amount = untaxed_amount
                line_rete.tax = config_voucher.account_rete_tecno
                line_rete.on_change_tax()
                line_rete.amount = round((retencion * -1), 2)
                if hasattr(Line, 'operation_center'):
                    OperationCenter = pool.get('company.operation_center')
                    operation_center, = OperationCenter.search([],
                                                               order=[('id',
                                                                       'ASC')
                                                                      ],
                                                               limit=1)
                    line_rete.operation_center = operation_center
                to_lines.append(line_rete)
            if retencion_iva > 0:
                line_retiva = Line()
                line_retiva.party = move_line.party
                line_retiva.reference = reference
                line_retiva.detail = 'RETENCION IVA - (' + str(
                    retencion_iva) + ')'
                line_retiva.type = 'tax'
                line_retiva.untaxed_amount = untaxed_amount
                line_retiva.tax = config_voucher.account_retiva_tecno
                line_retiva.on_change_tax()
                line_retiva.amount = round((retencion_iva * -1), 2)
                if hasattr(Line, 'operation_center'):
                    OperationCenter = pool.get('company.operation_center')
                    operation_center, = OperationCenter.search([],
                                                               order=[('id',
                                                                       'ASC')
                                                                      ],
                                                               limit=1)
                    line_retiva.operation_center = operation_center
                to_lines.append(line_retiva)
            if retencion_ica > 0:
                line_retica = Line()
                line_retica.party = move_line.party
                line_retica.reference = reference
                line_retica.detail = 'RETENCION ICA - (' + str(
                    retencion_ica) + ')'
                line_retica.type = 'tax'
                line_retica.untaxed_amount = untaxed_amount
                line_retica.tax = config_voucher.account_retica_tecno
                line_retica.on_change_tax()
                line_retica.amount = round((retencion_ica * -1), 2)
                if hasattr(Line, 'operation_center'):
                    OperationCenter = pool.get('company.operation_center')
                    operation_center, = OperationCenter.search([],
                                                               order=[('id',
                                                                       'ASC')
                                                                      ],
                                                               limit=1)
                    line_retica.operation_center = operation_center
                to_lines.append(line_retica)
            if ajuste > 0:
                line_ajuste = Line()
                line_ajuste.party = move_line.party
                line_ajuste.reference = reference
                line_ajuste.detail = 'AJUSTE'
                if Decimal(move_line.debit) > 0:
                    line_ajuste.account = config_voucher.account_adjust_income
                elif Decimal(move_line.credit) > 0:
                    line_ajuste.account = config_voucher.account_adjust_expense
                line_ajuste.amount = round(ajuste, 2)
                if hasattr(Line, 'operation_center'):
                    OperationCenter = pool.get('company.operation_center')
                    operation_center, = OperationCenter.search([],
                                                               order=[('id',
                                                                       'ASC')
                                                                      ],
                                                               limit=1)
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
        valor_pagado = valor + descuento + retencion + (
            ajuste * -1) + retencion_iva + retencion_ica
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
            line_rete.account = config_voucher.account_adjust_income  # se añade cualquier cuenta
            line_rete.amount = round((retencion * -1), 2)
            to_others.append(line_rete)
            valor_pagado += line_rete.amount
        if retencion_iva > 0:
            line_retiva = OthersConcepts()
            line_retiva.description = 'RETIVA:'
            # se añade cualquier cuenta
            line_retiva.account = config_voucher.account_adjust_income
            line_retiva.amount = round((retencion_iva * -1), 2)
            to_others.append(line_retiva)
            valor_pagado += line_retiva.amount
        if retencion_ica > 0:
            line_retica = OthersConcepts()
            line_retica.description = 'RETICA'
            # se añade cualquier cuenta
            line_retica.account = config_voucher.account_adjust_income
            line_retica.amount = round((retencion_ica * -1), 2)
            to_others.append(line_retica)
            valor_pagado += line_retica.amount
        if ajuste > 0:
            line_ajuste = OthersConcepts()
            line_ajuste.description = 'AJUSTE'
            line_ajuste.account = config_voucher.account_adjust_income
            line_ajuste.amount = round(ajuste, 2)
            to_others.append(line_ajuste)
            valor_pagado += line_ajuste.amount
        # Se verifica si la diferencia es minima para llevarla a un ajuste
        difference = (original_amount - valor_pagado)
        if difference != 0 and abs(difference) < 50:
            line_ajuste = OthersConcepts()
            line_ajuste.description = 'REDONDEO'
            line_ajuste.account = config_voucher.account_adjust_income
            line_ajuste.amount = round(Decimal(difference * -1), 2)
            to_others.append(line_ajuste)
        return to_others

    @classmethod
    def convert_fecha_tecno(cls, fecha_tecno):
        fecha = str(fecha_tecno).split()[0].split('-')
        fecha = date(int(fecha[0]), int(fecha[1]), int(fecha[2]))
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
            reconciliations = [
                l.reconciliation for l in move.lines if l.reconciliation
            ]
            if reconciliations:
                Reconciliation.delete(reconciliations)
        return reconciliations

    @classmethod
    def delete_note(cls, vouchers):
        pool = Pool()
        Note = pool.get('account.note')

        try:
            for voucher in vouchers:
                if voucher:
                    if voucher.move:
                        for lines in voucher.move.lines:
                            if lines.origin and lines.origin.move_line\
                                and lines.origin.move_line.move\
                                    and lines.origin.move_line.move.origin:

                                for notes in lines.origin.move_line.move.origin.payment_lines:
                                    if notes.origin and notes.origin.__name__ == 'account.note.line':
                                        note = notes.origin.note
                                        fixes.draft_unconciliate_delete_account_move(
                                            [note.move.id], action="draft")
                                        fixes.draft_unconciliate_delete_account_move(
                                            [note.move.id], action="unconciliate")
                                        fixes.draft_unconciliate_delete_account_move(
                                            [note.move.id], action="moves")
                                        Note.draft([note])
                                        note.lines[0].delete(note.lines)
                                        note.number = Null
                                        Note.delete([note])

        except Exception as e:
            print(e)

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
            voucher.number = Null
        if move_ids:
            cursor.execute(
                *move_table.update(columns=[move_table.state],
                                   values=['draft'],
                                   where=move_table.id.in_(move_ids)))
            cursor.execute(*move_table.delete(
                where=move_table.id.in_(move_ids)))
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
        pool = Pool()
        Line = pool.get('account.voucher.line')
        Invoice = pool.get('account.invoice')
        MoveLine = pool.get('account.move.line')
        Reconciliation = pool.get('account.move.reconciliation')
        Actualizacion = pool.get('conector.actualizacion')

        import_name = "CRUCE DE COMPROBANTES"
        print(f"---------------RUN {import_name}---------------")

        actualizacion = Actualizacion.create_or_update('CRUCE DE COMPROBANTES')
        """
        Se realiza la búsqueda de las líneas de comprobantes que no tengan
        factura (línea de asiento) asociada para asignarse y luego conciliar
        """
        lines = Line.search([('voucher.state', '=', 'posted'),
                             ('reference', 'like', '%-%'),
                             ('move_line', '=', None),
                             [
                                 'OR', ('account.type.receivable', '=', True),
                                 ('account.type.payable', '=', True)
        ]])
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

        for invoice in invoices:
            try:
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
                        Invoice.save([invoice])
                        if amount == _ZERO:
                            Reconciliation.delete(reconciliations)
                            MoveLine.reconcile(all_lines)
                    else:
                        msg = f"LA FACTURA CON ID {invoice} TIENE UN PAGO MAYOR "\
                            f"AL INTENTAR AGREGAR LA(S) LINEA(S) CRUCE {move_lines}"
                        logs[invoice.number] = msg
            except Exception as error:
                Transaction().rollback()
                print(f"ROLLBACK-{import_name}: {error}")
                logs[invoice.number] = f"EXCEPCION: {error}"
        actualizacion.add_logs(logs)
        print(f"---------------FINISH {import_name}---------------")

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
    account_discount_tecno = fields.Many2One(
        'account.account',
        'Account Discount for Conector TecnoCarnes',
        domain=[
            ('type', '!=', None),
        ])
    account_rete_tecno = fields.Many2One(
        'account.tax',
        'Account Retention for Conector TecnoCarnes',
        domain=[
            ('type', '!=', None),
        ])
    account_retiva_tecno = fields.Many2One(
        'account.tax',
        'Account Retention IVA for Conector TecnoCarnes',
        domain=[
            ('type', '!=', None),
        ])
    account_retica_tecno = fields.Many2One(
        'account.tax',
        'Account Retention ICA for Conector TecnoCarnes',
        domain=[
            ('type', '!=', None),
        ])
    adjustment_amount = fields.Numeric(
        'Adjustment amount',
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
                        'description':
                        f"MULTI-INGRESO FACTURA {line.reference_document}",
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
                        c_line[
                            'account'] = config_voucher.account_rete_tecno.invoice_account.id
                    elif concept.description == 'RETIVA':
                        c_line['untaxed_amount'] = line.original_amount
                        c_line['type'] = 'tax'
                        c_line['tax'] = config_voucher.account_retiva_tecno.id
                        c_line[
                            'account'] = config_voucher.account_retiva_tecno.invoice_account.id
                    elif concept.description == 'RETICA':
                        c_line['untaxed_amount'] = line.original_amount
                        c_line['type'] = 'tax'
                        c_line['tax'] = config_voucher.account_retica_tecno.id
                        c_line[
                            'account'] = config_voucher.account_retica_tecno.invoice_account.id
                    else:
                        c_line['account'] = concept.account.id
                    voucher_to_create[transaction.id][
                        line.id]['lines'][0][1].append(c_line)
                    concept_amounts += concept.amount
                    concept_ids.append(concept.id)
                net_payment = line.amount + concept_amounts
                if net_payment <= amount_tr:
                    _line_amount = line.amount
                    amount_tr -= net_payment
                    line_paid.append(line.id)
                else:
                    _line_amount = amount_tr + abs(concept_amounts)

                    line.amount = round(line.amount - _line_amount, 2)
                    amount_tr = 0
                if line.move_line:
                    move_line = line.move_line
                    origin_number = line.origin.number if line.origin else None
                    total_amount = line.origin.total_amount if line.origin and line.origin.__name__ == 'account.invoice' else move_line.amount
                    if _line_amount > total_amount:  # Se valida que el pago no sea mayor
                        _line_amount = total_amount
                    voucher_to_create[transaction.id][
                        line.id]['lines'][0][1].append({
                            'detail':
                            origin_number or move_line.reference
                            or move_line.description,
                            'amount':
                            _line_amount,
                            'amount_original':
                            total_amount,
                            'move_line':
                            move_line.id,
                            'account':
                            move_line.account.id,
                            'operation_center':
                            operation_center.id
                        })
                else:
                    detail_ = line.reference_document
                    account_id = line.account.id if line.account else None
                    if not account_id:
                        raise UserError('account_voucher.msg_without_account')
                    if line.is_prepayment:
                        detail_ = 'ANTICIPO'
                    voucher_to_create[transaction.id][
                        line.id]['lines'][0][1].append({
                            'detail': detail_,
                            'amount': _line_amount,
                            'account': account_id,
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

    # Reimportar multi-ingresos
    @classmethod
    def mark_rimport(cls, multirevenue):
        pool = Pool()
        Actualizacion = pool.get('conector.actualizacion')
        actualizacion = Actualizacion.create_or_update(
            'ELIMINAR MULTI-INGRESOS')
        logs = {}
        exceptions = []
        Conexion = pool.get('conector.configuration')
        MultiRevenue = pool.get('account.multirevenue')
        Line = pool.get('account.multirevenue.line')
        OthersConcepts = pool.get('account.multirevenue.others_concepts')
        Transaction = pool.get('account.multirevenue.transaction')
        Voucher = pool.get('account.voucher')
        Period = pool.get('account.period')
        ids_tecno = []
        for multi in multirevenue:
            dat = str(multi.date).split('-')
            name = f"{dat[0]}-{dat[1]}"
            validate_period = Period.search([('name', '=', name)])
            if validate_period[0].state == 'close':
                exceptions.append(multi.id_tecno)
                logs[
                    multi.
                    id_tecno] = "EXCEPCION: EL PERIODO DEL DOCUMENTO SE ENCUENTRA CERRADO \
                Y NO ES POSIBLE SU ELIMINACION O MODIFICACION"

                continue
            ids_tecno.append(multi.id_tecno)
            vouchers = Voucher.search([('reference', '=', multi.code)])
            Voucher.force_draft_voucher(vouchers)
            Voucher.delete(vouchers)
            for line in multi.lines:
                OthersConcepts.delete(line.others_concepts)
            Line.delete(multi.lines)
            Transaction.delete(multi.transactions)
        MultiRevenue.delete(multirevenue)
        if exceptions:
            actualizacion.add_logs(logs)
        for idt in ids_tecno:
            Conexion.update_exportado(idt, 'N')


class SelectMoveLines(metaclass=PoolMeta):
    'Select Lines'
    __name__ = 'account.voucher.select_move_lines'

    def transition_search_lines(self):
        Select = Pool().get('account.voucher.select_move_lines.ask')

        line_domain = [
            ('account.reconcile', '=', True),
            ('state', '=', 'valid'),
            ('reconciliation', '=', None),
            ('move.state', '=', 'posted'),
        ]
        Select.lines.domain = line_domain
        return 'start'
