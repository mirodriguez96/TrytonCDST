#!/usr/bin/python
#! -*- coding: utf8 -*-
import json
from builder_phase import ElectronicPayroll
#import xmltodict
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
        xml_payroll = ec_payroll.make(self.payroll.payroll_type)

        self._send_noova(xml_payroll)


    # Consumo API noova
    def _send_noova(self, dict):
        #Validamos que los datos del proveedor tecnologico este completo
        if self.payroll.company.url_supplier and self.payroll.company.auth_supplier and self.payroll.company.url_supplier_test and self.payroll.company.host_supplier and self.payroll.company.supplier_code:
            #Se valida en que entorno (prueba o producción) se va ha enviar la nómina
            if self.config.environment == '1':
                url = self.payroll.company.url_supplier
            if self.config.environment == '2':
                url = self.payroll.company.url_supplier_test
            auth = self.payroll.company.auth_supplier
            host = self.payroll.company.host_supplier
            sucode = self.payroll.company.supplier_code
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
        data = self._create_json_noova(dict, sucode)
        print(url)
        #print(header)
        print(data)
        response = requests.post(url, headers=header, data=data)
        if response.status_code == 200:
            print(type(response.text))
            res = json.loads(response.text)
            print(res)
            self.payroll.xml_payroll = data.encode('utf8')
            electronic_state = 'rejected'
            if res['Result'] == '0':
                electronic_state = 'authorized'
            self.payroll.electronic_state = electronic_state
            self.payroll.cune = res['Cune']
            self.payroll.electronic_message = res['Description']
            self.payroll.rules_fail = res['ErrorList']
            self.payroll.save()
            # return response
            print("ENVIO EXITOSO DE NOMINA")
        else:
            self.payroll.get_message(response.text)


    #Funcion encargada de crear el archivo json con los datos que se le envian al proveedor tecnologico (noova)
    def _create_json_noova(self, dict, sucode):
        dict_res = dict
        noova = {
            "Nvsuc_codi": sucode, # Código de la sucursal configurada en Noova
            "Nvnom_pref": dict_res["NumeroSecuenciaXML"]["Prefijo"], #prefijo de nomina
            "Nvnom_cons": dict_res["NumeroSecuenciaXML"]["Consecutivo"], #consecutivo para la nomina
            "Nvnom_nume": dict_res["NumeroSecuenciaXML"]["Numero"], #Es la union del prefijo y consecutivo
            "Nvope_tipo": "NM", #Tipo de operación nómina (siempre debe ir "NM")
            #"Nvnom_redo": "", #Se utiliza para cuando se utilice el redondeo en el Documento
            #"Nvnom_devt": dict_res["DevengadosTotal"],
            #"Nvnom_dedt": dict_res["DeduccionesTotal"],
            #"Nvnom_comt": dict_res["ComprobanteTotal"],
            #"Nvnom_fpag": dict_res["FechasPagos"]["FechaPago"][0],
            #"Nvnom_cnov": "", #Duda
            #"Periodo": { #
            #    "Nvper_fing": dict_res["Periodo"]["FechaIngreso"],
            #    #"Nvper_fret": "2020-12-31", #fecha retiro nomina
            #    "Nvper_fpin": dict_res["Periodo"]["FechaLiquidacionInicio"],
            #    "Nvper_fpfi": dict_res["Periodo"]["FechaLiquidacionFin"],
            #    "Nvper_tlab": dict_res["Periodo"]["TiempoLaborado"]
            #},
            "InformacionGeneral": { #
                "Nvinf_tnom": self.payroll.payroll_type,
                #"Nvinf_pnom": dict_res["InformacionGeneral"]["PeriodoNomina"],
                #"Nvinf_tmon": dict_res["InformacionGeneral"]["TipoMoneda"],
                #"Nvinf_mtrm": dict_res["InformacionGeneral"]["TRM"] #Tasa Representativa del mercado
            },
            #"LNotas": [
            #    ""
            #],
            "Empleador": {#
                "Nvemp_nomb": dict_res["Empleador"]["RazonSocial"],
                #"Nvemp_pape": dict_res["Empleador"]["PrimerApellido"],#opcional
                #"Nvemp_sape": dict_res["Empleador"]["SegundoApellido"],#opcional
                #"Nvemp_pnom": dict_res["Empleador"]["PrimerNombre"],#opcional
                #"Nvemp_onom": dict_res["Empleador"]["OtrosNombres"],#opcional
                "Nvemp_nnit": dict_res["Empleador"]["NIT"],
                "Nvemp_endv": dict_res["Empleador"]["DV"],
                "Nvemp_pais": dict_res["Empleador"]["Pais"],
                "Nvemp_depa": dict_res["Empleador"]["DepartamentoEstado"],
                "Nvemp_ciud": dict_res["Empleador"]["MunicipioCiudad"],
                "Nvemp_dire": dict_res["Empleador"]["Direccion"]
            },
            #"Trabajador": {#
            #    "Nvtra_tipo": dict_res["Trabajador"]["TipoTrabajador"],
            #    "Nvtra_stip": dict_res["Trabajador"]["SubTipoTrabajador"],
            #    "Nvtra_arpe": dict_res["Trabajador"]["AltoRiesgoPension"],
            #    "Nvtra_dtip": dict_res["Trabajador"]["TipoDocumento"],
            #    "Nvtra_ndoc": dict_res["Trabajador"]["NumeroDocumento"],
            #    "Nvtra_pape": dict_res["Trabajador"]["PrimerApellido"],
            #    "Nvtra_sape": dict_res["Trabajador"]["SegundoApellido"],
            #    "Nvtra_pnom": dict_res["Trabajador"]["PrimerNombre"],
            #    #"Nvtra_onom": dict_res["Trabajador"]["OtrosNombres"],
            #    "Nvtra_ltpa": dict_res["Trabajador"]["LugarTrabajoPais"],
            #    "Nvtra_ltde": dict_res["Trabajador"]["LugarTrabajoDepartamentoEstado"],
            #    "Nvtra_ltci": dict_res["Trabajador"]["LugarTrabajoMunicipioCiudad"],
            #    "Nvtra_ltdi": dict_res["Trabajador"]["LugarTrabajoDireccion"],
            #    "Nvtra_sint": dict_res["Trabajador"]["SalarioIntegral"],
            #    "Nvtra_tcon": dict_res["Trabajador"]["TipoContrato"],
            #    "Nvtra_suel": dict_res["Trabajador"]["Sueldo"],
            #    "Nvtra_codt": dict_res["Trabajador"]["CodigoTrabajador"]
            #},
            #"Pago": {#
            #    "Nvpag_form": dict_res["Pago"]["Forma"],
            #    "Nvpag_meto": dict_res["Pago"]["Metodo"],
            #    #"Nvpag_banc": dict_res["Pago"]["Banco"], #Validar
            #    #"Nvpag_tcue": dict_res["Pago"]["TipoCuenta"],
            #    #"Nvpag_ncue": dict_res["Pago"]["NumeroCuenta"]
            #},
            #"Devengados": {
                #"Basico": {#OBLIGATORIO
                #    "Nvbas_dtra": dict_res["Devengados"]["Basico"]["DiasTrabajados"],
                #    "Nvbas_stra": dict_res["Devengados"]["Basico"]["SueldoTrabajado"]
                #},
                #"LHorasExtras": [
                #    {
                #        "Nvcom_fini": "2020-12-01T19:00:00",
                #        "Nvcom_ffin": "2020-12-01T21:00:00",
                #        "Nvcom_cant": "2",
                #        "Nvcom_pago": "180000.00",
                #        "Nvhor_tipo": "HEN",
                #        "Nvhor_porc": "75.00"
                #    }
                #],
                #"LVacaciones": [
                #    {
                #        "Nvcom_fini": "2020-12-05",
                #        "Nvcom_ffin": "2020-12-07",
                #        "Nvcom_cant": "2",
                #        "Nvcom_pago": "200000.00",
                #        "Nvvac_tipo": "1"
                #    }
                #],
                #"Primas": {
                #    "Nvpri_cant": "30",
                #    "Nvpri_pago": "75000.00",
                #    "Nvpri_pagn": "10000.00"
                #},
                #"Cesantias": {
                #    "Nvces_pago": "35000.00",
                #    "Nvces_porc": "2.00",
                #    "Nvces_pagi": "6000.00"
                #},
                #"LIncapacidades": [
                #    {
                #        "Nvcom_fini": "2020-12-10",
                #        "Nvcom_ffin": "2020-12-12",
                #        "Nvcom_cant": "2",
                #        "Nvcom_pago": "180000.00",
                #        "Nvinc_tipo": "2"
                #    }
                #],
                #"LLicencias": [
                #    {
                #        "Nvcom_fini": "2020-12-01",
                #        "Nvcom_ffin": "2020-12-05",
                #        "Nvcom_cant": "4",
                #        "Nvcom_pago": "360000.00",
                #        "Nvlic_tipo": "1"
                #    }
                #],
                #"LHuelgasLegales": [
                #    {
                #        "Nvcom_fini": "2020-12-05",
                #        "Nvcom_ffin": "2020-12-06",
                #        "Nvcom_cant": "1",
                #        "Nvcom_pago": "90000.00"
                #    }
                #],
                #"LAnticipos": [
                #    "20500.00",
                #    "12300.00",
                #],
            #},
            #"Deducciones": {
                #"Salud": {#OBLIGATORIO
                    #"Nvsal_porc": dict_res["Deducciones"]["Salud"]["Porcentaje"],
                    #"Nvsal_dedu": dict_res["Deducciones"]["Salud"]["Deduccion"]
                #},
                #"FondoPension": {#
                #    "Nvfon_porc": "4.00",
                #    "Nvfon_dedu": "40000.00"
                #},
                #"FondoSP": {
                #    "Nvfsp_porc": "1.00",
                #    "Nvfsp_dedu": "25500.00",
                #    "Nvfsp_posb": "1.00",
                #    "Nvfsp_desb": "10000.00"
                #},
                #"LSindicatos": [
                #    {
                #        "Nvsin_porc": "4.00",
                #        "Nvsin_dedu": "40000.00"
                #    }
                #],
                #"LPagosTerceros": [
                #    "20500.00",
                #    "12300.00",
                #],
                #"PensionVoluntaria": "33000.00"
            #}
        }
        data_val = self._validate_data(dict_res, noova)
        data = json.dumps(data_val, indent=4)
        return data


    #Esta funcion se encarga de validar los datos que no son obligatorios en Tryton pero que hacen parte de la nomina a enviar
    #Recibe como entrada dos diccionarios. el primero es el diccionario con los valores de tryton y el segundo es el diccionario con los valores a enviar a noova
    #Devuelve el diccionario con los nuevos campos para enviar a noova
    def _validate_data(self, dic, noova):

        

        if self.payroll.payroll_type == '103':
            noova["Nvnom_tipo"] = self.payroll.type_note

            noova["Predecesor"] = {
                "Nvpre_nume": dic["Predecesor"]["NumeroPred"],
                "Nvpre_cune": dic["Predecesor"]["CUNEPred"],
                "Nvpre_fgen": dic["Predecesor"]["FechaGenPred"]
            }

            if self.payroll.type_note == '2':
                return noova
    
        noova["Nvnom_devt"] = dic["DevengadosTotal"]
        noova["Nvnom_dedt"] = dic["DeduccionesTotal"]
        noova["Nvnom_comt"] = dic["ComprobanteTotal"]

        lfpag = len(dic["FechasPagos"]["FechaPago"])
        noova["Nvnom_fpag"] = dic["FechasPagos"]["FechaPago"][lfpag-1]

        noova["Periodo"] = {
            "Nvper_fing": dic["Periodo"]["FechaIngreso"],
            #"Nvper_fret": "2020-12-31", #fecha retiro nomina
            "Nvper_fpin": dic["Periodo"]["FechaLiquidacionInicio"],
            "Nvper_fpfi": dic["Periodo"]["FechaLiquidacionFin"],
            "Nvper_tlab": dic["Periodo"]["TiempoLaborado"]
        }

        noova["InformacionGeneral"]["Nvinf_pnom"] = dic["InformacionGeneral"]["PeriodoNomina"]
        noova["InformacionGeneral"]["Nvinf_tmon"] = dic["InformacionGeneral"]["TipoMoneda"]
        #"Nvinf_mtrm": dict_res["InformacionGeneral"]["TRM"] #Tasa Representativa del mercado

        noova["Trabajador"] = {
            "Nvtra_tipo": dic["Trabajador"]["TipoTrabajador"],
            "Nvtra_stip": dic["Trabajador"]["SubTipoTrabajador"],
            "Nvtra_arpe": dic["Trabajador"]["AltoRiesgoPension"],
            "Nvtra_dtip": dic["Trabajador"]["TipoDocumento"],
            "Nvtra_ndoc": dic["Trabajador"]["NumeroDocumento"],
            "Nvtra_pape": dic["Trabajador"]["PrimerApellido"],
            "Nvtra_sape": dic["Trabajador"]["SegundoApellido"],
            "Nvtra_pnom": dic["Trabajador"]["PrimerNombre"],
            #"Nvtra_onom": dic["Trabajador"]["OtrosNombres"],
            "Nvtra_ltpa": dic["Trabajador"]["LugarTrabajoPais"],
            "Nvtra_ltde": dic["Trabajador"]["LugarTrabajoDepartamentoEstado"],
            "Nvtra_ltci": dic["Trabajador"]["LugarTrabajoMunicipioCiudad"],
            "Nvtra_ltdi": dic["Trabajador"]["LugarTrabajoDireccion"],
            "Nvtra_sint": dic["Trabajador"]["SalarioIntegral"],
            "Nvtra_tcon": dic["Trabajador"]["TipoContrato"],
            "Nvtra_suel": dic["Trabajador"]["Sueldo"],
            "Nvtra_codt": dic["Trabajador"]["CodigoTrabajador"]
        }

        noova["Pago"] = {
            "Nvpag_form": dic["Pago"]["Forma"],
            "Nvpag_meto": dic["Pago"]["Metodo"],
            #"Nvpag_banc": dic["Pago"]["Banco"], #Validar
            #"Nvpag_tcue": dic["Pago"]["TipoCuenta"],
            #"Nvpag_ncue": dic["Pago"]["NumeroCuenta"]
        }

        noova["Devengados"] = {
            "Basico": {#OBLIGATORIO
                    "Nvbas_dtra": dic["Devengados"]["Basico"]["DiasTrabajados"],
                    "Nvbas_stra": dic["Devengados"]["Basico"]["SueldoTrabajado"]
                }
        }

        noova["Deducciones"] = {
            "Salud": {}
        }

        #Si el contrato es de aprendiz, su valor es 0 en salud
        if dic["Trabajador"]["TipoContrato"] == 'learning':
            noova["Deducciones"]["Salud"]["Nvsal_porc"] = '0'
            noova["Deducciones"]["Salud"]["Nvsal_dedu"] = '0'
        else:
            noova["Deducciones"]["Salud"]["Nvsal_porc"] = dic["Deducciones"]["Salud"]["Porcentaje"]
            noova["Deducciones"]["Salud"]["Nvsal_dedu"] = dic["Deducciones"]["Salud"]["Deduccion"]

        if "Notas" in dic.keys():
           noova["LNotas"] = [dic["Notas"]]
        
        if self.payroll.employee.party.second_name:
            noova["Trabajador"]["Nvtra_onom"] = dic["Trabajador"]["OtrosNombres"]
        
        if self.payroll.bank_payment:
            noova["Pago"]["Nvpag_banc"] = dic["Pago"]["Banco"]
            noova["Pago"]["Nvpag_tcue"] = dic["Pago"]["TipoCuenta"]
            noova["Pago"]["Nvpag_ncue"] = dic["Pago"]["NumeroCuenta"]
        
        if "HEDs" in dic["Devengados"].keys():
            horas = []
            for h in dic["Devengados"]["HEDs"]:
                val = {
                    #"Nvcom_fini": h["FechaInicio"], #OPCIONAL
                    #"Nvcom_ffin": h["FechaFin"], #OPCIONAL
                    "Nvcom_cant": dic["Devengados"]["HEDs"][h]["Cantidad"],
                    "Nvcom_pago": dic["Devengados"]["HEDs"][h]["Pago"],
                    "Nvhor_tipo": h,
                    "Nvhor_porc": dic["Devengados"]["HEDs"][h]["Porcentaje"]
                }
                horas.append(val)
            noova["Devengados"]["LHorasExtras"] = horas

        if "Vacaciones" in dic["Devengados"].keys():
            data = []
            for h in dic["Devengados"]["Vacaciones"]:
                if h == "VacacionesComunes":
                    val = {
                        #"Nvcom_fini": dic["Devengados"]["Vacaciones"][h]["FechaInicio"], #OPCIONAL
                        #"Nvcom_ffin": dic["Devengados"]["Vacaciones"][h]["FechaFin"], #OPCIONAL
                        "Nvcom_cant": dic["Devengados"]["Vacaciones"][h]["Cantidad"],
                        "Nvcom_pago": dic["Devengados"]["Vacaciones"][h]["Pago"],
                        "Nvvac_tipo": "1"
                    }
                else:
                    val = {
                        "Nvcom_cant": dic["Devengados"]["Vacaciones"][h]["Cantidad"],
                        "Nvcom_pago": dic["Devengados"]["Vacaciones"][h]["Pago"],
                        "Nvvac_tipo": "2"
                    }
                data.append(val)
            noova["Devengados"]["LVacaciones"] = data

        if "Primas" in dic["Devengados"].keys():
            if "PrimasS" in dic["Devengados"]["Primas"].keys():
                val = {
                    "Nvpri_cant": dic["Devengados"]["Primas"]["Cantidad"],
                    "Nvpri_pago": dic["Devengados"]["Primas"]["Pago"]
                }
                noova["Devengados"]["Primas"] = val
            if "PagoNs" in dic["Devengados"]["Primas"].keys():
                val = {
                    "Nvpri_pagn": dic["Devengados"]['Primas']["PagoNs"]
                }
                if "Primas" in noova["Devengados"].keys():
                    noova["Devengados"]["Primas"]["Nvpri_pagn"] = dic["Devengados"]['Primas']["PagoNs"]
                else:
                    noova["Devengados"]["Primas"] = val

        if "Cesantias" in dic["Devengados"].keys():
            if "IntCesantias" in dic["Devengados"]["Cesantias"].keys():
                val = {
                    "Nvces_porc": dic["Devengados"]["Cesantias"]["Porcentaje"],
                    "Nvces_pagi": dic["Devengados"]["Cesantias"]["IntCesantias"]
                }
            else:
                val = {
                    "Nvces_pago": dic["Devengados"]["Cesantias"]["Cesantias"]
                }
            noova["Devengados"]["Cesantias"] = val

        if "Incapacidades" in dic["Devengados"].keys():
            horas = []
            for h in dic["Devengados"]["Incapacidades"]:
                val = {
                    "Nvcom_fini": dic["Devengados"]["Incapacidades"][h]["FechaInicio"],
                    "Nvcom_ffin": dic["Devengados"]["Incapacidades"][h]["FechaFin"],
                    "Nvcom_cant": dic["Devengados"]["Incapacidades"][h]["Cantidad"],
                    "Nvcom_pago": dic["Devengados"]["Incapacidades"][h]["Pago"],
                    "Nvinc_tipo": dic["Devengados"]["Incapacidades"][h]["Tipo"]
                }
                horas.append(val)
            noova["Devengados"]["LIncapacidades"] = horas

        if "Licencias" in dic["Devengados"].keys():
            data = []
            for h in dic["Devengados"]["Licencias"]:
                val = {
                    "Nvcom_fini": dic["Devengados"]["Licencias"][h]["FechaInicio"],
                    "Nvcom_ffin": dic["Devengados"]["Licencias"][h]["FechaFin"],
                    "Nvcom_cant": dic["Devengados"]["Licencias"][h]["Cantidad"],
                    "Nvcom_pago": dic["Devengados"]["Licencias"][h]["Pago"]
                }
                if "LicenciaMP" == h:
                    val["Nvlic_tipo"] = "1"
                elif "LicenciaR" == h:
                    val["Nvlic_tipo"] = "2"
                elif "LicenciaNR" == h:
                    val["Nvlic_tipo"] = "3"
                data.append(val)
            noova["Devengados"]["LLicencias"] = data

        if "OtrosTag" in dic["Devengados"].keys():
            data = []
            for h in dic["Devengados"]["OtrosTag"]:
                data.append(dic["Devengados"]["OtrosTag"][h])
            noova["Devengados"]["LAnticipos"] = data
        
        if "FondoPension" in dic["Deducciones"].keys():
            val = {
                "Nvfon_porc": dic["Deducciones"]["FondoPension"]["Porcentaje"],
                "Nvfon_dedu": dic["Deducciones"]["FondoPension"]["Deduccion"]
            }
            noova["Deducciones"]["FondoPension"] = val

        if "FondoSP" in dic["Deducciones"].keys():
            print(dic["Deducciones"]["FondoSP"])
            if "FondoSPSUB" in dic["Deducciones"]["FondoSP"]:
                val = {
                    "Nvfsp_posb": dic["Deducciones"]["FondoSP"]["FondoSPSUB"]["Porcentaje"],
                    "Nvfsp_desb": dic["Deducciones"]["FondoSP"]["FondoSPSUB"]["Deduccion"]
                }
            else:
                val = {
                    "Nvfsp_porc": dic["Deducciones"]["FondoSP"]["FondoSP"]["Porcentaje"],
                    "Nvfsp_dedu": dic["Deducciones"]["FondoSP"]["FondoSP"]["Deduccion"]
                }
            noova["Deducciones"]["FondoSP"] = val

        if "Sindicatos" in dic["Deducciones"].keys():
            if "Sindicato" in dic["Deducciones"]["Sindicatos"].keys():
                val = {
                    "Nvsin_porc": dic["Deducciones"]["Sindicatos"]["Sindicato"]["Porcentaje"],
                    "Nvsin_dedu": dic["Deducciones"]["Sindicatos"]["Sindicato"]["Deduccion"]
                }
        #Se pregunta si en la nómina hay otras deducciones y se agregan en caso de haber.
        if "OtrosD" in dic["Deducciones"].keys():
            data = []
            for od in dic["Deducciones"]["OtrosD"]:
                if dic["Deducciones"]["OtrosD"][od] == "PensionVoluntaria":
                    noova["Deducciones"]["PensionVoluntaria"] = dic["Deducciones"]["OtrosD"][od]
                else:
                    data.append(dic["Deducciones"]["OtrosD"][od])
            noova["Deducciones"]["LOtrasDeducciones"] = data

        #SE RETORNA EL DICCIONARIO PARA NOOVA CON LOS CAMPOS NUEVOS
        return noova
