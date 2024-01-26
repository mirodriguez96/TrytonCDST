# This file is part of Tryton.  The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.
from stdnum import iban, bic
from trytond.report import Report
from trytond.model import (ModelView, fields, ModelSQL, Unique)
from trytond.transaction import Transaction
from trytond.wizard import Wizard, StateView, Button, StateReport
from trytond.pool import Pool, PoolMeta
from trytond.model.exceptions import ValidationError
from trytond.pyson import Eval
from decimal import Decimal

TYPE_TRANSACTION_GET = {
    '01': 'Cuenta por Defecto',
    '25': 'Pago en efectivo',
    '27': 'Abono a cuenta corriente',
    '36': 'Pago cheque gerencia',
    '37': 'Abono a cuenta de ahorros',
    '40': 'Efectivo seguro (visa pagos o tarjeta prepago)',
}

_TYPES_BANK_ACCOUNT = {
    'Cuenta de Ahorros': 'S',
    'Cuenta Corriente': 'D',
}

BENEFICIARY_TYPE = {
    '12': '4',
    '13': '1',
    '21': '2',
    '31': '3',
    '41': '5',
}
_TYPES_PAYMENT = [
    ('220', ' Pago a Proveedores'), ('225', 'Pago de Nómina'),
    ('238', 'Pagos Terceros'), ('239', 'Abono Obligaciones con el Banco'),
    ('240', 'Pagos Cuenta Maestra'), ('250', 'Subsidios'),
    ('320', 'Credipago a Proveedores'), ('325', 'Credipago Nómina'),
    ('820', 'Pago Nómina Efectivo (Pago desde Transporte de Efectivo)'),
    ('920', 'Pago Proveedores Efectivo (Pago desde Transporte de Efectivo)')
]

TRANSACTION_TYPE = {
    '23': 'Pre-notificación cuenta corriente',
    '25': 'Pago en efectivo',
    '27': 'Abono a cuenta corriente',
    '33': 'Pre-notificación cuenta ahorros',
    '36': 'Pago Cheque Gerencia',
    '37': 'Abono a cuenta de ahorros',
    '40': 'Efectivo seguro/Tarjeta prepago',
    '52': 'Abono a depósito electrónico',
    '53': 'Pre-notificación depósito electrónico'
}

_TYPE_TRANSACTION = [
    ('', ''),
    ('25', 'Pago en efectivo'),
    ('27', 'Abono a cuenta corriente'),
    ('36', 'Pago cheque gerencia'),
    ('37', 'Abono a cuenta de ahorros'),
    ('40', 'Efectivo seguro (visa pagos o tarjeta prepago)'),
]

_STATES = {
    'readonly': Eval('state') != 'draft',
}
_DEPENDS = ['state']


class AccountBankParty(metaclass=PoolMeta):

    __name__ = 'bank.account-party.party'

    # Funcion que valida si la cuenta nueva a crear para el tercero ya tiene un tipo de pago asignado
    @classmethod
    def validate(cls, account):
        pool = Pool()
        Bank = pool.get('bank.account-party.party')
        BankNumber = pool.get('bank.account.number')
        super(AccountBankParty, cls).validate(account)
        result = []
        accounts = []
        partys = Bank.search(['owner', '=', account[0].owner.id])
        for party in partys:
            validateId = BankNumber.search(['account', '=', party.account.id])
            for validateI in validateId:
                print(validateId)
                if validateI.account_bank_party in result:
                    result.append(validateI.account_bank_party)
                    accounts.append(validateI.number)
                else:
                    if result.count(validateI.account_bank_party) >= 1:
                        temp = result.index(validateI.account_bank_party)
                        raise ValidationError(
                            'AVISO',
                            description=
                            f"El tipo de Transaccion {result[temp]}, ya tiene esta cuenta vinculada a la cuenta {accounts[temp]}"
                        )


