#from functools import partial
#from decimal import Decimal
from datetime import date

CLASIFICATION_TAX = {
    '01': 'IVA',
    '02': 'IC',
    '03': 'ICA',
    '04': 'INC',
    '05': 'ReteIVA',
    '06': 'ReteFuente',
    '07': 'ReteICA',
    '20': 'FtoHorticultura',
    '21': 'Timbre',
    '22': 'Bolsas',
    '23': 'INCarbono',
    '24': 'INCombustibles',
    '25': 'Sobretasa Combustibles',
    '26': 'Sordicom',
    'ZZ': 'Otro',
    'NA': 'No Aceptada',
    'renta': 'renta',
    'autorenta': 'autorenta',
    }

TAXES_CODE_VALID = [key for key in CLASIFICATION_TAX.keys() if key.isdigit()]

TYPE_PERSON = {
    'persona_juridica': '1',
    'persona_natural': '2',
}

FISCAL_REGIMEN = {
    '48': 'RESPONSABLE DE IMPUESTO SOBRE LAS VENTAS – IVA',
    '49': 'NO RESPONSABLE DE IVA',
}

ENVIRONMENT = {
    '1': 'Produccion',
    '2': 'Pruebas',
}

INVOICE_CODES = {
    1: 'venta',
}

MESSAGES = {
    'software_id': 'Falta ID del software Facturador',
    'company_id': 'Falta numero NIT de la empresa',
    #'company_registration': 'Falta la matricula mercantil de la empresa',
    'company_name': 'Falta el nombre de la empresa',
    #'company_email': 'Falta el email de la empresa',
    'company_phone': 'Falta el teléfono o celular de la empresa',
    'company_city': 'Falta la ciudad de la empresa',
    'company_city_code': 'Falta la ciudad de la empresa',
    'company_address': 'Falta la direccion de la empresa',
    'company_country_code': 'Falta el pais de la empresa',
    'company_department': 'Falta el departamento de la empresa',
    'company_department_code': 'Falta el departamento de la empresa',
    'company_ciiu_code': 'Falta el codigo CIIU en el tercero de la empresa',
    'company_postal_zone': 'Falta el codigo Postal en el tercero de la empresa',
    'company_type_id': 'Falta el tipo de documento que identifica a la compañía',
    'fiscal_regimen_company': 'Falta el Regimen Fiscal del tercero de la compañia',
    'company_tax_level_code': 'Falta el Regimen de Impuestos del tercero de la compañia',
    'currency': 'Falta el codigo de la moneda',
    'party_name': 'Falta el nombre del cliente',
    'party_id': 'Falta el id del cliente',
    'party_address': 'Falta la direccion del cliente',
    'party_country_code': 'Falta el pais del cliente',
    'party_department_code': 'Falta el departamento del cliente',
    'party_city_code': 'Falta la ciudad del cliente',
    'issue_date': 'Falta la fecha de factura',
    'party_country_name': 'Falta el pais del cliente',
    'party_department': 'Falta el departmento del cliente',
    'party_city': 'Falta la ciudad del cliente',
    'party_phone': 'Falta el telefono del cliente',
    'party_email': 'Falta el correo del cliente',
    'party_type_id': 'Falta el tipo de documento que identifica al cliente',
    'party_tax_level_code': 'Falta definir el tipo de persona juridica / natural del cliente',
    'payment_term': 'Falta el metodo de pago',
    'fiscal_regimen_party': 'Falta el Regimen Fiscal del cliente',
    'invoice_authorization': 'El campo Autorización de factura esta vacio',
    'operation_type': 'El campo Tipo de Operación de factura esta vacio',
    'invoice_type_code': 'El campo Tipo de Factura de factura esta vacio',
    'payment_type': 'Falta el tipo de concepto en el plazo de pago de la factura',
    #'company_tributes': 'Falta definir el grupo de tributos de impuesto al que es responsable la compañía',
}


def rvalue(value):
    # value = str(abs(value))
    # return value[:value.find('.') + 3]
    return str(round(abs(value), 2))


def tax_valid(tax):
    rate = hasattr(tax, 'rate')
    fixed = hasattr(tax, 'fixed')
    code = tax.classification_tax
    if code in TAXES_CODE_VALID and (rate and rate > 0 or fixed and fixed > 0):
        return True
    return False

def tax_valid_witholding(tax):
    rate = hasattr(tax, 'rate')
    fixed = hasattr(tax, 'fixed')
    code = tax.classification_tax
    if code and code != 'NA' and (rate and rate < 0 or fixed and fixed < 0):
        return True
    return False


