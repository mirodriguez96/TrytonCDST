import requests
import orjson as json

# The port is 8010 by default
api_url = '0.0.0.0:8010'
database = 'tryton'

api = '/'.join(['http:/', api_url, database])
ctx = {
    "company": 1,
    "user": 1,
    # "token": "e840ff064a4c46f9a307e07f28283273ae9fefb011af42ec88f91f2a1b907926d592b0532c87438e8c302d22d74cec7ad251ae30687647ae9659f2a09c585ba9"
}

def test_get():
    route = api + '/sales'
    body = False
    return route, body

def test_create_sale():
    body = {
        'user': 1,
        # 'company': 1,
        'record': {
            'sale_date': '2023-12-25',
            'party': 1,
            'state': 'draft',
            'number': 2,
            'company': 1,
            'shop': 1,
        },
    }
    route = api + '/sales'
    return route, body

def test_delete_sale():
    body = {
        'user': 1,
    }
    route = api + '/sales/14'
    return route, body
    
def test_create_sale_product():
    body = {
        'user': 1,
        'record': {
            'type': 'line',
            'quantity': 1,
            'unit_price': 30000,
            'product': 1,
        }
    }
    route = api + '/sales/15/line'
    return route, body

def test_write_sale_line():
    body = {
        'user': 1,
        'values': {
            'quantity': 12,
        }
    }
    route = api + '/sales/15/line/59'
    return route, body

def test_delete_sale_product():
    body = {
        'user': 1,
    }
    route = api + '/sale/15/line/100'
    return route, body

def test_login():
    body = {
        "method": "common.db.login",
        "params": [
            "soporte",
            {"device_cookie": None, "password": 'xxxxxxx'},
            "es",
        ],
        "id": 0,
        "context": {},
    }
    route = api + '/login'
    return route, body


def test_write():
    body = {
        'model': 'party.party',
        'context': ctx,
        'ids': [7183],
        'values': {
            'name': 'Abad Arturo Escalante'.upper(),
            'code': '007',
            'id_number': '8096251521',
            'type_document': '13',
            'type_person': 'persona_natural',
        }
    }
    route = api + '/write'
    return route, body


def test_create():
    body = {
        'model': 'party.party',
        'context': ctx,
        'record': {
            'name': 'Carolina Casta\u00f1o ',
            'code': '007',
            'id_number': '8096251521',
            'type_document': '13',
            'type_person': 'persona_natural',
        }
    }
    route = api + '/create'
    return route, body


def test_search():
    body = {
        'model': 'sale.sale',
        'context': ctx,
        'domain': [],
        'limit': 500,
        'fields_names': ['id', 'shop', 'company'],
    }
    route = api + '/search'
    return route, body

def test_search_line():
    body = {
        'model': 'sale.line',
        'context': ctx,
        'domain': [],
        'limit': 500,
        'fields_names': ['id', 'company', 'taxes'],
    }
    route = api + '/search'
    return route, body

def test_delete():
    body = {
        'model': 'party.party',
        'context': ctx,
        'ids': [8254]
    }
    route = api + '/delete'
    return route, body


def test_button_method():
    body = {
        'model': 'sale.sale',
        'context': ctx,
        'method': 'quote',
        'ids': [58310],
    }
    route = api + '/button_method'
    return route, body


def test_search_purchases():
    body = {
        'model': 'purchase.purchase',
        'context': ctx,
        'domain': [],
        'limit': 500,
        'fields_names': [
            'id', 'number', 'reference', 'purchase_date', 'state',
            'party.name'
        ],
    }
    route = api + '/search'
    return route, body


def test_wizard():
    body = {
        "context": {
            "company": 1,
            "user": 1
        },
        "wizard": "staff.payroll_group",
        "method": "transition_open_",
        "view": {
            "start": {
                "period": {
                    "id": 4
                },
                "department": {
                    "id": 1
                },
                "description": "PAYROLL DEC. 2022",
                "company": {
                    "id": 1
                },
                "employees": [{'id': 7}, {'id': 9}],
                "start_extras": None,
                "end_extras": None,
                "wage_types": None,
            }
        }
    }
    route = api + '/wizard'
    return route, body

def test_wizard_pay():
    body = {
        "user": 1,
        "view": {
            "start": {
                "journal": {
                    "id": 1
                },
                "payment_amount": 40000,
            },
            'fields': [],
        }
    }
    route = api + '/sales/16/success'
    return route, body


if __name__ == "__main__":
    from timeit import default_timer as timer
    start = timer()

    route, body = test_get()
    #route, body = test_search_line()
    #route, body = test_create_sale()
    #route, body = test_create_sale_product()
    #route, body = test_write_sale_line()
    #route, body = test_delete_sale_product()
    #route, body = test_delete_sale()
    #route, body = test_wizard_pay()
    
    print('route > ', route)
    if body:
        data = json.dumps(body)
        #result = requests.post(route, data=data)
        result = requests.get(route, data=data)
        #result = requests.delete(route, data=data)
    else:
        result = requests.get(route)

    values = result.json()
    end = timer()

    if isinstance(values, dict):
        for k, v in values.items():
            print(k, ' : ', v)
    elif isinstance(values, list):
        for v in values:
            print('-' * 110)
            print(v)
    else:
        print(values)
    print('total records: ', len(values))
    print('time elapsed:', end-start)
    # print('time elapsed:', timedelta(seconds=end-start))
