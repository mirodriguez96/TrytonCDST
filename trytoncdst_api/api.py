from functools import lru_cache
import requests
import base64
import logging
import orjson
from tools import get_config
from pydantic.json import ENCODERS_BY_TYPE
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, FileResponse
from fastapi.encoders import jsonable_encoder
from fastapi_tryton import Tryton, Settings
import json
import base64
from decimal import Decimal
import re
import tempfile
import subprocess

ENCODERS_BY_TYPE[bytes] = lambda v: base64.b64encode(
    v, altchars=None).decode('utf-8')

config = get_config()
local_url = list(
    eval(config.get('CORS', 'origins', fallback=['http://0.0.0.0'])))[0]

print(local_url)
uri_trytond = local_url + ':8000/'

HEADERS = {
    'Accept': 'application/json',
    'Content-type': 'application/json'
}

context = {
    'company': 1,
    'shops': [1, 2],
    'locations': [3],
    # 'context_model': 'stock.products_by_locations.context'
}  # There's only one company of interest, yes, I know, magic number, trying to fix that


def encode(rec):
    json_data = jsonable_encoder(
        rec, custom_encoder={bytes: lambda v: base64.b64encode(v).decode('utf-8')})
    return json_data


def get_dict_binaries(files: dict) -> dict:
    files_dict = {}
    for k, v in files.items():
        files_dict[k] = base64.b64decode(v, altchars=None)
    return files_dict


