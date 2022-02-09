from trytond.model import fields
from trytond.pool import Pool, PoolMeta
from trytond.exceptions import UserError
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
            ('sale.sale|import_data_production', "Importar producciones"),
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
        Location = pool.get('stock.location')
        Product = pool.get('product.product')

        to_create = []
        for transformacion in data:
            sw = transformacion.sw
            numero_doc = transformacion.Numero_documento
            tipo_doc = transformacion.tipo
            fecha = str(transformacion.Fecha_Hora_Factura).split()[0].split('-')
            fecha = datetime.date(int(fecha[0]), int(fecha[1]), int(fecha[2]))
            id_tecno = str(sw)+'-'+tipo_doc+'-'+str(numero_doc)
            reference = tipo_doc+'-'+str(numero_doc)
            production = {
                'id_tecno': id_tecno,
                'reference': reference,
                'planned_date': fecha,
                'effective_date': fecha,
            }
            lines = cls.get_data_line(str(sw), tipo_doc, str(numero_doc))
            entradas = {}
            salidas = {}
            for line in lines:
                cantidad = line.Cantidad_Facturada
                id_tecno_bodega = line.IdBodega
                bodega, = Location.search([('id_tecno', '=', id_tecno_bodega)])
                producto, = Product.search([('id_tecno', '=', line.IdProducto)])
                in_trans = {
                    ''
                }
            print(production)

    #Esta función se encarga de traer todos los datos de una tabla dada de acuerdo al rango de fecha dada de la bd
    @classmethod
    def get_data_tecno(cls, date):
        Config = Pool().get('conector.configuration')
        consult = "SET DATEFORMAT ymd SELECT TOP(100) * FROM dbo.Documentos WHERE sw = 18  AND fecha_hora >= CAST('"+date+"' AS datetime) AND exportado != 'T'"
        data = Config.get_data(consult)
        return data

    @classmethod
    def get_data_line(cls, sw, tipo, nro):
        Config = Pool().get('conector.configuration')
        consult = "SELECT * FROM dbo.Documentos_Lin WHERE sw = "+sw+" AND Numero_Documento = "+nro+" AND tipo = "+tipo+" order by seq"
        data = Config.get_data(consult)
        return data

    #Función encargada de traer los datos de la bd con una fecha dada.
    @classmethod
    def last_update(cls):
        Config = Pool().get('conector.configuration')
        config, = Config.search([], order=[('id', 'DESC')], limit=1)
        fecha = config.date
        fecha = fecha.strftime('%Y-%m-%d %H:%M:%S')
        data = cls.get_data_tecno(fecha)
        return data