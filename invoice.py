from decimal import Decimal
from trytond.pool import PoolMeta, Pool
from trytond.model import fields, ModelView
from trytond.pyson import Eval, Or, And
from trytond.wizard import Wizard, StateTransition
from trytond.transaction import Transaction
from trytond.exceptions import UserError, UserWarning
from sql import Table
import datetime

from .it_supplier_noova import SendElectronicInvoice



ELECTRONIC_STATES = [
    ('none', 'None'),
    ('submitted', 'Submitted'),
    ('pending', 'Pending'),
    ('rejected', 'Rejected'),
    ('authorized', 'Authorized'),
    ('accepted', 'Accepted'),
]


class Cron(metaclass=PoolMeta):
    'Cron'
    __name__ = 'ir.cron'

    @classmethod
    def __setup__(cls):
        super().__setup__()
        cls.method.selection.append(
            ('account.invoice|import_credit_note', "Importar Notas de Crédito"),
            )
        cls.method.selection.append(
            ('account.invoice|import_debit_note', "Importar Notas de Débito"),
            )


class Invoice(metaclass=PoolMeta):
    'Invoice'
    __name__ = 'account.invoice'
    id_tecno = fields.Char('Id Tabla Sqlserver (credit note)', required=False)

    @staticmethod
    def default_electronic_state():
        return 'none'


    @classmethod
    def unreconcile_move(self, move):
        Reconciliation = Pool().get('account.move.reconciliation')
        reconciliations = [l.reconciliation for l in move.lines if l.reconciliation]
        if reconciliations:
            Reconciliation.delete(reconciliations)
    
    #Importar notas de TecnoCarnes
    @classmethod
    def import_notas_tecno(cls, nota_tecno):
        print(f'RUN NOTAS DE {nota_tecno}')
        pool = Pool()
        Config = pool.get('conector.configuration')
        Actualizacion = pool.get('conector.actualizacion')
        actualizacion = Actualizacion.create_or_update(f'NOTAS DE {nota_tecno}')
        # Obtenemos las notas de credito de TecnoCarnes
        if nota_tecno == "CREDITO":
            documentos = Config.get_documentos_tecno('32')
        else:
            documentos = Config.get_documentos_tecno('31')
        if not documentos:
            #actualizacion.save()
            print(f"FINISH NOTAS DE {nota_tecno}")
            return
        ###
        Module = pool.get('ir.module')
        Tax = pool.get('account.tax')
        Party = pool.get('party.party')
        Invoice = pool.get('account.invoice')
        Line = pool.get('account.invoice.line')
        Product = pool.get('product.product')
        PaymentTerm = pool.get('account.invoice.payment_term')
        Configuration = pool.get('account.configuration')(1)
        operation_center = Module.search([('name', '=', 'company_operation'), ('state', '=', 'activated')])
        if operation_center:
            operation_center = pool.get('company.operation_center')(1)
        logs = []
        created = []
        to_exception = []
        not_import = []
        with Transaction().set_context(_skip_warnings=True):
            for nota in documentos:
                id_tecno = str(nota.sw)+'-'+nota.tipo+'-'+str(nota.Numero_documento)
                try:
                    invoice = Invoice.search([('id_tecno', '=', id_tecno)])
                    if invoice:
                        msg = f"LA NOTA {id_tecno} YA EXISTE EN TRYTON"
                        logs.append(msg)
                        created.append(id_tecno)
                        continue
                    if nota.anulado == 'S':
                        msg = f"{id_tecno} Documento anulado en TecnoCarnes"
                        logs.append(msg)
                        not_import.append(id_tecno)
                        continue
                    nit_cedula = nota.nit_Cedula.replace('\n',"")
                    party = Party.search([('id_number', '=', nit_cedula)])
                    if not party:
                        msg = f'EXCEPCION: NO SE ENCONTRO EL TERCERO {nit_cedula} DE LA NOTA {id_tecno}'
                        logs.append(msg)
                        actualizacion.reset_writedate('TERCEROS')
                        to_exception.append(id_tecno)
                        continue
                    party = party[0]
                    plazo_pago = PaymentTerm.search([('id_tecno', '=', nota.condicion)])
                    if not plazo_pago:
                        msg = f'EXCEPCION: PLAZO {nota.condicion} NO EXISTE PARA LA NOTA {id_tecno}'
                        logs.append(msg)
                        to_exception.append(id_tecno)
                        continue
                    plazo_pago = plazo_pago[0]
                    #print(id_tecno)
                    fecha = str(nota.fecha_hora).split()[0].split('-')
                    fecha_date = datetime.date(int(fecha[0]), int(fecha[1]), int(fecha[2]))
                    invoice = Invoice()
                    invoice.id_tecno = id_tecno
                    invoice.party = party
                    invoice.cufe = '0'
                    invoice.on_change_party() #Se usa para traer la dirección del tercero
                    invoice.invoice_date = fecha_date
                    invoice.number = nota.tipo+'-'+str(nota.Numero_documento)
                    dcto_base = str(nota.Tipo_Docto_Base)+'-'+str(nota.Numero_Docto_Base)
                    invoice.reference = dcto_base
                    description = (nota.notas).replace('\n', ' ').replace('\r', '')
                    if description:
                        invoice.description = description
                    invoice.type = 'out'
                    if nota_tecno == "CREDITO":
                        invoice.invoice_type = '91'
                        invoice.operation_type = '22'
                    else:
                        invoice.invoice_type = '92'
                        invoice.operation_type = '32'
                    if party.account_receivable:
                        invoice.account = party.account_receivable
                    elif Configuration.default_account_receivable:
                        invoice.account = Configuration.default_account_receivable
                    else:
                        msg = f'EXCEPCION: LA NOTA {id_tecno} NO SE CREO POR FALTA DE CUENTA POR COBRAR EN EL TERCERO Y LA CONFIGURACION CONTABLE POR DEFECTO'
                        logs.append(msg)
                        to_exception.append(id_tecno)
                        continue
                    invoice.payment_term = plazo_pago
                    original_invoice = Invoice.search([('number', '=', dcto_base)])
                    if original_invoice:
                        original_invoice = original_invoice[0]
                        invoice.original_invoice = original_invoice
                        invoice.date_document_reference = original_invoice.invoice_date
                        invoice.type_invoice_reference = original_invoice.invoice_type
                    else:
                        msg = f'EL DOCUMENTO {dcto_base} AL QUE HACE REFERENCIA LA NOTA {id_tecno} NO FUE ENCONTRADO'
                        logs.append(msg)
                    invoice.comment = f"NOTA DE {nota_tecno} DE LA FACTURA {dcto_base}"
                    invoice.number_document_reference = dcto_base
                    invoice.cufe_document_reference = '0'
                    invoice.on_change_type()
                    retencion_rete = False
                    if nota.retencion_causada > 0:
                        if nota.retencion_iva == 0 and nota.retencion_ica == 0:
                            retencion_rete = True
                        elif (nota.retencion_iva + nota.retencion_ica) != nota.retencion_causada:
                            retencion_rete = True
                    to_lines = []
                    lineas_tecno = Config.get_lineasd_tecno(id_tecno)
                    for linea in lineas_tecno:
                        product = Product.search([('id_tecno', '=', linea.IdProducto)])
                        if not product:
                            msg = f"EXCEPCION: NO SE ENCONTRO EL PRODUCTO {linea.IdProducto}"
                            logs.append(msg)
                            to_lines = []
                            break
                        if nota_tecno == "CREDITO":
                            cantidad = abs(round(linea.Cantidad_Facturada, 3)) * -1
                        else:
                            cantidad = abs(round(linea.Cantidad_Facturada, 3))
                        line = Line()
                        line.product = product[0]
                        line.quantity = cantidad
                        line.unit_price = linea.Valor_Unitario
                        if operation_center:
                            line.operation_center = operation_center
                        line.on_change_product()
                        tax_line = []
                        not_impoconsumo = False
                        for impuestol in line.taxes:
                            clase_impuesto = impuestol.classification_tax
                            if clase_impuesto == '05' and nota.retencion_iva > 0:
                                if impuestol not in tax_line:
                                    tax_line.append(impuestol)
                            elif clase_impuesto == '06' and retencion_rete:
                                if impuestol not in tax_line:
                                    tax_line.append(impuestol)
                            elif clase_impuesto == '07' and nota.retencion_ica > 0:
                                if impuestol not in tax_line:
                                    tax_line.append(impuestol)
                            elif impuestol.consumo and linea.Impuesto_Consumo > 0:
                                #Se busca el impuesto al consumo con el mismo valor para aplicarlo
                                tax = Tax.search([('consumo', '=', True), ('type', '=', 'fixed'), ('amount', '=', linea.Impuesto_Consumo)])
                                if tax:
                                    tax_line.append(tax[0])
                                else:
                                    msg = f'EXCEPCION: NO SE ENCONTRO EL IMPUESTO FIJO DE TIPO CONSUMO CON VALOR DE {linea.Impuesto_Consumo} EN EL DOCUMENTO {id_tecno}'
                                    logs.append(msg)
                                    to_exception.append(id_tecno)
                                    not_impoconsumo = True
                                    continue
                            elif clase_impuesto != '05' and clase_impuesto != '06' and clase_impuesto != '07' and not impuestol.consumo:
                                if impuestol not in tax_line:
                                    tax_line.append(impuestol)
                        if not_impoconsumo:
                            to_lines = []
                            break
                        line.taxes = tax_line
                        if linea.Porcentaje_Descuento_1 > 0:
                            descuento = (linea.Valor_Unitario * Decimal(linea.Porcentaje_Descuento_1)) / 100
                            line.unit_price = Decimal(linea.Valor_Unitario - descuento)
                            line.on_change_product()
                            line.gross_unit_price = linea.Valor_Unitario 
                            #line.discount = Decimal(linea.Porcentaje_Descuento_1/100)
                        to_lines.append(line)
                    if to_lines:
                        invoice.lines = to_lines
                    else:
                        msg = f"EXCEPCION: NO SE CREARON LINEAS PARA LA NOTA {id_tecno}"
                        logs.append(msg)
                        to_exception.append(id_tecno)
                        continue
                    invoice.on_change_lines()
                    invoice.save()
                    Invoice.validate_invoice([invoice])
                    total_tryton = abs(invoice.untaxed_amount)
                    valor_total = Decimal(abs(nota.valor_total))
                    valor_impuesto = Decimal(abs(nota.Valor_impuesto) + abs(nota.Impuesto_Consumo)) # + abs(nota.retencion_causada))
                    if valor_impuesto > 0:
                        total_tecno = valor_total - valor_impuesto
                    else:
                        total_tecno = valor_total
                    diferencia_total = abs(total_tryton - total_tecno)
                    if diferencia_total < Decimal(6.0):
                        Invoice.post([invoice])
                    else:
                        msg = f"NO SE CONTABILIZO LA NOTA {id_tecno} YA QUE LA DIFERENCIA ENTRE EL TOTAL DE TRYTON Y TECNOCARNES ES DE {diferencia_total}"
                        logs.append(msg)
                    created.append(id_tecno)
                except Exception as ex:
                    msg = f"EXCEPCION {id_tecno} - {ex}"
                    logs.append(msg)
                    to_exception.append(id_tecno)
        actualizacion.add_logs(actualizacion, logs)
        for idt in created:
            Config.update_exportado(idt, 'T')
            # print('creado...', idt) #TEST
        for idt in to_exception:
            Config.update_exportado(idt, 'E')
            # print('excepcion...', idt) #TEST
        for idt in not_import:
            Config.update_exportado(idt, 'X')
        print(f"FINISH NOTAS DE {nota_tecno}")


    #Nota de crédito
    @classmethod
    def import_credit_note(cls):
        cls.import_notas_tecno('CREDITO')

    #Nota de débito
    @classmethod
    def import_debit_note(cls):
        cls.import_notas_tecno('DEBITO')


    @classmethod
    def __setup__(cls):
        super(Invoice, cls).__setup__()
        cls._buttons.update({
            'send_support_document': {
                'invisible': Or(
                    And(Eval('type') != 'out', ~Eval('equivalent_invoice')),
                    Eval('electronic_state') == 'authorized',
                    Eval('number', None) == None,
                    Eval('authorization', None) == None,
                    Eval('state') != 'validated',
                )}
            },)

    @classmethod
    @ModelView.button
    def send_support_document(cls, records):
        for invoice in records:
            if invoice.invoice_type not in ('05', '95'):
                continue
            if invoice.authorization and not invoice.event:
                _ = SendElectronicInvoice(invoice, invoice.authorization)
            else:
                invoice.get_message('El campo proveedor de autorización no ha sido seleccionado')


