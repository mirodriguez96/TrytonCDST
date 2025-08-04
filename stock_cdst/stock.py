"""STOCK MOVEMENTS MODULE"""

import copy
import logging
from collections import defaultdict
from datetime import timedelta, date
from decimal import Decimal
from operator import itemgetter
from sql import Table
import calendar


from trytond.exceptions import UserError
from trytond.i18n import gettext
from trytond.model import ModelView, Workflow, fields
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Bool, Eval, Not
from trytond.report import Report
from trytond.transaction import Transaction
from trytond.wizard import Button, StateReport, StateView, Wizard

SW = 16

type_shipment = {
    'out': 'Envio a Clientes',
    'in': 'Envio de Proveedor',
    'internal': 'Envio Interno',
}

STATE_SHIPMENTS = [('', ''), ('draft', 'Borrador'), ('done', 'Finalizado')]
TYPES_PRODUCT = [('no_consumable', 'No consumible'),
                 ('consumable', 'Consumible')]


class Configuration(metaclass=PoolMeta):
    'Stock Configuration'
    __name__ = 'stock.configuration'

    state_shipment = fields.Selection(STATE_SHIPMENTS,
                                      'State shipment',
                                      required=True)

    consumable_products_state = fields.Boolean('Consumable products')

    to_location = fields.Many2One('stock.location', "Output inventory location",
                                  domain=[
                                      ('type', 'in', ['customer']),
                                  ],
                                  help="Where the stock is moved to.")

    logistic_user = fields.Many2One('res.user', 'Logistic user')
    validate_user = fields.Boolean('Validate user')

    @classmethod
    def default_consumable_products_state(cls):
        return False


class Inventory(metaclass=PoolMeta):
    'Stock Inventory'
    __name__ = 'stock.inventory'

    analitic_account = fields.Many2One(
        'analytic_account.account', 'Analytic Account',
        domain=[('type', '=', "normal")],
        required=True
    )

    product_type = fields.Selection(TYPES_PRODUCT, 'Type Product')

    @staticmethod
    def default_product_type():
        return 'no_consumable'

    @classmethod
    @ModelView.button
    def complete_lines(cls, inventories, fill=True):
        '''
        Complete or update the inventories
        '''
        pool = Pool()
        Line = pool.get('stock.inventory.line')
        Configuration = pool.get('stock.configuration')
        Product = pool.get('product.product')

        config = Configuration(1)
        products_consumables = Product.search(
            ['template.consumable', '=', True])
        grouping = cls.grouping()
        to_create, to_write = [], []
        for inventory in inventories:
            product_consumables = False
            if inventory.state == 'done':
                continue

            if (inventory.product_type == "consumable"
                    and config.consumable_products_state):
                product_consumables = True
                if not products_consumables:
                    msg = """No tiene productos consumibles."""
                    raise UserError("ERROR", msg.strip())
                product_ids = [product.id for product in products_consumables]
            else:
                if fill:
                    product_ids = None
                else:
                    product_ids = [l.product.id for l in inventory.lines]

            with Transaction().set_context(
                    company=inventory.company.id,
                    stock_date_end=inventory.date):
                pbl = Product.products_by_location(
                    [inventory.location.id],
                    grouping=grouping,
                    grouping_filter=(product_ids,))

            # Index some data
            product2type = {}
            product2consumable = {}
            for product in Product.browse({line[1] for line in pbl}):
                product2type[product.id] = product.type
                product2consumable[product.id] = product.consumable

            # Update existing lines
            for line in inventory.lines:
                if line.product.type != 'goods':
                    Line.delete([line])
                    continue

                key = (inventory.location.id,) + line.unique_key
                if key in pbl:
                    quantity = pbl.pop(key)
                else:
                    quantity = 0.0
                values = line.update_values4complete(quantity)
                if values:
                    to_write.extend(([line], values))

            if not fill:
                continue
            # Create lines if needed
            for key, quantity in pbl.items():
                product_id = key[grouping.index('product') + 1]

                if (product2type[product_id] != 'goods'
                        or (not product_consumables
                            and product2consumable[product_id])):
                    continue
                if not quantity:
                    continue

                values = Line.create_values4complete(inventory, quantity)
                for i, fname in enumerate(grouping, 1):
                    values[fname] = key[i]
                to_create.append(values)
        if to_create:
            Line.create(to_create)
        if to_write:
            Line.write(*to_write)


class Location(metaclass=PoolMeta):
    "Location"
    __name__ = 'stock.location'

    id_tecno = fields.Char('Id Tabla Sqlserver', required=False)

    @classmethod
    def import_warehouse(cls):
        """Function to import werehouses from tecnocarnes"""

        pool = Pool()
        Config = pool.get('conector.configuration')
        Location = pool.get('stock.location')
        bodegas = Config.get_data_table('TblBodega')
        Actualizacion = pool.get('conector.actualizacion')
        actualizacion = Actualizacion.create_or_update('BODEGAS')
        logs = {}

        import_name = "BODEGAS"
        print(f"---------------RUN {import_name}---------------")
        for bodega in bodegas:
            try:
                id_tecno = bodega.IdBodega
                nombre = bodega.Bodega.strip()
                existe = Location.search([('id_tecno', '=', id_tecno)])
                if existe:
                    if existe[0].name != nombre:
                        existe[0].name = nombre
                        Location.save([existe[0]])
                        msg = f"""Se actualiza nombre de la bodega "{nombre}"""
                        logs[id_tecno] = msg
                    continue
                # zona de entrada
                ze = Location()
                ze.id_tecno = 'ze-' + str(id_tecno)
                ze.name = 'ZE ' + nombre
                ze.type = 'storage'
                Location.save([ze])

                # zona de salida
                zs = Location()
                zs.id_tecno = 'zs-' + str(id_tecno)
                zs.name = 'ZS ' + nombre
                zs.type = 'storage'
                Location.save([zs])

                # zona de almacenamiento
                za = Location()
                za.id_tecno = 'za-' + str(id_tecno)
                za.name = 'ZA ' + nombre
                za.type = 'storage'
                Location.save([za])

                # zona de producción
                prod = Location()
                prod.id_tecno = 'prod-' + str(id_tecno)
                prod.name = 'PROD ' + nombre
                prod.type = 'production'
                Location.save([prod])

                # Bodega
                almacen = Location()
                almacen.id_tecno = id_tecno
                almacen.name = nombre
                almacen.type = 'warehouse'
                almacen.input_location = ze
                almacen.output_location = zs
                almacen.storage_location = za
                almacen.production_location = prod
                Location.save([almacen])
            except Exception as error:
                Transaction().rollback()
                print(f"ROLLBACK-{import_name}: {error}")
                logs[id_tecno] = f'EXCEPCION:{error}'

        actualizacion.add_logs(logs)
        print(f"---------------FINISH {import_name}---------------")


class BOMInput(metaclass=PoolMeta):
    "Bill of Material Input"
    __name__ = 'production.bom.input'

    location = fields.Many2One('stock.location', "location",
                               domain=[
                                      ('type', 'in', ['storage']),])


class BOMOutput(metaclass=PoolMeta):
    "Bill of Material Output"
    __name__ = 'production.bom.output'

    location = fields.Many2One('stock.location', "location",
                               domain=[
                                      ('type', 'in', ['storage']),])


