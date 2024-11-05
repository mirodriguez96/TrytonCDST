# PREDASH API

This guide show how config API Fast in server

## Get Started

### Configuration FastAPI Tryton enviroment

#### Create a config file

In Home you must create a new file for example in '/home/user/.fastapi':

```
nano /home/user/.fastapi/api-fast.ini

```

#### Add General Section information

Add all info required.

```
[General]
databases=['MYDB']
host=0.0.0.0
trytond_config=/home/user/.trytond/trytond.conf
```

#### Add Auth Section (Optional)

Add api_key and secret section if you want share API with parties.

```
[Auth]
api_key=XXXXXXXXXXXXXXXXXXXXXXX
secret_key=mysupersecretkey
user=admin
```

#### Activate SSL (Optional)

Creating Private Key and Certificate, so in console type:

```
openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365

```

Next add this section:

```
[SSL]
cert_file = /home/user/.fastapi/cert.pem
key_file = /home/user/.fastapi/key.pem
```

#### Activate CORS

```
# add domain with first item list
[CORS]
origins = ["http://localhost", "http://localhost:3100", "http://localhost:3100/login"] 
```

## Endpoints

## Test Running server using uWSGI

gunicorn -c gun_config.py wsgi:app

## Example connection to API

```

import logging
import requests
import simplejson as json

# The port is 8010 by default
api_url = 'localhost:8010'
database = 'MYDATABASE'

api = '/'.join(['http:/', api_url, database])
ctx = {
    'company': 1,
    'user': 1,
}

args_ = {
    'model': 'party.party',
    'domain': '[
      ('city', '!=', '15'),
    ]',
    'order': None,
    'limit': 13,
    'fields': ['name', 'id_number'], # Here you can add more fields
    'context': ctx,
}

data = json.dumps(args_)

# Test for search
route = api + '/search'
result = requests.post(route, data=data)

for r in result.json():
    print(r)

```

## Endpoints

# Context

Context is a dict with next keys:

company: id
user: id

#### Search

This route return a query as Select, as List of dicts (records) :

```
uri: /DB/search
type: POST

args_ = {
    'model': 'mymodel',  # ex, 'gnuhealth.inpatient'
    'domain': 'domain', # optional : see tryton docs
    'fields': ['field1', 'field2', ...]
    'order': number,  # optional
    'limit': limit, # optional
    'context': ctx, # Context Dict object
}

```

#### Create

This route is used for a create a record (just one), return created record data:

```

uri: /DB/create
type: POST

args = {
    'model': 'mymodel',
    'record': {field1: value, field2: value}, # Dict
    'context': ctx, # Context Dict object
}


```

#### Write / Save

This route is used for a modify a record (just one), return updated record data as Dict:

```

uri: /DB/save
type: PUT

args = {
    'model': 'mymodel',
    'record': {field1: value, field2: value}, # Dict
    'context': ctx, # Context Dict object
}

```

#### Write / Save

This route is used for a modify a record (just one), return updated record data as Dict:

```

uri: /DB/save
type: PUT

args = {
    'model': 'mymodel',
    'record': {field1: value, field2: value}, # Dict
    'context': ctx, # Context Dict object
}

```
