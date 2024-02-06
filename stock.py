"""STOCK MOVEMENTS MODULE"""

from operator import itemgetter
from decimal import Decimal
from collections import defaultdict
from datetime import timedelta
import copy

from trytond.pool import Pool, PoolMeta
from trytond.model import fields, Workflow, ModelView
from trytond.transaction import Transaction
from trytond.wizard import (StateReport, StateView, Button, Wizard)
from trytond.report import Report
from trytond.exceptions import UserError
from trytond.i18n import gettext
from trytond.pyson import Eval, Bool
from .additional import validate_documentos

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
                    logs[
                        id_tecno] = f'Se actualiza nombre de la bodega "{nombre}"'
                continue
            #zona de entrada
            ze = Location()
            ze.id_tecno = 'ze-' + str(id_tecno)
            ze.name = 'ZE ' + nombre
            ze.type = 'storage'
            _zones.append(ze)
            #zona de salida
            zs = Location()
            zs.id_tecno = 'zs-' + str(id_tecno)
            zs.name = 'ZS ' + nombre
            zs.type = 'storage'
            _zones.append(zs)
            #zona de almacenamiento
            za = Location()
            za.id_tecno = 'za-' + str(id_tecno)
            za.name = 'ZA ' + nombre
            za.type = 'storage'
            _zones.append(za)
            #zona de producción
            prod = Location()
            prod.id_tecno = 'prod-' + str(id_tecno)
            prod.name = 'PROD ' + nombre
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
        dom_shipment = [('company', '=', data['company']),
                        ('effective_date', '>=', data['start_date']),
                        ('effective_date', '<=', data['end_date'])]
        if data['from_locations']:
            dom_shipment.append(
                ('from_location', 'in', data['from_locations']))
        if data['to_locations']:
            dom_shipment.append(('to_location', 'in', data['to_locations']))

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
            'shipment.number', 'unit_price'
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
                'cost_base':
                Decimal(str(round(float(cost_price) * quantity, 2))),
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
    def __setup__(cls):
        super(ShipmentInternal, cls).__setup__()
        cls.from_location.domain = [('type', 'in', ['storage', 'lost_found']),
                                    ('active', '=', True)]

        cls.to_location.domain = [('type', 'in', ['storage', 'lost_found']),
                                  ('active', '=', True)]

    @classmethod
    def import_tecnocarnes(cls):
        print('RUN TRASLADOS INTERNOS')
        pool = Pool()
        Product = pool.get('product.product')
        Config = pool.get('conector.configuration')
        configuration = Config.get_configuration()
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
            for shipment in shipments:
                shipment.save()
        except Exception as e:
            result["logs"]["try_except"] = str(e)
            actualizacion.add_logs(result["logs"])
            return
        actualizacion.add_logs(result["logs"])
        for exportado, idt in result["exportado"].items():
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

    @classmethod
    def get_account_move(cls, shipment):
        pool = Pool()
        Uom = pool.get('product.uom')
        Configuration = pool.get('account.configuration')
        Period = pool.get('account.period')

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
                account_debit = move.product.account_expense_used
                if account_debit.party_required:
                    party = shipment.company.party.id
                else:
                    party = None

                cost_price = Uom.compute_price(move.product.default_uom,
                                               move.product.cost_price,
                                               move.uom)
                amount = shipment.company.currency.round(
                    Decimal(str(move.quantity)) * cost_price)
                line_debit = {
                    'account': account_debit,
                    'party': party,
                    'debit': amount,
                    'credit': Decimal(0),
                    'description': move.product.name,
                }
                op = True if hasattr(shipment, 'operation_center') else False
                if op:
                    line_debit.update(
                        {'operation_center': shipment.operation_center})

                if shipment.analytic_account and account_debit.type.statement != 'balance':
                    line_analytic = {
                        'account': shipment.analytic_account,
                        'debit': amount,
                        'credit': Decimal(0)
                    }
                    line_debit['analytic_lines'] = [('create', [line_analytic])
                                                    ]
                lines_to_create.append(line_debit)

                account_credit = move.product.account_stock_used

                if account_credit.party_required:
                    party = shipment.company.party.id
                else:
                    party = None

                line_credit = {
                    'account': account_credit,
                    'party': party,
                    'debit': Decimal(0),
                    'credit': amount,
                    'description': move.product.name,
                }
                lines_to_create.append(line_credit)
            except Exception as e:
                print(e)
                moves_error.append(
                    ['error:', move.product.name, shipment.number])
                raise UserError(
                    gettext('account_stock_latin.msg_missing_account_stock',
                            product=move.product.name))
        if moves_error:
            return None
        account_move = {
            'journal': journal,
            'date': shipment.effective_date,
            'origin': shipment,
            'company': shipment.company,
            'period': period_id,
            'lines': [('create', lines_to_create)]
        }
        return account_move


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

    def _get_account_stock_move_lines(self, type_):
        '''
        Return move lines for stock move
        '''
        pool = Pool()
        Uom = pool.get('product.uom')
        AccountMoveLine = pool.get('account.move.line')
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

        if self.product.template.salable:
            account = self.product.account_cogs_used

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
        AccountMove = pool.get('account.move')
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
        super(MoveCDT, cls).do(moves)
        account_moves = []
        for move in moves:
            account_move = move._get_account_stock_move()
            if account_move:
                account_moves.append(account_move)
        _moves = AccountMove.create(account_moves)
        AccountMove.post(_moves)


class Inventory(metaclass=PoolMeta):
    'Stock Inventory'
    __name__ = 'stock.inventory'

    analitic_account = fields.Many2One('analytic_account.account',
                                       'Analytic Account',
                                       required=False)


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
                      'conector.warehouse_kardex_stock_start_cds_view_form', [
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
        inventories = pool.get('stock.inventory')
        company = pool.get('company.company')
        product = pool.get('product.product')
        location = pool.get('stock.location')
        stock_move = pool.get('stock.move')

        wh_name = ""
        products = {}
        init_date = data['from_date']
        end_date = data['to_date']

        warehouses = location.browse(data['locations'])
        id_locations = data['locations']
        tup_locations = tuple(id_locations)
        detail_by_product = data['detail_by_product']

        dom_inventory = [
            ('OR', ('state', '=', "done"), ('state', '=', "pre_count")),
            ('date', '>=', init_date),
            ('date', '<=', end_date),
            ('location', 'in', tup_locations),
        ]
        inventory = inventories.search(dom_inventory)

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
                products_start = product.search_read(dom_products,
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

                    moves = stock_move.search(dom_moves)
                    if moves:
                        cls.set_moves(product, moves, products, tup_locations)
            with Transaction().set_context(stock_context_end):
                products_end = product.search_read(dom_products,
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
                    products_start = product.search_read(
                        dom_products, fields_names=fields_names)

                with Transaction().set_context(stock_context_end):
                    products_end = product.search_read(
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
                        moves = stock_move.search(dom_moves)
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
        report_context['company'] = company(data['company'])
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