class ShipmentDetailedReport(metaclass=PoolMeta):
    'Shipment Detailed Report'
    __name__ = 'stock.shipment.shipment_detailed.report'

    @classmethod
    def get_context(cls, records, header, data):
        report_context = Report.get_context(records, header, data)

        pool = Pool()
        company = Transaction().context.get('company.rec_name')
        ProductRevision = pool.get('product.cost_price.revision')

        type_shipment_ = data['type_shipment']
        model = 'stock.shipment.' + type_shipment_
        ModelShipment = pool.get(model)
        Move = pool.get('stock.move')
        Product = pool.get('product.product')
        dom_shipment = [('company', '=', data['company']),
                        ('effective_date', '>=', data['start_date']),
                        ('effective_date', '<=', data['end_date'])]

        # if type_shipment_ != 'out' and type_shipment_ != 'in':
        if data['from_locations']:
            dom_shipment.append(
                ('from_location', 'in', data['from_locations']))

        if data['to_locations']:
            dom_shipment.append(
                ('to_location', 'in', data['to_locations']))

        fields_names = ['id']
        shipments = ModelShipment.search_read(dom_shipment,
                                              fields_names=fields_names,
                                              order=[('effective_date', 'ASC')
                                                     ])
        shipments_id = [model + ',' + str(sh['id']) for sh in shipments]
        fields_names = [
            'product.account_category.name', 'product.name',
            'product.cost_price', 'quantity', 'to_location.name',
            'from_location.name', 'shipment.reference', 'effective_date',
            'shipment.number', 'unit_price', 'planned_date'
        ]
        fields = ModelShipment.fields_get(fields_names=[
            'operation_center', 'customer', 'supplier', 'incoming_moves'
        ])
        if 'operation_center' in fields.keys():
            fields_names.append('shipment.operation_center.rec_name')

        if type_shipment_ == 'in':
            fields_names.append('shipment.supplier.name')
        elif type_shipment_ == 'out':
            fields_names.append('shipment.customer.name')

        moves = Move.search_read(('shipment', 'in', shipments_id),
                                 fields_names=fields_names,
                                 order=[('to_location', 'DESC'),
                                        ('create_date', 'ASC')])

        dgetter = itemgetter('product.', 'quantity')
        product_browse = Product.browse
        for m in moves:
            code = None
            uom_name = None

            product, quantity = dgetter(m)
            product_, = product_browse([product['id']])
            try:
                oc = m['shipment.']['operation_center.']['rec_name']
            except:
                oc = ''

            cost_price = product['cost_price']
            if type_shipment_ == 'in':
                party = m['shipment.']['supplier.']['name']
                cost_price = m['unit_price'] or 0
            elif type_shipment_ == 'out':
                party = m['shipment.']['customer.']['name']
            else:
                party = ''

            category = product.get('account_category.', '')
            if category:
                category = category['name']
            category_ad = ''
            if product_.categories:
                category_ad = product_.categories[0].name

            if product_.template.default_uom:
                uom_name = product_.template.default_uom.name

            if product_.code:
                code = product_.code

            cost_revision = ProductRevision.search(
                        [('template', '=', product_.template),
                            ('date', '<=', m['planned_date'])],
                        order=[('id', 'DESC')],
                        limit=1
                    )
            if (cost_revision
                    and cost_revision[0].cost_price != cost_price):
                cost_price = cost_revision[0].cost_price

            value = {
                'party': party,
                'oc': oc,
                'codigo': code,
                'product': product['name'],
                'uom': uom_name,
                'cost_price': cost_price,
                'category': category,
                'category_ad': category_ad,
                'cost_base':
                Decimal(str(round(float(cost_price) * quantity, 2))),
            }
            try:
                value['cost_unit_w_tax'] = float(product_.cost_price)
                value['cost_w_tax'] = float(
                    product_.cost_price) * quantity
                value['last_cost'] = product_.last_cost
            except:
                value['cost_w_tax'] = 0
                value['cost_unit_w_tax'] = 0
                value['last_cost'] = 0

            try:
                m.update(product_.attributes)
            except:
                pass

            try:
                value['price_w_tax'] = float(
                    product_.sale_price_w_tax) * quantity
            except:
                value['price_w_tax'] = 0

            try:
                value['section'] = product_.section.name
                value['conservation'] = product_.conservation.name
            except:
                value['conservation'] = None
                value['section'] = None

            m.update(value)
        if not data['grouped']:
            report_context['records'] = moves
        else:
            records = {}
            for m in moves:
                key = str(m['to_location.']['id']) + \
                    '_' + str(m['product.']['id'])
                try:
                    records[key]['cost_w_tax'] += m['cost_w_tax']
                    records[key]['price_w_tax'] += m['price_w_tax']
                    records[key]['quantity'] += m['quantity']
                    records[key]['cost_base'] += m['cost_base']
                    records[key]['last_cost'] = m['last_cost']
                except:
                    records[key] = m
                    records[key]['shipment.']['reference'] = ''
                    records[key]['effective_date'] = ''
            report_context['records'] = records.values()

        report_context['company'] = company
        report_context['Decimal'] = Decimal
        report_context['kind'] = type_shipment[data['type_shipment']]
        return report_context


