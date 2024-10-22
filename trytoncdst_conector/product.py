from datetime import date, timedelta
from decimal import Decimal

from trytond.model import fields
from trytond.pool import Pool, PoolMeta
from trytond.transaction import Transaction


class Template(metaclass=PoolMeta):
    __name__ = "product.template"

    @classmethod
    def write(cls, *args):
        pool = Pool()
        active = True
        Product = pool.get("product.product")

        product = args[0]
        id_product = product[0].id
        domain = ["template", "=", id_product]
        variante = Product.search(domain)

        if not variante:
            domain = [("template", "=", id_product), ("active", "=", [])]
            variante = Product.search(domain)

        super().write(*args)

        for arg in args:
            if "active" in arg:
                variante = {"variante": variante, "active": active}

        Product.sync_code(variante)


class Product(metaclass=PoolMeta):
    __name__ = "product.product"
    id_tecno = fields.Char("Id TecnoCarnes", required=False)

    @classmethod
    def sync_code(cls, products):
        pool = Pool()
        Template = pool.get("product.template")
        active = False
        id_tecno = False

        if "active" in products:
            products = products["variante"]
            active = True

        for product in products:
            if product.id_tecno:
                products = [product]

        if not id_tecno:
            if len(products) >= 2:
                products = [products[-1]]
            else:
                if products:
                    products = [products[0]]

        for product in products:
            if active:
                template = Template.search(["id", "=", product.template])
                if template:
                    status = template[0].active
                    if status and not product.active:
                        product.active = True

            code = "".join(
                filter(None, [product.prefix_code, product.suffix_code]))

            if not code:
                code = None

            if code != product.code:
                product.code = code

        cls.save(products)

    @classmethod
    def import_products_tecno(cls):
        """Function to import or update tryton products
        when its created or updated in tecno
        """

        print("RUN PRODUCTOS")
        pool = Pool()
        Actualizacion = pool.get("conector.actualizacion")
        Config = pool.get("conector.configuration")
        Category = pool.get("product.category")
        Template = pool.get("product.template")
        Product = pool.get("product.product")

        actualizacion = Actualizacion.create_or_update("PRODUCTOS")
        date_updating = Actualizacion.get_fecha_actualizacion(actualizacion)
        products_tecno = Config.get_tblproducto(date_updating)
        if not products_tecno:
            actualizacion.save()
            print("FINISH PRODUCTOS")
            return

        for producto in products_tecno:
            try:
                id_product = str(producto.IdProducto)
                if producto.ref_anulada == "S":
                    log = {
                        "EXCEPCION": f"""EL PRODUCTO CON CODIGO {id_product}
                            ESTA MARCADO COMO ANULADO EN TECNOCARNES"""}
                    actualizacion.add_logs(log)
                    continue

                product_inactive = Product.search(
                    [("code", "=", id_product), ("active", "=", False)]
                )
                if product_inactive:
                    log = {
                        "EXCEPCION": f"""EL PRODUCTO CON CODIGO {id_product}
                            TIENE UNA VARIANTE MARCADA COMO
                            INACTIVO EN TRYTON"""}
                    actualizacion.add_logs(log)
                    continue

                category_id = producto.contable
                account_category = Category.search(
                    [("id_tecno", "=", category_id)])
                if account_category:
                    account_category = account_category[0]
                else:
                    category = Category()
                    category.id_tecno = category_id
                    category.name = str(category_id) + " - sin modelo"
                    category.accounting = True
                    category.save()
                    account_category = category
                product_name = producto.Producto.strip()
                product_type = cls.tipo_producto(producto.maneja_inventario)
                product_udm = cls.udm_producto(producto.unidad_Inventario)
                salable = cls.vendible_producto(producto.TipoProducto)
                unit_value = producto.valor_unitario
                if producto.PromedioVenta > 0:
                    unit_value = producto.PromedioVenta
                unit_value = round(unit_value, 2)

                product = Product.search([
                            ['OR', ('id_tecno', '=', id_product),
                             ('code', '=', id_product)],
                            ('active', '=', True)])

                if product:
                    product = product[0]
                    last_change = producto.Ultimo_Cambio_Registro
                    create_date = None
                    write_date = None

                    # Get create and write date
                    if product.write_date:
                        write_date = (product.write_date
                            - timedelta(hours=5))
                    elif product.create_date:
                        create_date = (product.create_date
                            - timedelta(hours=5))
                    if (last_change and write_date
                        and last_change > write_date
                    ) or (
                        last_change and not write_date
                        and last_change > create_date
                    ):
                        product.template.name = product_name
                        product.template.type = product_type
                        product.template.default_uom = product_udm
                        product.template.purchase_uom = product_udm
                        product.template.salable = salable
                        if salable:
                            product.template.sale_uom = product_udm
                        product.template.list_price = unit_value
                        product.template.account_category = account_category.id
                        product.template.sale_price_w_tax = unit_value
                        product.template.save()
                        product.id_tecno = id_product
                        product.save()
                        Transaction().commit()
                else:
                    prod = Product()
                    temp = Template()
                    temp.code = id_product
                    temp.name = product_name
                    temp.type = product_type
                    temp.default_uom = product_udm
                    temp.purchasable = True
                    temp.purchase_uom = product_udm
                    temp.salable = salable
                    if salable:
                        temp.sale_uom = product_udm
                    temp.list_price = unit_value
                    temp.account_category = account_category.id
                    temp.sale_price_w_tax = unit_value
                    prod.id_tecno = id_product
                    prod.template = temp
                    Product.save([prod])
                    Template.save([temp])
                    Transaction().commit()
            except Exception as error:
                Transaction().rollback()
                log = {id_product: f"{error}"}
                actualizacion.add_logs(log)
        print("FINISH PRODUCTOS")

    def get_avg_cost_price(self, name=None):
        super(Product, self).get_avg_cost_price(name)
        target_date = date.today()
        stock_date_end = Transaction().context.get("stock_date_end")
        if stock_date_end:
            target_date = stock_date_end
        AverageCost = Pool().get("product.average_cost")
        avg_product = AverageCost.search(
            [
                ("product", "=", self.id),
                ("effective_date", "<=", target_date),
            ],
            order=[("create_date", "DESC")],
            limit=1,
        )
        if avg_product:
            return avg_product[0].cost_price
        else:
            return self.cost_price

    # Función encargada de retornar que tipo de producto será un al realizar la equivalencia con el manejo de inventario de la bd de TecnoCarnes
    @classmethod
    def tipo_producto(cls, inventario):
        # equivalencia del tipo de producto (si maneja inventario o no)
        if inventario == "N":
            return "service"
        else:
            return "goods"

    # Función encargada de retornar la unidad de medida de un producto, al realizar la equivalencia con kg y unidades de la bd de TecnoCarnes
    @classmethod
    def udm_producto(cls, udm):
        # Equivalencia de la unidad de medida en Kg y Unidades.
        if udm == 1:
            return 2
        else:
            return 1

    # Función encargada de verificar si el producto es vendible, de acuerdo a su tipo
    @classmethod
    def vendible_producto(cls, tipo):
        Config = Pool().get("conector.configuration")
        tipoproducto = Config.get_tbltipoproducto(str(tipo))
        # Se verifica que el tipo de producto exista y el valor SI es vendible o NO
        if tipoproducto and tipoproducto[0].ProductoParaVender == "S":
            return True
        else:
            return False

    @classmethod
    def update_product_parent(cls, _products=None):
        print("RUN update_product_parent")
        pool = Pool()
        Config = pool.get("conector.configuration")
        Product = pool.get("product.product")
        Revision = pool.get("product.cost_price.revision")
        AverageCost = pool.get("product.average_cost")
        _today = date.today()
        if not _products:
            products = Product.search([])
            if not products:
                return
            _products = {}
            for pr in products:
                _products[pr.code] = pr
        result = Config.get_tblproducto_parent()
        if not result:
            return
        revisions = []
        averages = []
        for r in result:
            if str(r.IdProducto) in _products and str(r.IdResponsable) in _products:
                product = _products[str(r.IdProducto)]
                responsable = _products[str(r.IdResponsable)]
                factor = Decimal(r.tiempo_del_ciclo)
                cost_price = round(responsable.cost_price * factor, 2)
                revision = {
                    "company": 1,
                    "product": product.id,
                    "template": product.template.id,
                    "cost_price": cost_price,
                    "date": _today,
                }
                revisions.append(revision)
                # AverageCost
                average = {
                    "product": product.id,
                    "effective_date": _today,
                    "cost_price": cost_price,
                }
                averages.append(average)
        if revisions:
            Revision.create(revisions)
            Product.recompute_cost_price(products, start=_today)
        if averages:
            AverageCost.create(averages)
        print("FINISH update_product_parent")


