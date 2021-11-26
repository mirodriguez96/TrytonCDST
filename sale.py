import datetime
from trytond.model import fields
from trytond.pool import Pool, PoolMeta
from trytond.exceptions import UserError
from decimal import Decimal


__all__ = [
    'Sale',
    'SaleLine',
    'Cron',
    "Location"
    ]


class Cron(metaclass=PoolMeta):
    'Cron'
    __name__ = 'ir.cron'

    @classmethod
    def __setup__(cls):
        super().__setup__()
        cls.method.selection.append(
            ('sale.sale|import_data_sale', "Update sales"),
            )


#Heredamos del modelo sale.sale para agregar el campo id_tecno
class Sale(metaclass=PoolMeta):
    'Sale'
    __name__ = 'sale.sale'
    id_tecno = fields.Char('Id Tabla Sqlserver', required=False)

    @classmethod
    def import_data_sale(cls):
        print("--------------RUN VENTAS--------------")
        ventas_tecno = cls.last_update()
        cls.create_or_update()
        if ventas_tecno:
            pool = Pool()
            Sale = pool.get('sale.sale')
            SaleLine = pool.get('sale.line')
            Invoice = pool.get('account.invoice')
            #Tax = pool.get('account.tax')
            #Taxes = pool.get('sale.line-account.tax')
            #CustomerTax = pool.get('product.category-customer-account.tax')
            Party = pool.get('party.party')
            Address = pool.get('party.address')
            Template = pool.get('product.template')
            coluns_doc = cls.get_columns_db_tecno('Documentos')
            columns_tipodoc = cls.get_columns_db_tecno('TblTipoDoctos')
            cls.import_warehouse()
            #create_sale = []
            #Procedemos a realizar una venta
            for vent in ventas_tecno:
                sw = vent[coluns_doc.index('sw')]
                numero_doc = vent[coluns_doc.index('Numero_documento')]
                tipo_doc = vent[coluns_doc.index('tipo')].strip()
                id_venta = str(sw)+'-'+tipo_doc+'-'+str(numero_doc)
                existe = cls.buscar_venta(id_venta)
                if not existe:
                    venta = Sale()
                    venta.number = tipo_doc+'-'+str(numero_doc)
                    venta.id_tecno = id_venta
                    venta.description = vent[coluns_doc.index('notas')].replace('\n', ' ').replace('\r', '')
                    venta.invoice_method = 'order'
                    venta.invoice_type = 'M'
                    fecha = str(vent[coluns_doc.index('Fecha_Orden_Venta')]).split()[0].split('-')
                    fecha_date = datetime.date(int(fecha[0]), int(fecha[1]), int(fecha[2]))
                    venta.sale_date = fecha_date
                    venta.shipment_method = 'order'
                    try:
                        party, = Party.search([('id_number', '=', vent[coluns_doc.index('nit_Cedula')])])
                    except:
                        raise UserError("No se econtro el tercero con id: ", vent[coluns_doc.index('nit_Cedula')])
                    venta.party = party.id
                    address = Address.search([('party', '=', party.id)], limit=1)
                    venta.invoice_address = address[0].id
                    venta.shipment_address = address[0].id
                    #Ahora traemos las lineas de producto para la venta a procesar
                    documentos_linea = cls.get_line_where(str(sw), str(numero_doc), str(tipo_doc))
                    col_line = cls.get_columns_db_tecno('Documentos_Lin')
                    #create_line = []
                    for lin in documentos_linea:
                        producto = cls.buscar_producto(str(lin[col_line.index('IdProducto')]))
                        if producto:
                            template, = Template.search([('id', '=', producto.template)])
                            line = SaleLine()
                            seq = lin[col_line.index('seq')]
                            id_bodega = lin[col_line.index('IdBodega')]
                            id_t = str(sw)+'-'+tipo_doc+'-'+str(seq)+'-'+str(numero_doc)+'-'+str(id_bodega)
                            line.id_tecno = id_t
                            line.product = producto
                            if sw == 2:
                                line.quantity = (abs(int(lin[col_line.index('Cantidad_Facturada')])))*-1
                                #Se indica a que documento hace referencia la devolucion
                                venta.reference = vent[coluns_doc.index('Tipo_Docto_Base')].strip()+'-'+str(vent[coluns_doc.index('Numero_Docto_Base')])
                            else:
                                line.quantity = abs(int(lin[col_line.index('Cantidad_Facturada')]))
                                venta.reference = tipo_doc+'-'+str(numero_doc)
                            line.sale = venta
                            line.type = 'line'
                            line.unit = template.default_uom
                            line.on_change_product() #TEST
                            line.unit_price = lin[col_line.index('Valor_Unitario')]
                            #Agregar impuestos a la venta
                            #taxc = CustomerTax.search([('category', '=', template.account_category)])
                            #if taxc:
                            #    tax = Taxes()
                            #    tax.line = line
                            #    tax.tax = taxc[0].tax
                            #    line.save()
                            #    tax.save()
                            #Aplicamos una misma retención para todas las ventas
                            #retencion, = Tax.search([('name', '=', 'RET. RENTA 0,4%')])
                            #if lin[col_line.index('Porcentaje_ReteFuente')] > 0:
                            #    tax = Taxes()
                            #    tax.line = line
                            #    tax.tax = retencion
                            #    line.save()
                            #    tax.save()
                            #Verificamos si hay descuento para la linea de producto y se agrega su respectivo descuento
                            if lin[col_line.index('Porcentaje_Descuento_1')] > 0:
                                porcentaje = lin[col_line.index('Porcentaje_Descuento_1')]/100
                                line.base_price = lin[col_line.index('Valor_Unitario')]
                                line.discount_rate = Decimal(str(porcentaje))
                                line.on_change_discount_rate()
                            line.save()
                        else:
                            raise UserError("Error, no existe el producto con la siguiente id: ", str(lin[col_line.index('IdProducto')]))
                    #Procesamos la venta para generar la factura y procedemos a rellenar los campos de la factura
                    venta.state = 'confirmed'
                    print('state: ', venta.state)
                    if venta.state == 'confirmed':
                        venta.process([venta])
                        print('process....')
                    invoice, = venta.invoices
                    venta.save()
                    invoice.operation_type = 10
                    invoice.number = tipo_doc+'-'+str(numero_doc)
                    invoice.reference = tipo_doc+'-'+str(numero_doc)
                    invoice.invoice_date = fecha_date
                    #Se agrega en la descripcion el nombre del tipo de documento de la tabla en sqlserver
                    desc = cls.get_tipo_dcto(tipo_doc)
                    if desc:
                        invoice.description = desc[0][columns_tipodoc.index('TipoDoctos')].replace('\n', ' ').replace('\r', '')
                    Invoice.validate_invoice([invoice])
                    #Verificamos que el total de la tabla en sqlserver coincidan, para contabilizar la factura
                    total = Invoice.get_amount([invoice], 'total_amount')
                    total_tecno = Decimal(vent[coluns_doc.index('valor_total')])
                    if total['total_amount'][invoice.id] == total_tecno:
                        Invoice.post_batch([invoice])
                    invoice.save()
                #create_invoice.append(invoice)
            #Sale.save(create_sale)


    @classmethod
    def import_warehouse(cls):
        location = Pool().get('stock.location')
        bodegas = cls.get_data_table('TblBodega')
        columns = cls.get_columns_db_tecno('TblBodega')

        for bodega in bodegas:
            id_tecno = bodega[columns.index('IdBodega')]
            nombre = bodega[columns.index('Bodega')].strip()

            existe = location.search([('id_tecno', '=', id_tecno)])

            if existe:
                existe[0].name = nombre
                existe[0].save()
            else:
                almacen = location()
                almacen.id_tecno = id_tecno
                almacen.name = nombre
                almacen.type = 'warehouse'
                
                #zona de entrada
                ze = location()
                ze.id_tecno = 'ze-'+str(id_tecno)
                ze.name = 'ZE '+nombre
                ze.type = 'storage'
                ze.parent = almacen
                ze.save()
                almacen.input_location = ze
                
                #zona de salida
                zs = location()
                zs.id_tecno = 'zs-'+str(id_tecno)
                zs.name = 'ZS '+nombre
                zs.type = 'storage'
                zs.parent = almacen
                zs.save()
                almacen.output_location = zs
                
                #zona de almacenamiento
                za = location()
                za.id_tecno = 'za-'+str(id_tecno)
                za.name = 'ZA '+nombre
                za.type = 'storage'
                za.parent = almacen
                za.save()
                almacen.storage_location = za
                
                almacen.save()

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
    def get_data_where_tecno(cls, table, date):
        data = []
        try:
            Config = Pool().get('conector.configuration')
            conexion = Config.conexion()
            with conexion.cursor() as cursor:
                #(sw = 1  ventas) (sw = 2 devoluciones)
                query = cursor.execute("SELECT TOP(50) * FROM dbo."+table+" WHERE fecha_hora >= CAST('"+date+"' AS datetime) AND (sw = 1 OR sw = 2)")
                data = list(query.fetchall())
        except Exception as e:
            raise UserError('ERROR QUERY get_data_where_tecno: ', str(e))
            #print("ERROR QUERY get_data_where_tecno: ", e)
        return data

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
            return False
        else:
            return producto

    #Función encargada de traer los datos de la bd con una fecha dada.
    @classmethod
    def last_update(cls):
        Actualizacion = Pool().get('conector.actualizacion')
        #Se consulta la ultima actualización realizada para los terceros
        ultima_actualizacion = Actualizacion.search([('name', '=','VENTAS')])
        if ultima_actualizacion:
            #Se calcula la fecha restando la diferencia de horas que tiene el servidor con respecto al clienete
            if ultima_actualizacion[0].write_date:
                fecha = (ultima_actualizacion[0].write_date - datetime.timedelta(hours=5))
            else:
                fecha = (ultima_actualizacion[0].create_date - datetime.timedelta(hours=5))
        else:
            fecha = datetime.date(2021,1,1)
        fecha = fecha.strftime('%Y-%d-%m %H:%M:%S')
        data = cls.get_data_where_tecno('Documentos', fecha)
        return data

    #Crea o actualiza un registro de la tabla actualización en caso de ser necesario
    @classmethod
    def create_or_update(cls):
        Actualizacion = Pool().get('conector.actualizacion')
        actualizacion = Actualizacion.search([('name', '=','VENTAS')])
        if actualizacion:
            #Se busca un registro con la actualización
            actualizacion, = Actualizacion.search([('name', '=','VENTAS')])
            actualizacion.name = 'VENTAS'
            actualizacion.save()
        else:
            #Se crea un registro con la actualización
            actualizar = Actualizacion()
            actualizar.name = 'VENTAS'
            actualizar.save()

    #Metodo encargado de buscar si exste una venta
    @classmethod
    def buscar_venta(cls, id):
        Sale = Pool().get('sale.sale')
        try:
            sale, = Sale.search([('id_tecno', '=', id)])
        except ValueError:
            return False
        else:
            return True


#Heredamos del modelo sale.line para agregar el campo id_tecno
class SaleLine(metaclass=PoolMeta):
    'SaleLine'
    __name__ = 'sale.line'
    id_tecno = fields.Char('Id Tabla Sqlserver', required=False)


#Heredamos del modelo stock.location para agregar el campo id_tecno que nos servira de relación con db sqlserver
class Location(metaclass=PoolMeta):
    "Location"
    __name__ = 'stock.location'

    id_tecno = fields.Char('Id Tabla Sqlserver', required=False)