class ShipmentInternal(metaclass=PoolMeta):
    "Internal Shipment"
    __name__ = 'stock.shipment.internal'
    id_tecno = fields.Char('Id TecnoCarnes', required=False)

    @classmethod
    def __setup__(cls):
        super(ShipmentInternal, cls).__setup__()
        cls.from_location.domain = [('type', 'in', ['storage', 'lost_found']),
                                    ('active', '=', True)]

        cls.to_location.domain = [('type', 'in', ['storage', 'lost_found', 'customer']),
                                  ('active', '=', True)]

    @classmethod
    def get_documentos_traslado(cls):
        import_name = "TRASLADOS"
        cls.import_tecnocarnes(sw='16', import_name=import_name)

    @classmethod
    def get_documentos_traslado_(cls):
        import_name = "TRASLADOS - SALIDAS INVENTARIO"
        cls.import_tecnocarnes(sw='11', import_name=import_name)

    @classmethod
    def import_tecnocarnes(cls, sw, import_name):
        """Function to import internal shipments from tecnocarnes"""

        pool = Pool()
        Config = pool.get('conector.configuration')
        Product = pool.get('product.product')
        Actualizacion = pool.get('conector.actualizacion')
        ConfigShipment = pool.get('stock.configuration')

        print(f"---------------RUN {import_name}---------------")
        configuration = Config.get_configuration()
        config_shipment = ConfigShipment.search([])
        state_shipment = config_shipment[0].state_shipment
        output_location = config_shipment[0].to_location
        if not configuration:
            return

        data = Config.get_documentos_traslados(sw)
        if not data:
            print("---------------NO SE ENCONTRO INFO---------------")
            print(f"---------------FINISH {import_name}---------------")
            return
        actualizacion = Actualizacion.create_or_update(import_name)
        result = cls.validate_documentos(data)
        shipments = []
        for value in result["tryton"].values():
            try:
                if value['from_location'] == value['to_location'] and sw != '11':
                    msg = """En traslados no puede tener la misma ubicacion
                        de entrada y salida"""
                    result["logs"][value['id_tecno']] = str(msg)
                    result["exportado"]["E"].append(value['id_tecno'])
                    continue

                if sw == '11':
                    if not output_location:
                        msg = """Debe configuracion una ubicacion
                                        de salida por defecto"""
                        result["logs"][value['id_tecno']] = str(msg)
                        result["exportado"]["E"].append(value['id_tecno'])
                        break

                    if output_location == value['from_location']:
                        msg = """En traslados no puede tener la misma ubicacion
                        de entrada y salida"""
                        result["logs"][value['id_tecno']] = str(msg)
                        result["exportado"]["E"].append(value['id_tecno'])
                        continue

                    value['to_location'] = output_location.id

                    for moves in value['moves']:
                        for move in moves[1]:
                            product = Product(move['product'])
                            move['to_location'] = output_location.id
                            move['unit_price'] = product.cost_price
                shipment, = cls.create([value])
                if shipment:
                    shipments.append(shipment)
            except Exception as error:
                logging.error(f"ROLLBACK1-{import_name}-[{value['id_tecno']}]: {error}")
                result["logs"][value['id_tecno']] = str(error)
                result["exportado"]["E"].append(value['id_tecno'])

        if shipments:
            for shipment in shipments:
                id_shipment = shipment.id_tecno
                try:
                    if ((sw == '11')
                    or (state_shipment and state_shipment == 'done')):
                        cls.process_shipment(shipment)
                    result["exportado"]["T"].append(shipment.id_tecno)
                except Exception as error:
                    Transaction().rollback()
                    logging.error(f"ROLLBACK-{id_shipment}-{import_name}: {error}")
                    result["logs"][id_shipment] = str(error)

        for exportado, idt in result["exportado"].items():
            if idt:
                try:
                    for id in idt:
                        Config.update_exportado(id, exportado)
                except Exception as error:
                    result["logs"]["try_except"] = str(error)

        actualizacion.add_logs(result["logs"])
        print(f"---------------FINISH {import_name}---------------")

    @classmethod
    def validate_documentos(cls, data):
        """Function to validate documetns from internal shipments"""

        pool = Pool()
        Config = pool.get('conector.configuration')
        Actualizacion = pool.get('conector.actualizacion')
        Internal = pool.get('stock.shipment.internal')
        StockPeriod = pool.get('stock.period')

        actualizacion = Actualizacion.create_or_update(
            'CREAR ENVIOS INTERNOS VALIDACION DE PERIODOS')
        logs = {}
        dictprodut = {}
        to_exception = []
        exists = []
        tipos_doctos = []
        bodegas = []
        productos = []
        selecto_product = []

        result = {
            "tryton": {},
            "logs": {},
            "exportado": {
                "T": [],
                "E": [],
                "X": [],
            },
        }
        operation_center = cls.get_operation_center(Internal)
        id_company = Transaction().context.get('company')
        shipments = Internal.search([('id_tecno', '!=', None)])

        for ship in shipments:
            exists.append(ship.id_tecno)

        for p in data:
            if p.IdProducto not in selecto_product:
                selecto_product.append(p.IdProducto)

        selecto_product = tuple(selecto_product)

        if len(selecto_product) <= 1:
            selecto_product = f'({selecto_product[0]})'

        select = f"SELECT tr.IdProducto, tr.IdResponsable \
                    FROM TblProducto tr \
                    WHERE tr.IdProducto in {selecto_product};"

        set_data = Config.get_data(select)

        for item in set_data:

            dictprodut[item[0]] = {
                'idresponsable': str(item[1]),
            }

        move = {}
        for value, d in enumerate(data):
            tipo = str(d.tipo)
            reference = f"{tipo}-{d.Numero_Documento}"
            reference_ = f"{d.notas}"
            id_tecno = f"{d.sw}-{reference}"
            anulado = d.anulado
            sw = d.sw
            if id_tecno in exists:
                if anulado == "S" and sw == 11:
                    shipment = Internal.search([('id_tecno', '=', id_tecno)])
                    to_delete = {'shipment': [], 'stock_move': []}
                    if shipment:
                        shipment, = shipment
                        effective_date = shipment.effective_date
                        _, month_period = calendar.monthrange(effective_date.year, effective_date.month)
                        date_period = date(effective_date.year, effective_date.month, month_period)

                        period = StockPeriod.search([('date', '=', date_period),
                                                     ('state', '=', 'closed')])

                        if period:
                            result["logs"][id_tecno] = "Periodo del documento se encuentra cerrado"
                            result["exportado"]["E"].append(id_tecno)
                            continue
                        stock_move = shipment.moves
                        to_delete['shipment'] = [shipment.id]
                        if stock_move:
                            to_delete['stock_move'] = [stock_move[0].id]
                        cls.delete_shipments(to_delete)
                        result["logs"][id_tecno] = "Documento anulado fue eliminado"
                        result["exportado"]["X"].append(id_tecno)
                    continue

                result["logs"][id_tecno] = "Ya existe en Tryton"
                result["exportado"]["T"].append(id_tecno)
                continue
            fecha_documento = d.Fecha_Documento.date()
            if id_tecno not in result["tryton"]:
                shipment = {
                    "id_tecno": id_tecno,
                    "reference": reference_,
                    "number": reference,
                    "planned_date": fecha_documento,
                    "effective_date": fecha_documento,
                    "planned_start_date": fecha_documento,
                    "effective_start_date": fecha_documento,
                    "company": id_company,
                }

                if operation_center:
                    shipment["operation_center"] = operation_center.id
                if tipo not in tipos_doctos:
                    tipos_doctos.append(tipo)
                id_bodega = str(d.from_location)
                if id_bodega not in bodegas:
                    bodegas.append(id_bodega)
                id_bodega_destino = str(d.IdBodega)
                if id_bodega_destino not in bodegas:
                    bodegas.append(id_bodega_destino)

                shipment["from_location"] = id_bodega
                shipment["to_location"] = id_bodega_destino
                result["tryton"][id_tecno] = shipment

            shipment = result["tryton"][id_tecno]
            if "moves" not in shipment:
                shipment["moves"] = []
            # Se crea el movimiento
            producto = dictprodut[d.IdProducto]['idresponsable'] if dictprodut[
                d.IdProducto] and dictprodut[
                    d.IdProducto]['idresponsable'] != '0' else str(d.IdProducto)
            if producto not in productos:
                productos.append(producto)
            quantity = round(float(round(d.Cantidad_Facturada, 3)), 3)

            if quantity < 0:
                result["logs"][
                    id_tecno] = f"Cantidad en negativo: {quantity} Producto: {producto}"
                result["exportado"]["E"].append(id_tecno)
                del (result["tryton"][id_tecno])
                continue

            if id_tecno not in move:
                move[id_tecno] = {'move_product': {}}
            if producto not in move[id_tecno]['move_product']:

                move[id_tecno]['move_product'][producto] = {
                    "from_location": shipment["from_location"],
                    "to_location": shipment["to_location"],
                    "product": producto,
                    "company": id_company,
                    "quantity": round(float(0), 3),
                    "planned_date": shipment["planned_date"],
                    "effective_date": shipment["effective_date"],
                }

            quantity_float = move[id_tecno]['move_product'][producto]["quantity"]
            move[id_tecno]['move_product'][producto]["quantity"] = round(
                quantity + quantity_float, 3)

        for id_tec, line_move in result['tryton'].items():

            if result['tryton'][id_tec]:
                result['tryton'][id_tec]['moves'] = [
                    ('create', [i for i in move[id_tec]['move_product'].values()])
                ]

        products = cls.get_products(productos)
        locations = cls.get_locations(bodegas)
        analytic_types = None
        if hasattr(Internal, 'analytic_account') and tipos_doctos:
            analytic_types = cls.get_analytic_types(tipos_doctos)
        for id_tecno, shipment in result["tryton"].items():
            sw = id_tecno.split("-")[0]
            if analytic_types:
                # tipo = shipment["reference"].split("-")[0]
                tipo = shipment["number"].split("-")[0]
                if tipo in analytic_types:
                    shipment["analytic_account"] = analytic_types[tipo].id
                else:
                    result["logs"][
                        id_tecno] = f"No se encontro la cuenta analitica para el tipo: {tipo}"
                    result["exportado"]["E"].append(id_tecno)
                    continue
            from_location = shipment["from_location"]
            if from_location in locations:
                storage_location_id = locations[from_location].storage_location.id
                shipment["from_location"] = storage_location_id
                if (locations[from_location].operation_center) and sw == '11':
                    shipment["operation_center"] = locations[from_location].operation_center
            else:
                result["tryton"][
                    id_tecno] = f"No se encontro la bodega con id_tecno: {from_location}"
                result["exportado"]["E"].append(id_tecno)
                continue
            to_location = shipment["to_location"]
            if to_location in locations:
                storage_location_id = locations[to_location].storage_location.id
                shipment["to_location"] = storage_location_id
                if (locations[to_location].operation_center) and sw == '16':
                    shipment["operation_center"] = locations[to_location].operation_center
            else:
                result["tryton"][
                    id_tecno] = f"No se encontro la bodega con id_tecno: {to_location}"
                result["exportado"]["E"].append(id_tecno)
                continue
            products_exist = True
            for mv in shipment["moves"][0][1]:
                mv["from_location"] = shipment["from_location"]
                mv["to_location"] = shipment["to_location"]
                if mv["product"] in products:
                    product = products[mv["product"]]
                    mv["uom"] = product.default_uom.id
                    mv["product"] = product.id
                    if product.default_uom.symbol.upper() == 'U':
                        mv["quantity"] = round(float(int(mv["quantity"])), 3)
                else:
                    products_exist = False
                    result["logs"][
                        id_tecno] = f"No se encontro el producto: {mv['product']}"
                    break
            if not products_exist:
                result["exportado"]["E"].append(id_tecno)
                continue
        for to_delete in result["exportado"]["E"]:
            if to_delete in result["tryton"]:
                del (result["tryton"][to_delete])
        if to_exception:
            actualizacion.add_logs(logs)
        return result

    @classmethod
    def delete_shipments(cls, to_delete):
        shipment_table = Table('stock_shipment_internal')
        stock_move_table = Table('stock_move')
        cursor = Transaction().connection.cursor()

        if to_delete['shipment']:
            cursor.execute(*shipment_table.update(
                columns=[shipment_table.state],
                values=['draft'],
                where=shipment_table.id.in_(to_delete['shipment'])))
            cursor.execute(*shipment_table.delete(
                where=shipment_table.id.in_(to_delete['shipment'])))

        if to_delete['stock_move']:
            cursor.execute(*stock_move_table.update(
                columns=[stock_move_table.state],
                values=['draft'],
                where=stock_move_table.id.in_(to_delete['stock_move'])))
            cursor.execute(*stock_move_table.delete(
                where=stock_move_table.id.in_(to_delete['stock_move'])))

    @classmethod
    def get_operation_center(cls, shipment):
        operation_center = hasattr(shipment, 'operation_center')
        if operation_center:
            OperationCenter = Pool().get('company.operation_center')
            operation_center = OperationCenter.search([],
                                                    order=[('id', 'ASC')],
                                                    limit=1)
            if not operation_center:
                raise UserError("operation_center",
                                "the operation center is missing")
            operation_center, = operation_center
        return operation_center

    @classmethod
    def list_to_tuple(cls, value, string=False):
        result = None
        if value:
            if string:
                result = "('" + "', '".join(map(str, value)) + "')"
            else:
                result = "(" + ", ".join(map(str, value)) + ")"
        return result

    @classmethod
    def get_analytic_types(cls, tipos_doctos):
        analytic_types = {}
        if tipos_doctos:
            pool = Pool()
            Config = pool.get('conector.configuration')
            ids_tipos = cls.list_to_tuple(tipos_doctos)
            tbltipodocto = Config.get_tbltipodoctos_encabezado(ids_tipos)
            _values = {}
            for tipodocto in tbltipodocto:
                if tipodocto.Encabezado and tipodocto.Encabezado != '0':
                    encabezado = str(tipodocto.Encabezado)
                    idtipod = str(tipodocto.idTipoDoctos)
                    if encabezado not in _values:
                        _values[encabezado] = []
                    _values[encabezado].append(idtipod)
            if _values:
                AnalyticAccount = pool.get('analytic_account.account')
                analytic_accounts = AnalyticAccount.search([('code', 'in',
                                                            _values.keys())])
                for ac in analytic_accounts:
                    idstipo = _values[ac.code]
                    for idt in idstipo:
                        analytic_types[idt] = ac
        return analytic_types

    @classmethod
    def get_locations(cls, bodegas):
        result = {}
        if bodegas:
            Location = Pool().get('stock.location')
            locations = Location.search([('id_tecno', 'in', bodegas)])
            for l in locations:
                result[l.id_tecno] = l
        return result

    @classmethod
    def get_products(cls, values):
        result = {}
        if values:
            Product = Pool().get('product.product')
            products = Product.search(
                [['OR', ('id_tecno', 'in', values), ('code', 'in', values)],
                ('active', '=', True)])
            for p in products:
                result[p.code] = p
        return result

    @classmethod
    def process_shipment(cls, shipment):
        cls.wait([shipment])
        shipment = cls.set_origin(shipment)
        cls.assign([shipment])
        cls.done([shipment])

    @classmethod
    def create_account_move(cls, shipments):
        """Inherith function to create account move
        And validate TecnoCarnes shipments"""
        result = []
        for shipment in shipments:
            id_tecno_split = shipment.id_tecno.split(
                '-') if shipment.id_tecno else []
            sw = id_tecno_split[0] if id_tecno_split else None
            if ((not shipment.id_tecno) or (sw == '11')):
                result.append(shipment)
        super(ShipmentInternal, cls).create_account_move(result)

    @classmethod
    def set_origin(cls, shipment):
        for moves in shipment.assign_moves:
            moves.origin = shipment
        return shipment

    @classmethod
    def get_account_move(cls, shipment):
        pool = Pool()
        Uom = pool.get('product.uom')
        Period = pool.get('account.period')
        ProductCategory = pool.get('product.category')
        Configuration = pool.get('account.configuration')
        ProductRevision = pool.get('product.cost_price.revision')

        configuration = Configuration(1)
        if not configuration.stock_journal:
            raise UserError(
                gettext(
                    'account_stock_latin.msg_missing_journal_stock_configuration'
                ))
        journal = configuration.stock_journal
        period_id = Period.find(shipment.company.id,
                                date=shipment.effective_date)

        lines_to_create = []
        moves_error = []
        for move in shipment.moves:
            try:
                sw = None
                account_debit = account_credit = None
                product = move.product

                account_debit = product.account_expense_used
                account_credit = product.account_stock_used

                if shipment.id_tecno:
                    id_tecno_split = shipment.id_tecno.split('-')
                    sw = id_tecno_split[0]
                    code = id_tecno_split[1]
                    product_category = ProductCategory.search(
                        [('name', 'like', f'{code}-%'),
                         ('parent', '=', product.account_category)])

                if sw is not None and sw == '11' and product_category:
                    account_credit, account_debit = cls.get_accounts_shipment(
                        product_category[0], account_debit, account_credit)

                if account_debit.party_required:
                    party = shipment.company.party.id
                else:
                    party = None

                cost_price = Uom.compute_price(product.default_uom,
                                               product.cost_price,
                                               move.uom)

                date_inventory = move.effective_date

                if move.product and move.product.template:
                    cost_revision = ProductRevision.search(
                        [('template', '=', move.product.template),
                            ('date', '<=', date_inventory)],
                        order=[('date', 'DESC'), ('id', 'DESC')],
                        limit=1
                    )
                if cost_revision:
                    cost_price = cost_revision[0].cost_price

                amount_ = Decimal(str(move.quantity)) * Decimal(cost_price)
                amount = shipment.company.currency.round(amount_)
                line_debit = {
                    'account': account_debit,
                    'party': party,
                    'debit': amount,
                    'credit': Decimal(0),
                    'description': product.name,
                }
                op = True if hasattr(shipment, 'operation_center') else False
                if op:
                    line_debit.update(
                        {'operation_center': shipment.operation_center})

                if (shipment.analytic_account
                        and account_debit.analytical_management):
                    line_analytic = {
                        'account': shipment.analytic_account,
                        'debit': amount,
                        'credit': Decimal(0)
                    }
                    line_debit['analytic_lines'] = [('create', [line_analytic])
                                                    ]
                lines_to_create.append(line_debit)

                if account_credit.party_required:
                    party = shipment.company.party.id
                else:
                    party = None

                line_credit = {
                    'account': account_credit,
                    'party': party,
                    'debit': Decimal(0),
                    'credit': amount,
                    'description': product.name,
                }

                if (shipment.analytic_account
                        and account_credit.analytical_management):
                    line_analytic = {
                        'account': shipment.analytic_account,
                        'debit': Decimal(0),
                        'credit': amount
                    }
                    line_credit['analytic_lines'] = [('create', [line_analytic])
                                                    ]
                lines_to_create.append(line_credit)
            except Exception as e:
                print(e)
                moves_error.append(
                    ['error:', product.name, shipment.number])
                raise UserError(
                    gettext('account_stock_latin.msg_missing_account_stock',
                            product=product.name))
        if moves_error:
            return None
        account_move = {
            'journal': journal,
            'date': shipment.effective_date,
            'origin': shipment,
            'company': shipment.company,
            'period': period_id,
            'description': shipment.reference,
            'lines': [('create', lines_to_create)]
        }
        return account_move

    @classmethod
    def get_accounts_shipment(cls, product_category, debit_account,
                              credit_account):
        if product_category.account_stock_out_used:
            credit_account = product_category.account_stock_out_used
        if product_category.account_cogs_used.code:
            debit_account = product_category.account_cogs_used
        return credit_account, debit_account


