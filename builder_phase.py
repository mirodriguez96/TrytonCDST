
from decimal import Decimal
#from lxml import etree, builder
#from maker_phase import element
import os

EXTRAS = {
    'HED': {'code': 1, 'percentaje': '25.00'},
    'HEN': {'code': 2, 'percentaje': '75.00'},
    'HRN': {'code': 3, 'percentaje': '35.00'},
    'HEDDF': {'code': 4, 'percentaje': '100.00'},
    'HRDDF': {'code': 5, 'percentaje': '75.00'},
    'HENDF': {'code': 6, 'percentaje': '150.00'},
    'HRNDF': {'code': 7, 'percentaje': '110.00'},
}
KIND = {
    'steady': "1",
    'indefinite': "2",
    'job': "3",
    'learning': "4",
    'internships': "5",
}

TIPO_INCAPACIDAD = {
    'IncapacidadComun': '1',
    'IncapacidadProfesional': '2',
    'IncapacidadLaboral': '3',
}

path = os.path.dirname(__file__)
WAGE_TYPE = {
    'Basico': ['Basico'],
    'Transporte': ['AuxilioTransporte', 'ViaticoManuAlojS', 'ViaticoManuAlojNS'],
    'HEDs': ['HED', 'HEN', 'HRN', 'HEDDF', 'HRDDF', 'HENDF', 'HRNDF'],
    'Vacaciones': ['VacacionesComunes', 'VacacionesCompensadas'],
    'Primas': ['PrimasS', 'PrimasNS'],
    'Cesantias': ['Cesantias', 'IntCesantias'],
    'Incapacidades': ['IncapacidadComun', 'IncapacidadProfesional', 'IncapacidadLaboral'],
    'Licencias': ['LicenciaMP', 'LicenciaR', 'LicenciaNR'],
    'Bonificaciones': ['BonificacionS', 'BonificacionNS'],
    'Auxilios': ['AuxilioS', 'AuxilioNS'],
    'HuelgasLegales': ['HuelgaLegal'],
    'OtrosConceptos': ['OtroConceptoS', 'OtroConceptoNS'],
    'Compensaciones': ['CompensacionO', 'CompensacionE'],
    'BonoEPCTVs': ['PagoS', 'PagoNS', 'PagoAlimentacionS', 'PagoAlimentacionN'],
    'OtrosTag': ['Comision', 'PagoTercero', 'Anticipo'],
    'OtrosI': ['Dotacion', 'ApoyoSost', 'Teletrabajo', 'BonifRetiro', 'Indemnizacion', 'Reintegro'],
    'Salud': ['Salud'],
    'FondoPension': ['FondoPension'],
    'FondoSP': ['FondoSP', 'FondoSPSUB'],
    'Sindicatos': ['Sindicato'],
    'Sanciones': ['SancionPublic', 'SancionPriv'],
    'Libranzas': ['Libranza'],
    'OtrosD': ['PensionVoluntaria', 'RetencionFuente', 'AFC', 'Cooperativa', 'EmbargoFiscal', 'PlanComplementario', 'Educacion', 'Reintegro', 'Deuda']
    }

FISCAL_REGIMEN = {
    '48': 'RESPONSABLE DE IMPUESTO SOBRE LAS VENTAS – IVA',
    '49': 'NO RESPONSABLE DE IVA',
}

ENVIRONMENT = {
    '1': 'Produccion',
    '2': 'Pruebas',
}

