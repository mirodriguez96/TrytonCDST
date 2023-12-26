from trytond.pool import Pool, PoolMeta
from trytond.model import fields, Workflow, ModelView
from trytond.transaction import Transaction
from operator import itemgetter
from decimal import Decimal
from .additional import validate_documentos
from trytond.wizard import (
    StateReport, StateView, Button)
from collections import defaultdict
from trytond.pyson import Eval, If, Bool
from datetime import timedelta
import copy

SW = 16

type_shipment = {
    'out': 'Envio a Clientes',
    'in': 'Envio de Proveedor',
    'internal': 'Envio Interno',
}


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
        logs = {}
        for bodega in bodegas:
            id_tecno = bodega.IdBodega
            nombre = bodega.Bodega.strip()
            existe = Location.search([('id_tecno', '=', id_tecno)])
            if existe:
                if existe[0].name != nombre:
                    existe[0].name = nombre
                    _warehouses.append(existe[0])
                    logs[id_tecno] = f'Se actualiza nombre de la bodega "{nombre}"'
                continue
            #zona de entrada
            ze = Location()
            ze.id_tecno = 'ze-'+str(id_tecno)
            ze.name = 'ZE '+nombre
            ze.type = 'storage'
            _zones.append(ze)
            #zona de salida
            zs = Location()
            zs.id_tecno = 'zs-'+str(id_tecno)
            zs.name = 'ZS '+nombre
            zs.type = 'storage'
            _zones.append(zs)            
            #zona de almacenamiento
            za = Location()
            za.id_tecno = 'za-'+str(id_tecno)
            za.name = 'ZA '+nombre
            za.type = 'storage'
            _zones.append(za)
            #zona de producción
            prod = Location()
            prod.id_tecno = 'prod-'+str(id_tecno)
            prod.name = 'PROD '+nombre
            prod.type = 'production'
            _zones.append(prod)
            # Bodega
            almacen = Location()
            almacen.id_tecno = id_tecno
            almacen.name = nombre
            almacen.type = 'warehouse'
            almacen.input_location = ze
            almacen.output_location = zs
            almacen.storage_location = za
            almacen.production_location = prod
            _warehouses.append(almacen)
        # Se crean todas las bódegas y ubicaciones
        Location.save(_zones)
        Location.save(_warehouses)
        actualizacion.add_logs(logs)
        print('FINISH BODEGAS')