class ShipmentIn(metaclass=PoolMeta):
    "Internal Shipment"
    __name__ = 'stock.shipment.in'

    @classmethod
    def receive(cls, shipments):
        super(ShipmentIn, cls).receive(shipments)
        pool = Pool()
        StockMove = pool.get('stock.move')
        Purchase = pool.get('purchase.purchase')
        for shipment in shipments:
            stock_move = StockMove.search([
                ('shipment', '=', shipment)
            ])
            for move in stock_move:
                if move.origin and move.origin.__name__ == 'purchase.line':
                    purchase = move.origin.purchase
                    if purchase.invoice_method == 'shipment':
                        Purchase.process([purchase])


class ModifyCostPrice(metaclass=PoolMeta):
    "Modify Cost Price"
    __name__ = 'product.modify_cost_price'

    def transition_modify(self):
        pool = Pool()
        Product = pool.get('product.product')
        Revision = pool.get('product.cost_price.revision')
        AverageCost = Pool().get('product.average_cost')
        StockPeriod = Pool().get('stock.period')
        Date = pool.get('ir.date')
        revisions = []
        today = Date.today()
        date_period = StockPeriod.search(
            [('date', '=', self.start.date), ('state', '!=', 'closed')])

        if not date_period:
            raise UserError(
                'ERROR', 'No se encontro un periodo abierto para '
                'la fecha, la fecha debe coincidir con la fecha de '
                'cierre del periodo')

        costs = defaultdict(list)
        if self.model.__name__ == 'product.product':
            records = list(self.records)
            for product in list(records):
                revision = self.get_revision(Revision)
                revision.product = product
                revision.template = product.template
                revisions.append(revision)
                if ((product.cost_price_method == 'fixed'
                     and revision.date == today) or product.type == 'service'):
                    cost = revision.get_cost_price(product.cost_price)
                    costs[cost].append(product)
                    records.remove(product)
        elif self.model.__name__ == 'product.template':
            records = list(self.records)
            for template in list(records):
                revision = self.get_revision(Revision)
                revision.template = template
                revisions.append(revision)
                if ((template.cost_price_method == 'fixed'
                     and revision.date == today)
                        or template.type == 'service'):
                    for product in template.products:
                        cost = revision.get_cost_price(product.cost_price)
                        costs[cost].append(product)
                    records.remove(template)
                else:
                    print('actualiza')
                    product, = template.products
                    cost = revision.get_cost_price(product.cost_price)
                    AverageCost.create([{
                        "product": product.id,
                        "effective_date": self.start.date,
                        "cost_price": cost,
                    }])
        Revision.save(revisions)
        if costs:
            Product.update_cost_price(costs)
        if records:
            start = min((r.date for r in revisions), default=None)
            self.model.recompute_cost_price(records, start=start)
        return 'end'


