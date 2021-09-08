import datetime
from trytond.model import fields
from trytond.pool import Pool, PoolMeta
#from trytond.transaction import Transaction
from trytond.exceptions import UserError
#from conexion import conexion
from decimal import Decimal


__all__ = [
    'Sale',
    'SaleLine',
    'Cron',
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
        cls.create_actualizacion(False)
        if ventas_tecno:
            pool = Pool()
            Sale = pool.get('sale.sale')
            SaleLine = pool.get('sale.line')
            Invoice = pool.get('account.invoice')
            Taxes = pool.get('sale.line-account.tax')
            CustomerTax = Pool().get('product.category-customer-account.tax')
            Party = pool.get('party.party')
            Address = pool.get('party.address')
            Template = Pool().get('product.template')
            coluns_doc = cls.get_columns_db_tecno('Documentos')
            columns_tipodoc = cls.get_columns_db_tecno('TblTipoDoctos')
            #create_sale = []
            #Procedemos a realizar una venta
            for vent in ventas_tecno:
                numero_doc = vent[coluns_doc.index('Numero_documento')]
                tipo_doc = vent[coluns_doc.index('tipo')].strip()
                venta = Sale()
                venta.number = tipo_doc+'-'+str(numero_doc)
                venta.reference = tipo_doc+'-'+str(numero_doc)
                venta.id_tecno = str(numero_doc)+'-'+tipo_doc
                venta.description = vent[coluns_doc.index('notas')].replace('\n', ' ').replace('\r', '')
                venta.invoice_method = 'order'
                venta.invoice_type = 'M'
                fecha = str(vent[coluns_doc.index('Fecha_Orden_Venta')]).split()[0].split('-')
                fecha_date = datetime.date(int(fecha[0]), int(fecha[1]), int(fecha[2]))
                venta.sale_date = fecha_date
                venta.shipment_method = 'order'
                #venta.payment_term = 1 #FIX CUENTAS
                try:
                    party, = Party.search([('id_number', '=', vent[coluns_doc.index('nit_Cedula')])])
                except:
                    raise UserError("No se econtro el tercero con id: ", vent[coluns_doc.index('nit_Cedula')])
                venta.party = party.id
                address = Address.search([('party', '=', party.id)], limit=1)
                venta.invoice_address = address[0].id
                venta.shipment_address = address[0].id
                #Ahora traemos las lineas de producto para la venta a procesar
                documentos_linea = cls.get_line_where(str(numero_doc), str(tipo_doc))
                col_line = cls.get_columns_db_tecno('Documentos_Lin')
                #create_line = []
                for lin in documentos_linea:
                    producto = cls.buscar_producto(str(lin[col_line.index('IdProducto')]))
                    if producto:
                        print(producto.code)
                        template, = Template.search([('id', '=', producto.template)])
                        line = SaleLine()
                        id_t = lin[col_line.index('tipo')].strip()+'-'+str(lin[col_line.index('seq')])+'-'+str(lin[col_line.index('Numero_Documento')])+'-'+str(lin[col_line.index('IdBodega')])
                        line.id_tecno = id_t
                        line.product = producto
                        if vent[coluns_doc.index('notas')] == 3:
                            line.quantity = -abs(int(lin[col_line.index('Cantidad_Facturada')]))
                        else:
                            line.quantity = abs(int(lin[col_line.index('Cantidad_Facturada')]))
                        line.unit_price = lin[col_line.index('Valor_Unitario')]
                        line.sale = venta
                        line.type = 'line'
                        line.unit = template.default_uom
                        #Agregar impuestos a la venta
                        taxc = CustomerTax.search([('category', '=', template.account_category)])
                        if taxc:
                            tax = Taxes()
                            tax.line = line
                            tax.tax = taxc[0].tax
                            line.save()
                            tax.save()
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
                #venta.click('quote')
                #venta.click('confirm')
                #venta.quote([venta])
                #venta.confirm([venta])
                venta.state = 'confirmed'
                venta.process([venta])
                #print(venta.state)
                #create_sale.append(venta)
                #id_invoice = venta.get_invoices(None)
                #venta.save()
                #invoice, = Invoice.search([('id','=',id_invoice[0])])
                invoice, = venta.invoices
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
                    #invoice.click('post')
                    #print('TOTAL IGUALES')
                #invoice.save()
                #create_invoice.append(invoice)
            #Sale.save(create_sale)


    #Esta función se encarga de traer todos los datos de una tabla dada de la bd TecnoCarnes
    @classmethod
    def get_data_db_tecno(cls, table): #TESTS
        data = []
        try:
            Config = Pool().get('conector.configuration')
            conexion = Config.conexion()
            with conexion.cursor() as cursor:
                query = cursor.execute("SELECT TOP (5) * FROM dbo."+table+" WHERE sw = 1")
                data = list(query.fetchall())
        except Exception as e:
            print("ERROR QUERY "+table+": ", e)
        return data

    #Metodo encargado de traer el tipo de documento de la bd TecnoCarnes
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

    #Esta función se encarga de traer todos los datos de una tabla dada de la bd TecnoCarnes
    @classmethod
    def get_line_where(cls, id, tipo):
        data = []
        try:
            Config = Pool().get('conector.configuration')
            conexion = Config.conexion()
            with conexion.cursor() as cursor:
                query = cursor.execute("SELECT * FROM dbo.Documentos_Lin WHERE Numero_Documento = "+id+" AND tipo = "+tipo)
                data = list(query.fetchall())
        except Exception as e:
            print("ERROR QUERY Documentos_Lin: ", e)
        return data

    #Función encargada de consultar las columnas pertenecientes a 'x' tabla de la bd de TecnoCarnes
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

    #Esta función se encarga de traer todos los datos de una tabla dada de acuerdo al rango de fecha dada de la bd TecnoCarnes
    @classmethod
    def get_data_where_tecno(cls, table, date):
        data = []
        try:
            Config = Pool().get('conector.configuration')
            conexion = Config.conexion()
            with conexion.cursor() as cursor:
                query = cursor.execute("SELECT * FROM dbo."+table+" WHERE fecha_hora >= CAST('"+date+"' AS datetime) AND (sw = 1 OR sw = 2)")
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

    #Función encargada de consultar si existe un producto dado de la bd TecnoCarnes
    @classmethod
    def buscar_producto(cls, id_producto):
        Product = Pool().get('product.product')
        try:
            producto, = Product.search([('id_tecno', '=', id_producto)])
        except ValueError:
            return False
        else:
            return producto

    #Función encargada de traer los datos de la bd TecnoCarnes con una fecha dada.
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
            cls.create_actualizacion(True)
        fecha = fecha.strftime('%Y-%d-%m %H:%M:%S')
        data = cls.get_data_where_tecno('Documentos', fecha)
        return data

    #Crea o actualiza un registro de la tabla actualización en caso de ser necesario
    @classmethod
    def create_actualizacion(cls, create):
        Actualizacion = Pool().get('conector.actualizacion')
        if create:
            #Se crea un registro con la actualización realizada
            actualizar = Actualizacion()
            actualizar.name = 'VENTAS'
            actualizar.save()
        else:
            #Se busca un registro con la actualización realizada
            actualizacion, = Actualizacion.search([('name', '=','VENTAS')])
            actualizacion.name = 'VENTAS'
            actualizacion.save()


#Heredamos del modelo sale.line para agregar el campo id_tecno
class SaleLine(metaclass=PoolMeta):
    'SaleLine'
    __name__ = 'sale.line'
    id_tecno = fields.Char('Id Tabla Sqlserver', required=False)