class ElectronicInvoice_2(object):

    def __init__(self, invoice, auth):
        self.type = invoice.type
        self.invoice = invoice
        self.auth = auth
        self.number = invoice.number if invoice.type == 'out' else invoice.number_alternate
        # Company information --------------------------------------------------
        self.company_id = invoice.company.party.id_number
        self.company_type_id = invoice.company.party.type_document or ''
        self.company_registration = invoice.company.party.commercial_registration
        self.company_name = invoice.company.party.name
        self.company_phone = invoice.company.party.phone or invoice.company.party.mobile
        self.company_city = invoice.company.party.city_name
        self.company_city_code = invoice.company.party.department_code+invoice.company.party.city_code
        self.company_department_code = invoice.company.party.department_code
        self.company_currency_id = invoice.company.currency.id
        self.company_address = invoice.company.party.street.replace('\n', '')
        self.company_check_digit = invoice.company.party.check_digit
        self.company_country_code = 'CO'
        self.company_country_name = 'Colombia'
        self.company_postal_zone = [address.postal_code for address in invoice.company.party.addresses]
        self.company_ciiu_code = invoice.company.party.ciiu_code
        self.company_tributes = invoice.company.party.party_tributes or []
        #self.company_party_obligations = self.invoice.company.party.party_obligation_tax
        #if not self.company_party_obligations:
        #    MESSAGES['company_party_obligations'] = 'Falta definir la obligaciones fiscales de la compañía'

        if TYPE_PERSON.get(invoice.company.party.type_person):
            self.company_tax_level_code = TYPE_PERSON[invoice.company.party.type_person]
        self.company_department = invoice.company.party.department_name
        self.company_email = invoice.company.party.email
        self.fiscal_regimen_company = invoice.company.party.fiscal_regimen
        self.shop_address = None
        #if hasattr(self.invoice, 'shop') and self.invoice.shop:
        #    self.shop_address = self.invoice.shop.address or self.invoice.company.party.street
        #    if not self.shop_address:
        #        MESSAGES['shop_address'] = 'Falta la dirección de la tienda'
        
        self.company_resolution_number = self.invoice.company.itsupplier_billing_resolution or ''
        self.company_branch_code = self.invoice.company.itsupplier_code_ds or ''
        self.print_format = self.invoice.company.itsupplier_print_format or ''
        self.print_format_note = self.invoice.company.itsupplier_print_format_note or ''
        self.company_email_ds = self.invoice.company.itsupplier_email_ds or ''

        # Party information------------------------------------------------------------------------------------------
        self.party_first_name = invoice.party.first_name
        self.party_second_name = invoice.party.second_name or ''
        self.party_first_family_name = invoice.party.first_family_name
        self.party_second_family_name = invoice.party.second_family_name or ''
        self.party_department_code = invoice.party.department_code or ''
        self.party_city_code = invoice.party.city_code or ''
        self.party_city_code = self.party_department_code+self.party_city_code
        self.party_name = invoice.party.name or invoice.party.commercial_name
        self.party_postal_zone = [address.postal_code for address in invoice.party.addresses if address.postal_code]
        self.party_id = invoice.party.id_number
        self.party_ciiu_code = invoice.party.ciiu_code or ''
        self.party_check_digit = invoice.party.check_digit
        self.party_type_id = invoice.party.type_document or ''
        self.supplier_tax_level_code = '2'
        self.party_tributes = invoice.party.party_tributes or []
        self.invoice_type_name = 'Venta'
        self.party_registration = invoice.party.commercial_registration or '00000'
        self.brands = []
        self.models = []
        self.debit_note_concept = self.invoice.debit_note_concept
        self.credit_note_concept = self.invoice.credit_note_concept
        self.lines = invoice.lines
        self.invoice_type_code = invoice.invoice_type if invoice.invoice_type else ''
        if self.invoice_type_code in ['1', '2', '3', '4']:
            self.invoice_type_code = '0' + invoice.invoice_type
        if self.invoice_type_code == '02':
            self.brands = ['not_brand' for line in self.lines
                           if hasattr(line.product.template, 'brand') and not line.product.brand]
            self.models = ['not_reference' for line in self.lines
                           if hasattr(line.product.template, 'reference') and not line.product.reference]

        self.invoice_type_name = invoice.invoice_type_string
        # if TYPE_PERSON.get(invoice.party.type_person):
        self.party_tax_level_code = TYPE_PERSON[invoice.party.type_person] if invoice.party.type_person else None
        self.fiscal_regimen_party = invoice.party.fiscal_regimen
        self.party_address = invoice.party.street
        self.party_country_code = invoice.party.get_country_iso(invoice.party.country_code, 'code')  # 'CO'
        self.party_country_name = invoice.party.get_country_iso(invoice.party.country_code, 'name')  # 'CO'
        self.party_department = invoice.party.department_name if self.party_country_code == 'CO' else ''
        self.party_city = invoice.party.city_name if invoice.party.city_name else ''
        self.party_phone = invoice.party.phone or invoice.party.mobile
        self.party_email = invoice.party.email
        self.reference = invoice.reference or ''
        self.notes = invoice.comment or ' '
        self.concept = (invoice.description or '') + ' ' + (self.notes or '')
        self.comment = invoice.comment or ''
        self.total_amount_words = invoice.total_amount_words or ''
        self.due_date = str(self.invoice.due_date)
        self.payment_term = invoice.payment_term.name if invoice.payment_term else ''
        self.payment_type = invoice.payment_term.payment_type if invoice.payment_term else ''
        self.payment_means_code = invoice.payment_code or ''
        self.payment_method = invoice.payment_method or invoice.payment_term.description or ''
        self.untaxed_amount = str(abs(invoice.untaxed_amount))
        self.total_amount = str(abs(invoice.total_amount))
        self.tax_amount = str(abs(invoice.tax_amount))
        self.taxes = invoice.taxes
        self.not_classification_tax = [taxline.tax.name for taxline in self.taxes if not taxline.tax.classification_tax]
        self.currency = invoice.currency.code
        self.invoice_date = date.strftime(self.invoice.invoice_date, '%Y-%m-%d')
        # self.issue_time = str(self.invoice.company.convert_timezone(invoice.create_date).time())[:8]
        self.issue_date, self.issue_time = invoice.get_datetime_local()
        self.status = 'ok'
        if self.payment_type == '2' or self.payment_means_code == '':
            self.payment_means_code = '1'
        self.software_id = auth.software_id
        self.software_provider_id = auth.software_provider_id
        self.check_digit_provider = auth.check_digit_provider
        self.invoice_authorization = auth.number
        self.start_date_auth = str(auth.start_date_auth)
        self.end_date_auth = str(auth.end_date_auth)
        self.prefix = auth.sequence.prefix
        self.from_auth = str(auth.from_auth)
        self.to_auth = str(auth.to_auth)
        self.auth_environment = auth.environment
        self.operation_type = invoice.operation_type
        self.validate_invoice()
        self.type_document_reference = invoice.type_document_reference or ''
        self.number_document_reference = invoice.number_document_reference or ''
        self.cufe_document_reference = invoice.cufe_document_reference or ''
        self.date_document_reference = invoice.date_document_reference or ''
        self.elaborated = invoice.create_uid.name
        self.original_invoice_date = None
        self.original_invoice_number = None
        self.original_invoice_cufe = None
        self.original_invoice_invoice_type = None

        if invoice.operation_type in ('20', '30') or invoice.type == 'in':
            self.original_invoice_date = date.strftime(invoice.date_document_reference, '%Y-%m-%d')
            self.original_invoice_number = invoice.number_document_reference
            self.original_invoice_cufe = invoice.cufe_document_reference
            self.original_invoice_invoice_type = invoice.type_invoice_reference
            print('ingresa por este valor')

    def validate_invoice(self):
        for k in MESSAGES.keys():

            field_value = getattr(self, k)
            party_inf = ['party_department_code', 'party_city_code', 'party_department', 'party_city']
            if k in party_inf and getattr(self, 'party_country_code') != 'CO':
                continue
            elif not field_value:
                self.status = MESSAGES[k]
                break
            if self.not_classification_tax:
                self.status = 'Falta Asignar Clasificación a un impuesto'+";".join(self.not_classification_tax)
                break
            if len(self.brands) > 0:
                self.status = 'Las marcas de productos son obligatorias para tipo Exportación'
                break
            if len(self.models) > 0:
                self.status = 'Las referencias o modelos de productos son obligatorias para los tipo Exportación'
                break
            # for line in self.lines:
            #     if not line.product.code:
            #         self.status = f'El producto {line.product.name}, debe tener codigo'
            #         break

    def validate_value(self, value):
        if value < 0:
            return value * -1
        else:
            return value

    def _get_provider(self):
        provider = {
            "Nvpro_cper": self.party_tax_level_code,
            "Nvpro_cdoc": self.party_type_id,
            "Nvpro_docu": self.party_id,
            "Nvpro_mail": self.party_email,
            "Nvpro_depa": self.party_department,
            "Nvpro_ciud": self.party_city+"@"+self.party_city_code,
            "Nvpro_loca":"",
            "Nvpro_pais": self.party_country_code,
            "Nvpro_dire": self.party_address,
            "Nvpro_regi": self.fiscal_regimen_party, #FIX
        }
        if self.party_type_id == '31':
            provider["Nvpro_dive"] = self.party_check_digit
        if self.party_postal_zone:
            provider["Nvpro_zipc"] = self.party_postal_zone[0]
        if self.party_phone:
            provider["Nvpro_ntel"] = self.party_phone
            provider["Nvpro_ncon"] = self.party_name
        if self.party_tax_level_code == 2 or self.party_tax_level_code == '2':
            provider["Nvpro_nomb"] = self.party_name
            provider["Nvpro_pnom"] = self.party_first_name
            provider["Nvpro_snom"] = self.party_second_name
            provider["Nvpro_apel"] = self.party_first_family_name+" "+self.party_second_family_name
        else:
            provider["Nvpro_nomb"] = self.party_name
            provider["Nvpro_pnom"] = ""
            provider["Nvpro_snom"] = ""
            provider["Nvpro_apel"] = ""
        if self.invoice.party.party_obligation_tax:
            # Validar y añadir las obligaciones fiscales del proveedor
            pass

        return provider


    def _get_information(self):
        information = {
            "Nvfac_orig": "E",
            "Nvemp_nnit": self.company_id,
            "Nvres_nume": self.company_resolution_number,
            "Nvfac_tipo": "DS", # Documento Soporte
            "Nvfac_tcru": "",
            "Nvfac_cdet": len(self.invoice.lines),
            "Nvfac_nume": self.number,
            "Nvres_pref": self.prefix,
            "Nvfac_fech": self.invoice_date,
            "Nvfac_venc": self.due_date,
            "Nvsuc_codi": self.company_branch_code,
            "Nvmon_codi": self.currency,
            "Nvfor_codi": self.print_format,
            "Nvven_nomb": "",
            "Nvfac_fpag": self.payment_means_code,
            "Nvfac_obse": self.concept,
            "Nvfac_stot": self.untaxed_amount, # Se omite el total con impuestos para el envío
            "Nvdes_codi": "",
            "Nvfac_desc": "0.00",
            "Nvfac_tota": self.untaxed_amount, # Campo con el mismo valor de Nvfac_stot
            "Nvfac_totp": self.untaxed_amount, # Valor total sin impuestos
            "Nvfac_roun": "0.00",
            "Nvcon_codi": "", # Fix concepto de la nota de ajuste
            "Nvcon_desc": "", # Fix nombre concepto de la nota de ajuste
        }
        if self.company_email_ds:
            information["Nvema_copi"] = self.company_email_ds
        return information


    def _set_original_document_information(self, data):
        if self.original_invoice_number:
            data['NVFAC_TCRU'] = 'R'
            data['Nvfac_numb'] = self.original_invoice_number
            data["Nvfac_fecb"] = self.original_invoice_date
        else:
            data['NVFAC_TCRU'] = 'L'
        return data

    def _get_lines(self):
        _lines = []
        sequence = 1
        for line in self.invoice.lines:
            unit_price = str(abs(line.unit_price))
            amount = str(abs(line.amount))
            if line.unit.symbol.upper() == 'KG':
                unit = 'KGM'
            else:
                unit = '94'
            detail = {
                "Nvfac_dcop": sequence,
                "Nvpro_codi": line.product.template.code,
                "Nvpro_nomb": line.product.template.name,
                "Nvuni_desc": unit,
                "Nvfac_cant": abs(line.quantity),
                "Nvfac_valo": unit_price,
                "Nvfac_pdes": "0.00", # Fix porcentaje descuento
                "Nvfac_desc": "0.00", # Fix valor descuento
                "Nvfac_stot": amount,
                "Nvimp_cdia": "00",
                "Nvdet_nota": line.note,
            }
            _lines.append(detail)
            sequence += 1
        return _lines


    def make(self, type):
        #document = {}
        document = self._get_information()
        document["proveedor"] = self._get_provider()
        document["lDetalle"] = self._get_lines()
        if type == '95': # NOTA DE AJUSTE
            document["Nvfac_tipo"] = "CS"
            document["Nvfor_codi"] = self.print_format_note
            document = self._set_original_document_information(document)
            document['NVCON_CODI'] = self.credit_note_concept
            document['NVCON_DESC'] = self.credit_note_concept
        print(document)
        return document