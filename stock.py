from trytond.pool import Pool, PoolMeta
from trytond.model import fields
from trytond.transaction import Transaction
from operator import itemgetter
from decimal import Decimal

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