class Move(metaclass=PoolMeta):
    "Stock Move"
    __name__ = 'stock.move'

    def set_average_cost(self):
        AverageCost = Pool().get('product.average_cost')
        Revision = Pool().get('product.cost_price.revision')
        revision = {
            "company": 1,
            "product": self.product.id,
            "template": self.product.template.id,
            "cost_price": self.product.cost_price,
            "date": self.effective_date,
        }
        data = {
            "stock_move": self.id,
            "product": self.product.id,
            "effective_date": self.effective_date,
            "cost_price": self.product.cost_price,
        }
        Revision.create([revision])
        AverageCost.create([data])

    @classmethod
    def _get_origin(cls):
        add_origin = ['production', 'stock.shipment.internal']
        return super(Move, cls)._get_origin() + add_origin

    def _get_account_stock_move_lines(self, type_):
        '''
        Return move lines for stock move
        '''
        pool = Pool()
        Uom = pool.get('product.uom')
        Account = pool.get('account.account')

        assert type_.startswith('in_') or type_.startswith('out_'), \
            'wrong type'

        move_line = []
        if ((type_.endswith('supplier')
             or type_ in {'in_production', 'in_warehouse'})
                and self.product.cost_price_method != 'fixed'):
            unit_price = self.unit_price_company
        else:
            unit_price = self.cost_price
        unit_price = Uom.compute_price(self.product.default_uom, unit_price,
                                       self.uom)
        amount = self.company.currency.round(
            Decimal(str(self.quantity)) * unit_price)

        account = self.product.account_expense_used

        category = self.product.template.account_category
        category_name = category.name
        product_name = self.product.template.name
        lost_found_account = category.account_lost_found
        product_salable = self.product.template.salable
        product_purchasable = self.product.template.purchasable

        if product_salable or (product_salable and product_purchasable):

            if not lost_found_account:
                raise UserError(
                    'ERROR', f'Debe configurar la cuenta de perdidos\
                          y encontrados en la categoria \
                            ({category_name}) del producto {product_name}')
            _account = Account.search(['id', '=', lost_found_account])
            account = _account[0]

        if type_.startswith('in_'):
            line = {
                'account': account,
                'party': self.company.party.id,
                'debit': Decimal('0.0'),
                'credit': amount,
                'description': self.product.name,
            }

            if self.shipment:
                if self.shipment.analytic_account:
                    line_analytic = {
                        'account': self.shipment.analytic_account,
                        'debit': Decimal(0),
                        'credit': amount,
                    }
                    line['analytic_lines'] = [('create', [line_analytic])]

            if self.origin:
                if self.origin.__name__ == 'stock.inventory.line':
                    line_analytic = {
                        'account': self.origin.inventory.analitic_account,
                        'debit': Decimal(0),
                        'credit': amount,
                    }
                    line['analytic_lines'] = [('create', [line_analytic])]

            move_line.append(line)

        else:
            line = {
                'account': account,
                'party': self.company.party.id,
                'debit': amount,
                'credit': Decimal('0.0'),
                'description': self.product.name,
            }

            if self.shipment:
                if self.shipment.analytic_account:
                    line_analytic = {
                        'account': self.shipment.analytic_account,
                        'debit': amount,
                        'credit': Decimal(0),
                    }
                    line['analytic_lines'] = [('create', [line_analytic])]

            if self.origin:
                if self.origin.__name__ == 'stock.inventory.line':
                    line_analytic = {
                        'account': self.origin.inventory.analitic_account,
                        'debit': amount,
                        'credit': Decimal(0),
                    }
                    line['analytic_lines'] = [('create', [line_analytic])]

            move_line.append(line)

        if self.shipment:
            if self.shipment.operation_center:
                line.update(
                    {'operation_center': self.shipment.operation_center})

        return move_line

    def _get_account_stock_move_line(self, amount):
        '''
        Return counterpart move line value for stock move
        '''

        if not amount:
            return

        if amount >= Decimal('0.0'):
            line = {
                'account': self.product.account_stock_used,
                'party': self.company.party.id,
                'debit': Decimal('0.0'),
                'credit': abs(amount)
            }
        else:
            line = {
                'account': self.product.account_stock_used,
                'party': self.company.party.id,
                'debit': abs(amount),
                'credit': Decimal('0.0')
            }

        return line

    def _get_account_stock_move_type(self):
        '''
        Get account move type
        '''
        type_ = (self.from_location.type, self.to_location.type)
        if type_ == ('storage', 'lost_found'):
            return 'out_lost_found'
        elif type_ == ('lost_found', 'storage'):
            return 'in_lost_found'

    def _get_account_stock_move(self):
        '''
        Return account move for stock move
        '''

        pool = Pool()
        Date = pool.get('ir.date')
        Period = pool.get('account.period')
        AccountConfiguration = pool.get('account.configuration')

        if self.product.type != 'goods':
            return

        date = self.effective_date or Date.today()
        period_id = Period.find(self.company.id, date=date)
        period = Period(period_id)
        if not period.fiscalyear.account_stock_method:
            return

        type_ = self._get_account_stock_move_type()
        if not type_:
            return

        with Transaction().set_context(company=self.company.id, date=date):
            if type_ == 'supplier_customer':
                account_move_lines = self._get_account_stock_move_lines(
                    'in_supplier')
                account_move_lines.extend(
                    self._get_account_stock_move_lines('out_customer'))
            elif type_ == 'customer_supplier':
                account_move_lines = self._get_account_stock_move_lines(
                    'in_customer')
                account_move_lines.extend(
                    self._get_account_stock_move_lines('out_supplier'))
            else:
                account_move_lines = self._get_account_stock_move_lines(type_)

        amount = Decimal('0.0')
        for line in account_move_lines:
            amount += line['debit'] - line['credit']

        if not amount:
            return
        move_line = self._get_account_stock_move_line(amount)
        if move_line:
            account_move_lines.append(move_line)

        account_configuration = AccountConfiguration(1)
        journal = account_configuration.get_multivalue('stock_journal',
                                                       company=self.company.id)

        account_move = {
            'journal': journal,
            'date': date,
            'origin': self,
            'period': period_id,
            'lines': [('create', account_move_lines)]
        }

        return account_move

    @classmethod
    @ModelView.button
    @Workflow.transition('done')
    def do(cls, moves):
        pool = Pool()
        AccountMove = pool.get('account.move')
        ProductRevision = pool.get('product.cost_price.revision')
        super(Move, cls).do(moves)
        for move in moves:
            cost_price_move = move.cost_price
            date_inventory = move.effective_date
            if move.product and move.product.template:
                cost_revision = ProductRevision.search(
                    [('template', '=', move.product.template),
                        ('date', '<=', date_inventory)],
                    order=[('date', 'DESC'), ('id', 'DESC')],
                    limit=1
                )
            if cost_revision:
                if cost_revision[0].cost_price != cost_price_move:
                    cost_price = cost_revision[0].cost_price
                    move.cost_price = cost_price
                    move.save()
        account_moves = []
        for move in moves:
            account_move = move._get_account_stock_move()
            if account_move:
                account_moves.append(account_move)
        _moves = AccountMove.create(account_moves)
        AccountMove.post(_moves)

    @classmethod
    @ModelView.button
    @Workflow.transition('assigned')
    def assign(cls, moves):
        super(Move, cls).assign(moves)
        pool = Pool()
        Product = pool.get('product.product')
        StockConfig = pool.get('stock.configuration')
        config = StockConfig(1)
        bom_inputs = {}

        for move in moves:
            production_ = None

            if move.production_input:
                production_ = move.production_input
            if move.production_output:
                production_ = move.production_output

            if production_:
                if production_.bom:
                    if config.logistic_user and config.validate_user:
                        user_ = Transaction().user
                        bom_inputs = {production.product: production.location for production in production_.bom.inputs}
                        from_location_enable = False
                        to_location_enable = False

                        # Validar si en las entradas se modifico alguna ubicacion
                        for input in production_.inputs:
                            if (input.product in bom_inputs.keys()
                                    and input.from_location != bom_inputs[input.product]):
                                if user_ != config.logistic_user:
                                    from_location_enable = True
                        # Validar si en las salidas se modifico alguna ubicacion
                        for input in production_.outputs:
                            if (input.product in bom_inputs.keys()
                                    and input.to_location != bom_inputs[input.product]):
                                if user_ != config.logistic_user:
                                    to_location_enable = True

                        # Validar si el usuario tiene permisos de modificar
                        if ((from_location_enable or to_location_enable)
                                and (user_ != config.logistic_user.id)):
                            msg = """No tiene permitido modificar producciones."""
                            raise UserError(f'Error, {msg}')

                        # Validar que haya cantidades en las ubicaciones de entrada
                        product_ = move.product
                        location_ = move.from_location
                        context = {
                            'location_ids': [location_.id],
                            'stock_date_end': date.today(),
                        }

                        with Transaction().set_context(context):
                            res_dict = Product._get_quantity(
                                [product_],
                                'quantity',
                                [location_.id],
                                grouping_filter=([product_.id],)
                            )
                            stock_quantity = res_dict.get(product_.id)
                            if stock_quantity < move.quantity:
                                msg = f"""No hay suficiente existencias para el producto
                                {product_.name} en la ubicacion {location_.name}.
                                """.replace("\n", " ").strip()
                                raise UserError(f'Error, {msg}')


