#!/usr/bin/python
#! -*- coding: utf8 -*-
import json
from . builder_phase import ElectronicPayroll
from .builder_phase2 import ElectronicInvoice_2
import requests
import base64

class ElectronicPayrollCdst(object):

    def __init__(self, payroll, config):
        self.payroll = payroll
        self.config = config
        #self.dic_payroll = None
        self._create_electronic_payroll_phase()

    def _create_electronic_payroll_phase(self):
        ec_payroll = ElectronicPayroll(self.payroll, self.config)
        #Validamos que el tipo de Nomina sea correcto
        if self.payroll.payroll_type != '102' and self.payroll.payroll_type != '103':
            self.payroll.get_message("Wrong payroll type for supplier it.")

        if ec_payroll.status != 'ok':
            self.payroll.get_message(ec_payroll.status)
        json_payroll = ec_payroll.make(self.payroll.payroll_type)
        data = json.dumps(json_payroll, indent=4)
        #print(data)
        self._send_noova(data)


    # Consumo API noova
    def _send_noova(self, data):
        #Validamos que los datos del proveedor tecnologico este completo
        if self.payroll.company.url_supplier and self.payroll.company.auth_supplier and self.payroll.company.host_supplier and self.payroll.company.supplier_code:
            #Se valida en que entorno (prueba o producción) se va ha enviar la nómina
            url = self.payroll.company.url_supplier
            auth = self.payroll.company.auth_supplier
            host = self.payroll.company.host_supplier
        else:
            self.payroll.get_message('Missing fields in company | supplier it')
        auth = auth.encode('utf-8')
        auth = base64.b64encode(auth)
        auth = auth.decode('utf-8')
        #Se crea el encabezado que se enviara al proveedor it
        header = {
            'Authorization': 'Basic '+auth,
            'Content-Type': 'application/json',
            'Host': host,
            'Content-Length': '967',
            'Expect': '100-continue',
            'Connection': 'Keep-Alive'
        }
        response = requests.post(url, headers=header, data=data)
        print(response.text)
        if response.status_code == 200:
            res = json.loads(response.text)
            #print(res)
            self.payroll.xml_payroll = data.encode('utf8')
            electronic_state = 'rejected'
            if res['Result'] == 0 and res['State'] == 'Exitosa':
                electronic_state = 'authorized'
            self.payroll.electronic_state = electronic_state
            self.payroll.cune = res['Cune']
            self.payroll.electronic_message = res['State']
            if res['Result'] == 1:
                self.payroll.electronic_message = res['Description']
            if res['ErrorList']:
                self.payroll.rules_fail = res['ErrorList']
            self.payroll.save()
            print("ENVIO EXITOSO DE NOMINA")
        else:
            self.payroll.get_message(response.text)


class SendElectronicInvoice(object):

    def __init__(self, invoice, auth):
        self.invoice = invoice
        self.auth = auth
        self._create_support_document_phase()

    def _create_support_document_phase(self):
        ec_invoice = ElectronicInvoice_2(self.invoice, self.auth)
        # Validamos que el tipo de factura sea correcto
        if self.invoice.invoice_type != '05' and self.invoice.invoice_type != '95':
            self.invoice.get_message("Wrong invoice type for supplier it.")
        if ec_invoice.status != 'ok':
            self.invoice.get_message(ec_invoice.status)
        json_ = ec_invoice.make(self.invoice.invoice_type)
        data = json.dumps(json_, indent=4)
        print(data)
        self._send_noova(data)


    # Consumo API noova
    def _send_noova(self, data):
        url = self.invoice.company.url_ds_itsupplier
        auth = self.invoice.company.auth_ds_itsupplier
        host = self.invoice.company.host_ds_itsupplier
        #Validamos que los datos del proveedor tecnologico este completo
        if not url or not auth or not host:
            self.invoice.get_message('Missing fields in company | supplier it')
        auth = auth.encode('utf-8')
        auth = base64.b64encode(auth)
        auth = auth.decode('utf-8')
        #Se crea el encabezado que se enviara al proveedor it
        header = {
            'Authorization': 'Basic '+auth,
            'Content-Type': 'application/json',
            'Host': host,
            'Content-Length': '967',
            'Expect': '100-continue',
            'Connection': 'Keep-Alive'
        }
        response = requests.post(url, headers=header, data=data)
        print(response.text)
        if response.status_code == 200:
            res = json.loads(response.text)
            #print(res)
            self.invoice.xml_face_ = data.encode('utf8')
            electronic_state = 'rejected'
            if res['Result'] == 0 and res['State'] == 'Exitosa':
                electronic_state = 'authorized'
            self.invoice.electronic_state = electronic_state
            self.invoice.cufe = res['Cufe']
            self.invoice.electronic_message = res['State']
            if res['Result'] == 1:
                self.invoice.electronic_message = res['Description']
            if res['ErrorList']:
                self.invoice.rules_fail = res['ErrorList']
            self.invoice.save()
            print("ENVIO EXITOSO DE NOMINA")
        else:
            self.invoice.get_message(response.text)