class BankPayment(metaclass=PoolMeta):

    __name__ = 'bank.account.number'

    account_bank_party = fields.Selection([
        ('', ''),
        ('01', 'Todos los pagos'),
        ('25', 'Pago en efectivo'),
        ('27', 'Abono a cuenta corriente'),
        ('36', 'Pago cheque gerencia'),
        ('37', 'Abono a cuenta de ahorros'),
        ('40', 'Efectivo seguro (visa pagos o tarjeta prepago)'),
    ],
                                          'Transaction Type',
                                          select=False)

    # Metodo para validar que la cuenta que se esta ingresando contenga un metodo de pago que ya este en uso, si es asi, enviara un mensaje de validacion
    @classmethod
    def validate(cls, accounts):
        cursor = Transaction().connection.cursor()
        pool = Pool()
        BankNumber = pool.get('bank.account.number')
        Bank = pool.get('bank.account-party.party')
        res = []
        select2 = ''
        bankNumber = BankNumber.__table__()
        bank = Bank.__table__()
        super(BankPayment, cls).validate(accounts)

        # Consulta que busca si la cuenta ingresada, pertenece a la misma cuenta contable con el mismo banco.
        select = bankNumber.join(
            bank, 'LEFT',
            condition=(bank.account == bankNumber.account)).select(
                bank.owner, where=accounts[0].account.id == bankNumber.account)

        cursor.execute(*select)
        validate = cursor.fetchall()
        # Vilidamos que la consulta traiga datos y que los datos sean igual a 1, si no es asi, quiere decir que el numero de cuenta pertenece a una misma cuenta contable y banco, lo cual necesita otra validacion en el else

        if list(validate[0]) != [] and len(list(validate)) == 1:
            if str(list(validate[0])[0]) != 'None':
                where = list(validate[0])[0] == bank.owner
                where |= accounts[0].account.id == bank.account
                # Contulta que busca los numeros de cuenta del tercero y las devuelve
                select2 = bankNumber.join(
                    bank,
                    'LEFT',
                    condition=(bank.account == bankNumber.account)).select(
                        bankNumber.account_bank_party,
                        bankNumber.number,
                        bank.owner,
                        bank.account,
                        where=where)
                cursor.execute(*select2)
                validate1 = cursor.fetchall()
                print(validate1)
                # En este for validamos que el tipo de pago este vinculado a una sola cuenta del tercero, si es asi, pasara, si no, arrojara una alerta
                for curso in validate1:
                    accountResult = curso[1]
                    pay = curso[0]
                    if curso[0] == None:
                        continue
                    if curso[0] not in res:
                        res.append(curso[0])
                    else:
                        raise ValidationError(
                            'AVISO',
                            description=
                            f"El tipo de pago {pay}, ya tiene esta cuenta vinculada a la cuenta {accountResult}"
                        )
        else:
            print('Ingresamos aqui')
            # Esto sucede solo si el tercero ya tiene alguna cuenta creada y la quiere cambiar de tipo de pago o esta creando una dentro de otra
            where = bankNumber.account_bank_party == accounts[
                0].account_bank_party
            where &= bankNumber.account == accounts[0].account.id
            select2 = bankNumber.select(bankNumber.account_bank_party,
                                        bankNumber.account,
                                        where=where)

            cursor.execute(*select2)

            for curso in cursor.fetchall():
                accountResult = curso[1]
                pay = curso[0]
                if curso[0] == None:
                    continue
                if curso not in res:
                    res.append(curso)
                else:
                    raise ValidationError(
                        'AVISO',
                        description=
                        f"El tipo de pago {pay}, ya tiene esta cuenta vinculada a la cuenta {accountResult}"
                    )