MESSAGES = {
    'software_id': 'Falta ID del software Facturador',
    'software_pin': 'Falta PIN del software Facturador',
    'company_id': 'Falta numero NIT de la empresa',
    'company_full_name': 'Falta el nombre de la empresa',
    'company_check_digit': 'Falta el digito de verificacion de la empresa',
    'company_city_code': 'Falta la ciudad de la empresa',
    'company_address': 'Falta la direccion de la empresa',
    'company_country_code': 'Falta el pais de la empresa',
    'company_department_code': 'Falta el departamento de la empresa',
    'company_type_id': 'Falta el tipo de documento que identifica a la compañía',
    'work_place_department': 'Falta definir el departamento lugar de trabajo del empleado',
    'work_place_city': 'Falta definir el ciudad lugar de trabajo del empleado',
    'work_place_address': 'Falta definir el direccion lugar de trabajo del empleado',
    'type_contract': 'Debe definir el tipo de contrato',
    'salary': 'El contrato no tiene definido un salario',
    'payment_term': 'Falta el medio de pago',
    'payment_method': 'Falta el metodo de pago',
    'payroll_type': 'Falta definir el tipo de nomina',
    'environment': 'Debe definir el ambiente pruebas o produccion',
    'period_payroll': 'Falta definir el periodo de nomina',
    'prefix': 'Falta definir el prefijo de la secuencia',
    'party_name': 'Falta el nombre del cliente',
    'party_id': 'Falta el id del cliente',
    'issue_date': 'Falta la fecha de factura'
}


def rvalue(value, n):
    return str(round(abs(value), n))


