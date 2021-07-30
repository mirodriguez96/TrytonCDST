"""
from trytond.model import ModelSQL, ModelView, fields
from trytond.pool import Pool, PoolMeta
import datetime
from trytond.transaction import Transaction

__all__ = [
    'productos',
    'Cron',
    ]


class Cron(metaclass=PoolMeta):
    'Cron'
    __name__ = 'ir.cron'

    @classmethod
    def __setup__(cls):
        super().__setup__()
        cls.method.selection.append(
            ('Productos|carga_productos', "Run Actualización de Productos"),
            )


class Productos():
    'Productos'

    @classmethod
    def carga_productos(cls):
        productos_tecno = cls.get_data_db_tecno('TblProducto')
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
"""