class PaymentBankGroupStart(ModelView):
    'Payment Bank Group Start'
    __name__ = 'account.payment_bank.start'
    company = fields.Many2One('company.company', 'Company', required=True)
    party = fields.Function(fields.Many2One('party.party', 'Party Bank'),
                            'on_change_with_party')
    report = fields.Many2One('ir.action.report',
                             'Report',
                             domain=[('report_name', 'ilike',
                                      'account.payment_bank%')],
                             required=True)
    sequence = fields.Char('Sequence', size=1, required=True)

    tarjet = fields.Many2One('bank.account',
                             'Bank Account',
                             domain=[('owners', '=', Eval('party'))],
                             depends=['party'],
                             required=True)
    type_transaction = fields.Selection(_TYPE_TRANSACTION,
                                        'Type of transaction',
                                        required=True)
    payment_type = fields.Selection(_TYPES_PAYMENT,
                                    'Type payment',
                                    required=True)

    @fields.depends('company')
    def on_change_with_party(self, name=None):
        res = None
        if self.company:
            res = self.company.party.id
        return res

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
            'sequence': self.start.sequence,
            'type_transaction': self.start.type_transaction,
            'payment_type': self.start.payment_type,
            'tarjet': self.start.tarjet.numbers[0].number,
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
    def Wrongs(cls, voucher=None, response=None, types_pay=None):
        respon = ",".join(response)
        respon += ",".join(voucher)
        respon += ",".join(types_pay)
        return respon.replace(",", "")

    @classmethod
    def get_context(cls, records, header, data):
        report_context = super().get_context(records, header, data)
        pool = Pool()
        cursor = Transaction().connection.cursor()
        Bank = pool.get('bank')
        Bank_account = pool.get('bank.account')
        BankParty = pool.get('bank.account-party.party')
        PaymentGroup = pool.get('account.payment.group')
        BankAccount = pool.get('bank.account.number')
        Payment = pool.get('account.payment')
        Company = pool.get('company.company')
        Party = pool.get('party.party')

        bankAccount = BankAccount.__table__()
        payment = Payment.__table__()
        paymentGroup = PaymentGroup.__table__()
        party = Party.__table__()
        bankParty = BankParty.__table__()
        code_bank = Bank.__table__()
        bank_account = Bank_account.__table__()

        columns = {
            'state': payment.state,
            'group': payment.group,
            'name': party.name,
            'amount': payment.amount,
            'id_number': party.id_number,
            'type_document': party.type_document,
            'bank': code_bank.party,
            'number': bankAccount.number,
            'bank_code_sap': code_bank.bank_code_sap,
            'account_bank_party': bankAccount.account_bank_party,
            'id': payment.id,
            'voucher': payment.voucher,
        }

        # Condiciones where para filtrar la informacion
        where = payment.group.in_(data['ids'])
        # where &= bankAccount.account_bank_party == data['type_transaction']

        # Consulta que retorna la informacion de las lineas de pagos de cada uno de los grupo
        selectPayment = payment.join(
            paymentGroup, 'LEFT', condition=payment.group == paymentGroup.id
        ).join(party, 'LEFT', condition=party.id == payment.party).join(
            bankParty, 'LEFT', condition=bankParty.owner == party.id).join(
                bankAccount,
                'LEFT',
                condition=bankAccount.account == bankParty.account).join(
                    bank_account,
                    'LEFT',
                    condition=bank_account.id == bankParty.account).join(
                        code_bank,
                        'LEFT',
                        condition=code_bank.id == bank_account.bank).select(
                            *columns.values(), where=where)

        cursor.execute(*selectPayment)  # Estada funcion ejecuta la consulta

        types_pay = []
        wrong = {}
        voucher = []
        voucherGroup = []
        response = []
        none_accounts = []
        record_dict = {}
        validate = cursor.fetchall()

        # Recorremos el contexto del reporte para buscar las lineas que ya contienen comprobante
        for i in records:
            lineas = Payment.search([('group', '=', i.number),
                                     ('voucher', '!=', None)])
            if lineas:
                for j in lineas:
                    if j.group not in voucherGroup:
                        voucherGroup.append(j.group)
                        voucher.append(
                            f"El grupo {j.group} ya tiene comprobante generado \n"
                        )

        for record in validate:

            curso = dict(zip(columns.keys(), record))

            if curso[
                    'state'] != 'succeeded':  # EN esta validacion nos permite agrupar todas las lineas de los grupos que tienen pagos fallidos o un estado diferente a con exito
                if curso['group'] in wrong:
                    accomulated = wrong[curso['group']]['id'] + ' | ' + str(
                        curso['id']) + '_' + curso['name']
                    wrong[curso['group']]['id'] = accomulated
                else:
                    wrong[curso['group']] = {
                        'id':
                        str(curso['account_bank_party']) + '_' + curso['name']
                    }

            if not curso['number']:
                none_accounts.append(
                    f"El terceros {curso['name']} del grupo {curso['group']} no tiene ninguna cuenta de banco asociada \n"
                )

            if curso['group'] not in record_dict:

                record_dict[curso['group']] = {'lines': {}}

            if curso['id_number'] not in record_dict[curso['group']]['lines']:

                record_dict[curso['group']]['lines'][curso['id_number']] = {
                    'accounts_bank': {}
                }

            if curso['number'] not in record_dict[curso['group']]['lines'][
                    curso['id_number']]['accounts_bank']:
                bank_name = Party.search(['id', '=', curso['bank']])
                record_dict[curso['group']]['lines'][
                    curso['id_number']]['accounts_bank'][curso['number']] = {
                        'id':
                        curso['id'],
                        'party_name':
                        curso['name'],
                        'amount':
                        0,
                        'id_number':
                        curso['id_number'],
                        'type_document':
                        curso['type_document'],
                        'bank_name':
                        bank_name[0].name,
                        'bank_account':
                        curso['number'],
                        'code_bank':
                        curso['bank_code_sap'],
                        'beneficiary_type':
                        BENEFICIARY_TYPE.get(curso['type_document']),
                        'payment_type':
                        curso['account_bank_party'],
                    }

            record_dict[curso['group']]['lines'][curso['id_number']][
                'accounts_bank'][curso['number']]['amount'] += curso['amount']

        # Aqui realizamos la validacion de todas las cuentas del tercero y verificamos que tenga alguna
        # cuenta vinculada al tipo de transaccion, si no es asi, lo guardara en la lista de errores
        items = []
        keywords = []
        default = []
        for key, move_line in record_dict.items():
            for nit, line in move_line['lines'].items():
                for accounts in line.values():
                    for account, lineas in accounts.items():
                        # Validamos si el tercero tiene una cuenta con tipo 01, si es asi, le asigna esa cuenta por
                        # defecto, sin emabrgo, si tiene una cuenta con el tipo asignado por el cliente, esta
                        # en la siguienta validacion, sale y se le asigna la cuenta con el pago proiritario
                        if lineas['payment_type'] == '01' and lineas[
                                'id'] not in keywords:
                            items.append(lineas)
                            default.append(lineas['id_number'])
                            continue

                        if lineas['payment_type'] == data[
                                'type_transaction'] and lineas[
                                    'id'] not in keywords:
                            if lineas['id_number'] in default:
                                items.pop()
                                keywords.pop()
                            items.append(lineas)
                            keywords.append(lineas['id_number'])
                            continue

                # Si hay un tercero el cual no tenga el tipo de transacción, este condicional permite guardarlo en los errores
                if nit not in keywords and nit not in default:
                    party = Party.search(['id_number', '=', nit])
                    types_pay.append(
                        f"El terceros {party[0].name} de grupo {key} no tiene asociada una cuenta con el tipo de transaccion {TYPE_TRANSACTION_GET.get(data['type_transaction'])} \n"
                    )

        # Aqui validamos que la consulta traiga informacion, si no, arroja una alerta
        if items == []:
            raise ValidationError(
                message='AVISO',
                description=
                f"Ninguno de los grupo tiene cuentas con el tipo de transaccion {TYPE_TRANSACTION_GET.get(data['type_transaction'])}"
            )

        # Aqui validamos si tenemos algunos de los errores antes señalados, si es asi, arroja la alerta con toda la informacion para que el usuario corrija
        if wrong != {} or types_pay != [] or voucher != []:
            for value in wrong:
                response.append(
                    f"pagos fallidos del grupo {value} con id/s {wrong.get(value).get('id')} \n"
                )

            raise ValidationError(
                message='AVISO',
                description=cls.Wrongs(voucher=voucher,
                                       response=response,
                                       types_pay=types_pay)
            )  # La funcion Wrongs... nos permite agrupar todos los errores que hallamos tenido y devolverlo en pantalla

        company = Company.search_read([('id', '=', data['company'])],
                                      fields_names=[
                                          'party.id_number',
                                          'party.bank_account',
                                          'party.bank_account_type',
                                          'party.name', 'party.bank_name'
                                      ])

        for i in _TYPES_BANK_ACCOUNT.keys():
            if i == company[0].get('party.').get('bank_account_type'):
                company[0]['party.'][
                    'bank_account_type'] = _TYPES_BANK_ACCOUNT.get(i)
        company[0]['party.']['bank_account'] = data.get('tarjet')

        report_context['records'] = items
        report_context['company'] = company[0]
        return report_context


###############################  REPORTS  ##############################


class BankReportBancolombia(PaymentBankGroupReport):
    __name__ = 'account.payment_bank.report_bancolombia'


# class BankReportBancamia(PaymentBankGroupReport):
#     __name__ = 'account.payment_bank.report_bancamia'
