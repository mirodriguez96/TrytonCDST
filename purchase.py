import datetime
from trytond.model import fields
from trytond.pool import Pool, PoolMeta
from trytond.exceptions import UserError
from trytond.transaction import Transaction
from decimal import Decimal
import logging


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
        print("--------------RUN COMPRAS--------------")
        cls.last_update()

    @classmethod
    def add_purchase(cls, compras_tecno):
        logs = 'Logs...'
        if compras_tecno:
            pool = Pool()
            Purchase = pool.get('purchase.purchase')
            PurchaseLine = pool.get('purchase.line')
            location = pool.get('stock.location')
            payment_term = pool.get('account.invoice.payment_term')
            Party = pool.get('party.party')
            Address = pool.get('party.address')
            coluns_doc = cls.get_columns_db_tecno('Documentos')
            columns_tipodoc = cls.get_columns_db_tecno('TblTipoDoctos')
            
            #Procedemos a realizar la compra
            for compra in compras_tecno:
                sw = compra[coluns_doc.index('sw')]
                numero_doc = compra[coluns_doc.index('Numero_documento')]
                tipo_doc = compra[coluns_doc.index('tipo')].strip()
                id_compra = str(sw)+'-'+tipo_doc+'-'+str(numero_doc)
                existe = cls.buscar_compra(id_compra)
                if not existe:
                    #purchase = {}
                    purchase = Purchase()
                    purchase.number = tipo_doc+'-'+str(numero_doc)
                    purchase.id_tecno = id_compra
                    purchase.description = compra[coluns_doc.index('notas')].replace('\n', ' ').replace('\r', '')
                    #Se trae la fecha de la compra y se adapta al formato correcto para Tryton
                    fecha = str(compra[coluns_doc.index('fecha_hora')]).split()[0].split('-')
                    fecha_date = datetime.date(int(fecha[0]), int(fecha[1]), int(fecha[2]))
                    purchase.purchase_date = fecha_date
                    party = Party.search([('id_number', '=', compra[coluns_doc.index('nit_Cedula')])])
                    if not party:
                        logging.warning("No se econtro el tercero con id: "+compra[coluns_doc.index('nit_Cedula')], id_compra)
                        logs = logs+"\n"+"Error compra: "+id_compra+" - No se econtro el tercero con id: "+compra[coluns_doc.index('nit_Cedula')]
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
                    purchase.payment_term = plazo_pago
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
                        #print(id_producto, line.unit)
                        line.on_change_product() #Comprueba los cambios y trae los impuestos del producto
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
                            raise UserError("ERROR ENVIO: "+str(shipment_in.number), e)                     
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
                        total = abs(total_amount['total_amount'][invoice.id])
                        total_tecno = Decimal(compra[coluns_doc.index('valor_total')])
                        diferencia_total = abs(total - total_tecno)
                        if diferencia_total <= 0.5:
                            invoice.post_batch([invoice])
                            invoice.post([invoice])
                        invoice.save()
                    except Exception as e:
                        print(e)
                        raise UserError("ERROR FACTURA: "+str(invoice.number), e)
                    purchase.save()
                    cls.importado(id_compra)
                    #Transaction().connection.commit()
                else:
                    cls.importado(id_compra)
        #Se crea o actualiza la fecha de importación junto a los logs
        cls.create_or_update(logs)


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
    def get_data_where_tecno(cls, date): #REVISAR PARA OPTIMIZAR
        data = []
        try:
            Config = Pool().get('conector.configuration')
            conexion = Config.conexion()
            with conexion.cursor() as cursor:
                consult = "FROM dbo.Documentos WHERE fecha_hora >= CAST('"+date+"' AS datetime) AND (sw = 3 or sw = 4) AND exportado != 'T'"
                #cant_importar = cursor.execute("SELECT COUNT(*) "+consult)
                #total_importar = int(cant_importar.fetchall()[0][0])
                #cant = int(total_importar/1000)+1
                #for n in range(cant):
                #    cant_importados = cursor.execute("SELECT COUNT(*) FROM dbo.Documentos WHERE fecha_hora >= CAST('"+date+"' AS datetime) AND (sw = 1 OR sw = 2) AND exportado = 'T'")
                #    total_importados = int(cant_importados.fetchall()[0][0])
                #    inicio = 0
                #    if ((n+1)*1000 - total_importados) == 0:
                #        pass
                #    #(sw = 1  compras) (sw = 2 devoluciones)
                #    query = cursor.execute("SELECT * "+consult+" ORDER BY sw OFFSET "+str(inicio)+" ROWS FETCH NEXT 1000 ROWS ONLY")
                #    data = list(query.fetchall())
                #    cls.add_purchase(data)
                query = cursor.execute("SELECT TOP(100) * "+consult)
                data = list(query.fetchall())
                cls.add_purchase(data)
                #faltantes = cursor.execute("SELECT * "+consult)
                #print("FINALIZADO: ", list(faltantes.fetchall()))
                #raise UserError("Documentos faltantes ", list(faltantes.fetchall()))
        except Exception as e:
            print(e)
            raise UserError('ERROR ', str(e))
            #print("ERROR QUERY get_data_where_tecno: ", e)
        #return data

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
            raise UserError('Error al actualizar como importado: ', e)

    #Función encargada de convertir una fecha dada, al formato y orden para consultas sql server
    @classmethod
    def convert_date(cls, fecha):
        result = fecha.strftime('%Y-%d-%m %H:%M:%S')
        return result

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

    #Función encargada de traer los datos de la bd con una fecha dada.
    @classmethod
    def last_update(cls):
        Actualizacion = Pool().get('conector.actualizacion')
        #Se consulta la ultima actualización realizada para los terceros
        ultima_actualizacion = Actualizacion.search([('name', '=','COMPRAS')])
        if ultima_actualizacion:
            #Se calcula la fecha restando la diferencia de horas que tiene el servidor con respecto al clienete
            if ultima_actualizacion[0].write_date:
                fecha = (ultima_actualizacion[0].write_date - datetime.timedelta(hours=5))
            else:
                fecha = (ultima_actualizacion[0].create_date - datetime.timedelta(hours=5))
        else:
            Config = Pool().get('conector.configuration')
            config, = Config.search([], order=[('id', 'DESC')], limit=1)
            fecha = config.date
            #fecha = datetime.date(1,1,1)
        fecha = fecha.strftime('%Y-%d-%m %H:%M:%S')
        data = cls.get_data_where_tecno(fecha)
        return data

    #Crea o actualiza un registro de la tabla actualización en caso de ser necesario
    @classmethod
    def create_or_update(cls, logs):
        Actualizacion = Pool().get('conector.actualizacion')
        actualizacion = Actualizacion.search([('name', '=','COMPRAS')])
        if actualizacion:
            #Se busca un registro con la actualización
            actualizacion, = Actualizacion.search([('name', '=','COMPRAS')])
            actualizacion.name = 'COMPRAS'
            actualizacion.logs = logs
            actualizacion.save()
        else:
            #Se crea un registro con la actualización
            actualizar = Actualizacion()
            actualizar.name = 'COMPRAS'
            actualizar.logs = logs
            actualizar.save()

    #Metodo encargado de buscar si exste una compra
    @classmethod
    def buscar_compra(cls, id):
        purchase = Pool().get('purchase.purchase')
        purchase = purchase.search([('id_tecno', '=', id)])
        if purchase:
            return purchase[0]
        else:
            return False