class ElectronicPayroll(object):

    def __init__(self, payroll, config):
        self.payroll = payroll
        self.config = config
        self.status = 'ok'
        # self.auth = auth
        self.number = payroll.number
        # Company information --------------------------------------------------
        self.company_id = payroll.company.party.id_number
        self.company_type_id = payroll.company.party.type_document
        self.company_full_name = payroll.company.party.name
        self.company_first_name = payroll.company.party.first_name or None
        self.company_second_name = payroll.company.party.second_name or ''
        self.company_first_familyname = payroll.company.party.first_family_name or ''
        self.company_second_familyname = payroll.company.party.second_family_name or ''
        self.company_check_digit = payroll.company.party.check_digit
        self.company_country_code = 'CO'
        self.company_department_code = payroll.company.party.department_code
        self.company_city_code = payroll.company.party.city_code
        self.company_address = payroll.company.party.street.replace('\n', '')
    #     # Employee information------------------------------------------------------------------------------------------
        # self.department_code = payroll.employee.party.department_code
        # self.party_city_code = payroll.employee.party.city_code
        self.party_name = payroll.employee.party.name
        self.party_id = payroll.employee.party.id_number
        self.party_type_id = payroll.employee.party.type_document
        self.type_employee = payroll.contract.type_of_employee
        self.subtype_employee = payroll.contract.subtype_of_employee
        self.alto_riesgo_pension = payroll.contract.high_pension_risk or 'false'
        self.employee_first_name = payroll.employee.party.first_name
        self.employee_second_name = payroll.employee.party.second_name or ''
        self.employee_first_family_name = payroll.employee.party.first_family_name
        self.employee_second_family_name = payroll.employee.party.second_family_name or ''
        self.work_place_country = 'CO'
        self.work_place_department = payroll.contract.subdivision_activity.code
        self.work_place_city = payroll.contract.city_activity.code
        self.work_place_address = payroll.contract.address_activity
        self.integral_salary = payroll.contract.integral_salary or 'false'
        self.type_contract = KIND[payroll.contract.kind]
        self.salary = payroll.contract.salary
        self.code_employee = payroll.employee.code or None
        self.payment_term = payroll.contract.payment_term
        self.payment_method = payroll.payment_method
        if payroll.bank_payment and payroll.employee.party.bank_accounts:
            self.bank = payroll.employee.party.bank_name or None
            self.bank_account_type = payroll.employee.party.bank_account_type or None
            self.bank_account = payroll.employee.party.bank_account or None

        self.currency = payroll.currency.code
        self.issue_date, self.issue_time = payroll.get_datetime_local()

        self.environment = config.environment
        self.period_payroll = config.period_payroll
        self.prefix = config.payroll_electronic_sequence.prefix
        self.software_id = config.software_id
        self.software_pin = config.pin_software
        self.payroll_type = self.payroll.payroll_type

        self.validate_payroll()

    def validate_payroll(self):
        for k in MESSAGES.keys():

            field_value = getattr(self, k)
            bank_inf = ['bank', 'bank_account_type', 'bank_account']
            if k in bank_inf and not self.payroll.bank_payment:
                continue
            elif not field_value:
                self.status = MESSAGES[k]
                break

    #def _get_head_psk(self):
    #    NomInd = open(path + '/Nomina_Individual_Electronica_V1.0.xml', 'r')
    #    root = etree.parse(NomInd).getroot()
    #    return root

    #def _get_credit_head_psk(self):
    #    NomIndA = open(path + '/Nomina_Individual_Ajuste_Electronica_V1.0.xml', 'r')
    #    root = etree.parse(NomIndA).getroot()
    #    return root

    def _get_payroll_period(self):

        start_date = self.payroll.contract.start_date
        # if start_date < self.payroll.start:
        #     start_date = ''
        end_date = None
        settlement_start_date, settlement_end_date = None, None
        if self.payroll.contract.finished_date and self.payroll.end <= self.payroll.contract.finished_date:
            settlement_end_date = self.payroll.contract.finished_date
            end_date = settlement_end_date

        for p in self.payroll.payrolls_relationship:
            if not settlement_start_date:
                settlement_start_date = p.start
            elif settlement_start_date <= p.start:
                settlement_start_date = p.start

            if not settlement_end_date:
                settlement_end_date = p.end
            elif settlement_end_date >= p.end:
                settlement_end_date = p.end

        payroll_period = {
            "FechaIngreso":str(start_date),
            "FechaLiquidacionInicio":str(settlement_start_date),
            "FechaLiquidacionFin":str(settlement_end_date),
            "TiempoLaborado":str(self.payroll.get_time_worked()),
            "FechaGen":self.issue_date,
            }
        if end_date:
            print(end_date)
            payroll_period['FechaRetiro'] = str(end_date)
        return payroll_period

    def _get_sequence(self):
        seq = self.number.split(self.prefix, maxsplit=1)
        sequence = {
            "Prefijo":self.prefix,
            "Consecutivo":seq[1],
            "Numero":self.number,
            }
        if self.code_employee:
            sequence['CodigoTrabajador'] = self.code_employee
        return sequence

    def _get_place_generation(self):
        place_generation = {
            "Pais":self.company_country_code,
            "DepartamentoEstado":self.company_department_code,
            "MunicipioCiudad":str(self.company_department_code + self.company_city_code),
            "Idioma":"es"
            }
        return place_generation

    def _get_provider(self):
        provider = {
            "RazonSocial":self.company_full_name,
            "NIT":str(self.company_id),
            "DV":str(self.company_check_digit),
            "SoftwareID":self.software_id,
            "SoftwareSC":self.payroll.get_security_code(self.config)
            }
        if self.company_first_name:
            provider['PrimerApellido'] = self.company_first_name
            provider['SegundoApellido'] = self.company_second_familyname
            provider['PrimerNombre'] = self.company_first_name
            provider['OtrosNombres'] = self.company_second_name
        return provider

    def _get_qrcode(self):
        qrcode = { 
            "CodigoQR": self.payroll.get_link_dian(cune=True, config=self.config)
            }
        return qrcode

    def _get_general_information(self):
        information = {
            "Version":"V1.0: Documento Soporte de Pago de Nómina Electrónica",
            "Ambiente":str(self.environment),
            "TipoXML":self.payroll_type,
            "CUNE":self.payroll.get_cune(),
            "EncripCUNE":"CUNE-SHA384",
            "FechaGen":self.issue_date,
            "HoraGen":self.issue_time,
            "PeriodoNomina":self.period_payroll,
            "TipoMoneda":self.currency,
            "TRM":"0"
            }
        return information

    def _get_notes(self):
        notes = {
            "Notas": ''
            }
        return notes

    def _get_information_company(self):
        information = {
            "RazonSocial":self.company_full_name,
            "NIT":str(self.company_id),
            "DV":str(self.company_check_digit),
            "Pais":str(self.company_country_code),
            "DepartamentoEstado":str(self.company_department_code),
            "MunicipioCiudad":str(self.company_department_code + self.company_city_code),
            "Direccion":str(self.company_address),
            }
        if self.company_first_name:
            information['PrimerApellido'] = self.company_first_name
            information['SegundoApellido'] = self.company_second_familyname
            information['PrimerNombre'] = self.company_first_name
            information['OtrosNombres'] = self.company_second_name
        return information

    def _get_information_employee(self):
        information = {
            "TipoTrabajador":str(self.type_employee),
            "SubTipoTrabajador":str(self.subtype_employee),
            "AltoRiesgoPension":self.alto_riesgo_pension,
            "TipoDocumento":str(self.party_type_id),
            "NumeroDocumento":str(self.party_id),
            "PrimerApellido":self.employee_first_family_name,
            "SegundoApellido":self.employee_second_family_name,
            "PrimerNombre":self.employee_first_name,
            "LugarTrabajoPais":str(self.work_place_country),
            "LugarTrabajoDepartamentoEstado":str(self.work_place_department),
            "LugarTrabajoMunicipioCiudad":str(self.work_place_department + self.work_place_city),
            "LugarTrabajoDireccion":str(self.work_place_address),
            "SalarioIntegral":self.integral_salary,
            "TipoContrato":str(self.type_contract),
            "Sueldo":str(self.salary),
            }
        if self.employee_second_name:
            information['OtrosNombres'] = self.employee_second_name
        if self.code_employee:
            information['CodigoTrabajador'] = str(self.code_employee)
        return information

    def _get_payment_terms(self):
        information = {
            "Forma":self.payment_term,
            "Metodo":self.payment_method
            }
        if self.payroll.bank_payment:
            information['Banco'] = self.bank
            information['TipoCuenta'] = self.bank_account_type
            information['NumeroCuenta'] = self.bank_account
        return information

    def _get_pay_date(self):
        pay_dates = {
            }
        pagos = []
        for pay in self.payroll.payrolls_relationship:
            pagos.append(str(pay.date_effective))
        pay_dates["FechaPago"] = pagos
        return pay_dates
    
    """
    def _get_predecessor(self, type):
        if type == '1':
            predecessor = element.ReemplazandoPredecesor()
        else:
            predecessor = element.EliminandoPredecesor()
        predecessor.set('NumeroPred', )
        predecessor.set('CUNEPred', )
        predecessor.set('FechaGenPred', )
        return predecessor
    """

    def _get_type_note(self):
        return {"TipoNota":self.payroll.type_note}

    def _get_lines(self):
        line_payments = []
        line_deductions = []
        for line in self.payroll.lines:
            if line.wage_type.definition == 'payment':
                line_payments.append(line)
            else:
                line_deductions.append(line)
        payments = self._get_payments(line_payments)
        deductions = self._get_deductions(line_deductions)

        return payments, deductions

    def _get_payments(self, line_payments):
        devengados = {}
        subelements = {}

        for line in line_payments:
            concept = line.wage_type.type_concept_electronic
            if concept == 'Basico':
                basico = {}
                factor = 1.0
                if line.uom.name == 'Hora':
                    factor = 8.0
                worked_days = line.quantity / Decimal(factor)
                basico['DiasTrabajados'] = rvalue(worked_days, 0)
                basico['SueldoTrabajado'] = rvalue(line.amount, 1)
                subelements['Basico'] = basico

            elif concept in WAGE_TYPE['Transporte']:
                if concept not in subelements.keys():
                    subelements['Transporte'] = {}
                subelements['Transporte'][concept] = rvalue(line.amount, 1)

            elif concept in WAGE_TYPE['HEDs']:
                if 'HEDs' not in subelements.keys():
                    subelements['HEDs'] = {}
                hr = {
                'Cantidad': rvalue(line.quantity, 0),
                'Porcentaje': str(EXTRAS[concept]['percentaje']),
                'Pago': rvalue(line.amount, 2)
                }
                subelements['HEDs'][concept] = hr

            elif concept in WAGE_TYPE['Vacaciones']:
                if 'Vacaciones' not in subelements.keys():
                    subelements['Vacaciones'] = {}
                if concept == 'VacacionesComunes':
                    for l in line.lines_payroll:
                        # line_payroll = l.line_payroll
                        e ={
                            "FechaInicio":str(l.start_date),
                            "FechaFin":str(l.end_date),
                            "Cantidad":rvalue(l.quantity, 0),
                            "Pago":rvalue(l.amount, 2)
                            }
                        subelements['Vacaciones'][concept] = e
                else:
                    e = {
                        "Cantidad":rvalue(line.quantity, 0),
                        "Pago":rvalue(line.amount, 2)
                        }
                    subelements['Vacaciones'][concept] = e

            elif concept in WAGE_TYPE['Primas']:
                if 'Primas' not in subelements.keys():
                    subelements['Primas'] = {}
                if concept == 'PrimasS':
                    subelements['Primas']['Cantidad'] = rvalue(line.quantity, 0)
                    subelements['Primas']['Pago'] = rvalue(line.amount, 2)
                else:
                    subelements['Primas']['PagoNs'] = rvalue(line.amount, 2)
            
            elif concept in WAGE_TYPE['Cesantias']:
                if 'Cesantias' not in subelements.keys():
                    subelements['Cesantias'] = {}
                if concept == 'Cesantias':
                    subelements['Cesantias']['Cesantias'] = rvalue(line.amount, 2)
                else:
                    subelements['Cesantias']['Porcentaje'] = '12.0'
                    subelements['Cesantias']['IntCesantias'] = rvalue(line.amount, 2)

            elif concept in WAGE_TYPE['Incapacidades']:
                if 'Incapacidades' not in subelements.keys():
                    subelements['Incapacidades'] = {}
                    for l in line.lines_payroll:
                        # line_payroll = l.line_payroll
                        e = {}
                        e['FechaInicio'] = str(l.start_date)
                        e['FechaFin'] = str(l.end_date)
                        e['Cantidad'] = rvalue(l.quantity, 0)
                        e['Tipo'] = TIPO_INCAPACIDAD[concept]
                        e['Pago'] = rvalue(l.amount, 2)
                        subelements['Incapacidades'][concept] = e

            elif concept in WAGE_TYPE['Licencias']:
                if 'Licencias' not in subelements.keys():
                    subelements['Licencias'] = {}
                    for l in line.lines_payroll:
                        # line_payroll = l.line_payroll
                        e = {}
                        e['FechaInicio'] = str(l.start_date)
                        e['FechaFin'] = str(l.end_date)
                        e['Cantidad'] = rvalue(l.quantity, 0)
                        if concept != 'LicenciaNR':
                            e['Pago'] = rvalue(l.amount, 2)
                        subelements['Licencias'][concept] = e

            elif concept in WAGE_TYPE['Bonificaciones']:
                if 'Bonificaciones' not in subelements.keys():
                    #subelements['Bonificaciones'] = {}
                    subelements['Bonificaciones'] = {}
                #if concept == 'BonificacionS':
                #    subelements['Bonificaciones'][0] = {concept: }
                #else:
                #    subelements['Bonificaciones'][0] = {concept: rvalue(line.amount, 2)}
                subelements['Bonificaciones'][concept] = rvalue(line.amount, 2)

            elif concept in WAGE_TYPE['Auxilios']:
                if 'Auxilios' not in subelements.keys():
                    #subelements['Auxilios'] = element.Auxilios()
                    subelements['Auxilios'] = {}
                #if concept == 'AuxilioS':
                #    subelements['Auxilios'][0] = {concept: rvalue(line.amount, 2)}
                #else:
                #    subelements['Auxilios'][0] = {concept, rvalue(line.amount, 2)}
                subelements['Auxilios'][concept] = rvalue(line.amount, 2)

            #SIN USO
            #elif concept in WAGE_TYPE['HuelgasLegales']:
            #    if 'HuelgasLegales' not in subelements.keys():
            #        subelements['HuelgaLegales'] = {}
            #    e = {"HuelgaLegal": {
            #        "FechaInicio":"9999-12-31",
            #        "FechaFin":"9999-12-31",
            #        "Cantidad":"0"
            #        }
            #    }
            #    subelements['HuelgaLegales'] = e

            elif concept in WAGE_TYPE['OtrosConceptos']:
                if 'OtrosConceptos' not in subelements.keys():
                    subelements['OtrosConceptos'] = {}
                e = {}
                e['DescripcionConcepto'] = line.description
                e[concept] = rvalue(line.amount, 2)
                subelements['OtrosConceptos'][concept] = e

            elif concept in WAGE_TYPE['Compensaciones']:
                if 'Compensaciones' not in subelements.keys():
                    subelements['Compensaciones'] = {}
                subelements['Compensaciones'][concept] = rvalue(line.amount, 2)
            
            elif concept in WAGE_TYPE['BonoEPCTVs']:
                if 'BonoEPCTVs' not in subelements.keys():
                    subelements['BonoEPCTVs'] = {}
                subelements['BonoEPCTVs'][concept] = rvalue(line.amount, 2)

            elif concept in WAGE_TYPE['OtrosTag']:
                if 'OtrosTag' not in subelements.keys():
                    subelements['OtrosTag'] = {}
                subelements['OtrosTag'][concept] = rvalue(line.amount, 2)

            elif concept in WAGE_TYPE['OtrosI']:
                if 'OtrosI' not in subelements.keys():
                    subelements['OtrosI'] = {}
                subelements['OtrosI'][concept] = rvalue(line.amount, 2)

        #for e in subelements.values():
        #    devengados.append(e)
        devengados = subelements
        return devengados

    def _get_deductions(self, line_deductions):
        deductions = {}
        subelements = {}

        for line in line_deductions:
            concept = line.wage_type.type_concept_electronic
            if concept == 'Salud':
                p = line.wage_type.unit_price_formula.split('*')
                p = Decimal(p[1].strip()) * 100
                e = {
                    "Porcentaje": str(p),
                    "Deduccion":rvalue(line.amount, 2)
                    }
                subelements[concept] = e
            
            elif concept == 'FondoPension':
                p = line.wage_type.unit_price_formula.split('*')
                p = Decimal(p[1].strip()) * 100
                e = {
                    "Porcentaje": str(p),
                    "Deduccion":rvalue(line.amount, 2)
                }
                subelements[concept] = e

            elif concept in WAGE_TYPE['FondoSP']:
                if 'FondoSP' not in subelements.keys():
                    subelements['FondoSP'] = {}
                p = line.wage_type.unit_price_formula.split('*')
                p = Decimal(p[1].strip()) * 100
                e = {
                    'Porcentaje': str(p),
                    'Deduccion': rvalue(line.amount, 2)
                }
                subelements['FondoSP'][concept] = e

            elif concept in WAGE_TYPE['Sindicatos']:
                if 'Sindicatos' not in subelements.keys():
                    subelements['Sindicatos'] = {}
                p = line.wage_type.unit_price_formula.split('*')
                p = Decimal(p[1].strip()) * 100
                e = {
                    "Porcentaje":str(p),
                    "Deduccion":rvalue(line.amount, 2)
                }
                subelements['Sindicatos'][concept] = e

            elif concept in WAGE_TYPE['Sanciones']:
                if 'Sanciones' not in subelements.keys():
                    subelements['Sanciones'] = {}
                #if concept == 'SancionPublic':
                #    subelements['Sanciones'][0] = {concept: rvalue(line.amount, 2)}
                #else:
                #    subelements['Sanciones'][0] = {concept: rvalue(line.amount, 2)}
                subelements['Sanciones'][0] = {concept: rvalue(line.amount, 2)}

            elif concept in WAGE_TYPE['Libranzas']:
                if 'Libranzas' not in subelements.keys():
                    subelements['Libranzas'] = {}
                e = {
                    "Descripcion":line.description,
                    "Deduccion":rvalue(line.amount, 2)
                }
                subelements['Libranzas'] = {concept: e}

            elif concept in WAGE_TYPE['OtrosTag']:
                if 'OtrosTag' not in subelements.keys():
                    subelements['OtrosTag'] = {}
                subelements['OtrosTag'][concept] = rvalue(line.amount, 2)

            elif concept == 'OtraDeduccion':
                if 'OtrasDeducciones' not in subelements.keys():
                    subelements['OtrasDeducciones'] = {}
                #e = element.OtraDeduccion(rvalue(line.amount, 2))
                subelements['OtrasDeducciones'] = {concept: rvalue(line.amount, 2)}

            elif concept in WAGE_TYPE['OtrosD']:
                if 'OtrosD' not in subelements.keys():
                    subelements['OtrosD'] = {}
                e = {concept: rvalue(line.amount, 2)}
                #e = element(concept)
                #e.text = rvalue(line.amount, 2)
                #print(subelements)
                subelements['OtrosD'] = e

            #for e in subelements.values():
            #    deductions.append(e)
            deductions = subelements
        return deductions

    def _get_total(self):
        DevengadosTotal = rvalue(self.payroll.gross_payments, 2)
        DeduccionesTotal = rvalue(self.payroll.total_deductions, 2)
        ComprobanteTotal = rvalue(self.payroll.net_payment, 2)
        return DevengadosTotal, DeduccionesTotal, ComprobanteTotal

