import datetime
from trytond.model import fields
from trytond.pool import Pool, PoolMeta
#from trytond.transaction import Transaction
from trytond.exceptions import UserError
from conexion import conexion


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
    id_tecno = fields.Char('Id TecnoCarnes', required=False)

    @classmethod
    def import_data_sale(cls):
        print("--------------RUN WIZARD VENTAS--------------")
        ventas_tecno = cls.last_update()
        cls.create_actualizacion(False)
        if ventas_tecno:
            """"""
            pool = Pool()        
            Sale = pool.get('sale.sale')
            SaleLine = pool.get('sale.line')
            Party = pool.get('party.party')
            Address = pool.get('party.address')
            Template = Pool().get('product.template')
            documentos = cls.get_data_db_tecno('Documentos')
            coluns_doc = cls.get_columns_db_tecno('Documentos')
            create_sale = []
            #Procedemos a realizar una venta
            for vent in documentos:
                numero_doc = vent[coluns_doc.index('Numero_documento')]
                tipo_doc = vent[coluns_doc.index('tipo')].strip()
                venta = Sale()
                venta.number = numero_doc
                #venta.company = 3
                #venta.currency = 1
                venta.id_tecno = str(numero_doc)+'-'+tipo_doc
                venta.description = vent[coluns_doc.index('notas')]
                venta.invoice_method = 'manual'
                venta.invoice_state = 'none'
                venta.invoice_type = 'M'
                fecha = str(vent[coluns_doc.index('Fecha_Orden_Venta')]).split()[0].split('-')
                fecha_date = datetime.date(int(fecha[0]), int(fecha[1]), int(fecha[2]))
                venta.sale_date = fecha_date
                venta.shipment_method = 'manual'
                venta.shipment_state = 'none'
                venta.state = 'done'
                party, = Party.search([('id_number', '=', vent[coluns_doc.index('nit_Cedula')])])
                venta.party = party.id
                address = Address.search([('party', '=', party.id)], limit=1)
                venta.invoice_address = address[0].id
                venta.shipment_address = address[0].id

                documentos_linea = cls.get_line_where(str(numero_doc), str(tipo_doc))
                col_line = cls.get_columns_db_tecno('Documentos_Lin')
                #create_line = []
                for lin in documentos_linea:
                    producto = cls.buscar_producto(str(lin[col_line.index('IdProducto')]))
                    if producto:
                        template, = Template.search([('id', '=', producto.template)])
                        line = SaleLine()
                        id_t = lin[col_line.index('tipo')].strip()+'-'+str(lin[col_line.index('seq')])+'-'+str(lin[col_line.index('Numero_Documento')])+'-'+str(lin[col_line.index('IdBodega')])
                        line.id_tecno = id_t
                        line.product = producto
                        line.quantity = abs(int(lin[col_line.index('Cantidad_Facturada')]))
                        line.unit_price = lin[col_line.index('Valor_Unitario')]
                        line.sale = venta
                        line.type = 'line'
                        line.unit = template.default_uom
                        #create_line.append(line)
                        line.save()
                    else:
                        raise UserError("Error", "No existe el producto con la siguiente id: ", lin[col_line.index('IdProducto')])
                create_sale.append(venta)
                #venta.save()
            
            Sale.save(create_sale)
            


    @classmethod
    def process_pos(cls, sale):
        pool = Pool()
        Date = pool.get('ir.date')
        # Necesitamos mantener esa secuencia para las facturas 
        # tomadas de la configuración de la tienda en lugar del año fiscal, 
        # porque algunas secuencias de países las establece la tienda.
        number = None

        if not sale:
            return

        invoice = sale.create_invoice()
        sale.set_invoice_state()
        sequence = sale.get_sequence(sale)
        if not sale.invoice_number and sale.invoice_method == 'order':
            if sequence:
                number = sequence.get()
                sale_date = Date.today()
                cls.write([sale], {
                    'invoice_number': number,
                    'invoice_date': sale_date,
                })
        else:
            number = sale.invoice_number
        position = sale.position if sale.position else None
        if invoice:
            if sale.invoice_date:
                inv_date = sale.invoice_date
            elif sale.shipment_date:
                inv_date = sale.shipment_date
            else:
                inv_date = Date.today()

            sale.invoice = invoice.id
            to_write = {
                'shop': sale.shop.id,
                'invoice_date': inv_date,
                'number': number,
                'reference': sale.reference or sale.number,
                'position': position,
                'turn': sale.turn,
            }

            if sale.invoice_type:
                pass
            invoice.write([invoice], to_write)

        sale.save()
        return sale


    #Esta función se encarga de traer todos los datos de una tabla dada de la bd TecnoCarnes
    @classmethod
    def get_data_db_tecno(cls, table):
        data = []
        try:
            with conexion.cursor() as cursor:
                query = cursor.execute("SELECT TOP (5) * FROM dbo."+table+" WHERE sw = 1")
                data = list(query.fetchall())
        except Exception as e:
            print("ERROR QUERY "+table+": ", e)
        return data
    
    #Esta función se encarga de traer todos los datos de una tabla dada de la bd TecnoCarnes
    @classmethod
    def get_line_where(cls, id, tipo):
        data = []
        try:
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
            with conexion.cursor() as cursor:
                query = cursor.execute("SELECT TOP (5) * FROM dbo."+table+" WHERE fecha_hora >= CAST('"+date+"' AS datetime) AND sw = 1")
                data = list(query.fetchall())
        except Exception as e:
            print("ERROR QUERY get_data_where_tecno: ", e)
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
            producto, = Product.search([('code', '=', id_producto)])
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
            fecha = datetime.date(1,1,1)
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
    id_tecno = fields.Char('Id TecnoCarnes', required=False)