class ShipmentDetailedReport(metaclass=PoolMeta):
    'Shipment Detailed Report'
    __name__ = 'stock.shipment.shipment_detailed.report'


    @classmethod
    def get_context(cls, records, header, data):
        report_context = super().get_context(records, header, data)

        pool = Pool()
        company = Transaction().context.get('company.rec_name')
        type_shipment_ = data['type_shipment']
        model = 'stock.shipment.' + type_shipment_
        ModelShipment = pool.get(model)
        Move = pool.get('stock.move')
        Product = pool.get('product.product')
        dom_shipment = [
            ('company', '=', data['company']),
            ('effective_date', '>=', data['start_date']),
            ('effective_date', '<=', data['end_date'])
        ]
        if data['from_locations']:
            dom_shipment.append(('from_location' , 'in', data['from_locations']))
        if data['to_locations']:
            dom_shipment.append(('to_location' , 'in', data['to_locations']))

        fields_names = ['id']
        shipments = ModelShipment.search_read(dom_shipment,
                                              fields_names=fields_names,
                                              order=[('effective_date', 'ASC')]
                                              )
        shipments_id = [model + ',' + str(sh['id']) for sh in shipments]
        fields_names = [
            'product.account_category.name', 'product.name', 'product.cost_price',
            'quantity', 'to_location.name', 'from_location.name', 'shipment.reference',
            'effective_date', 'shipment.number', 'unit_price'
        ]
        fields = ModelShipment.fields_get(fields_names=['operation_center', 'customer', 'supplier', 'incoming_moves'])
        if 'operation_center' in fields.keys():
            fields_names.append('shipment.operation_center.rec_name')

        if type_shipment_ == 'in':
            fields_names.append('shipment.supplier.name')
        elif type_shipment_ == 'out':
            fields_names.append('shipment.customer.name')

        moves = Move.search_read(
            ('shipment', 'in', shipments_id),
            fields_names=fields_names,
            order=[('to_location', 'DESC'), ('create_date', 'ASC')]
        )

        dgetter = itemgetter('product.', 'quantity')
        product_browse = Product.browse
        for m in moves:
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

            value = {
                'party': party,
                'oc': oc,
                'product': product['name'],
                'cost_price': cost_price,
                'category': category,
                'category_ad': category_ad,
                'cost_base': Decimal(str(round(float(cost_price) * quantity, 2))),

            }
            try:
                value['cost_unit_w_tax'] = float(product_.cost_price_taxed)
                value['cost_w_tax'] = float(
                    product_.cost_price_taxed) * quantity
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
    def import_tecnocarnes(cls):
        print('RUN TRASLADOS INTERNOS')
        pool = Pool()
        Product = pool.get('product.product')
        Config = pool.get('conector.configuration')
        configuration = Config.get_configuration()
        logs = {}
        to_exception = []
        id_ = 0
        if not configuration:
            return
        data = Config.get_documentos_traslados()
        if not data:
            return
        Actualizacion = pool.get('conector.actualizacion')
        actualizacion = Actualizacion.create_or_update('TRASLADOS')
        result = validate_documentos(data)

        try:
            shipments = cls.create(result["tryton"].values())
            # with Transaction().set_context(_skip_warnings=True):
            for shipment in shipments:
            #     create_line = []
            #     acomulate_lines = {}
            #     validate = True
            #     for productmove in shipment.outgoing_moves:
                #     if not productmove.product.id_tecno:
                #         msg = f"EXCEPCION: No se encontro id_tecno del producto {productmove.product.template.name}"
                #         logs[productmove.product] = msg
                #         to_exception.append(productmove.product)
                #         continue
                #     idTecno = int(productmove.product.id_tecno)

                #     if idTecno in dictprodut.keys():
                #         id_ = dictprodut[idTecno]['idresponsable']

                #         producto = Product.search(['OR', ('id_tecno', '=', id_), ('code', '=', id_)])
                #         if producto:
                #             product, = producto
                #             if productmove.product.default_uom.symbol == product.default_uom.symbol:
                #                 productmove.product = product


                #         productmove.save()
                #     if productmove.product not in acomulate_lines:
                #         acomulate_lines[productmove.product] = {
                #             'line': productmove
                #         }
                        
                #     amount = round(productmove.quantity,1)
                #     if validate:
                #         acomulate_lines[productmove.product]['line'].quantity = 0
                #         validate = False
                #     acomulate_lines[productmove.product]['line'].quantity += amount
                #     acomulate_lines[productmove.product]['line'].quantity = round( acomulate_lines[productmove.product]['line'].quantity,3)
                # for item in acomulate_lines.values():
                #     create_line.append(item['line'])
                # shipment.outgoing_moves = list(create_line)
                shipment.save()
        except Exception as e:
            result["logs"]["try_except"] = str(e)
            actualizacion.add_logs(result["logs"])
            return
        actualizacion.add_logs(result["logs"])
        for exportado, idt in result["exportado"].items():
            print(exportado,idt)
            if idt:
                Config.update_exportado_list(idt, exportado)
        print('FINISH import_tecnocarnes')
        

    @classmethod
    def create_account_move(cls, shipments):
        result = []
        for shipment in shipments:
            if not shipment.id_tecno:
                result.append(shipment)
        # Se valida que solo procese los que no se han importado de TecnoCarnes
        super(ShipmentInternal, cls).create_account_move(result)


class ModifyCostPrice(metaclass=PoolMeta):
    "Modify Cost Price"
    __name__ = 'product.modify_cost_price'

    def transition_modify(self):
        pool = Pool()
        Product = pool.get('product.product')
        Revision = pool.get('product.cost_price.revision')
        AverageCost = Pool().get('product.average_cost')
        Date = pool.get('ir.date')
        today = Date.today()
        revisions = []
        costs = defaultdict(list)
        if self.model.__name__ == 'product.product':
            records = list(self.records)
            for product in list(records):
                revision = self.get_revision(Revision)
                revision.product = product
                revision.template = product.template
                revisions.append(revision)
                if ((
                            product.cost_price_method == 'fixed'
                            and revision.date == today)
                        or product.type == 'service'):
                    cost = revision.get_cost_price(product.cost_price)
                    costs[cost].append(product)
                    records.remove(product)
        elif self.model.__name__ == 'product.template':
            records = list(self.records)
            for template in list(records):
                revision = self.get_revision(Revision)
                revision.template = template
                revisions.append(revision)
                if ((
                            template.cost_price_method == 'fixed'
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
    


class MoveCDT(metaclass=PoolMeta):
    "Stock Move"
    __name__ = 'stock.move'


    def set_average_cost(self):
        Product = Pool().get('product.product')
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
        Product.recompute_cost_price([self.product], start=self.effective_date)


    @classmethod
    def _get_origin(cls):
        return super(MoveCDT, cls)._get_origin() + ['production']