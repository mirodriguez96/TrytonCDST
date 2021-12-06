import datetime
from trytond.model import fields
from trytond.pool import Pool, PoolMeta
from trytond.exceptions import UserError
from trytond.transaction import Transaction
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
        #cls.add_venta(ventas_tecno)

    @classmethod
    def add_sale(cls, ventas_tecno):
        if ventas_tecno:
            pool = Pool()
            Sale = pool.get('sale.sale')
            SaleLine = pool.get('sale.line')
            location = pool.get('stock.location')
            payment_term = pool.get('account.invoice.payment_term')
            Party = pool.get('party.party')
            Address = pool.get('party.address')
            coluns_doc = cls.get_columns_db_tecno('Documentos')
            columns_tipodoc = cls.get_columns_db_tecno('TblTipoDoctos')
            cls.import_warehouse()
            cls.import_payment_term()
            
            col_param = cls.get_columns_db_tecno('TblParametro')
            venta_pos = cls.get_data_parametros('8')
            venta_electronica = cls.get_data_parametros('9')

            venta_pos = venta_pos[0][col_param.index('Valor')].strip().split(',')
            venta_electronica = venta_electronica[0][col_param.index('Valor')].strip().split(',')

            #Procedemos a realizar una venta
            for venta in ventas_tecno:
                sw = venta[coluns_doc.index('sw')]
                numero_doc = venta[coluns_doc.index('Numero_documento')]
                tipo_doc = venta[coluns_doc.index('tipo')].strip()
                id_venta = str(sw)+'-'+tipo_doc+'-'+str(numero_doc)
                existe = cls.buscar_venta(id_venta)
                if not existe:
                    sale = Sale()
                    sale.number = tipo_doc+'-'+str(numero_doc)
                    print(tipo_doc+'-'+str(numero_doc))
                    sale.id_tecno = id_venta
                    sale.description = venta[coluns_doc.index('notas')].replace('\n', ' ').replace('\r', '')
                    #Defino por defecto el tipo de venta por computador
                    sale.invoice_type = 'C'
                    #Se revisa si la venta es clasificada como electronica o pos y se cambia el tipo
                    if tipo_doc in venta_electronica:
                        sale.invoice_type = '1'
                    elif tipo_doc in venta_pos:
                        sale.invoice_type = 'P'
                    #Se trae la fecha de la venta y se adapta al formato correcto para Tryton
                    fecha = str(venta[coluns_doc.index('Fecha_Orden_Venta')]).split()[0].split('-')
                    fecha_date = datetime.date(int(fecha[0]), int(fecha[1]), int(fecha[2]))
                    sale.sale_date = fecha_date
                    #sale.shipment_method = 'order'
                    try:
                        party, = Party.search([('id_number', '=', venta[coluns_doc.index('nit_Cedula')])])
                    except:
                        raise UserError("No se econtro el tercero con id: ", venta[coluns_doc.index('nit_Cedula')])
                    sale.party = party
                    sale.invoice_party = party
                    sale.shipment_party = party
                    #Se busca una dirección del tercero para agregar en la factura y envio
                    address = Address.search([('party', '=', party.id)], limit=1)
                    if address:
                        sale.invoice_address = address[0].id
                        sale.shipment_address = address[0].id
                    #Se indica a que bodega pertenece
                    try:
                        bodega, = location.search([('id_tecno', '=', venta[coluns_doc.index('bodega')])])
                    except Exception as e:
                        print(e)
                        raise UserError("No se econtro la bodega: ", venta[coluns_doc.index('bodega')])
                    sale.warehouse = bodega
                    #Se le asigna el plazo de pago correspondiente
                    try:
                        condicion = venta[coluns_doc.index('condicion')]
                        plazo_pago, = payment_term.search([('id_tecno', '=', condicion)])
                    except Exception as e:
                        print(e)
                        raise UserError("No se econtro el plazo de pago: ", condicion)
                    sale.payment_term = plazo_pago
                    #Ahora traemos las lineas de producto para la venta a procesar
                    documentos_linea = cls.get_line_where(str(sw), str(numero_doc), str(tipo_doc))
                    col_line = cls.get_columns_db_tecno('Documentos_Lin')
                    #create_line = []
                    for lin in documentos_linea:
                        id_producto = str(lin[col_line.index('IdProducto')])
                        print(id_producto)
                        producto = cls.buscar_producto(id_producto)
                        if not producto.template.salable:
                            raise UserError("El siguiente producto no es vendible: ", producto)
                        #template, = Template.search([('id', '=', producto.template)])
                        line = SaleLine()
                        seq = lin[col_line.index('seq')]
                        id_bodega = lin[col_line.index('IdBodega')]
                        id_t = str(sw)+'-'+tipo_doc+'-'+str(seq)+'-'+str(numero_doc)+'-'+str(id_bodega)
                        line.id_tecno = id_t
                        line.product = producto
                        #Se verifica si es una devolución
                        if sw == 2:
                            line.quantity = (abs(int(lin[col_line.index('Cantidad_Facturada')])))*-1
                            #Se indica a que documento hace referencia la devolucion
                            sale.reference = venta[coluns_doc.index('Tipo_Docto_Base')].strip()+'-'+str(venta[coluns_doc.index('Numero_Docto_Base')])
                        else:
                            line.quantity = abs(int(lin[col_line.index('Cantidad_Facturada')]))
                            sale.reference = tipo_doc+'-'+str(numero_doc)
                        line.sale = sale
                        line.type = 'line'
                        line.unit = producto.template.default_uom
                        #print(id_producto, line.unit)
                        line.unit_price = lin[col_line.index('Valor_Unitario')]
                        line.on_change_product() #Comprueba los cambios y trae los impuestos del producto
                        #Verificamos si hay descuento para la linea de producto y se agrega su respectivo descuento
                        if lin[col_line.index('Porcentaje_Descuento_1')] > 0:
                            porcentaje = lin[col_line.index('Porcentaje_Descuento_1')]/100
                            line.base_price = lin[col_line.index('Valor_Unitario')]
                            line.discount_rate = Decimal(str(porcentaje))
                            line.on_change_discount_rate()
                        line.save()
                    #Procesamos la venta para generar la factura y procedemos a rellenar los campos de la factura
                    sale.quote([sale])
                    sale.confirm([sale])
                    #print(sale.state)
                    #Se requiere procesar de forma 'manual' la venta para que genere la factura
                    sale.process([sale])
                    #print(len(sale.shipments), len(sale.shipment_returns), len(sale.invoices))
                    try:
                        invoice, = sale.invoices
                        #invoice.operation_type = 10
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
                        total_tecno = Decimal(venta[coluns_doc.index('valor_total')])
                        diferencia_total = abs(total - total_tecno)
                        if diferencia_total < 0.4:
                            invoice.post_batch([invoice])
                            invoice.post([invoice])
                        invoice.save()
                    except Exception as e:
                        print(e)
                        logging.error(e)
                    sale.save()
                    Transaction().connection.commit()
                    """"""


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
                #zona de entrada
                ze = location()
                ze.id_tecno = 'ze-'+str(id_tecno)
                ze.name = 'ZE '+nombre
                ze.type = 'storage'
                ze.save()

                #zona de salida
                zs = location()
                zs.id_tecno = 'zs-'+str(id_tecno)
                zs.name = 'ZS '+nombre
                zs.type = 'storage'
                zs.save()
                
                #zona de almacenamiento
                za = location()
                za.id_tecno = 'za-'+str(id_tecno)
                za.name = 'ZA '+nombre
                za.type = 'storage'
                za.save()

                #zona de producción
                prod = location()
                prod.id_tecno = 'prod-'+str(id_tecno)
                prod.name = 'PROD '+nombre
                prod.type = 'production'
                prod.save()

                almacen = location()
                almacen.id_tecno = id_tecno
                almacen.name = nombre
                almacen.type = 'warehouse'
                almacen.input_location = ze
                almacen.output_location = zs
                almacen.storage_location = za
                almacen.production_location = prod
                
                almacen.save()


    @classmethod
    def import_payment_term(cls):
        payment_term = Pool().get('account.invoice.payment_term')
        condiciones_pago = cls.get_data_table('TblCondiciones_pago')
        columns = cls.get_columns_db_tecno('TblCondiciones_pago')

        for condiciones in condiciones_pago:
            id_tecno = condiciones[columns.index('IdCondiciones_pago')]
            nombre = condiciones[columns.index('Condiciones_pago')].strip()
            dias = int(condiciones[columns.index('dias_vcto')])

            existe = payment_term.search([('id_tecno', '=', id_tecno)])

            if existe:
                existe[0].name = nombre
                #existe[0].lines.relativedeltas.days = dias
                line, = existe[0].lines
                delta, = line.relativedeltas
                delta.days = dias
                existe[0].save()
            else:
                payment_term_line = Pool().get('account.invoice.payment_term.line')
                payment_term_line_delta = Pool().get('account.invoice.payment_term.line.delta')
                #Se crea un nuevo plazo de pago
                plazo_pago = payment_term()
                plazo_pago.id_tecno = id_tecno
                plazo_pago.name = nombre
                #delta es quien se le indica los días del plazo de pago
                delta = payment_term_line_delta()
                delta.days = dias
                #line es quien se le indica el tipo del plazo de pago
                line = payment_term_line()
                line.type = 'remainder'
                line.relativedeltas = [delta]
                plazo_pago.lines = [line]
                plazo_pago.save()
                

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
    def get_data_where_tecno(cls, date):
        data = []
        try:
            Config = Pool().get('conector.configuration')
            conexion = Config.conexion()
            with conexion.cursor() as cursor:
                cant = cursor.execute("SELECT COUNT(*) FROM dbo.Documentos WHERE fecha_hora >= CAST('"+date+"' AS datetime) AND (sw = 1 OR sw = 2)")
                cant = int(cant.fetchall()[0][0])
                cant = int(cant/1000)+1
                for n in range(cant):
                    #(sw = 1  ventas) (sw = 2 devoluciones)
                    query = cursor.execute("SELECT * FROM dbo.Documentos WHERE fecha_hora >= CAST('"+date+"' AS datetime) AND (sw = 1 OR sw = 2) ORDER BY sw OFFSET "+str(n)+" ROWS FETCH NEXT 1000 ROWS ONLY")
                    data = list(query.fetchall())
                    cls.add_sale(data)
        except Exception as e:
            raise UserError('ERROR QUERY get_data_where_tecno: ', str(e))
            #print("ERROR QUERY get_data_where_tecno: ", e)
        #return data

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
        data = cls.get_data_where_tecno(fecha)
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