# Herencia del party.contact_mechanism e insercción del campo id_tecno
class ProductCategory(metaclass=PoolMeta):
    __name__ = "product.category"
    id_tecno = fields.Char("Id TecnoCarnes", required=False)
    account_lost_found = fields.Many2One(
        "account.account",
        "Lost and Found Account",
        domain=[
            ("type.id", "in", ["92"]),
        ],
    )

    @classmethod
    def import_categories_tecno(cls):
        print("RUN CATEGORIAS DE PRODUCTOS")
        pool = Pool()
        Config = pool.get("conector.configuration")
        Actualizacion = pool.get("conector.actualizacion")
        actualizacion = Actualizacion.create_or_update(
            "CATEGORIAS DE PRODUCTOS")
        logs = {}
        modelos = Config.get_data_table("vistamodelos")
        if not modelos:
            print('E3')
            logs["vistamodelos"] = (
                "No se encontraron valores para importar en la tabla vistamodelos"
            )
            actualizacion.add_logs(logs)
            return
        # Creación o actualización de las categorias de los productos
        Category = pool.get("product.category")
        Account = pool.get("account.account")
        to_create = []
        for modelo in modelos:
            id_tecno = modelo.IDMODELOS
            try:
                name = str(id_tecno) + " - " + modelo.MODELOS.strip()
                category = Category.search([("id_tecno", "=", id_tecno)])
                if not category:
                    category = {"id_tecno": id_tecno,
                        "name": name, "accounting": True}

                    # Gastos
                    l_expense = list(modelo.CUENTA1)
                    if int(l_expense[0]) >= 5:
                        expense = Account.search(
                            [("code", "=", modelo.CUENTA1)])
                        if expense:
                            category["account_expense"] = expense[0]

                    # Ingresos
                    l_revenue = list(modelo.CUENTA3)
                    if l_revenue[0] == "4":
                        revenue = Account.search(
                            [("code", "=", modelo.CUENTA3)])
                        if revenue:
                            category["account_revenue"] = revenue[0]

                    # Devolucion venta
                    l_return_sale = list(modelo.CUENTA4)
                    if int(l_return_sale[0]) >= 4:
                        return_sale = Account.search(
                            [("code", "=", modelo.CUENTA4)])
                        if return_sale:
                            category["account_return_sale"] = return_sale[0]

                    to_create.append(category)
            except Exception as e:
                logs[id_tecno] = f"EXCEPCION: {str(e)}"
        Category.create(to_create)
        actualizacion.add_logs(logs)
        print("FINISH CATEGORIAS DE PRODUCTOS")


