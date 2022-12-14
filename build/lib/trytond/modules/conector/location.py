from trytond.model import fields
from trytond.pool import Pool, PoolMeta


#Heredamos del modelo stock.location para agregar el campo id_tecno que nos servira de relación con db sqlserver
class Location(metaclass=PoolMeta):
    "Location"
    __name__ = 'stock.location'

    id_tecno = fields.Char('Id Tabla Sqlserver', required=False)

    # Se importa de la base de datos SqlServer (TecnoCarnes) las bodegas
    @classmethod
    def import_warehouse(cls):
        print('RUN BODEGAS')
        pool = Pool()
        Config = pool.get('conector.configuration')
        Location = pool.get('stock.location')
        bodegas = Config.get_data_table('TblBodega')
        Actualizacion = pool.get('conector.actualizacion')
        actualizacion = Actualizacion.create_or_update('BODEGAS')
        _zones = []
        _warehouses = []
        for bodega in bodegas:
            id_tecno = bodega.IdBodega
            nombre = bodega.Bodega.strip()

            existe = Location.search([('id_tecno', '=', id_tecno)])
            if existe:
                existe[0].name = nombre
                _warehouses.append(existe[0])
                continue

            #zona de entrada
            ze = Location()
            ze.id_tecno = 'ze-'+str(id_tecno)
            ze.name = 'ZE '+nombre
            ze.type = 'storage'
            _zones.append(ze)
            #ze.save()

            #zona de salida
            zs = Location()
            zs.id_tecno = 'zs-'+str(id_tecno)
            zs.name = 'ZS '+nombre
            zs.type = 'storage'
            _zones.append(zs)
            #zs.save()
            
            #zona de almacenamiento
            za = Location()
            za.id_tecno = 'za-'+str(id_tecno)
            za.name = 'ZA '+nombre
            za.type = 'storage'
            _zones.append(za)
            #za.save()

            #zona de producción
            prod = Location()
            prod.id_tecno = 'prod-'+str(id_tecno)
            prod.name = 'PROD '+nombre
            prod.type = 'production'
            _zones.append(prod)
            #prod.save()

            almacen = Location()
            almacen.id_tecno = id_tecno
            almacen.name = nombre
            almacen.type = 'warehouse'
            almacen.input_location = ze
            almacen.output_location = zs
            almacen.storage_location = za
            almacen.production_location = prod
            _warehouses.append(almacen)
            #almacen.save()

        Location.save(_zones)
        Location.save(_warehouses)
        actualizacion.save()
        print('FINISH BODEGAS')
