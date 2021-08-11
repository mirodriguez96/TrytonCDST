from trytond.model import ModelSQL, ModelView, fields
from trytond.pool import Pool, PoolMeta
import datetime
from conexion import conexion


__all__ = [
    'Products',
    'ProductCategory',
    'Cron',
    ]


class Cron(metaclass=PoolMeta):
    'Cron'
    __name__ = 'ir.cron'

    @classmethod
    def __setup__(cls):
        super().__setup__()
        cls.method.selection.append(
            ('products.products|update_products', "Update products"),
            )


class Products(ModelSQL, ModelView):
    'Products'
    __name__ = 'products.products'

    #Función encargada de crear o actualizar los productos y categorias de db TecnoCarnes,
    #teniendo en cuenta la ultima fecha de actualizacion y si existe o no.
    @classmethod
    def update_products(cls):
        print("---------------RUN PRODUCTOS---------------")
        productos_tecno = cls.last_update()
        
        col_pro = cls.get_columns_db_tecno('TblProducto')
        col_gproducto = cls.get_columns_db_tecno('TblGrupoProducto')
        grupos_producto = cls.get_data_db_tecno('TblGrupoProducto')

        #Creación o actualización de las categorias de los productos
        Category = Pool().get('product.category')
        to_categorias = []
        for categoria in grupos_producto:
            id_tecno = str(categoria[col_gproducto.index('IdGrupoProducto')])
            existe = cls.buscar_categoria(id_tecno)
            if existe:
                existe.name = categoria[col_gproducto.index('GrupoProducto')]
                existe.save()
            else:
                categoria_prod = Category()
                categoria_prod.id_tecno = id_tecno
                categoria_prod.name = categoria[col_gproducto.index('GrupoProducto')]
                to_categorias.append(categoria_prod)
        Category.save(to_categorias)

        if productos_tecno:
            #Creación de los productos con su respectiva categoria e información
            Producto = Pool().get('product.product')
            Template_Product = Pool().get('product.template')
            to_producto = []
            for producto in productos_tecno:
                id_producto = str(producto[col_pro.index('IdProducto')])
                existe = cls.buscar_producto(id_producto)
                id_tecno = str(producto[col_pro.index('IdGrupoProducto')])
                categoria_producto, = Category.search([('id_tecno', '=', id_tecno)])
                nombre_producto = producto[col_pro.index('Producto')].strip()
                tipo_producto = cls.tipo_producto(producto[col_pro.index('maneja_inventario')])
                udm_producto = cls.udm_producto(producto[col_pro.index('unidad_Inventario')])
                vendible = cls.vendible_producto(producto[col_pro.index('TipoProducto')])
                valor_unitario = producto[col_pro.index('valor_unitario')]
                costo_unitario = producto[col_pro.index('costo_unitario')]
                ultimo_cambio = producto[col_pro.index('Ultimo_Cambio_Registro')]
                if existe:
                    if (ultimo_cambio and existe.write_date and ultimo_cambio > existe.write_date) or (ultimo_cambio and not existe.write_date and ultimo_cambio > existe.create_date):
                        existe.template.name = nombre_producto
                        existe.template.type = tipo_producto
                        existe.template.default_uom = udm_producto
                        existe.template.salable = vendible
                        if vendible:
                            existe.template.sale_uom = udm_producto
                        existe.template.list_price = valor_unitario
                        existe.cost_price = costo_unitario
                        existe.template.categories = [categoria_producto]
                        existe.template.save()
                else:
                    prod = Producto()
                    prod.code = id_producto
                    temp = Template_Product()
                    temp.code = id_producto
                    temp.name = nombre_producto
                    temp.type = tipo_producto
                    temp.default_uom = udm_producto
                    temp.salable = vendible
                    if vendible:
                        temp.sale_uom = udm_producto
                    temp.list_price = valor_unitario
                    prod.cost_price = costo_unitario
                    temp.categories = [categoria_producto]
                    prod.template = temp
                    to_producto.append(prod)
            Producto.save(to_producto)
            cls.create_actualizacion(False)
        else:
            cls.create_actualizacion(True)


    #Función encargada de consultar si existe una categoria dada de la bd TecnoCarnes
    @classmethod
    def buscar_categoria(cls, id_categoria):
        Category = Pool().get('product.category')
        try:
            categoria_producto, = Category.search([('id_tecno', '=', id_categoria)])
        except ValueError:
            return False
        else:
            return categoria_producto

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

    #Función encargada de retornar que tipo de producto será un al realizar la equivalencia con el manejo de inventario de la bd de TecnoCarnes
    @classmethod
    def tipo_producto(cls, inventario):
        #equivalencia del tipo de producto (si maneja inventario o no)
        if inventario == 'N':
            return 'service'
        else:
            return 'goods'

    #Función encargada de retornar la unidad de medida de un producto, al realizar la equivalencia con kg y unidades de la bd de TecnoCarnes
    @classmethod
    def udm_producto(cls, udm):
        #Equivalencia de la unidad de medida en Kg y Unidades.
        if udm == 1:
            return 2
        else:
            return 1

    #Función encargada de verificar si el producto es vendible, de acuerdo a su tipo
    @classmethod
    def vendible_producto(cls, tipo):
        columns_tiproduct = cls.get_columns_db_tecno('TblTipoProducto')
        tiproduct = None
        try:
            with conexion.cursor() as cursor:
                query = cursor.execute("SELECT * FROM dbo.TblTipoProducto WHERE IdTipoProducto = "+str(tipo))
                tiproduct = query.fetchone()
        except Exception as e:
            print("ERROR QUERY TblTipoProducto: ", e)
        #Se verifica que el tipo de producto exista y el valor si es vendible o no
        if tiproduct and tiproduct[columns_tiproduct.index('ProductoParaVender')] == 'S':
            return True
        else:
            return False


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

    #Esta función se encarga de traer todos los datos de una tabla dada de la bd TecnoCarnes
    @classmethod
    def get_data_db_tecno(cls, table):
        data = []
        try:
            with conexion.cursor() as cursor:
                query = cursor.execute("SELECT * FROM dbo."+table)
                data = list(query.fetchall())
        except Exception as e:
            print("ERROR QUERY "+table+": ", e)
        return data

    #Esta función se encarga de traer todos los datos de una tabla dada de acuerdo al rango de fecha dada de la bd TecnoCarnes
    @classmethod
    def get_data_where_tecno(cls, table, date):
        data = []
        try:
            with conexion.cursor() as cursor:
                query = cursor.execute("SELECT * FROM dbo."+table+" WHERE fecha_creacion >= CAST('"+date+"' AS datetime) OR Ultimo_Cambio_Registro >= CAST('"+date+"' AS datetime)")
                data = list(query.fetchall())
        except Exception as e:
            print("ERROR QUERY get_data_where_tecno: ", e)
        return data

    #Función encargada de traer los datos de la bd TecnoCarnes con una fecha dada.
    @classmethod
    def last_update(cls):
        Actualizacion = Pool().get('conector.actualizacion')
        #Se consulta la ultima actualización realizada para los terceros
        ultima_actualizacion, = Actualizacion.search([('name', '=','PRODUCTOS')])
        if ultima_actualizacion:
            #Se calcula la fecha restando la diferencia de horas que tiene el servidor con respecto al clienete
            if ultima_actualizacion.write_date:
                fecha = (ultima_actualizacion.write_date - datetime.timedelta(hours=5))
            else:
                fecha = (ultima_actualizacion.create_date - datetime.timedelta(hours=5))
        else:
            fecha = datetime.date(1,1,1)
        fecha = fecha.strftime('%Y-%d-%m %H:%M:%S')
        terceros_tecno = cls.get_data_where_tecno('TblProducto', fecha)
        return terceros_tecno

    #Crea o actualiza un registro de la tabla actualización en caso de ser necesario
    @classmethod
    def create_actualizacion(cls, create):
        Actualizacion = Pool().get('conector.actualizacion')
        if create:
            #Se crea un registro con la actualización realizada
            actualizar = Actualizacion()
            actualizar.name = 'PRODUCTOS'
            actualizar.save()
        else:
            #Se busca un registro con la actualización realizada
            actualizacion, = Actualizacion.search([('name', '=','PRODUCTOS')])
            actualizacion.name = 'PRODUCTOS'
            actualizacion.save()


#Herencia del party.contact_mechanism e insercción del campo id_tecno
class ProductCategory(ModelSQL, ModelView):
    'ProductCategory'
    __name__ = 'product.category'
    id_tecno = fields.Char('Id TecnoCarnes', required=False)