class CostPriceRevision(metaclass=PoolMeta):
    "Product Cost Price Revision"
    __name__ = "product.cost_price.revision"

    @classmethod
    def apply_up_to(cls, revisions, cost_price, date_form):
        """Apply revision to cost price up to date
        revisions list is modified"""

        try:
            last_date = cls.get_last_date(date_form, revisions)

            while True:
                revision = revisions.pop(0)
                if revision.date <= date_form:
                    date_ = revision.create_date
                    if last_date is not None and date_.date() == last_date:
                        cost_price = revision.get_cost_price(cost_price)
                # else:
                #     revisions.insert(0, revision)
                #     break
        except IndexError:
            pass
        return cost_price

    @classmethod
    def get_last_date(cls, date_form, revisions):
        major_dates = []
        minor_last_date = None
        major_last_date = None
        last_date = None
        for revision in revisions:
            date_ = revision.create_date
            if date_form > date_.date():
                if minor_last_date is None:
                    minor_last_date = date_
                else:
                    if date_.date() >= minor_last_date.date():
                        minor_last_date = date_
            else:
                major_dates.append(date_.date())

        if major_dates:
            for date_ in major_dates:
                if major_last_date is None:
                    major_last_date = date_
                else:
                    if date_ <= major_last_date:
                        major_last_date = date_

        last_date = minor_last_date if minor_last_date is not None else major_last_date
        return last_date
