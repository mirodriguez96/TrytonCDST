import datetime
from trytond.model import fields
from trytond.pool import Pool, PoolMeta
from trytond.exceptions import UserError
from trytond.transaction import Transaction
from decimal import Decimal
import logging
from sql import Table


__all__ = [
    'Purchase',
    'Cron',
    ]


class Cron(metaclass=PoolMeta):
    'Cron'
    __name__ = 'ir.cron'

    @classmethod
    def __setup__(cls):
        super().__setup__()
        cls.method.selection.append(
            ('purchase.purchase|import_data_purchase', "Importar compras"),
            )


#Heredamos del modelo purchase.purchase para agregar el campo id_tecno
class Purchase(metaclass=PoolMeta):
    'Purchase'
    __name__ = 'purchase.purchase'
    id_tecno = fields.Char('Id Tabla Sqlserver', required=False)

    @classmethod
    def import_data_purchase(cls):
        logging.warning('RUN COMPRAS')
        data = cls.get_data_tecno()
        cls.add_purchase(data)

    @classmethod
    def add_purchase(cls, compras_tecno):
        actualizacion = cls.create_or_update()
        logs = actualizacion.logs
        if not logs:
            logs = 'logs...'
        created_purchase = []
        if compras_tecno:
            pool = Pool()
            Purchase = pool.get('purchase.purchase')
            PurchaseLine = pool.get('purchase.line')
            location = pool.get('stock.location')
            payment_term = pool.get('account.invoice.payment_term')
            Party = pool.get('party.party')
            Address = pool.get('party.address')
            Tax = pool.get('account.tax')
            Module = pool.get('ir.module')
            coluns_doc = cls.get_columns_db_tecno('Documentos')
            columns_tipodoc = cls.get_columns_db_tecno('TblTipoDoctos')

            company_operation = Module.search([('name', '=', 'company_operation'), ('state', '=', 'activated')])
            if company_operation:
                CompanyOperation = pool.get('company.operation_center')
                company_operation = CompanyOperation(1)
            #Procedemos a realizar la compra
            for compra in compras_tecno:
                sw = compra[coluns_doc.index('sw')]
                numero_doc = compra[coluns_doc.index('Numero_documento')]
                tipo_doc = compra[coluns_doc.index('tipo')].strip()
                id_compra = str(sw)+'-'+tipo_doc+'-'+str(numero_doc)
                try:
                    existe = cls.buscar_compra(id_compra)
                    if not existe:
                        #purchase = {}
                        purchase = Purchase()
                        purchase.number = tipo_doc+'-'+str(numero_doc)
                        purchase.id_tecno = id_compra
                        print(id_compra)
                        purchase.description = compra[coluns_doc.index('notas')].replace('\n', ' ').replace('\r', '')
                        #Se trae la fecha de la compra y se adapta al formato correcto para Tryton
                        fecha = str(compra[coluns_doc.index('fecha_hora')]).split()[0].split('-')
                        fecha_date = datetime.date(int(fecha[0]), int(fecha[1]), int(fecha[2]))
                        purchase.purchase_date = fecha_date
                        party_id_number = compra[coluns_doc.index('nit_Cedula')]
                        party = Party.search([('id_number', '=', party_id_number)])
                        if not party:
                            msg1 = f'Error compra: {id_compra}'
                            msg2 = f'No se encontró el cliente con id: {party_id_number}'
                            full_msg = ' - '.join([msg1, msg2])
                            logging.warning(full_msg)
                            logs += '\n' + full_msg
                            continue
                        party = party[0]                        
                        purchase.party = party
                        purchase.invoice_party = party
                        #Se busca una dirección del tercero para agregar en la factura y envio
                        address = Address.search([('party', '=', party.id)], limit=1)
                        if address:
                            purchase.invoice_address = address[0].id
                        #Se indica a que bodega pertenece
                        bodega = location.search([('id_tecno', '=', compra[coluns_doc.index('bodega')])])
                        if not bodega:
                            logging.warning("No se econtro la bodega: "+compra[coluns_doc.index('bodega')], id_compra)
                            logs = logs+"\n"+"Error compra: "+id_compra+" - NO EXISTE LA BODEGA: "+compra[coluns_doc.index('bodega')]
                            continue
                        bodega = bodega[0]
                        purchase.warehouse = bodega
                        #Se le asigna el plazo de pago correspondiente
                        condicion = compra[coluns_doc.index('condicion')]
                        plazo_pago = payment_term.search([('id_tecno', '=', condicion)])
                        if not plazo_pago:
                            logging.warning("No se econtro el plazo de pago: "+condicion, id_compra)
                            logs = logs+"\n"+"Error compra: "+id_compra+" - No se econtro el plazo de pago: "+condicion
                            continue
                        purchase.payment_term = plazo_pago[0]

                        retencion_iva = False
                        if compra.retencion_iva and compra.retencion_iva > 0:
                            retencion_iva = True
                        retencion_ica = False
                        if compra.retencion_ica and compra.retencion_ica > 0:
                            retencion_ica = True
                        retencion_rete = False
                        if compra.retencion_causada and compra.retencion_causada > 0:
                            if not retencion_iva and not retencion_ica:
                                retencion_rete = True
                            elif (compra.retencion_iva + compra.retencion_ica) != compra.retencion_causada:
                                retencion_rete = True

                        #Ahora traemos las lineas de producto para la compra a procesar
                        documentos_linea = cls.get_line_where(str(sw), str(numero_doc), str(tipo_doc))
                        col_line = cls.get_columns_db_tecno('Documentos_Lin')
                        for lin in documentos_linea:
                            id_producto = str(lin[col_line.index('IdProducto')])
                            #print(id_producto)
                            producto = cls.buscar_producto(id_producto)
                            if not producto.template.purchasable:
                                raise UserError("El siguiente producto no es comprable: ", producto)
                            #template, = Template.search([('id', '=', producto.template)])
                            line = PurchaseLine()
                            line.product = producto
                            line.purchase = purchase
                            line.type = 'line'
                            line.unit = producto.template.default_uom
                            #Se verifica si es una devolución
                            cantidad_facturada = abs(round(lin[col_line.index('Cantidad_Facturada')], 3))
                            if line.unit.id == 1:
                                cantidad_facturada = int(cantidad_facturada)
                            if sw == 4:
                                line.quantity = cantidad_facturada * -1
                                #Se indica a que documento hace referencia la devolucion
                                purchase.reference = compra[coluns_doc.index('Tipo_Docto_Base')].strip()+'-'+str(compra[coluns_doc.index('Numero_Docto_Base')])
                            else:
                                line.quantity = cantidad_facturada
                                purchase.reference = tipo_doc+'-'+str(numero_doc)
                            if company_operation:
                                line.operation_center = company_operation
                            #Comprueba los cambios y trae los impuestos del producto
                            line.on_change_product()
                            #Se verifica si el impuesto al consumo fue aplicado
                            impuesto_consumo = lin[col_line.index('Impuesto_Consumo')]
                            #A continuación se verifica las retenciones e impuesto al consumo
                            impuestos_linea = []
                            for impuestol in line.taxes:
                                clase_impuesto = impuestol.classification_tax
                                if clase_impuesto == '05' and retencion_iva:
                                    impuestos_linea.append(impuestol)
                                elif clase_impuesto == '06' and retencion_rete:
                                    impuestos_linea.append(impuestol)
                                elif clase_impuesto == '07' and retencion_ica:
                                    impuestos_linea.append(impuestol)
                                elif impuestol.consumo and impuesto_consumo > 0:
                                    #Se busca el impuesto al consumo con el mismo valor para aplicarlo
                                    tax = Tax.search([('consumo', '=', True), ('type', '=', 'fixed'), ('amount', '=', impuesto_consumo)])
                                    if tax:
                                        tax, = tax
                                        impuestos_linea.append(tax)
                                    else:
                                        raise UserError('ERROR IMPUESTO', 'No se encontró el impuesto al consumo: '+id_compra)
                                elif clase_impuesto != '05' and clase_impuesto != '06' and clase_impuesto != '07' and not impuestol.consumo:
                                    impuestos_linea.append(impuestol)
                            line.taxes = impuestos_linea
                            
                            line.unit_price = lin[col_line.index('Valor_Unitario')]
                            line.save()
                        #Procesamos la compra para generar la factura y procedemos a rellenar los campos de la factura
                        #purchase.save()
                        purchase.quote([purchase])
                        purchase.confirm([purchase])
                        #Se requiere procesar de forma 'manual' la compra para que genere la factura
                        purchase.process([purchase])
                        #Se hace uso del asistente para crear el envio del proveedor
                        purchase.generate_shipment([purchase])
                        if purchase.shipments:
                            try:
                                shipment_in, = purchase.shipments
                                shipment_in.number = tipo_doc+'-'+str(numero_doc)
                                shipment_in.reference = tipo_doc+'-'+str(numero_doc)
                                shipment_in.planned_date = fecha_date
                                shipment_in.effective_date = fecha_date
                                shipment_in.receive([shipment_in])
                                shipment_in.done([shipment_in])
                            except Exception as e:
                                print(e)
                                raise UserError("ERROR ENVIO: "+str(shipment_in.number), str(e))
                        else:
                            msg1 = f'No se creo envio en la compra: {purchase.id_tecno}'
                            logs += '\n' + msg1
                        if purchase.invoices:
                            try:
                                invoice, = purchase.invoices
                                invoice.number = tipo_doc+'-'+str(numero_doc)
                                invoice.reference = tipo_doc+'-'+str(numero_doc)
                                invoice.invoice_date = fecha_date
                                #Se agrega en la descripcion el nombre del tipo de documento de la tabla en sqlserver
                                desc = cls.get_tipo_dcto(tipo_doc)
                                if desc:
                                    invoice.description = desc[0][columns_tipodoc.index('TipoDoctos')].replace('\n', ' ').replace('\r', '')
                                invoice.validate_invoice([invoice])
                                #Verificamos que el total de la tabla en sqlserver coincidan o tengan una diferencia menor a 4 decimales, para contabilizar la factura
                                total_amount = invoice.get_amount([invoice], 'total_amount')
                                total_amount = abs(total_amount['total_amount'][invoice.id])
                                total_tecno = Decimal(abs(compra.valor_total))
                                retencion_causada = Decimal(abs(compra.retencion_causada))
                                total_tecno = total_tecno - retencion_causada
                                diferencia_total = abs(total_amount - total_tecno)
                                if diferencia_total < Decimal(6.0):
                                    with Transaction().set_context(_skip_warnings=True):
                                        invoice.post_batch([invoice])
                                        invoice.post([invoice])
                                invoice.save()
                            except Exception as e:
                                print(e)
                                raise UserError(f"ERROR FACTURA: {invoice.number}", str(e))
                        else:
                            msg1 = f'No se creo factura en la compra: {purchase.id_tecno}'
                            logs += '\n' + msg1
                        purchase.save()
                    created_purchase.append(id_compra)
                except Exception as e:
                    msg = f"EXCEPCION: Compra {id_compra}  {str(e)}"
                    logs.append(msg)
                    continue
        for idc in created_purchase:
            cls.importado(idc)
            #print('creado...', idc) #TEST
        #Se crea o actualiza la fecha de importación junto a los logs
        actualizacion.logs = logs
        actualizacion.save()
        logging.warning('FINISH COMPRAS')

    @classmethod
    def get_data_table(cls, table):
        data = []
        try:
            Config = Pool().get('conector.configuration')
            conexion = Config.conexion()
            with conexion.cursor() as cursor:
                query = cursor.execute("SELECT * FROM dbo."+table+"")
                data = list(query.fetchall())
        except Exception as e:
            print("ERROR QUERY get_data_table: ", e)
            raise UserError('ERROR QUERY get_data_table: ', str(e))
        return data

    @classmethod
    def get_data_parametros(cls, id):
        data = []
        try:
            Config = Pool().get('conector.configuration')
            conexion = Config.conexion()
            with conexion.cursor() as cursor:
                query = cursor.execute("SELECT * FROM dbo.TblParametro WHERE IdParametro = "+id+"")
                data = list(query.fetchall())
        except Exception as e:
            print("ERROR QUERY get_data_parametros: ", e)
            raise UserError('ERROR QUERY get_data_parametros: ', str(e))
        return data

    #Metodo encargado de traer el tipo de documento de la bd
    @classmethod
    def get_tipo_dcto(cls, id):
        data = []
        try:
            Config = Pool().get('conector.configuration')
            conexion = Config.conexion()
            with conexion.cursor() as cursor:
                query = cursor.execute("SELECT * FROM dbo.TblTipoDoctos WHERE idTipoDoctos = '"+id+"'")
                data = list(query.fetchall())
        except Exception as e:
            print("ERROR QUERY TblTipoDoctos: ", e)
        return data

    #Esta función se encarga de traer todos los datos de una tabla dada de la bd
    @classmethod
    def get_line_where(cls, sw, nro, tipo):
        data = []
        try:
            Config = Pool().get('conector.configuration')
            conexion = Config.conexion()
            with conexion.cursor() as cursor:
                query = cursor.execute("SELECT * FROM dbo.Documentos_Lin WHERE sw = "+sw+" AND Numero_Documento = "+nro+" AND tipo = "+tipo)
                data = list(query.fetchall())
        except Exception as e:
            print("ERROR QUERY Documentos_Lin: ", e)
        return data

    #Función encargada de consultar las columnas pertenecientes a 'x' tabla de la bd
    @classmethod
    def get_columns_db_tecno(cls, table):
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

    #Esta función se encarga de traer todos los datos de una tabla dada de acuerdo al rango de fecha dada de la bd
    @classmethod
    def get_data_tecno(cls):
        Config = Pool().get('conector.configuration')
        config, = Config.search([], order=[('id', 'DESC')], limit=1)
        fecha = config.date.strftime('%Y-%m-%d %H:%M:%S')
        #consult = "SET DATEFORMAT ymd SELECT * FROM dbo.Documentos WHERE (sw = 3 OR sw = 4) AND tipo = 148 AND fecha_hora >= CAST('"+fecha+"' AS datetime) AND exportado != 'T'"
        consult = "SET DATEFORMAT ymd SELECT TOP(100) * FROM dbo.Documentos WHERE fecha_hora >= CAST('"+fecha+"' AS datetime) AND (sw = 3 OR sw = 4) AND exportado != 'T' ORDER BY fecha_hora ASC"
        result = Config.get_data(consult)
        return result

    #Se marca como importado 'T' la compra en la DB de sql server
    @classmethod
    def importado(cls, id):
        lista = id.split('-')
        Config = Pool().get('conector.configuration')
        consult = "UPDATE dbo.Documentos SET exportado = 'T' WHERE sw ="+lista[0]+" and tipo = "+lista[1]+" and Numero_documento = "+lista[2]
        Config.set_data(consult)

    #Función encargada de consultar si existe un producto dado de la bd
    @classmethod
    def buscar_producto(cls, id_producto):
        Product = Pool().get('product.product')
        try:
            producto, = Product.search([('id_tecno', '=', id_producto)])
        except ValueError:
            print("Error, no existe el producto con la siguiente id: ", id_producto)
            raise UserError("Error, no existe el producto con la siguiente id: ", id_producto)
        else:
            return producto


    #Crea o actualiza un registro de la tabla actualización en caso de ser necesario
    @classmethod
    def create_or_update(cls):
        Actualizacion = Pool().get('conector.actualizacion')
        actualizacion = Actualizacion.search([('name', '=','COMPRAS')])
        if actualizacion:
            #Se busca un registro con la actualización
            actualizacion, = Actualizacion.search([('name', '=','COMPRAS')])
            actualizacion.name = 'COMPRAS'
            actualizacion.logs = 'logs...'
            actualizacion.save()
        else:
            #Se crea un registro con la actualización
            actualizacion = Actualizacion()
            actualizacion.name = 'COMPRAS'
            actualizacion.save()
        return actualizacion

    #Metodo encargado de buscar si exste una compra
    @classmethod
    def buscar_compra(cls, id):
        purchase = Pool().get('purchase.purchase')
        purchase = purchase.search([('id_tecno', '=', id)])
        if purchase:
            return purchase[0]
        else:
            return False


    @classmethod
    def delete_imported_purchases(cls, purchases):
        pool = Pool()
        #Purchase = pool.get('purchase.purchase')
        purchase_table = Table('purchase_purchase')
        invoice_table = Table('account_invoice')
        move_table = Table('account_move')
        stock_move_table = Table('stock_move')
        cursor = Transaction().connection.cursor()
        Conexion = pool.get('conector.configuration')
        for purchase in purchases:
            if purchase.id_tecno:
                lista = purchase.id_tecno.split('-')
                consult = "UPDATE dbo.Documentos SET exportado = 'S' WHERE sw ="+lista[0]+" and tipo = "+lista[1]+" and Numero_documento = "+lista[2]
                Conexion.set_data(consult)
            else:
                raise UserError("Error: ", f"No se encontró el id_tecno de {purchase}")
            for invoice in purchase.invoices:
                if invoice.state == 'paid':
                    cls.unreconcile_move(invoice.move)
                if invoice.move:
                    cursor.execute(*move_table.update(
                        columns=[move_table.state],
                        values=['draft'],
                        where=move_table.id == invoice.move.id)
                    )
                    cursor.execute(*move_table.delete(
                        where=move_table.id == invoice.move.id)
                    )
                cursor.execute(*invoice_table.update(
                    columns=[invoice_table.state, invoice_table.number],
                    values=['validate', None],
                    where=invoice_table.id == invoice.id)
                )
                cursor.execute(*invoice_table.delete(
                    where=invoice_table.id == invoice.id)
                )

            if purchase.id:
                cursor.execute(*purchase_table.update(
                    columns=[purchase_table.state, purchase_table.shipment_state, purchase_table.invoice_state],
                    values=['draft', 'none', 'none'],
                    where=purchase_table.id == purchase.id)
                )
            # The stock moves must be delete
            stock_moves = [m.id for line in purchase.lines for m in line.moves]
            if stock_moves:
                cursor.execute(*stock_move_table.update(
                    columns=[stock_move_table.state],
                    values=['draft'],
                    where=stock_move_table.id.in_(stock_moves)
                ))

                cursor.execute(*stock_move_table.delete(
                    where=stock_move_table.id.in_(stock_moves))
                )

            # Se elimina la compra
            cursor.execute(*purchase_table.delete(
                where=purchase_table.id == purchase.id)
            )


    @classmethod
    def unreconcile_move(self, move):
        Reconciliation = Pool().get('account.move.reconciliation')
        reconciliations = [l.reconciliation for l in move.lines if l.reconciliation]
        if reconciliations:
            Reconciliation.delete(reconciliations)