def create_app(dbname, config):
    @lru_cache()
    def get_settings():
        return Settings(
            tryton_db=dbname,
            tryton_user=None,
            tryton_config=config
        )

    app = FastAPI()
    try:
        app.settings = get_settings()
        tryton = Tryton(app)
    except Exception as e:
        print('-----', e)
        logging.warning(
            'Error database disabled or unknown error: %s' % dbname)
        return None

    def is_user_verified(request: Request):
        # session is a string of the form:
        # Bearer login:id:token

        if not "Authorization" in request.headers:
            return False

        session = request.headers["Authorization"].split()[1]
        token = session.split(':')[2]

        data = {
            "method": "common.session.get",
            "params": [token],
            "id": 1
        }
        data = json.dumps(data).encode('utf-8')
        uri = local_url + ':8000/' + dbname
        user_id = None
        headers = HEADERS.copy()

        authSession = base64.b64encode(session.encode('utf-8')).decode('utf-8')

        headers["Authorization"] = "Session " + authSession

        try:
            response = requests.post(uri, headers=headers, data=data)
        except Exception as e:
            print(' Error ...', e)

        if not response.ok:
            return False

        return True

    @app.post("/auth/login")
    async def login(request: Request, responseApp: Response, args: dict):
        res = {"user": {}}
        data = {
            "method": "common.db.login",
            "params": [
                args["username"],
                {"device_cookie": None, "password": args["password"]}
                ]
        }
        data = json.dumps(data).encode('utf-8')
        uri = local_url + ':8000/' + dbname
        user_id = None
        try:
            response = requests.post(uri, headers=HEADERS, data=data)
            if response.ok:
                user_id, session = response.json()
            # print(response.status_code, 'status_code')
        except Exception as e:
            print(' Error ...', e)

        if response.status_code == 200 and user_id:
            User = tryton._get('res.user')
            args = {
                'domain': [
                    ('id', '=', user_id),
                    ('active', '=', True),
                ],
                'fields_names': [
                    'name', 'login', 'company', 'company.party.name', 'groups',
                    'company.timezone', 'employee', 'company.currency',
                    'language.code', 'groups.name', 'sale_device', 'shop'
                ],
                'limit': 1,
                'context': {
                    'user': user_id,
                }
            }
            users = User.search_read(args)
            if users:
                _user = users[0]
                company = _user['company.']
                # res['session'] = session
                res['token'] = session
                res['user']['id'] = _user['id']
                res['user']['name'] = _user['name']
                res['user']['username'] = _user['login']

                Device = tryton._get('sale.device')
                args = {
                    'domain': [('id', '=', _user['sale_device'])],
                    'fields_names': ['id', 'name'],
                }
                device = Device.search_read(args)[0]
                res['user']['device'] = device

                # res['company'] = _user['company']
                # res['company_name'] = company['party.']['name']
                # res['currency'] = company['currency']
                # res['timezone'] = company['timezone']
                # print('_user........', _user)
                # res['language'] = _user['language.']['code'] if _user.get('languaje.') else None
                # res['user_employee'] = _user['employee']

                # FIXME
                # res['user_employee_name'] = _user.employee.rec_name if _user.employee else None

                # res['shop'] = _user["shop"]
                # if "shop" in _user and _user["shop"]:
                #    res['shop'] = _user["shop"]
                #    res['shop_name'] = _user.shop.name

                res['user']['role'] = 'Vendedor'
                for group in _user['groups.']:
                    if group['id'] == 1:
                        res['user']['role'] = 'Administrador'

                        # Device = tryton._get('sale.device')
                        # args = {
                        #    'domain': [],
                        #    'fields_names': ['id'],
                        # }

                        # devices = Device.search_read(args)
                        # devicesResult = []
                        # for device in devices:
                        #    devicesResult.append({'_id': device['id'], 'name': device['id']})

                        # res['user']['all_devices'] = devicesResult

                        break
                return res

        else:
            return JSONResponse(
                status_code=401,
                content={'message': 'Invalid credentials'}
            )

    @app.post("/fast_login")
    async def fast_login(request: Request, args: dict):
        body = orjson.dumps({
            "method": "common.db.login",
            "params": [
                args['username'],
                {"device_cookie": None, "password": args['passwd']},
                "es",
            ],
            "id": 0,
            "context": {},
        })
        uri = f'{uri_trytond}/{dbname}'
        user_id = None
        res = {'user': None}
        try:
            response = requests.post(uri, headers=HEADERS, data=body)
            user_id, session = response.json()
        except Exception as e:
            res['status'] = response.status_code
            res['message'] = response.text
            print(' Error ...', e)
            return res
        if response.status_code != 200 or not user_id:
            return {}
        User = tryton._get('res.user')
        args = {
            'domain': [
                ('id', '=', user_id),
                ('active', '=', True),
            ],
            'fields_names': [
                'name', 'login', 'company', 'company.party.name', 'groups',
                'company.timezone', 'employee', 'company.currency',
                'language.code', 'groups.name'
            ],
            'limit': 1,
            'context': {
                'user': user_id,
            }
        }
        users = User.search_read(args)
        if users:
            _user = users[0]
            company = _user['company.']
            res['session'] = session
            res['token'] = 'not token'
            res['user'] = _user['id']
            res['user_name'] = _user['name']
            res['login'] = _user['login']
            res['company'] = _user['company']
            res['company_name'] = company['party.']['name']
            res['currency'] = company['currency']
            res['timezone'] = company['timezone']
            print('_user........', _user)
            res['language'] = _user['language.']['code'] if _user.get(
                'language.') else None
            res['user_employee'] = _user['employee']
            if hasattr(_user, 'shop') and _user.shop:
                res['shop'] = _user.shop.id
                res['shop_name'] = _user.shop.name
            res['groups'] = _user['groups.']
        return res

    @app.get("/auth/me")
    async def session(request: Request, response: Response):
        if not is_user_verified(request):
            return JSONResponse(
                status_code=401,
                content={'message': 'Invalid token'}
            )

        res = {'user': {}}
        user_id = request.headers["Authorization"].split()[1].split(':')[1]

        User = tryton._get('res.user')
        args = {
            'domain': [
                ('id', '=', user_id),
                ('active', '=', True),
            ],
            'fields_names': [
                'name', 'login', 'groups', 'sale_device', 'groups.name'
            ],
            'limit': 1,
            'context': {
                'user': user_id,
            }
        }
        users = User.search_read(args)
        if users:
            _user = users[0]
            # res['token'] = session
            res['id'] = _user['id']
            res['name'] = _user['name']
            res['username'] = _user['login']

            Device = tryton._get('sale.device')
            args = {
                'domain': [('id', '=', _user['sale_device'])],
                'fields_names': ['id', 'name'],
            }
            device = Device.search_read(args)[0]
            res['device'] = device

            res['role'] = 'Vendedor'
            for group in _user['groups.']:
                if group['id'] == 1:
                    res['role'] = 'Administrador'

                    # Device = tryton._get('sale.device')
                    # args = {
                    #    'domain': [],
                    #    'fields_names': ['id'],
                    # }

                    # devices = Device.search_read(args)
                    # devicesResult = []
                    # for device in devices:
                    #    devicesResult.append({'_id': device['id'], 'name': device['id']})

                    # res['all_devices'] = devicesResult
                    break
        else:
            return JSONResponse(
                status_code=401,
                content={'message': 'Invalid token'}
            )

        return res

    @app.post("/auth/logout")
    async def session(request: Request, responseApp: Response):
        data = {
            "method": "common.db.logout",
            "params": [],
            "id": 0
        }
        data = json.dumps(data).encode('utf-8')
        uri = local_url + ':8000/' + dbname
        user_id = None
        headers = HEADERS.copy()

        session = request.headers["Authorization"].split()[1]
        authSession = base64.b64encode(session.encode('utf-8')).decode('utf-8')

        headers["Authorization"] = "Session " + authSession

        try:
            response = requests.post(uri, headers=headers, data=data)
            response = response.json()
            print(response.status_code, 'status_code')
        except Exception as e:
            print(' Error ...', e)

        if not response:
            responseApp.status_code = 404  # Hablar con Juan sobre el body de la respuesta
            return responseApp

        return None  # Hablar con Juan sobre el body de la respuesta

    # Se debe corregir para que represente las bases de datos a utilizar
    @app.get("/warehouses/detail")
    async def warehouses(request: Request, response: Response):
        if not is_user_verified(request):
            response.status_code = 401
            return response

        return [
            {
                "_id": "1",
                "name": "tryton",
            }
        ]

    @app.get("/categories")
    async def categories(request: Request, response: Response):
        if not is_user_verified(request):
            response.status_code = 401
            return response

        Category = tryton._get('product.category')
        args = {
            'context': context.copy(),
            'domain': [('accounting', '=', False)],
            # 'domain': [],
            'fields_names': ['id', 'name', 'accounting'],
        }
        categories = Category.search_read(args)

        Product = tryton._get('product.template')
        for category in categories:
            args = {
                'context': context.copy(),
                'domain': [('categories', '=', category["id"]),
                    ('salable', '=', True)],  # Los productos no tienen categorias definidas en la base de datos de prueba
                'fields_names': ['name'],
            }
            category["products"] = len(Product.search_read(args))

        return categories

    @app.get("/products")
    async def products(request: Request, response: Response):
        if not is_user_verified(request):
            response.status_code = 401
            return response

        Product = tryton._get('product.template')
        args = {
            'context': context.copy(),
            'domain': [('salable', '=', True)],
            'fields_names': ['name', 'code', 'list_price', 'image_url', 'categories', 'account_category'],
        }

        products = Product.search_read(args)

        Category = tryton._get('product.category')
        Taxes = tryton._get('account.tax')

        for product in products:
            if product['image_url']:
                product['image_url'] = "https://elsalvador.onecluster.org" + \
                    product["image_url"]

            argsCategory = {
                'context': context.copy(),
                'domain': [('id', '=', product['account_category'])],
                'fields_names': ['customer_taxes']
            }

            categoryTax = Category.search_read(
                argsCategory)[0]['customer_taxes']
            # Argumentos para busqueda de impuestos
            argsTaxes = {
                'context': context.copy(),
                'domain': [('id', 'in', categoryTax)],
                'fields_names': ['name']
            }

            taxName = Taxes.search_read(argsTaxes)
            if len(taxName) > 0:
                taxName = taxName[0]['name']
            else:
                taxName = ''

            if re.search(r"[0-z]*19[0-z]*", taxName):
                product['list_price'] *= Decimal('1.19')

            elif re.search(r"[0-z]*5[0-z]*", taxName):
                product['list_price'] *= Decimal('1.05')

            product['list_price'] = round(product['list_price'], 4)
            product.pop('account_category')

        return products

    @app.get("/tables")
    async def tables(request: Request, response: Response):
        if not is_user_verified(request):
            response.status_code = 401
            return response

        Table = tryton._get('sale.table')
        args = {
            'context': context.copy(),
            'domain': [],
            'fields_names': ['id', 'name', 'busy', 'horizontal_position', 'vertical_position'],
        }
        tables = Table.search_read(args)

        Sale = tryton._get('sale.sale')
        for table in tables:
            argsSale = {
                'domain': [('table', '=', table['id']),
                    ('state', '=', 'draft')],
                'fields_names': ['id'],
            }
            saleTable = Sale.search_read(argsSale)

            if len(saleTable) > 0:
                table['sale'] = saleTable[0]['id']
            else:
                table['sale'] = None

        return tables

    @app.put("/tables/{table_id}")
    async def tables(request: Request, response: Response, table_id: int, arg: dict):
        if not is_user_verified(request):
            response.status_code = 401
            return response

        argCopy = arg.copy()
        arg = {}
        arg['values'] = argCopy
        arg['context'] = context.copy()
        arg['context']['user'] = int(
            request.headers["Authorization"].split()[1].split(':')[1])
        Table = tryton._get('sale.table')
        arg['fields_names'] = ['id', 'name', 'busy',
            'horizontal_position', 'vertical_position']
        arg['ids'] = [table_id]

        result = Table.write(arg)

        arg.pop('ids')
        if arg.get('fields_names'):
            del arg['values']
            arg['domain'] = [('id', '=', table_id)]
            result = Table.search_read(arg)

        return result[0]

    @app.get("/parties")
    async def parties(request: Request, response: Response):
        if not is_user_verified(request):
            response.status_code = 401
            return response

        Party_category = tryton._get('party.category')
        args = {
            'context': context.copy(),
            'domain': [('name', '=', 'CLIENTE')],
            'fields_names': ['id'],
        }
        category_id = Party_category.search_read(args)[0]['id']

        Party = tryton.pool.get('party.party')
        args = {
            'domain': [('categories', '=', category_id)],
            'fields_names': ['id', 'name'],
        }

        @tryton.transaction(request)
        def _get_data():
            records = Party.search_read(**args)
            return records

        res = _get_data()
        return res

    @app.get("/devices")
    async def devices(request: Request, response: Response):
        if not is_user_verified(request):
            response.status_code = 401
            return response

        Device = tryton._get('sale.device')
        args = {
            'domain': [],
            'fields_names': ['id', 'name'],
        }
        devices = Device.search_read(args)

        return devices

    @app.get("/sales")
    async def sales(request: Request, response: Response, device: int):
        if not is_user_verified(request):
            response.status_code = 401
            return response

        Sale = tryton._get('sale.sale')
        args = {
            'domain': [('state', '=', 'draft'),
               ('sale_device', '=', device)
            ],
            'fields_names': ['id', 'party', 'total_amount', 'sale_device', 'table'],
        }
        sales = Sale.search_read(args)

        SaleLine = tryton._get('sale.line')
        for sale in sales:
            argsLine = {
                'domain': [('sale', '=', sale['id'])],
                'fields_names': ['id', 'quantity', 'base_price', 'amount_w_tax', 'product', 'discount_amount'],
            }
            sale['lines'] = SaleLine.search_read(argsLine)
            for line in sale['lines']:
                if len(line) > 0:
                    if line['base_price'] == Decimal('0'):
                        line['unit_price'] = line.pop('amount_w_tax')
                        line.pop('base_price')
                        continue
                    iva = (line['amount_w_tax']) / ((line['base_price']
                           - line['discount_amount']) * Decimal(line['quantity']))
                    line['unit_price'] = line.pop('amount_w_tax')
                    line['discount_amount'] = round(
                        line['discount_amount'] * Decimal(line['quantity']) * iva, 3)
                    line.pop('base_price')

                    Stock = tryton._get('product.template')
                    stockContext = context.copy()
                    stockContext['user'] = int(
                        request.headers["Authorization"].split()[1].split(':')[1])
                    args = {
                        'context': stockContext,
                        'domain': [('salable', '=', True),
                            ('id', '=', line['product'])],
                        'fields_names': ['quantity'],
                    }

                    line['stock'] = Stock.search_read(args)[0]['quantity']

        return sales

    @app.post("/sales")
    async def create_sale(request: Request, response: Response, arg: dict):
        """
        This method create a new record from 'arg' Dict:
        ...record: Dict example, {'name': 'James Bond', 'code': '007'}
        ...context: Optional, dict of key-values including {company?, user?}
        """
        if not is_user_verified(request):
            response.status_code = 401
            return response

        user_id = int(request.headers["Authorization"].split()[
                      1].split(':')[1])

        Sale = tryton._get('sale.sale')

        if 'device' in arg:
            arg.pop('device')

        zone = None

        if 'table' in arg:
            # do table stuff
            Table = tryton._get('sale.table')
            argTable = {
                'domain': [('id', '=', arg['table'])],
                'fields_names': ['busy']
            }
            if Table.search_read(argTable)[0]['busy']:
                return JSONResponse(
                    status_code=400,
                    content={'message': 'Table is busy'}
                )

            argTable = {}
            argTable['values'] = {'busy': True}
            argTable['context'] = context.copy()
            argTable['context']['user'] = user_id
            argTable['fields_names'] = ['zone']

            argTable['ids'] = [arg['table']]

            Table.write(argTable)

            argTable.pop('ids')
            if argTable.get('fields_names'):
                del argTable['values']
                argTable['domain'] = [('id', '=', arg['table'])]
                zone = Table.search_read(argTable)[0]['zone']

        argCopy = arg.copy()
        arg = {}
        arg['record'] = argCopy

        arg['context'] = context.copy()
        arg['context']['user'] = int(
            request.headers["Authorization"].split()[1].split(':')[1])

        arg['record']['state'] = 'draft'
        arg['record']['fe_way_to_pay'] = 1  # Payments will be done in cash
        arg['record']['payment_term'] = 2  # Payments will be done in cash
        arg['record']['zone'] = zone
        arg['record']['self_pick_up'] = True
        arg['record']['shipment_method'] = 'order'

        # Find party information for the sale model
        Party = tryton.pool.get('party.party')
        argsParty = {
            'domain': [('id', '=', arg['record']['party'])],
            'fields_names': ['addresses', 'name'],
        }

        @tryton.transaction(arg)
        def _get_data():
            records = Party.search_read(**argsParty)
            return records

        parties = _get_data()

        if parties[0]['name'] == 'PUBLICO':
            arg['record']['price_list'] = 1

        arg['record']['invoice_address'] = parties[0]['addresses'][0]
        arg['record']['shipment_address'] = parties[0]['addresses'][0]

        result = Sale.create(arg)

        arg['fields_names'] = ['id', 'party',
            'total_amount', 'sale_device', 'table']

        del arg['record']
        arg['domain'] = [('id', 'in', result)]
        result = Sale.search_read(arg)[0]

        SaleLine = tryton._get('sale.line')
        argsLine = {
            'domain': [('sale', '=', result['id'])],
            'fields_names': ['id', 'quantity', 'base_price', 'amount_w_tax', 'product', 'discount_amount'],
        }
        result['lines'] = SaleLine.search_read(argsLine)
        for line in result['lines']:
            if len(line) > 0:
                if line['base_price'] == Decimal('0'):
                    line['unit_price'] = line.pop('amount_w_tax')
                    line.pop('base_price')
                    continue

                iva = (line['amount_w_tax']) / ((line['base_price']
                       - line['discount_amount']) * Decimal(line['quantity']))
                line['unit_price'] = line.pop('amount_w_tax')
                line['discount_amount'] = round(
                    line['discount_amount'] * Decimal(line['quantity']) * iva, 3)
                line.pop('base_price')

        return result

    @app.get("/sales/{sale_id}")
    async def sales(request: Request, response: Response, sale_id: int):
        if not is_user_verified(request):
            response.status_code = 401
            return response

        Sale = tryton._get('sale.sale')
        args = {
            'domain': [('id', '=', sale_id),
               # ('sale_device', '=', int(request.headers["device"]))
            ],
            'fields_names': ['id', 'party', 'total_amount', 'sale_device', 'table'],
        }
        sale = Sale.search_read(args)[0]

        SaleLine = tryton._get('sale.line')
        argsLine = {
            'domain': [('sale', '=', sale['id'])],
            'fields_names': ['id', 'quantity', 'base_price', 'amount_w_tax', 'product', 'discount_amount'],
        }
        sale['lines'] = SaleLine.search_read(argsLine)
        for line in sale['lines']:
            if len(line) > 0:
                if line['base_price'] == Decimal('0'):
                    line['unit_price'] = line.pop('amount_w_tax')
                    line.pop('base_price')
                    continue

                iva = (line['amount_w_tax']) / ((line['base_price']
                       - line['discount_amount']) * Decimal(line['quantity']))
                line['unit_price'] = line.pop('amount_w_tax')
                line['discount_amount'] = round(
                    line['discount_amount'] * Decimal(line['quantity']) * iva, 3)
                line.pop('base_price')

                Stock = tryton._get('product.template')
                stockContext = context.copy()
                stockContext['user'] = int(
                    request.headers["Authorization"].split()[1].split(':')[1])
                args = {
                    'context': stockContext,
                    'domain': [('salable', '=', True),
                        ('id', '=', line['product'])],
                    'fields_names': ['quantity'],
                }

                line['stock'] = Stock.search_read(args)[0]['quantity']

        return sale

    @app.put("/sales/{sale_id}")
    async def modify_sale(request: Request, response: Response, sale_id: int, arg: dict):
        """
        This method create a new record from 'arg' Dict:
        ...record: Dict example, {'name': 'James Bond', 'code': '007'}
        ...context: Optional, dict of key-values including {company?, user?}
        """
        if not is_user_verified(request):
            response.status_code = 401
            return response

        Sale = tryton._get('sale.sale')

        if 'table' in arg:
            # do table stuff
            Table = tryton._get('sale.table')
            argTable = {
                'domain': [('id', '=', arg['table'])],
                'fields_names': ['busy']
            }
            if Table.search_read(argTable)[0]['busy']:
                return JSONResponse(
                    status_code=400,
                    content={'message': 'Table is busy'}
                )

            argTable = {}
            argTable['values'] = {'busy': True}
            argTable['context'] = context.copy()
            argTable['context']['user'] = int(
                request.headers["Authorization"].split()[1].split(':')[1])
            argTable['fields_names'] = ['zone']

            argTable['ids'] = [arg['table']]

            Table.write(argTable)

            argTable.pop('ids')
            if argTable.get('fields_names'):
                del argTable['values']
                argTable['domain'] = [('id', '=', arg['table'])]
                zone = Table.search_read(argTable)[0]['zone']

            argsSale = {
                'domain': [('id', '=', sale_id)],
                'fields_names': ['table'],
            }
            currentTable = Sale.search_read(argsSale)[0]['table']

            if currentTable != None:
                argTable = {}
                argTable['values'] = {'busy': False}
                argTable['context'] = context.copy()
                argTable['context']['user'] = int(
                    request.headers["Authorization"].split()[1].split(':')[1])

                argTable['ids'] = [currentTable]

                Table.write(argTable)

        if 'paymentMethod' in arg:
            arg.pop('paymentMethod')

        argCopy = arg.copy()
        arg = {}
        arg['values'] = argCopy

        arg['context'] = context.copy()
        arg['context']['user'] = int(
            request.headers["Authorization"].split()[1].split(':')[1])

        arg['values']['fe_way_to_pay'] = 1

        if 'party' in arg:
            # Find party information for the sale model
            Party = tryton.pool.get('party.party')
            argsParty = {
                'domain': [('id', '=', arg.pop('party'))],
                'fields_names': ['addresses'],
            }

            @tryton.transaction(arg)
            def _get_data():
                records = Party.search_read(**argsParty)
                return records

            parties = _get_data()

            arg['values']['invoice_address'] = parties[0]['addresses'][0]
            arg['values']['shipment_address'] = parties[0]['addresses'][0]

        arg['ids'] = [sale_id]

        Sale.write(arg)

        argsSale = {
            'domain': [('id', '=', sale_id)],
            'fields_names': ['id', 'party', 'total_amount', 'sale_device', 'table'],
        }
        result = Sale.search_read(argsSale)[0]

        SaleLine = tryton._get('sale.line')
        argsLine = {
            'domain': [('sale', '=', result['id'])],
            'fields_names': ['id', 'quantity', 'base_price', 'amount_w_tax', 'product', 'discount_amount'],
        }
        result['lines'] = SaleLine.search_read(argsLine)
        for line in result['lines']:
            if len(line) > 0:
                if line['base_price'] == Decimal('0'):
                    line['unit_price'] = line.pop('amount_w_tax')
                    line.pop('base_price')
                    continue

                iva = (line['amount_w_tax']) / ((line['base_price']
                       - line['discount_amount']) * Decimal(line['quantity']))
                line['unit_price'] = line.pop('amount_w_tax')
                line['discount_amount'] = round(
                    line['discount_amount'] * Decimal(line['quantity']) * iva, 3)
                line.pop('base_price')

        return result

    @app.put("/sales/{sale_id}/success")
    async def payment_wizard(request: Request, response: Response, sale_id: int, arg: dict):
        """
        This method call class method on Tryton wizard, 'arg' is a Dict:
        ...wizard: Name of wizard, example: 'purchase.purchase'
        ...method: List of records ids to render
        ...view: Dict with values
        ...context: Optional, dict of key-values including {company?, user?}
        """
        if not is_user_verified(request):
            response.status_code = 401
            return response

        Sale = tryton._get('sale.sale')
        argsSale = {
            'domain': [('id', '=', sale_id)],
            'fields_names': ['table'],
        }
        currentTable = Sale.search_read(argsSale)[0]['table']

        if currentTable != None:
            # do table stuff
            Table = tryton._get('sale.table')

            argTable = {}
            argTable['values'] = {'busy': False}
            argTable['context'] = context.copy()
            argTable['context']['user'] = int(
                request.headers["Authorization"].split()[1].split(':')[1])

            argTable['ids'] = [currentTable]

            Table.write(argTable)

        args = {
            'domain': [('id', '=', sale_id)],
            'fields_names': ['total_amount', 'sale_device'],
        }
        saleInfo = Sale.search_read(args)[0]
        total_amount = saleInfo['total_amount']
        sale_device = saleInfo['sale_device']

        Device = tryton._get('sale.device')
        argsDevice = {
            'domain': [('id', '=', sale_device)],
            'fields_names': ['journal', 'journals'],
        }

        deviceInfo = Device.search_read(argsDevice)[0]

        journal_id = deviceInfo['journal']
        journals = deviceInfo['journals']

        if 'payment_method' in arg:
            Journal = tryton._get('account.statement.journal')
            if arg['payment_method'] == 'cash':
                argsJournal = {
                    'domain': [('id', 'in', journals),
                        ('name', 'ilike', 'Efectivo%')],
                    'fields_names': ['id'],
                }
                journal_id = Journal.search_read(argsJournal)[0]['id']

            elif arg['payment_method'] == 'transfer':
                argsJournal = {
                    'domain': [('id', 'in', journals),
                        ('name', 'ilike', 'Transferencia%')],
                    'fields_names': ['id'],
                }
                journal_id = Journal.search_read(argsJournal)[0]['id']

        view = {
            'start': {
                'journal': {'id': journal_id},
                'payment_amount': total_amount
            }
        }

        Payment = tryton._get_wizard('sale.payment')

        ctx = context.copy()
        ctx["user"] = int(
            request.headers["Authorization"].split()[1].split(':')[1])
        ctx["active_id"] = sale_id
        result = Payment.run('transition_pay_', view, ctx)

        SaleReport = tryton.pool.get('sale.sale', type='report')

        @tryton.transaction()
        def _get_data():
            _, report, _, _ = SaleReport.execute([sale_id], context.copy())

            return report

        report = _get_data()

        with tempfile.NamedTemporaryFile(
                    prefix=f'{dbname}',
                    suffix='.odt',
                    delete=False
                ) as tempOdt:
            tempOdt.write(report)
            tempOdt.close()

        with tempfile.NamedTemporaryFile(
                    prefix=f'{dbname}-',
                    suffix='.pdf',
                    delete=False
                ) as tempPdf:
            try:
                subprocess.call(['unoconv', '-f', 'pdf', '-o',
                                tempPdf.name, tempOdt.name])
            except Exception as e:
                print('Conversion failed:', str(e))

        response.headers["Content-Disposition"] = "attachment; filename=file.pdf"

        return FileResponse(tempPdf.name, media_type='application/pdf')

    @app.delete("/sales/{sale_id}")
    async def delete_sale(request: Request, response: Response, sale_id: int):
        """
        This method delete records from 'arg' Dict:
        ...model: Str for name of model, example: 'party.party'
        ...ids: List of ids of records
        ...context: Optional, dict of key-values including {company?, user?}
        """
        if not is_user_verified(request):
            response.status_code = 401
            return response

        Sale = tryton._get('sale.sale')
        argsSale = {
            'domain': [('id', '=', sale_id)],
            'fields_names': ['table'],
        }
        currentTable = Sale.search_read(argsSale)[0]['table']

        if currentTable != None:
            # do table stuff
            Table = tryton._get('sale.table')

            argTable = {}
            argTable['values'] = {'busy': False}
            argTable['context'] = context.copy()
            argTable['context']['user'] = int(
                request.headers["Authorization"].split()[1].split(':')[1])

            argTable['ids'] = [currentTable]

            Table.write(argTable)

        arg = {}

        arg['context'] = context.copy()
        arg['context']['user'] = int(
            request.headers["Authorization"].split()[1].split(':')[1])
        arg['ids'] = [sale_id]

        result = Sale.delete(arg)
        return result

    @app.post("/sales/{sale_id}/line")
    async def create_sale_line(request: Request, response: Response, sale_id: int, arg: dict):
        """
        This method create a new record from 'arg' Dict:
        ...record: Dict example, {'name': 'James Bond', 'code': '007'}
        ...context: Optional, dict of key-values including {company?, user?}
        """
        # print(request.headers['Authorization'])
        if not is_user_verified(request):
            response.status_code = 401
            return response

        SaleLine = tryton._get('sale.line')

        arg['context'] = context.copy()
        # print(arg['context'])
        # sleep(5)
        arg['context']['user'] = int(
            request.headers["Authorization"].split()[1].split(':')[1])

        arg['record'] = {
                'type': 'line',
                'quantity': arg.pop('quantity'),
                'product': arg.pop('product'),
        }
        arg['record']['sale'] = sale_id

        # Find the product information for the Sale Line model
        Product = tryton._get('product.template')
        argsProduct = {
            'context': context.copy(),
            'domain': [('id', '=', arg['record']['product']),
                       ('salable', '=', True)],
            'fields_names': ['sale_uom', 'account_category', 'list_price'],
        }
        products = Product.search_read(argsProduct)[0]

        arg['record']['unit'] = products['sale_uom']

        Sale = tryton._get('sale.sale')
        argsSale = {
            'domain': [('id', '=', sale_id)],
            'fields_names': ['party'],
        }
        party_id = Sale.search_read(argsSale)[0]['party']

        Party = tryton.pool.get('party.party')
        argsParty = {
            'domain': [('id', '=', party_id)],
            'fields_names': ['name'],
        }

        @tryton.transaction(arg)
        def _get_data():
            records = Party.search_read(**argsParty)
            return records

        parties = _get_data()

        base_price = products['list_price']
        unit_price = products['list_price']

        if parties[0]['name'] == 'PUBLICO':
            base_price *= round(Decimal(1.1), 4)
            unit_price *= round(Decimal(1.1), 4)

        if 'unit_price' in arg:
            arg.pop('unit_price')

         # Encontrar la categoria contable con sus impuestos
        Category = tryton._get('product.category')
        argsCategory = {
            'context': context.copy(),
            'domain': [('id', '=', products['account_category'])],
            'fields_names': ['customer_taxes']
        }

        categoryTaxes = Category.search_read(
            argsCategory)[0]['customer_taxes'][0]

        AccountTaxes = tryton._get('account.tax')
        argsAccountTaxes = {
            'context': context.copy(),
            'domain': [('id', '=', categoryTaxes)],
            'fields_names': ['name']
        }

        taxName = AccountTaxes.search_read(argsAccountTaxes)
        if len(taxName) > 0:
            taxName = taxName[0]['name']
        else:
            taxName = ''

        discount = 0
        if 'discount_amount' in arg:
            if arg['discount_amount'] != None:
                discount = arg['discount_amount']
            arg.pop('discount_amount')

        if re.search(r"[0-z]*19[0-z]*", taxName) and discount >= 1:
            discount /= 1.19

        elif re.search(r"[0-z]*5[0-z]*", taxName) and discount >= 1:
            discount /= 1.05

        if discount >= 1:
            discount /= arg['record']['quantity']
            unit_price = round(base_price - Decimal(discount), 4)
        else:
            unit_price = round(base_price * Decimal(1 - discount), 4)

        arg['record']['base_price'] = base_price
        arg['record']['unit_price'] = unit_price

        result = SaleLine.create(arg)[0]

        argsLine = {
            'domain': [('id', '=', result)],
            'fields_names': ['id', 'quantity', 'product', 'base_price', 'discount_amount', 'amount_w_tax'],
        }
        result = SaleLine.search_read(argsLine)[0]

        # print(result)
        # sleep(5)
        # Cargar el modelo que contiene los impuestos
        Taxes = tryton._get('sale.line-account.tax')

        # Argumentos para busqueda de impuestos
        argsTaxes = {
            'context': context.copy(),
            'domain': [],
            'record': {
                'line': result['id'],
                'tax': categoryTaxes
            }
        }
        taxes = Taxes.create(argsTaxes)

        line = SaleLine.search_read(argsLine)[0]
        if line['base_price'] == Decimal('0'):
            line['unit_price'] = line.pop('amount_w_tax')
            line.pop('base_price')
        else:
            iva = (line['amount_w_tax']) / ((line['base_price']
                   - line['discount_amount']) * Decimal(line['quantity']))
            line['unit_price'] = line.pop('amount_w_tax')
            line['discount_amount'] = round(
                line['discount_amount'] * Decimal(line['quantity']) * iva, 3)
            line.pop('base_price')

        # ProductSaleContext = tryton._get('product.sale.context')

        response.status_code = 201

        return line

    @app.put("/sales/{sale_id}/line/{line_id}")
    async def update_sale_line(request: Request, response: Response, sale_id: int, line_id: int, arg: dict):
        """
        This method call class method on Tryton wizard, 'arg' is a Dict:
        ...wizard: Name of wizard, example: 'purchase.purchase'
        ...method: List of records ids to render
        ...view: Dict with values
        ...context: Optional, dict of key-values including {company?, user?}
        """
        if not is_user_verified(request):
            response.status_code = 401
            return response

        SaleLine = tryton._get('sale.line')
        argsLine = {
            'domain': [('id', '=', line_id)],
            'fields_names': ['product'],
        }
        product = SaleLine.search_read(argsLine)[0]['product']

        Product = tryton._get('product.template')
        argsProduct = {
            'context': context.copy(),
            'domain': [('id', '=', product),
                       ('salable', '=', True)],
            'fields_names': ['account_category', 'list_price'],
        }
        productInfo = Product.search_read(argsProduct)[0]

        Category = tryton._get('product.category')
        argsCategory = {
            'context': context.copy(),
            'domain': [('id', '=', productInfo['account_category'])],
            'fields_names': ['customer_taxes']
        }
        categoryTaxes = Category.search_read(
            argsCategory)[0]['customer_taxes'][0]

        AccountTaxes = tryton._get('account.tax')
        argsAccountTaxes = {
            'context': context.copy(),
            'domain': [('id', '=', categoryTaxes)],
            'fields_names': ['name']
        }
        taxName = AccountTaxes.search_read(argsAccountTaxes)

        Sale = tryton._get('sale.sale')
        argsSale = {
            'domain': [('id', '=', sale_id)],
            'fields_names': ['party'],
        }
        party_id = Sale.search_read(argsSale)[0]['party']

        Party = tryton.pool.get('party.party')
        argsParty = {
            'domain': [('id', '=', party_id)],
            'fields_names': ['name'],
        }

        @tryton.transaction(arg)
        def _get_data():
            records = Party.search_read(**argsParty)
            return records

        parties = _get_data()

        base_price = productInfo['list_price']
        unit_price = productInfo['list_price']

        if parties[0]['name'] == 'PUBLICO':
            base_price *= round(Decimal(1.1), 4)
            unit_price *= round(Decimal(1.1), 4)

        if len(taxName) > 0:
            taxName = taxName[0]['name']
        else:
            taxName = ''

        discount = 0
        if 'discount_amount' in arg:
            if arg['discount_amount'] != None:
                discount = arg['discount_amount']
            arg.pop('discount_amount')

        if re.search(r"[0-z]*19[0-z]*", taxName) and discount >= 1:
            discount /= 1.19

        elif re.search(r"[0-z]*5[0-z]*", taxName) and discount >= 1:
            discount /= 1.05

        if discount >= 1:
            discount /= arg['quantity']
            unit_price = round(base_price - Decimal(discount), 4)
        else:
            unit_price = round(base_price * Decimal(1 - discount), 4)

        argCopy = arg.copy()
        arg = {}
        arg['values'] = argCopy

        arg['values']['base_price'] = base_price
        arg['values']['unit_price'] = unit_price

        SaleLine = tryton._get('sale.line')

        arg['context'] = context.copy()
        arg['context']['user'] = int(
            request.headers["Authorization"].split()[1].split(':')[1])
        arg['ids'] = [line_id]

        try:
            SaleLine.write(arg)
            argsLine = {
                'domain': [('id', '=', line_id)],
                'fields_names': ['id', 'quantity', 'base_price', 'amount_w_tax', 'product', 'discount_amount'],
            }
            line = SaleLine.search_read(argsLine)[0]
            if line['base_price'] == Decimal('0'):
                line['unit_price'] = line.pop('amount_w_tax')
                line.pop('base_price')
            else:
                iva = (line['amount_w_tax']) / ((line['base_price']
                       - line['discount_amount']) * Decimal(line['quantity']))
                line['unit_price'] = line.pop('amount_w_tax')
                line['discount_amount'] = round(
                    line['discount_amount'] * Decimal(line['quantity']) * iva, 3)
                line.pop('base_price')

            result = line

        except:
            result = f"Sale Line with id {line_id} not found"

        return result

    @app.delete("/sales/{sale_id}/line/{line_id}")
    async def delete_saleLine(request: Request, response: Response, sale_id: int, line_id: int):
        """
        This method delete records from 'arg' Dict:
        ...model: Str for name of model, example: 'party.party'
        ...ids: List of ids of records
        ...context: Optional, dict of key-values including {company?, user?}
        """
        if not is_user_verified(request):
            response.status_code = 401
            return response

        arg = {}

        SaleLine = tryton._get('sale.line')

        arg['context'] = context.copy()
        arg['context']['user'] = int(
            request.headers["Authorization"].split()[1].split(':')[1])
        arg['ids'] = [line_id]

        try:
            SaleLine.delete(arg)
            result = f"Sale Line with id {line_id} deleted"
        except:
            result = f"Sale Line with id {line_id} not found"

        return result

    @app.get("/sales/{sale_id}/print")
    async def sale_print(request: Request, response: Response, sale_id: int):
        if not is_user_verified(request):
            response.status_code = 401
            return response

        SaleReport = tryton.pool.get('sale.sale', type='report')

        @tryton.transaction()
        def _get_data():
            _, report, _, _ = SaleReport.execute([sale_id], context.copy())

            return report

        report = _get_data()

        with tempfile.NamedTemporaryFile(
                    prefix=f'{dbname}',
                    suffix='.odt',
                    delete=False
                ) as tempOdt:
            tempOdt.write(report)
            tempOdt.close()

        with tempfile.NamedTemporaryFile(
                    prefix=f'{dbname}-',
                    suffix='.pdf',
                    delete=False
                ) as tempPdf:
            try:
                subprocess.call(['unoconv', '-f', 'pdf', '-o',
                                tempPdf.name, tempOdt.name])
                # print('Conversion successful.')
            except Exception as e:
                print('Conversion failed:', str(e))

        response.headers["Content-Disposition"] = "attachment; filename=file.pdf"

        return FileResponse(tempPdf.name, media_type='application/pdf')

    @app.get("/cities")
    async def cities():
        City = tryton._get('party.city_code')
        args = {
            'domain': [],
            'limit': 17,
            'fields_names': ['id', 'name', 'code'],
        }
        cities = City.search_read(args)
        return cities

    @app.post("/create")
    async def create(arg: dict):
        """
        This method create a new record from 'arg' Dict:
        ...model: Str for name of model, example: 'party.party'
        ...record: Dict example, {'name': 'James Bond', 'code': '007'}
        ...context: Optional, dict of key-values including {company?, user?}
        """
        Model = tryton._get(arg.pop('model'))
        result = Model.create(arg)
        if arg.get('fields_names'):
            del arg['record']
            arg['domain'] = [('id', 'in', result)]
            result = Model.search_read(arg)
        return result

    @app.post("/search")
    async def search(arg: dict):
        """
        This method search records from 'arg' Dict:
        ...model: Str for name of model, example: 'res.user'
        ...domain: String (As Tryton domain)
        ...fields_names: List, example, ['name', 'login', ...]
        ...offset: Integer --Optional If offset or limit are set, the result starts at the offset and has the length of the limit
        ...limit: Integer --Optional
        ...order: Tuple/List, example ('create_date', 'ASC') --Optional
        ...context: Optional, dict of key-values including {company?, user?}
        """
        Model = tryton._get(arg.pop('model'))
        domain = arg.get('domain', [])
        if isinstance(domain, str):
            domain = eval(domain)

        arg['domain'] = domain
        result = Model.search_read(arg)
        return result

    @app.post("/search_count")
    async def search_count(arg: dict):
        """
        This method search records from 'arg' Dict:
        ...model: Str for name of model, example: 'res.user'
        ...domain: String (As Tryton domain)
        ...context: Optional, dict of key-values including {company?, user?}
        """
        Model = tryton._get(arg.pop('model'))
        domain = arg.get('domain', [])
        if isinstance(domain, str):
            domain = eval(domain)

        arg['domain'] = domain
        result = Model.search_count(arg)
        return result

    @app.post("/write")
    async def write(arg: dict):
        """
        This method write records from 'arg' Dict:
        ...model: Str for name of model, example: 'party.party'
        ...ids: List ids of records
        ...values: Dict example, {'name': 'James Bond', 'code': '007'}
        ...context: Optional, dict of key-values including {company?, user?}
        ...files: Optional, dict of name_field and content bytes base64
        """
        Model = tryton._get(arg.pop('model'))
        if arg['values'].get('files'):
            dict_files = get_dict_binaries(arg['values'].pop('files'))
            arg['values'].update(dict_files)
        result = Model.write(arg)
        return result

    @app.post("/browse")
    async def browse(arg: dict):
        """
        This method return records from ids from 'arg' Dict:
        ...model: Str for name of model, example: 'party.party'
        ...ids: List ids of records
        ...fields_names: List, example, ['name', 'code', ...]
        ...context: Optional, dict of key-values including {company?, user?}
        """
        Model = tryton._get(arg.pop('model'))
        result = Model.browse(arg)
        return encode(result)

    @app.post("/delete")
    async def delete(arg: dict):
        """
        This method delete records from 'arg' Dict:
        ...model: Str for name of model, example: 'party.party'
        ...ids: List of ids of records
        ...context: Optional, dict of key-values including {company?, user?}
        """
        Model = tryton._get(arg.pop('model'))
        result = Model.delete(arg)
        return result

    @app.post("/button_method")
    async def button_method(arg: dict):
        """
        This method call trigger method/button on Tryton model 'arg' Dict:
        ...model: Str for name of model, example: 'sale.sale'
        ...method: String, Example 'quote'
        ...ids: List of ids
        ...context: Optional, dict of key-values including {company?, user?}
        """
        Model = tryton._get(arg.pop('model'))
        result = Model.button_method(arg)
        return result

    @app.post("/method")
    async def method(arg: dict):
        """
        This method call class method on Tryton model 'arg' Dict:
        ...model: Str for name of model, example: 'party.party'
        ...method: String
        ...args: Dict values variables
        ...context: Optional, dict of key-values including {company?, user?}
        """
        Model = tryton._get(arg.pop('model'))
        result = Model.method(arg)
        return result

    @app.post("/method_instance")
    async def method_instance(arg: dict):
        """
        This method call class method on Tryton model 'arg' Dict:
        ...model: Str for name of model, example: 'party.party'
        ...method: String
        ...instance: int or dict
        ...args: Dict values variables
        ...kwargs: list variables
        ...context: Optional, dict of key-values including {company?, user?}
        """
        Model = tryton._get(arg.pop('model'))
        result = Model.method_instance(arg)
        return result

    @app.post("/fields_get")
    async def fields_get(arg: dict):
        """
        This method call the fields in views on Tryton model 'arg' Dict:
        ...model: Str for name of model, example: 'party.party'
        ...fields_names: List values fields names
        ...context: Optional, dict of key-values including {company?, user?}
        """
        Model = tryton._get(arg.pop('model'))
        result = Model.fields_get(arg)
        return result

    @app.post("/report")
    async def report(arg: dict):
        """
        This method call class method on Tryton report, 'arg' is a Dict:
        ...report: Name of report, example: 'purchase.purchase'
        ...records: List of records ids to render
        ...data: Dict with values
        ...context: Optional, dict of key-values including {company?, user?}
        """
        report = tryton._get_report(arg.pop('report'))
        ctx = arg.get('context', {})
        data = arg.get('data', {})
        records = arg.get('records', [])
        oext, content, direct_print, name = report.execute(records, data, ctx)
        result = {
            'name': name,
            'oext': oext,
            'content': content,
            'direct_print': direct_print,
        }
        return result

    @app.post("/wizard")
    async def wizard(arg: dict):
        """
        This method call class method on Tryton wizard, 'arg' is a Dict:
        ...wizard: Name of wizard, example: 'purchase.purchase'
        ...method: List of records ids to render
        ...view: Dict with values
        ...context: Optional, dict of key-values including {company?, user?}
        """
        method = arg.get('method')
        view = arg.get('view')
        ctx = arg.get('context', {})
        Wizard = tryton._get_wizard(arg.pop('wizard'))
        result = Wizard.run(method, view, ctx)
        return result

    # This return all app
    return app
