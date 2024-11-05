# Main file for FastAPI server
import sys
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from api import create_app
from tools import get_config
from version import version

config = get_config()
databases = list(eval(config.get('General', 'databases')))
trytond_config = config.get('General', 'trytond_config')

app = FastAPI()

origins = list(eval(config.get('CORS', 'origins')))
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

print('Python version: ', sys.version)
print('API version: ', version)


for db in databases:
    print('Starting API-fast for...', db)
    try:
        apiv1 = create_app(db, trytond_config)
        app.mount(f'/{db}/', apiv1)
        app.mount(f'/api/{db}', apiv1)
    except Exception as e:
        print(e)


@app.get("/api")
async def root(request: Request):
    return {"message": "Hi, FastAPI is working...!"}

@app.get("/api/warehouses")
async def warehouses(request: Request):
    warehouses = []
    for db in databases:
        warehouses.append({
            "id":str(databases.index(db)),
            "name": db
        })

    return warehouses
