# TRYTON INSTALL API

Esta guia describe los métodos para conectarse a la API de Tryton,
creada por Presik SAS.

## Dependences

Install next libraries:

    sudo apt install build-essential
    sudo apt install python3-dev
    sudo apt install libpq-dev
    sudo apt install uvicorn

    pip3 install uvicorn
    pip3 install fastapi
    pip3 install fastapi_tryton
    pip3 install orjson

## Configuration

Create a directory in home called ".fastapi" in Home, for add configuration files.

    mkdir ~/.fastapi

Enter in api-fast directory and copy file api-fast.ini to .fastapi directory

    cp api-fast.ini ~/.fastapi/api-fast.ini

Edit api-fast.ini and adjust for your company, database, etc.

Test uvicorn is installed starting app from terminal, inside fastapi
directory, (inside virtualenv):

      uvicorn main:app --reload --port 8010

Create api-fast.service file for systemd:

    sudo nano /etc/systemd/system/api-fast.service

Add this text to the api-fast.service file, don't forget to change "User" and
path to "WorkingDirectory" directory

---

# Script Server Presik API Technologies

[Unit]
Description=API Fast Server
After=network.target

[Service]
User=XXXXX
WorkingDirectory=/home/psk/predash/api-fast
ExecStart=/home/psk/.virtualenvs/tryton60/bin/uvicorn main:app --reload --port 8010
#ExecStop=

[Install]
WantedBy=multi-user.target

---

Enable the service

    sudo systemctl enable api-fast.service

Start the service

    sudo systemctl start api-fast.service

Check status

    sudo systemctl status api-fast.service
