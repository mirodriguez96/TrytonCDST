"""STOCK MOVEMENTS MODULE"""

import copy
import logging
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal
from operator import itemgetter

from trytond.exceptions import UserError
from trytond.i18n import gettext
from trytond.model import ModelView, Workflow, fields
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Bool, Eval, Not
from trytond.report import Report
from trytond.transaction import Transaction
from trytond.wizard import Button, StateReport, StateView, Wizard

from .additional import validate_documentos

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

    # product_type = fields.Selection(
    #     TYPES_PRODUCT, 'Type Product',
    #     states={
    #         'invisible': Eval('get_product_type_visible') is False,
    #     },
    #     depends=['get_product_type_visible']
    # )

    # get_product_type_visible = fields.Function(
    #     fields.Boolean('Get Product Type Visible'),
    #     'get_product_type_visible_'
    # )

    # @fields.depends('id')
    # def get_product_type_visible_(self, name=None):
    #     """Function to get config for salable products visibility"""
    #     Configuration = Pool().get('stock.configuration')
    #     # Consider changing this to fetch the correct configuration record
    #     config = Configuration(1)
    #     if config and config.consumable_products_state:
    #         print(config.consumable_products_state)
    #         return config.consumable_products_state
    #     return False

    # @fields.depends('id')
    # def on_change_with_get_product_type_visible(self, name=None):
    #     """Function to get config for salable products visibility"""
    #     Configuration = Pool().get('stock.configuration')
    #     # Consider changing this to fetch the correct configuration record
    #     config = Configuration(1)
    #     if config and config.consumable_products_state:
    #         print(config.consumable_products_state)
    #         return config.consumable_products_state
    #     return False

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
        """Function to import internal shipments from tecnocarnes"""

        pool = Pool()
        Config = pool.get('conector.configuration')
        Actualizacion = pool.get('conector.actualizacion')
        ConfigShipment = pool.get('stock.configuration')

        import_name = "TRASLADOS INTERNOS"
        print(f"---------------RUN {import_name}---------------")
        configuration = Config.get_configuration()
        config_shipment = ConfigShipment.search([])
        state_shipment = config_shipment[0].state_shipment
        if not configuration:
            return
        data = Config.get_documentos_traslados()
        if not data:
            return

        actualizacion = Actualizacion.create_or_update('TRASLADOS')
        result = validate_documentos(data)

        shipments = []
        for value in result["tryton"].values():
            try:
                shipment, = cls.create([value])
                shipments.append(shipment)
            except Exception as error:
                # Transaction().rollback()
                logging.error(f"ROLLBACK-{import_name}: {error}")
                result["logs"][value['id_tecno']] = str(error)
                result["exportado"][shipment.id_tecno] = "E"

        for shipment in shipments:
            try:
                if state_shipment and state_shipment == 'done':
                    cls.wait([shipment])
                    cls.assign([shipment])
                    cls.done([shipment])
            except Exception as error:
                Transaction().rollback()
                logging.error(f"ROLLBACK-{import_name}: {error}")
                result["logs"]["EXCEPCION"] = str(error)

        for exportado, idt in result["exportado"].items():
            if idt:
                if exportado != 'E':
                    try:
                        Config.update_exportado_list(idt, exportado)
                    except Exception as error:
                        result["logs"]["try_except"] = str(error)

        actualizacion.add_logs(result["logs"])
        print(f"---------------FINISH {import_name}---------------")

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


class MoveCDT(metaclass=PoolMeta):
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
        # try:
        #     Product.recompute_cost_price(
        #         [self.product], start=self.effective_date)
        # except Exception as error:
        #     raise UserError(f"ERROR:",error)
        # code_product = self.product.template.code
        # name_product = self.product.template.name
        # raise UserError(f"ERROR:",
        #                 f"El producto con codigo [{code_product}-{name_product}] No coinice la UDM")

    @classmethod
    def _get_origin(cls):
        return super(MoveCDT, cls)._get_origin() + ['production']

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
        super(MoveCDT, cls).do(moves)
        for move in moves:
            cost_price_move = move.cost_price
            if move.origin and move.origin.__name__ == 'stock.inventory.line':
                date_inventory = move.origin.inventory.date
                if move.product and move.product.template:
                    cost_revision = ProductRevision.search(
                        [('template', '=', move.product.template),
                            ('date', '<=', date_inventory)],
                        order=[('id', 'DESC')],
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