#----------------------------------------------- MAKE ELECTRONIC payroll------------------------------------------------------

    def make(self, type):
        if type == '102': #Nomina individual
            #xml_invoice = self._get_head_psk()
            dic_invoice = {}
            dic_invoice["Periodo"] = self._get_payroll_period()
            dic_invoice["NumeroSecuenciaXML"] = (self._get_sequence())
            dic_invoice["LugarGeneracionXML"] = (self._get_place_generation())
            dic_invoice["ProveedorXML"] = (self._get_provider())
            #xml_invoice.append(self._get_qrcode())
            dic_invoice["InformacionGeneral"] = (self._get_general_information())
            # xml_invoice.append(self._get_notes())
            dic_invoice["Empleador"] = (self._get_information_company())
            dic_invoice["Trabajador"] = (self._get_information_employee())
            dic_invoice["Pago"] = (self._get_payment_terms())
            dic_invoice["FechasPagos"] = (self._get_pay_date())
            acrueds, deductions = self._get_lines()
            dic_invoice["Devengados"] = (acrueds)
            dic_invoice["Deducciones"] = (deductions)
            gross, deductions, net_payment = self._get_total()
            dic_invoice["DevengadosTotal"] = gross
            dic_invoice["DeduccionesTotal"] = deductions
            dic_invoice["ComprobanteTotal"] = net_payment

        """
        elif type == '103': #Nomina individual ajuste
            #xml_invoice = self._get_credit_head_psk()
            xml_invoice = []
            type_note = self._get_type_note()
            xml_invoice.append(type_note)
            if self.payroll.type_note == '1':
                replace = element.Reemplazar()
                replace.append(self._get_predecessor(type_note))
                replace.append(self._get_payroll_period())
                replace.append(self._get_sequence())
                replace.append(self._get_place_generation())
                replace.append(self._get_provider())
                replace.append(self._get_qrcode())
                replace.append(self._get_general_information())
                # replace.append(self._get_notes())
                replace.append(self._get_information_company())
                replace.append(self._get_information_employee())
                replace.append(self._get_payment_terms())
                replace.append(self._get_pay_date())
                acrueds, deductions = self._get_lines()
                replace.append(acrueds)
                replace.append(deductions)
                gross, deductions, net_payment = self._get_total()
                replace.append(gross)
                replace.append(deductions)
                replace.append(net_payment)
                xml_invoice.append(replace)
            elif type_note == '2':
                delete = element.Eliminar()
                delete.append(self._get_predecessor(type_note))
                delete.append(self._get_sequence())
                delete.append(self._get_place_generation())
                delete.append(self._get_provider())
                delete.append(self._get_qrcode())
                delete.append(self._get_general_information())
                delete.append(self._get_notes())
                delete.append(self._get_information_company())
                xml_invoice.append(delete)
        """
        #exml = etree.tostring(xml_invoice, encoding='UTF-8', pretty_print=True, xml_declaration=True)
        return dic_invoice

