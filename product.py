from trytond.model import fields
from trytond.pool import Pool, PoolMeta
import datetime


class Cron(metaclass=PoolMeta):
    __name__ = 'ir.cron'

    @classmethod
    def __setup__(cls):
        super().__setup__()
        cls.method.selection.append(
            ('product.product|import_products_tecno', "Importar productos"),
            )
        cls.method.selection.append(
            ('product.category|import_categories_tecno', "Importar categorias de productos"),
            )


class Product(metaclass=PoolMeta):
    __name__ = 'product.product'
    id_tecno = fields.Char('Id TecnoCarnes', required=False)

    #Función encargada de crear o actualizar los productos y categorias de db TecnoCarnes,
    #teniendo en cuenta la ultima fecha de actualizacion y si existe o no.
    @classmethod
    def import_products_tecno(cls):
        print('RUN PRODUCTOS')
        pool = Pool()
        Config = pool.get('conector.configuration')
        Actualizacion = pool.get('conector.actualizacion')
        actualizacion = Actualizacion.create_or_update('PRODUCTOS')
        fecha_actualizacion = Actualizacion.get_fecha_actualizacion(actualizacion)
        productos_tecno = Config.get_tblproducto(fecha_actualizacion)
        if not productos_tecno:
            actualizacion.save()
            print('FINISH PRODUCTOS')
            return
        Category = pool.get('product.category')
        Product = pool.get('product.product')
        Template = pool.get('product.template')
        #to_category = []
        to_product = []
        to_template = []
        logs = []
        for producto in productos_tecno:
            try:
                id_producto = str(producto.IdProducto)
                existe = Product.search(['OR', ('id_tecno', '=', id_producto), ('code', '=', id_producto)])
                id_categoria = producto.contable
                categoria_contable = Category.search([('id_tecno', '=', id_categoria)])
                if categoria_contable:
                    categoria_contable = categoria_contable[0]
                else:
                    categoria = Category()
                    categoria.id_tecno = id_categoria
                    categoria.name = str(id_categoria)+' - sin modelo'
                    categoria.accounting = True
                    categoria.save()
                    categoria_contable = categoria
                nombre_producto = producto.Producto.strip()
                tipo_producto = cls.tipo_producto(producto.maneja_inventario)
                udm_producto = cls.udm_producto(producto.unidad_Inventario)
                vendible = cls.vendible_producto(producto.TipoProducto)
                valor_unitario = producto.valor_unitario
                #En caso de existir el producto se procede a verificar su ultimo cambio y a modificar
                if existe:
                    existe, = existe
                    ultimo_cambio = producto.Ultimo_Cambio_Registro
                    create_date = None
                    write_date = None
                    #LA HORA DEL SISTEMA DE TRYTON TIENE UNA DIFERENCIA HORARIA DE 5 HORAS CON LA DE TECNO
                    if existe.write_date:
                        write_date = (existe.write_date - datetime.timedelta(hours=5))
                    elif existe.create_date:
                        create_date = (existe.create_date - datetime.timedelta(hours=5))
                    #print(ultimo_cambio, create_date, write_date)
                    if (ultimo_cambio and write_date and ultimo_cambio > write_date) or (ultimo_cambio and not write_date and ultimo_cambio > create_date):
                        existe.template.name = nombre_producto
                        existe.template.type = tipo_producto
                        existe.template.default_uom = udm_producto
                        existe.template.purchase_uom = udm_producto
                        existe.template.salable = vendible
                        if vendible:
                            existe.template.sale_uom = udm_producto
                        existe.template.list_price = valor_unitario
                        existe.template.account_category = categoria_contable.id
                        existe.template.sale_price_w_tax = 0
                        existe.template.save()
                else:
                    prod = Product()
                    temp = Template()
                    temp.code = id_producto
                    temp.name = nombre_producto
                    temp.type = tipo_producto
                    temp.default_uom = udm_producto
                    temp.purchasable = True
                    temp.purchase_uom = udm_producto
                    temp.salable = vendible
                    if vendible:
                        temp.sale_uom = udm_producto
                    temp.list_price = valor_unitario
                    temp.account_category = categoria_contable.id
                    temp.sale_price_w_tax = 0
                    prod.id_tecno = id_producto
                    prod.template = temp
                    to_template.append(temp)
                    to_product.append(prod)
            except Exception as e:
                msg = f"EXCEPTION {id_producto} -> {str(e)}"
                logs.append(msg)
        #Category.save(to_category)
        Template.save(to_template)
        Product.save(to_product)
        Actualizacion.add_logs(actualizacion, logs)
        print('FINISH PRODUCTOS')


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
        Config = Pool().get('conector.configuration')
        tipoproducto = Config.get_tbltipoproducto(str(tipo))
        #Se verifica que el tipo de producto exista y el valor SI es vendible o NO
        if tipoproducto and tipoproducto[0].ProductoParaVender == 'S':
            return True
        else:
            return False



#Herencia del party.contact_mechanism e insercción del campo id_tecno
class ProductCategory(metaclass=PoolMeta):
    __name__ = 'product.category'
    id_tecno = fields.Char('Id TecnoCarnes', required=False)


    @classmethod
    def import_categories_tecno(cls):
        print("RUN CATEGORIAS DE PRODUCTOS")
        pool = Pool()
        Config = pool.get('conector.configuration')
        Actualizacion = pool.get('conector.actualizacion')
        actualizacion = Actualizacion.create_or_update('CATEGORIAS DE PRODUCTOS')
        modelos = Config.get_data_table('vistamodelos')
        if not modelos:
            msg = "No se encontraron valores para importar en la tabla vistamodelos"
            Actualizacion.add_logs(actualizacion, [msg])
            return
        # Creación o actualización de las categorias de los productos
        Category = pool.get('product.category')
        Account = pool.get('account.account')
        to_create = []
        logs = []
        for modelo in modelos:
            try:
                id_tecno = modelo.IDMODELOS
                name = str(id_tecno)+' - '+modelo.MODELOS.strip()
                existe = Category.search([('id_tecno', '=', id_tecno)])
                if not existe:
                    category = {
                        'id_tecno': id_tecno,
                        'name': name,
                        'accounting': True
                    }

                    #Gastos
                    l_expense = list(modelo.CUENTA1)
                    if int(l_expense[0]) >= 5:
                        expense = Account.search([('code', '=', modelo.CUENTA1)])
                        if expense:
                            category['account_expense'] = expense[0]
                    
                    #Ingresos
                    l_revenue = list(modelo.CUENTA3)
                    if l_revenue[0] == '4':
                        revenue = Account.search([('code', '=', modelo.CUENTA3)])
                        if revenue:
                            category['account_revenue'] = revenue[0]
                    
                    #Devolucion venta
                    l_return_sale = list(modelo.CUENTA4)
                    if int(l_return_sale[0]) >= 4:
                        return_sale = Account.search([('code', '=', modelo.CUENTA4)])
                        if return_sale:
                            category['account_return_sale'] = return_sale[0]

                    to_create.append(category)
            except Exception as e:
                msg = f"EXCEPTION {name} -> {str(e)}"
                logs.append(msg)
        Category.create(to_create)
        Actualizacion.add_logs(actualizacion, logs)
        print("FINISH CATEGORIAS DE PRODUCTOS")