from decimal import Decimal
from trytond.pool import PoolMeta, Pool
from trytond.model import fields
from trytond.pyson import Eval
from trytond.wizard import Wizard, StateTransition
from trytond.transaction import Transaction
from trytond.exceptions import UserError, UserWarning
from sql import Table
import logging
import datetime



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
            ('account.invoice|import_credit_note', "Importar Nota de Crédito"),
            )

class Invoice(metaclass=PoolMeta):
    'Invoice'
    __name__ = 'account.invoice'
    electronic_state = fields.Selection(ELECTRONIC_STATES, 'Electronic State',
                                        states={'invisible': Eval('type') != 'out'}, readonly=True)
    id_tecno = fields.Char('Id Tabla Sqlserver (credit note)', required=False)

    @staticmethod
    def default_electronic_state():
        return 'none'

    
    #Nota de crédito
    @classmethod
    def import_credit_note(cls):
        logging.warning('RUN NOTA')
        nota_tecno = cls.get_data_tecno()
        actualizacion = cls.create_or_update()

        if not nota_tecno:
            actualizacion.save()
            return

        logs = []
        pool = Pool()
        Party = pool.get('party.party')
        Invoice = pool.get('account.invoice')
        Line = pool.get('account.invoice.line')
        Product = Pool().get('product.product')
        Config = pool.get('conector.configuration')
        PaymentTerm = pool.get('account.invoice.payment_term')

        invoices_create = []
        lines_create = []
        for nota in nota_tecno:
            id_nota = str(nota.sw)+'-'+nota.tipo+'-'+str(nota.Numero_documento)
            invoice = Invoice.search([('id_tecno', '=', id_nota)])
            if invoice:
                msg = f"La nota {id_nota} ya existe en Tryton"
                logs.append(msg)
                Config.mark_imported(id_nota)
                continue
            party = Party.search([('id_number', '=', nota.nit_Cedula)])
            if not party:
                msg = f' No se encontro el tercero {nota.nit_Cedula} de la nota {id_nota}'
                logging.error(msg)
                logs.append(msg)
                actualizacion.reset_writedate('TERCEROS')
                continue
            party = party[0]
            plazo_pago = PaymentTerm.search([('id_tecno', '=', nota.condicion)])
            if not plazo_pago:
                msg = f'Plazo de pago {nota.condicion} no existe para la nota {id_nota}'
                logging.error(msg)
                logs.append(msg)
                continue
            plazo_pago = plazo_pago[0]
            fecha = str(nota.fecha_hora).split()[0].split('-')
            fecha_date = datetime.date(int(fecha[0]), int(fecha[1]), int(fecha[2]))

            invoice = Invoice()
            invoice.party = party
            invoice.invoice_date = fecha_date
            invoice.number = nota.tipo+'-'+str(nota.Numero_documento)
            invoice.reference = nota.tipo+'-'+str(nota.Numero_documento)
            invoice.description = 'NOTA DE CREDITO'
            invoice.invoice_type = '91'
            invoice.payment_term = plazo_pago

            linea_tecno = cls.get_dataline_tecno(id_nota)
            for linea in linea_tecno:
                product = Product.search([('id_tecno', '=', linea.IdProducto)])
                if not product:
                    msg = f"no se encontro el producto con id {linea.IdProducto}"
                    logs.append(msg)
                    raise UserError("ERROR PRODUCTO", msg)
                cantidad = abs(round(linea.Cantidad_Facturada, 3)) * -1
                valor_unitario = Decimal(linea.Valor_Unitario)
                line = Line()
                line.invoice = invoice
                line.product = product[0]
                line.quantity = cantidad
                line.unit_price = valor_unitario
                lines_create.append(line)
        
        Invoice.create(invoices_create)
        Line.create(lines_create)
        Invoice.post(invoices_create)
        actualizacion.add_logs(actualizacion, logs)
        for invoice in invoices_create:
            Config.mark_imported(invoice.id_tecno)
        logging.warning('FINISH NOTA')


    @classmethod
    def get_data_tecno(cls):
        Config = Pool().get('conector.configuration')
        config, = Config.search([], order=[('id', 'DESC')], limit=1)
        fecha = config.date.strftime('%Y-%m-%d %H:%M:%S')
        consult = "SET DATEFORMAT ymd SELECT * FROM dbo.Documentos WHERE sw = 32 AND fecha_hora >= CAST('"+fecha+"' AS datetime) AND exportado != 'T'"
        result = Config.get_data(consult)
        return result

    @classmethod
    def get_dataline_tecno(cls, id):
        lista = id.split('-')
        Config = Pool().get('conector.configuration')
        consult = "SELECT * FROM dbo.Documentos_Lin WHERE sw = "+lista[0]+" AND Numero_Documento = "+lista[1]+" AND tipo = "+lista[2]+" order by seq"
        result = Config.get_data(consult)
        return result

    
    #Crea o actualiza un registro de la tabla actualización en caso de ser necesario
    @classmethod
    def create_or_update(cls):
        Actualizacion = Pool().get('conector.actualizacion')
        actualizacion = Actualizacion.search([('name', '=','NOTA DE CREDITO')])
        if actualizacion:
            #Se busca un registro con la actualización
            actualizacion, = actualizacion
        else:
            #Se crea un registro con la actualización
            actualizacion = Actualizacion()
            actualizacion.name = 'NOTA DE CREDITO'
            actualizacion.logs = 'logs...'
            actualizacion.save()
        return actualizacion


class UpdateInvoiceTecno(Wizard):
    'Update Invoice Tecno'
    __name__ = 'account.invoice.update_invoice_tecno'
    start_state = 'do_submit'
    do_submit = StateTransition()

    def transition_do_submit(self):
        pool = Pool()
        Invoice = pool.get('account.invoice')
        Sale = pool.get('sale.sale')
        Purchase = pool.get('purchase.purchase')

        ids = Transaction().context['active_ids']

        to_delete_sales = []
        to_delete_purchases = []
        for invoice in Invoice.browse(ids):
            rec_name = invoice.rec_name
            party_name = invoice.party.name
            rec_party = rec_name+' de '+party_name
            if invoice.number and '-' in invoice.number:
                if invoice.type == 'out':
                    #print('Factura de cliente: ', rec_party)
                    sale = Sale.search([('number', '=', invoice.number)])
                    if sale:
                        to_delete_sales.append(sale[0])
                    #else:
                    #    raise UserError("No existe la venta para la factura: ", rec_party)
                elif invoice.type == 'in':
                    #print('Factura de proveedor: ', rec_party)
                    purchase = Purchase.search([('number', '=', invoice.number)])
                    if purchase:
                        to_delete_purchases.append(purchase[0])
                    #else:
                    #    raise UserError("No existe la compra para la factura: ", rec_party)
            else:
                raise UserError("Revisa el número de la factura (tipo-numero): ", rec_party)
        Sale.delete_imported_sales(to_delete_sales)
        Purchase.delete_imported_purchases(to_delete_purchases)
        return 'end'

    def end(self):
        return 'reload'



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