class WarehouseKardexStockStartCds(ModelView):
    'Warehouse Kardex Stock Start'
    __name__ = 'stock_co.warehouse_kardex_cds_stock.start'
    company = fields.Many2One('company.company', 'Company', required=True)

    from_date = fields.Date('From Date', required=True)
    to_date = fields.Date('To Date', required=True)
    categories = fields.Many2Many('product.category', None, None, 'Categories')

    locations = fields.Many2Many('stock.location',
                                 None,
                                 None,
                                 "Location",
                                 domain=[('type', 'in',
                                          ['warehouse', 'storage']),
                                         ('active', '=', True)],
                                 required=True)

    detail_by_product = fields.Boolean('Detail By Product')

    products = fields.Many2Many('product.product',
                                None,
                                None,
                                'Products',
                                domain=[
                                    ('active', '=', True),
                                    ('template.active', '=', True),
                                    ('type', '=', 'goods'),
                                    ('consumable', '=', False),
                                    ('quantity', '!=', 0),
                                ],
                                states={
                                    'required':
                                    Bool(Eval('detail_by_product')),
                                    'invisible':
                                    ~Bool(Eval('detail_by_product'))
                                },
                                depends=['detail_by_product'])

    @staticmethod
    def default_company():
        return Transaction().context.get('company')

    @staticmethod
    def default_to_date():
        Date_ = Pool().get('ir.date')
        return Date_.today()


