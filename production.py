from trytond.model import fields
from trytond.pool import Pool, PoolMeta
#from trytond.exceptions import UserError
from decimal import Decimal
import logging
import datetime

__all__ = [
    'Production',
    'Cron',
    ]


class Cron(metaclass=PoolMeta):
    'Cron'
    __name__ = 'ir.cron'

    @classmethod
    def __setup__(cls):
        super().__setup__()
        cls.method.selection.append(
            ('production|import_data_production', "Importar producciones"),
            )


#Heredamos del modelo sale.sale para agregar el campo id_tecno
class Production(metaclass=PoolMeta):
    'Production'
    __name__ = 'production'
    id_tecno = fields.Char('Id Tabla Sqlserver', required=False)


    @classmethod
    def import_data_production(cls):
        logging.warning('RUN PRODUCTION')
        data = cls.last_update()

        pool = Pool()
        Production = pool.get('production')
        Location = pool.get('stock.location')
        Product = pool.get('product.product')
        Template = pool.get('product.template')

        to_create = []
        for transformacion in data:
            sw = transformacion.sw
            numero_doc = transformacion.Numero_documento
            tipo_doc = transformacion.tipo
            id_tecno = str(sw)+'-'+tipo_doc+'-'+str(numero_doc)

            existe = Production.search([('id_tecno', '=', id_tecno)])
            if existe:
                #cls.importado(id_tecno)
                existe, = existe
                existe.id_tecno = ''
                existe.save()
                cls.reverse_production(existe)
                pass

            #tipo_doc = transformacion.tipo
            fecha = str(transformacion.Fecha_Hora_Factura).split()[0].split('-')
            fecha = datetime.date(int(fecha[0]), int(fecha[1]), int(fecha[2]))
            reference = tipo_doc+'-'+str(numero_doc)
            id_bodega = transformacion.bodega
            bodega, = Location.search([('id_tecno', '=', id_bodega)])
            production = {
                'id_tecno': id_tecno,
                'reference': reference,
                'planned_date': fecha,
                'planned_start_date': fecha,
                'effective_date': fecha,
                'warehouse': bodega.id,
                'location': bodega.production_location.id,
            }
            lines = cls.get_data_line(str(sw), tipo_doc, str(numero_doc))
            entradas = []
            salidas = []
            cont = 0
            for line in lines:
                cantidad = float(line.Cantidad_Facturada)
                id_tecno_bodega = line.IdBodega
                bodega, = Location.search([('id_tecno', '=', id_tecno_bodega)])
                producto, = Product.search([('id_tecno', '=', line.IdProducto)])
                #print(producto)
                transf = {
                    'product': producto.id,
                    'quantity': abs(cantidad),
                    'uom': producto.default_uom.id,
                }
                #Entrada (-1)
                if cantidad < 0:
                    transf['from_location'] = bodega.storage_location.id
                    transf['to_location'] = bodega.production_location.id
                    entradas.append(transf)
                #Salida (1)
                elif cantidad > 0:
                    transf['from_location'] = bodega.production_location.id
                    transf['to_location'] = bodega.storage_location.id
                    #print(line.Valor_Unitario)
                    transf['unit_price'] = Decimal(line.Valor_Unitario)
                    salidas.append(transf)
                    template, = Template.search([('products', '=', producto)])
                    to_write = {
                        'sale_price_w_tax': Decimal(line.Valor_Unitario),
                        'list_price': Decimal(line.Valor_Unitario)
                        }
                    Template.write([template], to_write)
                    if cont == 0:
                        #Se actualiza el producto para que sea producible
                        if not producto.template.producible:
                            
                            Template.write([template], {'producible': True})
                        production['product'] = producto.id
                    cont += 1
            if entradas:
                production['inputs'] = [('create', entradas)]
            if salidas:
                production['outputs'] = [('create', salidas)]
            to_create.append(production)
        #Se crean las producciones
        producciones = Production.create(to_create)
        Production.wait(producciones)
        #Production.assign(producciones)
        #Production.run(producciones)
        #Production.done(producciones)
        #cls.importado(id_tecno)
        logging.warning('FINISH PRODUCTION')

    #Esta función se encarga de traer todos los datos de una tabla dada de acuerdo al rango de fecha dada de la bd
    @classmethod
    def get_data_tecno(cls, date):
        Config = Pool().get('conector.configuration')
        consult = "SELECT * FROM dbo.Documentos WHERE sw = 12 and tipo = 110  AND Numero_documento = 126335"
        #consult = "SET DATEFORMAT ymd SELECT TOP(1000) * FROM dbo.Documentos WHERE sw = 12 and tipo = 110  AND fecha_hora >= CAST('"+date+"' AS datetime) AND exportado != 'T'"
        data = Config.get_data(consult)
        return data

    @classmethod
    def get_data_line(cls, sw, tipo, nro):
        Config = Pool().get('conector.configuration')
        consult = "SELECT * FROM dbo.Documentos_Lin WHERE sw = "+sw+" AND Numero_Documento = "+nro+" AND tipo = "+tipo+" order by seq"
        data = Config.get_data(consult)
        return data

    @classmethod
    def importado(cls, id):
        lista = id.split('-')
        Config = Pool().get('conector.configuration')
        query = "UPDATE dbo.Documentos SET exportado = 'T' WHERE sw ="+lista[0]+" and tipo = "+lista[1]+" and Numero_documento = "+lista[2]
        Config.set_data(query)

    #Función encargada de traer los datos de la bd con una fecha dada.
    @classmethod
    def last_update(cls):
        Config = Pool().get('conector.configuration')
        config, = Config.search([], order=[('id', 'DESC')], limit=1)
        fecha = config.date
        fecha = fecha.strftime('%Y-%m-%d %H:%M:%S')
        #fecha = "2021-01-01" #PRUEBAS
        data = cls.get_data_tecno(fecha)
        return data

    #Función encargada de revertir las producciones hechas
    @classmethod
    def reverse_production(cls, productions):
        pool = Pool()
        Production = pool.get('production')
        Move = pool.get('stock.move')
        reverse = Production.copy(productions)
        to_reverse = []
        for production in reverse:
            to_inputs = []
            for output in production.outputs:
                inp = Move()
                inp.product = output.product
                inp.quantity = output.quantity
                inp.uom = output.uom
                inp.from_location = output.to_location
                inp.to_location = output.from_location
                to_inputs.append(inp)
            to_outputs = []
            for input in production.inputs:
                out = Move()
                out.product = input.product
                out.quantity = input.quantity
                out.uom = input.uom
                out.from_location = input.to_location
                out.to_location = input.from_location
                out.unit_price = input.product.template.list_price
                to_outputs.append(out)
            production.inputs = to_inputs
            production.outputs = to_outputs
            to_reverse.append(production)
        #print(to_reverse)
        Production.save(to_reverse)