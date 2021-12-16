from trytond.model import fields
from trytond.pool import Pool, PoolMeta
from trytond.exceptions import UserError


__all__ = [
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
            ('stock.location|import_warehouse', "Importar bodegas"),
            )


#Heredamos del modelo stock.location para agregar el campo id_tecno que nos servira de relación con db sqlserver
class Location(metaclass=PoolMeta):
    "Location"
    __name__ = 'stock.location'

    id_tecno = fields.Char('Id Tabla Sqlserver', required=False)

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
    def get_data_table(cls, table):
        data = []
        try:
            Config = Pool().get('conector.configuration')
            conexion = Config.conexion()
            with conexion.cursor() as cursor:
                query = cursor.execute("SELECT * FROM dbo."+table+"")
                data = list(query.fetchall())
        except Exception as e:
            print(e)
            raise UserError('ERROR QUERY get_data_table: ', str(e))
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
            print(e)
            raise UserError('ERROR QUERY get_data_table: ', str(e))
        return columns