# class UpdateInvoiceTecno(Wizard):
#     'Update Invoice Tecno'
#     __name__ = 'account.invoice.update_invoice_tecno'
#     start_state = 'do_submit'
#     do_submit = StateTransition()

#     def transition_do_submit(self):
#         pool = Pool()
#         Invoice = pool.get('account.invoice')
#         Sale = pool.get('sale.sale')
#         Purchase = pool.get('purchase.purchase')

#         ids = Transaction().context['active_ids']

#         to_delete_sales = []
#         to_delete_purchases = []
#         for invoice in Invoice.browse(ids):
#             rec_name = invoice.rec_name
#             party_name = invoice.party.name
#             rec_party = rec_name+' de '+party_name
#             if invoice.number and '-' in invoice.number:
#                 if invoice.type == 'out':
#                     sale = Sale.search([('number', '=', invoice.number)])
#                     if sale:
#                         to_delete_sales.append(sale[0])
#                 elif invoice.type == 'in':
#                     purchase = Purchase.search([('number', '=', invoice.number)])
#                     if purchase:
#                         to_delete_purchases.append(purchase[0])
#             else:
#                 raise UserError("Revisa el número de la factura (tipo-numero): ", rec_party)
#         Sale.delete_imported_sales(to_delete_sales)
#         Purchase.delete_imported_purchases(to_delete_purchases)
#         return 'end'