class WarehouseKardexStockCds(Wizard):
    'Warehouse Kardex Stock'
    __name__ = 'stock_co.warehouse_kardex_cds_stock'
    start = StateView('stock_co.warehouse_kardex_cds_stock.start',
                      'stock_cdst.warehouse_kardex_stock_start_cds_view_form', [
                          Button('Cancel', 'end', 'tryton-cancel'),
                          Button('Print', 'print_', 'tryton-ok', default=True),
                      ])
    print_ = StateReport('stock_co.warehouse_kardex_cds_stock.report')

    def do_print_(self, action):
        data = {
            'company': self.start.company.id,
            'from_date': self.start.from_date,
            'to_date': self.start.to_date,
            'detail_by_product': self.start.detail_by_product,
            'categories': [l.id for l in self.start.categories],
            'locations': [l.id for l in self.start.locations],
            'products': [l.id for l in self.start.products],
        }
        return action, data


class WarehouseCdsKardexReport(Report):
    'Warehouse Kardex Report'
    __name__ = 'stock_co.warehouse_kardex_cds_stock.report'

    @classmethod
    def get_context(cls, records, header, data):
        """Function that take context of report and import it"""
        report_context = super().get_context(records, header, data)

        pool = Pool()
        StockInventory = pool.get('stock.inventory')
        Company = pool.get('company.company')
        Product = pool.get('product.product')
        StockLocation = pool.get('stock.location')
        StockMove = pool.get('stock.move')

        wh_name = ""
        products = {}
        init_date = data['from_date']
        end_date = data['to_date']

        warehouses = StockLocation.browse(data['locations'])
        id_locations = data['locations']
        tup_locations = tuple(id_locations)
        detail_by_product = data['detail_by_product']

        dom_inventory = [
            ('OR', ('state', '=', "done"), ('state', '=', "pre_count")),
            ('date', '>=', init_date),
            ('date', '<=', end_date),
            ('location', 'in', tup_locations),
        ]
        inventory = StockInventory.search(dom_inventory)

        dom_products = [
            ('active', '=', True),
            ('template.active', '=', True),
            ('type', '=', 'goods'),
            ('consumable', '=', False),
        ]
        if data['categories']:
            dom_products.append([
                'AND',
                [
                    'OR',
                    [
                        ('account_category', 'in', data['categories']),
                    ],
                    [
                        ('categories', 'in', data['categories']),
                    ],
                ]
            ])

        stock_context_start = {
            'stock_date_end': (data['from_date'] - timedelta(1)),
            'locations': id_locations,
        }
        stock_context_end = {
            'stock_date_end': data['to_date'],
            'locations': id_locations,
        }
        fields_names = ['code', 'name', 'quantity']

        if not detail_by_product:
            with Transaction().set_context(stock_context_start):
                products_start = Product.search_read(dom_products,
                                                     fields_names=fields_names)
            if products_start:
                for product in products_start:
                    cls.set_value(product, 'start', products)
                    moves = {}
                    dom_moves = [('product', '=', product["id"]),
                                 ('OR', ('state', '=', "done"), ('state', '=',
                                                                 "assigned")),
                                 ('effective_date', '>=', init_date),
                                 ('effective_date', '<=', end_date),
                                 ('OR', ('to_location', 'in', tup_locations),
                                  ('from_location', 'in', tup_locations))]

                    moves = StockMove.search(dom_moves)
                    if moves:
                        cls.set_moves(product, moves, products, tup_locations)
            with Transaction().set_context(stock_context_end):
                products_end = Product.search_read(dom_products,
                                                   fields_names=fields_names)
            if products_end:
                for product in products_end:
                    cls.set_value(product, 'end', products)
                if inventory:
                    for product in products_end:
                        cls.set_inventory(product, inventory, products, "end")
        else:
            for prod in data["products"]:
                dom_products = [
                    ('active', '=', True),
                    ('template.active', '=', True),
                    ('type', '=', 'goods'),
                    ('consumable', '=', False),
                    ('id', '=', prod),
                ]
                with Transaction().set_context(stock_context_start):
                    products_start = Product.search_read(
                        dom_products, fields_names=fields_names)

                with Transaction().set_context(stock_context_end):
                    products_end = Product.search_read(
                        dom_products, fields_names=fields_names)

                if products_start:
                    for product in products_start:
                        cls.set_value(product, 'start', products)
                        moves = {}
                        dom_moves = [('product', '=', product["id"]),
                                     ('state', 'in', ['done', 'assigned']),
                                     ('effective_date', '>=', init_date),
                                     ('effective_date', '<=', end_date),
                                     ('OR', ('to_location', 'in',
                                             tup_locations),
                                      ('from_location', 'in', tup_locations))]
                        moves = StockMove.search(dom_moves)
                        if moves:
                            cls.set_moves(product, moves, products,
                                          tup_locations)
                if products_end:
                    for product in products_end:
                        cls.set_value(product, 'end', products)
                    if inventory:
                        for product in products_end:
                            cls.set_inventory(product, inventory, products,
                                              "end")

        if len(warehouses) > 1:
            for warehouse in warehouses:
                wh_name += (warehouse.name + ' | ')
        else:
            wh_name = warehouses[0].name

        report_context['products'] = products.values()
        report_context['warehouse'] = wh_name
        report_context['company'] = Company(data['company'])
        return report_context

    @classmethod
    def set_value(cls, product, key, products):
        """Function that update list of data by report"""
        pool = Pool()
        product_template = pool.get('product.template')
        uom_product = ""

        id_product = int(product["id"])
        code_product = int(product["code"])
        product_oum = product_template.search(["code", "=", code_product])

        if product_oum:
            uom_product = product_oum[0].default_uom.name

        defaults = {
            'name': "",
            'code': "",
            'udm': "",
            'start': 0,
            'input': 0,
            'output': 0,
            'end': 0,
            'inventory': 0,
            'difference': 0,
            'difference_porcent': "",
            'line_product': {
                'input': 0,
                'output': 0,
            },
            'detail_by_product': False
        }

        if id_product not in products:
            products[id_product] = copy.deepcopy(defaults)

        if key == "start":
            products[id_product].update({key: product['quantity']})

        if key == "end":
            move_quantity = products[product['id']]["end"]
            new_quantity = move_quantity + product['quantity']
            products[id_product].update({key: new_quantity})

        products[id_product].update({
            'code': product['code'],
            'name': product['name'],
            'udm': uom_product
        })

    @classmethod
    def set_moves(cls, product, moves, products, tup_locations):
        """Function that update stock moves by list of data by report"""

        moves_in = 0
        moves_out = 0

        for move in moves:
            if move.to_location.id in tup_locations:
                moves_in += move.quantity
                if move.state == "assigned":
                    move_quantity = products[product['id']]["end"]
                    new_quantity = move_quantity + move.quantity
                    products[product['id']].update({"end": new_quantity})
            else:
                moves_out += move.quantity
                if move.state == "assigned":
                    move_quantity = products[product['id']]["end"]
                    new_quantity = move_quantity - move.quantity
                    products[product['id']].update({"end": new_quantity})

        products[product['id']].update({"input": moves_in})
        products[product['id']].update({"output": moves_out})

    @classmethod
    def set_inventory(cls, product, inventories, products, key):
        """function that compare data info with physic inventory"""

        pool = Pool()
        stock_inventory_line = pool.get('stock.inventory.line')

        for inventory in inventories:
            id_inventory = inventory.id
            dom_inventory = [('product', '=', product["id"]),
                             ('inventory', '=', id_inventory)]
            inventory_lines = stock_inventory_line.search(dom_inventory)
            quantity = 0
            inventory_quantity = 0
            difference = 0
            difference_porcent = Decimal(0)

            if inventory_lines:
                quantity = inventory_lines[0].quantity
                products[product['id']].update({"inventory": quantity})

            if key == "end":
                final_quantity = abs(products[product['id']]['end'])
                inventory_quantity = products[product['id']]['inventory']

                if inventory_quantity:
                    inventory_quantity = abs(inventory_quantity)
                    difference = final_quantity - inventory_quantity
                    difference_porcent = round(
                        ((final_quantity - inventory_quantity) /
                         inventory_quantity) * 100)
                    difference_porcent = f"{difference_porcent}%"

                products[product['id']].update({"difference": difference})
                products[product['id']].update(
                    {"difference_porcent": difference_porcent})


