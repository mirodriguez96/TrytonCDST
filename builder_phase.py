#import json
import datetime
import os
from decimal import Decimal

EXTRAS = {
    'HED': {
        'code': 1,
        'percentaje': '25.00'
    },
    'HEN': {
        'code': 2,
        'percentaje': '75.00'
    },
    'HRN': {
        'code': 3,
        'percentaje': '35.00'
    },
    'HEDDF': {
        'code': 4,
        'percentaje': '100.00'
    },
    'HRDDF': {
        'code': 5,
        'percentaje': '75.00'
    },
    'HENDF': {
        'code': 6,
        'percentaje': '150.00'
    },
    'HRNDF': {
        'code': 7,
        'percentaje': '110.00'
    },
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
    'Transporte':
    ['AuxilioTransporte', 'ViaticoManuAlojS', 'ViaticoManuAlojNS'],
    'HEDs': ['HED', 'HEN', 'HRN', 'HEDDF', 'HRDDF', 'HENDF', 'HRNDF'],
    'Vacaciones': ['VacacionesComunes', 'VacacionesCompensadas'],
    'Primas': ['PrimasS', 'PrimasNS'],
    'Cesantias': ['Cesantias', 'IntCesantias'],
    'Incapacidades':
    ['IncapacidadComun', 'IncapacidadProfesional', 'IncapacidadLaboral'],
    'Licencias': ['LicenciaMP', 'LicenciaR', 'LicenciaNR'],
    'Bonificaciones': ['BonificacionS', 'BonificacionNS'],
    'Auxilios': ['AuxilioS', 'AuxilioNS'],
    'HuelgasLegales': ['HuelgaLegal'],
    'OtrosConceptos': ['OtroConceptoS', 'OtroConceptoNS'],
    'Compensaciones': ['CompensacionO', 'CompensacionE'],
    'BonoEPCTVs':
    ['PagoS', 'PagoNS', 'PagoAlimentacionS', 'PagoAlimentacionN'],
    'OtrosTag': ['Comision', 'PagoTercero', 'Anticipo'],
    'OtrosI': [
        'Dotacion', 'ApoyoSost', 'Teletrabajo', 'BonifRetiro', 'Indemnizacion',
        'Reintegro'
    ],
    'Salud': ['Salud'],
    'FondoPension': ['FondoPension'],
    'FondoSP': ['FondoSP', 'FondoSPSUB'],
    'Sindicatos': ['Sindicato'],
    'Sanciones': ['SancionPublic', 'SancionPriv'],
    'Libranzas': ['Libranza'],
    'OtrosD': [
        'PensionVoluntaria', 'RetencionFuente', 'AFC', 'Cooperativa',
        'EmbargoFiscal', 'PlanComplementario', 'Educacion', 'Reintegro',
        'Deuda'
    ]
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
    'company_type_id':
    'Falta el tipo de documento que identifica a la compañía',
    'work_place_department':
    'Falta definir el departamento lugar de trabajo del empleado',
    'work_place_city': 'Falta definir el ciudad lugar de trabajo del empleado',
    'work_place_address':
    'Falta definir el direccion lugar de trabajo del empleado',
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
        if self.company_check_digit and self.company_check_digit == 0:
            self.company_check_digit = '0'
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
        self.sucode = self.payroll.company.supplier_code

        self.validate_payroll()

    def validate_payroll(self):
        for k in MESSAGES.keys():

            field_value = getattr(self, k)
            bank_inf = ['bank', 'bank_account_type', 'bank_account']
            if k in bank_inf and not self.payroll.bank_payment:
                continue
            elif not field_value:
                if k == 'company_check_digit':  # FIX
                    continue
                self.status = MESSAGES[k]
                break

    #funcion encargada de reunir la información del periodo de pago
    def _get_payroll_period(self):
        start_date = self.payroll.contract.start_date
        end_date = None
        settlement_start_date = None
        settlement_end_date = None

        for p in self.payroll.payrolls_relationship:
            if not settlement_start_date:
                settlement_start_date = p.start
            elif settlement_start_date >= p.start:
                settlement_start_date = p.start

            if not settlement_end_date:
                settlement_end_date = p.end
            elif settlement_end_date <= p.end:
                settlement_end_date = p.end

        if self.payroll.contract.finished_date and self.payroll.end >= self.payroll.contract.finished_date:
            settlement_end_date = self.payroll.contract.finished_date
            end_date = settlement_end_date

        payroll_period = {
            "Nvper_fing": str(start_date),  #FechaIngreso
            "Nvper_fpin": str(settlement_start_date),  #FechaLiquidacionInicio
            "Nvper_fpfi": str(settlement_end_date),  #FechaLiquidacionFin
            "Nvper_tlab": str(self.payroll.get_time_worked()),  #TiempoLaborado
            #"FechaGen":self.issue_date,
        }
        if end_date:
            payroll_period['Nvper_fret'] = str(end_date)  #FechaRetiro
        return payroll_period

    def _get_sequence(self):
        seq = self.number.split(self.prefix, maxsplit=1)
        sequence = {
            "Nvsuc_codi": self.sucode,  #Codigo sucursal (noova)
            "Nvnom_pref": self.prefix,  #Prefijo
            "Nvnom_cons": seq[1],  #Consecutivo
            "Nvnom_nume": self.number,  #Numero (pref+num)
            "Nvope_tipo":
            "NM"  #Tipo de operación nómina (siempre debe ir "NM")
        }
        #if self.code_employee:
        #    sequence['CodigoTrabajador'] = self.code_employee
        return sequence

    #SIN USO
    def _get_place_generation(self):
        place_generation = {
            "Pais":
            self.company_country_code,
            "DepartamentoEstado":
            self.company_department_code,
            "MunicipioCiudad":
            str(self.company_department_code + self.company_city_code),
            "Idioma":
            "es"
        }
        return place_generation

    #SIN USO
    def _get_provider(self):
        provider = {
            "RazonSocial": self.company_full_name,  #RazonSocial
            "NIT": str(self.company_id),  #NIT
            "DV": str(self.company_check_digit),  #DV
            "SoftwareID": self.software_id,
            "SoftwareSC": self.payroll.get_security_code(self.config)
        }
        if self.company_first_name:
            provider[
                'PrimerApellido'] = self.company_first_name  #PrimerApellido
            provider[
                'SegundoApellido'] = self.company_second_familyname  #SegundoApellido
            provider['PrimerNombre'] = self.company_first_name  #PrimerNombre
            provider['OtrosNombres'] = self.company_second_name  #OtrosNombres
        return provider

    def _get_qrcode(self):
        qrcode = {
            "CodigoQR": self.payroll.get_link_dian(cune=True,
                                                   config=self.config)
        }
        return qrcode

    def _get_general_information(self):
        information = {
            #"Version":"V1.0: Documento Soporte de Pago de Nómina Electrónica",
            #"Ambiente":str(self.environment),
            "Nvinf_tnom": self.payroll_type,  #Tipo de nomina
            #"CUNE":self.payroll.get_cune(),
            #"EncripCUNE":"CUNE-SHA384",
            #"FechaGen":self.issue_date,
            #"HoraGen":self.issue_time,
            "Nvinf_pnom": self.period_payroll,  #PeriodoNomina
            "Nvinf_tmon": self.currency,  #TipoMoneda
            #"TRM":"0"
        }
        return information

    def _get_notes(self):
        notes = ''
        return notes

    def _get_information_company(self):
        information = {
            "Nvemp_nomb":
            self.company_full_name,  #RazonSocial
            "Nvemp_nnit":
            str(self.company_id),
            "Nvemp_endv":
            str(self.company_check_digit),
            "Nvemp_pais":
            str(self.company_country_code),
            "Nvemp_depa":
            str(self.company_department_code),
            "Nvemp_ciud":
            str(self.company_department_code + self.company_city_code),
            "Nvemp_dire":
            str(self.company_address),
        }
        if self.company_first_name:
            information['Nvemp_pape'] = self.company_first_name
            information['Nvemp_sape'] = self.company_second_familyname
            information['Nvemp_pnom'] = self.company_first_name
            information['Nvemp_onom'] = self.company_second_name
        return information

    def _get_information_employee(self):
        information = {
            "Nvtra_tipo": str(self.type_employee),  #TipoTrabajador
            "Nvtra_stip": str(self.subtype_employee),
            "Nvtra_arpe": self.alto_riesgo_pension,
            "Nvtra_dtip": str(self.party_type_id),
            "Nvtra_ndoc": str(self.party_id),
            "Nvtra_pape": self.employee_first_family_name,
            "Nvtra_sape": self.employee_second_family_name,
            "Nvtra_pnom": self.employee_first_name,
            "Nvtra_ltpa": str(self.work_place_country),
            "Nvtra_ltde": str(self.work_place_department),
            "Nvtra_ltci":
            str(self.work_place_department + self.work_place_city),
            "Nvtra_ltdi": str(self.work_place_address),
            "Nvtra_sint": self.integral_salary,
            "Nvtra_tcon": str(self.type_contract),
            "Nvtra_suel": str(self.salary),
        }
        if self.employee_second_name:
            information['Nvtra_onom'] = self.employee_second_name
        if self.code_employee:
            information['Nvtra_codt'] = str(self.code_employee)
        return information

    def _get_payment_terms(self):
        information = {
            "Nvpag_form": self.payment_term,  #Forma
            "Nvpag_meto": self.payment_method  #Metodo
        }
        if self.payroll.bank_payment:
            information['Nvpag_banc'] = self.bank  #Banco
            information['Nvpag_tcue'] = self.bank_account_type  #TipoCuenta
            information['Nvpag_ncue'] = self.bank_account  #NumeroCuenta
        return information

    def _get_pay_date(self):
        #pay_dates = {}
        #pagos = []
        #for pay in self.payroll.payrolls_relationship:
        #    pagos.append(str(pay.date_effective))
        #pay_dates["FechaPago"] = pagos
        pay_date = datetime.date(999, 1, 1)
        for pay in self.payroll.payrolls_relationship:
            print(pay.date_effective)
            if pay_date <= pay.date_effective:
                pay_date = pay.date_effective
        return str(pay_date)

    def _get_predecessor(self):
        issue_date = self.payroll.original_payroll.get_datetime_local()
        predecessor = {
            "Nvpre_nume": self.payroll.original_payroll.number,  #NumeroPred
            "Nvpre_cune": self.payroll.original_payroll.cune,  #CUNEPred
            "Nvpre_fgen": issue_date[0]  #FechaGenPred
        }
        return predecessor

    def _get_type_note(self):
        return self.payroll.type_note

    #
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

    # DEVENGADOS
    def _get_payments(self, line_payments):
        subelements = {}

        for line in line_payments:
            concept = line.wage_type.type_concept_electronic

            if concept == 'Basico':
                factor = 1.0
                if line.uom and line.uom.name == 'Hora':
                    factor = 8.0
                worked_days = line.quantity / Decimal(factor)
                basico = {
                    'Nvbas_dtra': rvalue(worked_days, 0),  #DiasTrabajados
                    'Nvbas_stra': rvalue(line.amount, 1)  #SueldoTrabajado
                }
                subelements['Basico'] = basico

            elif concept in WAGE_TYPE['Transporte']:
                if 'Transporte' not in subelements.keys():
                    subelements['Transporte'] = {}
                if concept == 'AuxilioTransporte':
                    subelements['Transporte']['Nvtrn_auxt'] = rvalue(
                        line.amount, 1)
                elif concept == 'ViaticoManuAlojS':
                    subelements['Transporte']['Nvtrn_vias'] = rvalue(
                        line.amount, 1)
                elif concept == 'ViaticoManuAlojNS':
                    subelements['Transporte']['Nvtrn_vins'] = rvalue(
                        line.amount, 1)

            elif concept in WAGE_TYPE['HEDs']:
                if 'LHorasExtras' not in subelements.keys():
                    subelements['LHorasExtras'] = []
                hr = {
                    'Nvcom_cant': rvalue(line.quantity, 2),
                    'Nvcom_pago': rvalue(line.amount, 2),
                    'Nvhor_tipo': concept,
                    'Nvhor_porc': str(EXTRAS[concept]['percentaje'])
                }
                subelements['LHorasExtras'].append(hr)

            elif concept in WAGE_TYPE['Vacaciones']:
                if 'LVacaciones' not in subelements.keys():
                    subelements['LVacaciones'] = []
                if concept == 'VacacionesComunes':
                    for l in line.lines_payroll:
                        e = {
                            "Nvcom_cant": rvalue(l.quantity, 2),
                            "Nvcom_pago": rvalue(l.amount, 2),
                            "Nvvac_tipo": "1"
                        }
                        subelements['LVacaciones'].append(e)
                    if not line.lines_payroll:
                        e = {
                            "Nvcom_cant": rvalue(line.quantity, 2),
                            "Nvcom_pago": rvalue(line.amount, 2),
                            "Nvvac_tipo": "1"
                        }
                        subelements['LVacaciones'].append(e)
                else:
                    e = {
                        "Nvcom_cant": rvalue(line.quantity, 2),
                        "Nvcom_pago": rvalue(line.amount, 2),
                        "Nvvac_tipo": "2"
                    }
                    subelements['LVacaciones'].append(e)

            elif concept in WAGE_TYPE['Primas']:
                if 'Primas' not in subelements.keys():
                    subelements['Primas'] = {}
                if concept == 'PrimasS':
                    subelements['Primas']['Nvpri_cant'] = rvalue(
                        line.quantity, 2)
                    subelements['Primas']['Nvpri_pago'] = rvalue(
                        line.amount, 2)
                else:
                    subelements['Primas']['Nvpri_pagn'] = rvalue(
                        line.amount, 2)

            elif concept in WAGE_TYPE['Cesantias']:
                if 'Cesantias' not in subelements.keys():
                    subelements['Cesantias'] = {}
                if concept == 'Cesantias':
                    subelements['Cesantias']['Nvces_pago'] = rvalue(
                        line.amount, 2)
                else:
                    subelements['Cesantias']['Nvces_porc'] = '12.00'
                    subelements['Cesantias']['Nvces_pagi'] = rvalue(
                        line.amount, 2)

            elif concept in WAGE_TYPE['Incapacidades']:
                if 'LIncapacidades' not in subelements.keys():
                    subelements['LIncapacidades'] = []
                    for l in line.lines_payroll:
                        e = {
                            'Nvcom_fini': str(l.start_date),
                            'Nvcom_ffin': str(l.end_date),
                            'Nvcom_cant': rvalue(l.quantity, 2),
                            'Nvcom_pago': rvalue(l.amount, 2),
                            'Nvinc_tipo': TIPO_INCAPACIDAD[concept]
                        }
                        subelements['LIncapacidades'].append(e)

            elif concept in WAGE_TYPE['Licencias']:
                if 'LLicencias' not in subelements.keys():
                    subelements['LLicencias'] = []
                    for l in line.lines_payroll:
                        tipo = '3'
                        if concept == 'LicenciaMP':
                            tipo = '1'
                        if concept == 'LicenciaR':
                            tipo = '2'
                        e = {
                            'Nvcom_fini': str(l.start_date),
                            'Nvcom_ffin': str(l.end_date),
                            'Nvcom_cant': rvalue(l.quantity, 2),
                            'Nvlic_tipo': tipo
                        }
                        if concept != 'LicenciaNR':
                            e['Nvcom_pago'] = rvalue(l.amount, 2)
                        subelements['LLicencias'].append(e)

            elif concept in WAGE_TYPE['Bonificaciones']:
                if 'LBonificaciones' not in subelements.keys():
                    subelements['LBonificaciones'] = []
                if concept == 'BonificacionS':
                    e = {"Nvbon_bofs": rvalue(line.amount, 2)}
                else:
                    e = {"Nvbon_bons": rvalue(line.amount, 2)}
                subelements['LBonificaciones'].append(e)

            elif concept in WAGE_TYPE['Auxilios']:
                if 'LAuxilios' not in subelements.keys():
                    subelements['LAuxilios'] = []
                if concept == 'AuxilioS':
                    e = {'Nvaux_auxs': rvalue(line.amount, 2)}
                else:
                    e = {'Nvaux_auns': rvalue(line.amount, 2)}
                subelements['LAuxilios'].append(e)

            elif concept in WAGE_TYPE['HuelgasLegales']:
                if 'LHuelgasLegales' not in subelements.keys():
                    subelements['LHuelgasLegales'] = []
                e = {
                    "NVCOM_FINI": "9999-12-31",
                    "NVCOM_FFIN": "9999-12-31",
                    "NVCOM_CANT": "0"
                }
                subelements['LHuelgasLegales'].append(e)

            elif concept in WAGE_TYPE['OtrosConceptos']:
                if 'LOtrosConceptos' not in subelements.keys():
                    subelements['LOtrosConceptos'] = []
                e = {'Nvotr_desc': line.description}
                if concept == 'OtroConceptoS':
                    e['Nvotr_pags'] = rvalue(line.amount, 2)
                else:
                    e['Nvotr_pans'] = rvalue(line.amount, 2)
                subelements['LOtrosConceptos'].append(e)

            elif concept in WAGE_TYPE['Compensaciones']:
                if 'LCompensaciones' not in subelements.keys():
                    subelements['LCompensaciones'] = []
                if concept == 'CompensacionO':
                    e = {'Nvcom_como': rvalue(line.amount, 2)}
                else:
                    e = {'Nvcom_come': rvalue(line.amount, 2)}
                subelements['LCompensaciones'].append(e)

            elif concept in WAGE_TYPE['BonoEPCTVs']:
                if 'LBonoEPCTVs' not in subelements.keys():
                    subelements['LBonoEPCTVs'] = []
                if concept == 'PagoS':
                    e = {'Nvbon_pags': rvalue(line.amount, 2)}
                elif concept == 'PagoNS':
                    e = {'Nvbon_pans': rvalue(line.amount, 2)}
                elif concept == 'PagoAlimentacionS':
                    e = {'Nvbon_alis': rvalue(line.amount, 2)}
                else:
                    e = {'Nvbon_alns': rvalue(line.amount, 2)}
                subelements['LBonoEPCTVs'].append(e)

            elif concept in WAGE_TYPE['OtrosTag']:
                valor = rvalue(line.amount, 2)
                if concept == 'Comision':
                    if 'LComisiones' not in subelements.keys():
                        subelements['LComisiones'] = []
                    subelements['LComisiones'].append(valor)
                if concept == 'PagoTercero':
                    if 'LPagosTerceros' not in subelements.keys():
                        subelements['LPagosTerceros'] = []
                    subelements['LPagosTerceros'].append(valor)
                if concept == 'Anticipo':
                    if 'LAnticipos' not in subelements.keys():
                        subelements['LAnticipos'] = []
                    subelements['LAnticipos'].append(valor)

            elif concept in WAGE_TYPE['OtrosI']:
                valor = rvalue(line.amount, 2)
                if concept == 'Dotacion':
                    subelements['Dotacion'] = valor
                if concept == 'ApoyoSost':
                    subelements['ApoyoSostenimiento'] = valor
                if concept == 'Teletrabajo':
                    subelements['Teletrabajo'] = valor
                if concept == 'BonifRetiro':
                    subelements['BonificacionRetiro'] = valor
                if concept == 'Indemnizacion':
                    subelements['Indemnización'] = valor
                if concept == 'Reintegro':
                    subelements['Reintegro'] = valor

        return subelements

    # DEDUCCIONES
    def _get_deductions(self, line_deductions):
        subelements = {}

        subelements['Salud'] = {"Nvsal_porc": "0", "Nvsal_dedu": "0"}

        subelements['FondoPension'] = {"Nvfon_porc": "0", "Nvfon_dedu": "0"}

        for line in line_deductions:
            concept = line.wage_type.type_concept_electronic

            if concept == 'Salud':
                p = line.wage_type.unit_price_formula.split('*')
                p = Decimal(p[1].strip()) * 100
                subelements['Salud']["Nvsal_porc"] = str(p)
                subelements['Salud']["Nvsal_dedu"] = rvalue(line.amount, 2)

            elif concept == 'FondoPension':
                p = line.wage_type.unit_price_formula.split('*')
                p = Decimal(p[1].strip()) * 100
                subelements['FondoPension']["Nvfon_porc"] = str(p)
                subelements['FondoPension']["Nvfon_dedu"] = rvalue(
                    line.amount, 2)

            elif concept in WAGE_TYPE['FondoSP']:
                if 'FondoSP' not in subelements.keys():
                    subelements['FondoSP'] = {}
                p = line.wage_type.unit_price_formula.split('*')
                p = Decimal(p[1].strip()) * 100
                valor = rvalue(line.amount, 2)
                if concept == 'FondoSP':
                    subelements['FondoSP']['Nvfsp_porc'] = str(p)
                    subelements['FondoSP']['Nvfsp_dedu'] = valor
                else:
                    subelements['FondoSP']['Nvfsp_posb'] = str(p)
                    subelements['FondoSP']['Nvfsp_desb'] = valor

            elif concept in WAGE_TYPE['Sindicatos']:
                if 'LSindicatos' not in subelements.keys():
                    subelements['LSindicatos'] = []
                p = line.wage_type.unit_price_formula.split('*')
                p = Decimal(p[1].strip()) * 100
                e = {
                    "Nvsin_porc": str(p),
                    "Nvsin_dedu": rvalue(line.amount, 2)
                }
                subelements['LSindicatos'].append(e)

            elif concept in WAGE_TYPE['Sanciones']:
                if 'LSanciones' not in subelements.keys():
                    subelements['LSanciones'] = []
                if concept == 'SancionPublic':
                    e = {'Nvsan_sapu': rvalue(line.amount, 2)}
                else:
                    e = {'Nvsan_sapv': rvalue(line.amount, 2)}
                subelements['LSanciones'].append(e)

            elif concept in WAGE_TYPE['Libranzas']:
                if 'LLibranzas' not in subelements.keys():
                    subelements['LLibranzas'] = []
                e = {
                    "Nvlib_desc": line.description,
                    "Nvlib_dedu": rvalue(line.amount, 2)
                }
                subelements['LLibranzas'].append(e)

            elif concept in WAGE_TYPE['OtrosTag']:
                valor = rvalue(line.amount, 2)
                if concept == 'PagoTercero':
                    if 'LPagosTerceros' not in subelements.keys():
                        subelements['LPagosTerceros'] = []
                    subelements['LPagosTerceros'].append(valor)
                if concept == 'Anticipo':
                    if 'LAnticipos' not in subelements.keys():
                        subelements['LAnticipos'] = []
                    subelements['LAnticipos'].append(valor)

            elif concept == 'OtraDeduccion':
                if 'LOtrasDeducciones' not in subelements.keys():
                    subelements['LOtrasDeducciones'] = []
                subelements['LOtrasDeducciones'].append(rvalue(line.amount, 2))

            elif concept in WAGE_TYPE['OtrosD']:
                'PensionVoluntaria', 'RetencionFuente', 'AFC', 'Cooperativa', 'EmbargoFiscal', 'PlanComplementario', 'Educacion', 'Reintegro', 'Deuda'
                valor = rvalue(line.amount, 2)
                if concept == 'PensionVoluntaria':
                    subelements['PensionVoluntaria'] = valor
                if concept == 'RetencionFuente':
                    subelements['RetencionFuente'] = valor
                if concept == 'AFC':
                    subelements['AhorroFomentoConstr'] = valor
                if concept == 'Cooperativa':
                    subelements['Cooperativa'] = valor
                if concept == 'EmbargoFiscal':
                    subelements['EmbargoFiscal'] = valor
                if concept == 'PlanComplementario':
                    subelements['PlanComplementarios'] = valor
                if concept == 'Educacion':
                    subelements['Educación'] = valor
                if concept == 'Reintegro':
                    subelements['Reintegro'] = valor
                if concept == 'Deuda':
                    subelements['Deuda'] = valor

        return subelements

    def _get_total(self):
        DevengadosTotal = rvalue(self.payroll.gross_payments, 2)
        DeduccionesTotal = rvalue(self.payroll.total_deductions, 2)
        ComprobanteTotal = rvalue(self.payroll.net_payment, 2)
        return DevengadosTotal, DeduccionesTotal, ComprobanteTotal


#----------------------------------------------- MAKE ELECTRONIC payroll------------------------------------------------------

    def make(self, type):
        nom = {}
        if type == '102':  #Nomina individua
            nom.update(self._get_sequence())
            gross, deductions, net_payment = self._get_total()
            nom["Nvnom_devt"] = gross
            nom["Nvnom_dedt"] = deductions
            nom["Nvnom_comt"] = net_payment
            nom["Nvnom_fpag"] = self._get_pay_date()
            nom["Periodo"] = self._get_payroll_period()
            nom["InformacionGeneral"] = self._get_general_information()
            #nom["LNotas"] = [self._get_notes()]
            nom["Empleador"] = self._get_information_company()
            nom["Trabajador"] = self._get_information_employee()
            nom["Pago"] = self._get_payment_terms()
            acrueds, deductions = self._get_lines()
            nom["Devengados"] = acrueds
            nom["Deducciones"] = deductions

        elif type == '103':  #Nomina individual de ajuste
            nom.update(self._get_sequence())
            type_note = self._get_type_note()
            if type_note == '1':
                gross, deductions, net_payment = self._get_total()
                nom["Nvnom_devt"] = gross
                nom["Nvnom_dedt"] = deductions
                nom["Nvnom_comt"] = net_payment
                nom["Nvnom_fpag"] = self._get_pay_date()
                nom["Nvnom_tipo"] = type_note
                nom["Predecesor"] = self._get_predecessor()
                nom["Periodo"] = self._get_payroll_period()
                nom["InformacionGeneral"] = self._get_general_information()
                #nom["LNotas"] = [self._get_notes()]
                nom["Empleador"] = self._get_information_company()
                nom["Trabajador"] = self._get_information_employee()
                nom["Pago"] = self._get_payment_terms()
                acrueds, deductions = self._get_lines()
                nom["Devengados"] = acrueds
                nom["Deducciones"] = deductions

            elif type_note == '2':
                nom["Nvnom_tipo"] = type_note
                nom["Predecesor"] = self._get_predecessor()
                nom["InformacionGeneral"] = self._get_general_information()
                #nom["LNotas"] = [self._get_notes()]
                nom["Empleador"] = self._get_information_company()

        #data = json.dumps(nom, indent=4)
        #print(nom)
        return nom
