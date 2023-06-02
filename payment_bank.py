# This file is part of Tryton.  The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.
from trytond.report import Report
from trytond.model import (ModelView, fields)
from trytond.transaction import Transaction
from trytond.wizard import Wizard, StateView, Button, StateReport
from trytond.pool import Pool
from trytond.model.exceptions import ValidationError


BANCOS = {
'BANCAMIA S.A.'	:	'1059',
'BANCO AGRARIO'	:	'1040',
'BANCO AV VILLAS'	:	'1052',
'BANCO CAJA SOCIAL BCSC SA'	:	'1032'	,
'BANCO COLPATRIA'	:	'1019'	,
'BANCO DAVIVIENDA SA'	:	'1051'	,
'BANCO DE BOGOTA'	:	'1001'	,
'BANCO  DE  OCCIDENTE S.A.'	:	'1023'	,
'BANCO FALABELLA S.A.'	:	'1062'	,
'BANCO FINANDINA S.A.'	:	'1063'	,
'BANCO GNB SUDAMERIS S.A.'	:	'1012'	,
'BANCO MUNDO MUJER S.A.'	:	'1047'	,
'BANCO PICHINCHA S.A.'	:	'1060'	,
'BANCO POPULAR S.A.'	:	'1002'	,
'BANCO SANTANDER DE NEGOCIOS COLOMBIA S. A'	:	'1065'	,
'BANCO SERFINANZA S.A'	:	'1069'	,
'BANCO W S.A.'	:	'1053'	,
'BANCOLOMBIA'	:	'1007'	,
'BANCOOMEVA'	:	'1061'	,
'BBVA COLOMBIA'	:	'1013'	,
'CITIBANK'	:	'1009'	,

}

BENEFICIARY_TYPE = {
'12' : '4',
'13' : '1',
'21' : '2',
'31' : '3',
'41' : '5',
}

TRANSACTION_TYPE = {
'23' :'Pre-notificación cuenta corriente',
'25': 'Pago en efectivo',
'27': 'Abono a cuenta corriente',
'33': 'Pre-notificación cuenta ahorros',
'36': 'Pago Cheque Gerencia',
'37': 'Abono a cuenta de ahorros',
'40': 'Efectivo seguro/Tarjeta prepago',
'52': 'Abono a depósito electrónico',
'53': 'Pre-notificación depósito electrónico'
}


class PaymentBankGroupStart(ModelView):
    'Payment Bank Group Start'
    __name__ = 'account.payment_bank.start'
    company = fields.Many2One('company.company', 'Company', required=True)
    report = fields.Many2One('ir.action.report', 'Report',
            domain=[('report_name', 'ilike', 'account.payment_bank%')], required=True)
    @staticmethod
    def default_company():
        return Transaction().context.get('company')


class PaymentBankGroup(Wizard):
    'Payment Bank Group'
    __name__ = 'account.payment_bank'
    start = StateView('account.payment_bank.start',
        'conector.payment_bank_start_view_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Print', 'print_', 'tryton-ok', default=True),
        ])
    print_ = StateReport('account.payment_bank.report')

    def do_print_(self, action):
        data = {
            'ids': Transaction().context.get('active_ids'),
            'company': self.start.company.id,
            'report': self.start.report.id,
        }

        action['report'] = self.start.report.report
        action['report_name'] = self.start.report.report_name
        action['id'] = self.start.report.id
        action['action'] = self.start.report.action.id
        return action, data

    def transition_print_(self):
        return 'end'


class PaymentBankGroupReport(Report):
    __name__ = 'account.payment_bank.report'

    @classmethod
    def get_context(cls, records, header, data):
        report_context = super().get_context(records, header,  data)
        pool = Pool()
        Code_bank = pool.get('bank')
        PaymentGroup = pool.get('account.payment.group')
        Payment = pool.get('account.payment')
        Company = pool.get('company.company')
        Banks = Code_bank.search([])

        for i in PaymentGroup.browse(data['ids']):
            if not i.payment_amount_succeeded:
                raise ValidationError(message=None, description= f"El pago numero {i.id} no tiene pago con exito")
            elif not i.payment_complete:
                raise ValidationError(message=None, description= f"El pago numero {i.id} no tiene pagos completados")
            
            domain = [
                ('company', '=', data['company']),
                ('group', 'in', data['ids']),
                ('state', '=', 'succeeded')
            ]
            fields_names = [
                'party.id_number', 'party.name', 'amount', 'party.bank_name',
                'party.bank_account', 'party.bank_account_type', 'party.type_document'
            ]
            records = Payment.search_read(domain, fields_names=fields_names)
            company = Company.search_read([('id', '=', data['company'])],
                fields_names=['party.id_number', 'party.bank_account',
                'party.bank_account_type', 'party.name', 'party.bank_name'])

            party_amount = 0
            record_dict = {}
            for rec in records:
                record_dict[party_amount] = {
                        'party' : rec['party.']['id'],
                        'amount': rec['amount'],
                        'party_name': rec['party.']['name'],
                        'id_number': rec['party.']['id_number'],
                        'type_document': rec['party.']['type_document'],
                        'bank_name': rec['party.']['bank_name'],
                        'bank_account': rec['party.']['bank_account'],
                        'bank_account_type': rec['party.']['bank_account_type'],
                        'code_bank' : '',
                        'beneficiary_type': ''
                    }
                for i in Banks:
                    if i.party.rec_name == record_dict[party_amount]['bank_name']:
                        record_dict[party_amount]['code_bank'] = i.bank_code_sap
                        break
                    else:
                        raise ValidationError(message=None, description= f"El tercero {rec['party.']['name']} no tiene una cuenta de banco asociado")
                for i in BENEFICIARY_TYPE.keys():
                    if  i == record_dict[party_amount]['type_document']:
                        record_dict[party_amount]['beneficiary_type'] = BENEFICIARY_TYPE.get(i)
                        break
                if record_dict[party_amount]['beneficiary_type'] == '':
                        raise ValidationError(message=None, description="")

                party_amount += 1
                
                
        report_context['records'] = record_dict.values()
        report_context['company'] = company[0]
        return report_context



###############################  REPORTS  ##############################



class BankReportBancolombia(PaymentBankGroupReport):
    __name__ = 'account.payment_bank.report_bancolombia'

# class BankReportBancamia(PaymentBankGroupReport):
#     __name__ = 'account.payment_bank.report_bancamia'