class WarehouseReport(metaclass=PoolMeta):
    'Warehouse Report'
    __name__ = 'stock_co.warehouse_stock.report'

    @classmethod
    def get_context(cls, records, header, data):
        report_context = Report.get_context(records, header, data)
        pool = Pool()
        Company = pool.get('company.company')
        Product = pool.get('product.product')
        OrderPoint = pool.get('stock.order_point')
        Location = pool.get('stock.location')
        ids_location = data['locations']
        locations = Location.browse(data['locations'])
        dom_products = [
            ('active', '=', True),
            ('template.active', '=', True),
            ('type', '=', 'goods'),
        ]

        stock_context = {
            'stock_date_end': data['to_date'],
            'locations': ids_location,
        }

        if data['category']:
            dom_products.append(['AND', ['OR', [
                ('account_category', '=', data['category']),
            ], [
                ('categories', 'in', [data['category']]),
            ],
            ]])

        if not data['zero_quantity']:
            dom_products.append([('quantity', '!=', 0)])

        if data['only_minimal_level']:
            order_points = OrderPoint.search([
                ('warehouse_location', 'in', ids_location),
                ('type', '=', 'purchase'),
            ])
            min_quantities = {
                op.product.id: op.min_quantity for op in order_points}

            products_ids = min_quantities.keys()
            dom_products.append(('id', 'in', products_ids))
        if data['suppliers']:
            dom_products.append(
                [('template.product_suppliers.party', 'in', data['suppliers'])])

        total_amount = 0
        values = {}
        products = []
        if data['group_by_location']:
            for l in locations:
                stock_context['locations'] = [l.id]
                with Transaction().set_context(stock_context):
                    prdts = Product.search(
                        dom_products, order=[('code', 'ASC')])
                suppliers = {}
                if data['group_by_supplier']:
                    for p in prdts:
                        if not p.template.product_suppliers:
                            continue
                        for prod_sup in p.template.product_suppliers:
                            sup_id = prod_sup.party.id
                            try:
                                suppliers[sup_id]['products'].append(p)
                                suppliers[sup_id]['total_amount'].append(
                                    p.amount_cost if p.amount_cost else 0)
                            except:
                                suppliers[sup_id] = {}
                                suppliers[sup_id]['products'] = [p]
                                suppliers[sup_id]['party'] = prod_sup.party
                                suppliers[sup_id]['total_amount'] = [
                                    p.amount_cost if p.amount_cost else 0]
                total_amount = sum(
                    [p.amount_cost for p in prdts if p.amount_cost])
                values[l.id] = {
                    'name': l.name,
                    'products': prdts,
                    'suppliers': suppliers.values(),
                    'total_amount': total_amount
                }
            products = values.values()
        else:
            with Transaction().set_context(stock_context):
                products = Product.search(
                    dom_products, order=[('code', 'ASC')])

            if data['only_minimal_level']:
                products = [p for p in products if p.quantity
                            <= min_quantities[p.id]]
            total_amount = sum(
                [p.amount_cost for p in products if p.amount_cost])
            suppliers = {}
            if data['group_by_supplier']:
                for p in products:
                    if not p.template.product_suppliers:
                        continue
                    for prod_sup in p.template.product_suppliers:
                        sup_id = prod_sup.party.id
                        try:
                            suppliers[sup_id]['products'].append(p)
                            suppliers[sup_id]['total_amount'].append(
                                p.amount_cost if p.amount_cost else 0)
                        except:
                            suppliers[sup_id] = {}
                            suppliers[sup_id]['products'] = [p]
                            suppliers[sup_id]['party'] = prod_sup.party
                            suppliers[sup_id]['total_amount'] = [
                                p.amount_cost if p.amount_cost else 0]
                products = suppliers.values()

        cursor = Transaction().connection.cursor()
        query = "select distinct on(p.id) p.id, t.name, p.code, s.effective_date from product_product as p right join stock_move as s on p.id=s.product join product_template as t on p.template=t.id where s.shipment ilike 'stock.shipment.in,%' and state='done' order by p.id, s.effective_date DESC;"
        cursor.execute(query)
        columns = list(cursor.description)
        result = cursor.fetchall()
        last_purchase = {}

        for row in result:
            row_dict = {}
            for i, col in enumerate(columns):
                row_dict[col.name] = row[i]
            last_purchase[row[0]] = row_dict

        report_context['group_by_location'] = data['group_by_location']
        report_context['group_by_supplier'] = data['group_by_supplier']
        report_context['records'] = products
        report_context['total_amount'] = total_amount
        report_context['last_purchase'] = last_purchase
        report_context['location'] = data['location_names']
        report_context['stock_date_end'] = data['to_date']
        report_context['company'] = Company(data['company'])
        return report_context


class ShipmentDetailedStart(metaclass=PoolMeta):
    'Shipment Detailed Start'
    __name__ = 'stock.shipment.shipment_detailed.start'

    @classmethod
    def __setup__(cls):
        super().__setup__()
        cls.from_locations.domain = [('active', '=', True)]
        cls.to_locations.domain = [('active', '=', True)]