#     def end(self):
#         return 'reload'



class UpdateNoteDate(Wizard):
    'Update Note Date'
    __name__ = 'account.invoice.update_note_date'
    start_state = 'to_update'
    to_update = StateTransition()

    def transition_to_update(self):
        pool = Pool()
        Warning = pool.get('res.user.warning')
        Invoice = pool.get('account.invoice')
        move_table = Table('account_move')
        note_table = Table('account_note')
        cursor = Transaction().connection.cursor()
        ids = Transaction().context['active_ids']

        warning_name = 'warning_udate_note_%s' % ids
        if Warning.check(warning_name):
            raise UserWarning(warning_name, "Se va a actualizar las fechas de los anticipos cruzados con respecto a la fecha de la factura.")

        for invoice in Invoice.browse(ids):
            rec_name = invoice.rec_name
            party_name = invoice.party.name
            rec_party = rec_name+' de '+party_name
            if invoice.state == 'posted' or invoice.state == 'paid':
                movelines = invoice.reconciliation_lines or invoice.payment_lines
                if movelines:
                    for line in movelines:
                        if line.move_origin and hasattr(line.move_origin, '__name__') and line.move_origin.__name__ == 'account.note':
                            cursor.execute(*move_table.update(
                                columns=[move_table.date, move_table.post_date, move_table.period],
                                values=[invoice.invoice_date, invoice.invoice_date, invoice.move.period.id],
                                where=move_table.id == line.move.id)
                            )
                            cursor.execute(*note_table.update(
                                columns=[note_table.date],
                                values=[invoice.invoice_date],
                                where=note_table.id == line.move_origin.id)
                            )
            else:
                raise UserError("La factura debe estar en estado contabilizada o pagada.", rec_party)
        return 'end'