from trytond.model import ModelView, ModelSQL, fields
from trytond.pool import Pool, PoolMeta
from trytond.exceptions import UserError
from trytond.transaction import Transaction

PAYMENT_CODES = [
    ('', ''),
    ('1', 'Instrumento no definido'),
    ('10', 'Efectivo'),
    ('44', 'Nota Cambiaria'),
    ('20', 'Cheque'),
    ('48', 'Tarjeta Crédito'),
    ('49', 'Tarjeta Débito'),
    ('42', 'Consignación bancaria'),
    ('47', 'Transferencia Débito Bancaria'),
    ('45', 'Transferencia Crédito Bancaria'),
]

__all__ = [
    'VoucherPayMode',
    ]

class VoucherPayMode(ModelSQL, ModelView):
    'Voucher Pay Mode'
    __name__ = 'account.voucher.paymode'
    id_tecno = fields.Char('Id Tabla Sqlserver', required=False)
    #Campo habilitado y necesario por módulos de psk al desactivar (electronic_invoice_co)
    payment_means_code = fields.Selection(PAYMENT_CODES, 'Payment Means Code', required=True)


    #Funcion encargada de crear o actualizar las formas de pago de TecnoCarnes
    @classmethod
    def update_paymode(cls):
        print('RUN FORMAS DE PAGO')
        pool = Pool()
        Config = pool.get('conector.configuration')
        Actualizacion = pool.get('conector.actualizacion')
        PayMode = pool.get('account.voucher.paymode')
        Journal = pool.get('account.journal')
        actualizacion = Actualizacion.create_or_update('FORMAS DE PAGO')
        formas_pago = Config.get_data_table('TblFormaPago')
        to_save = []
        for fp in formas_pago:
            id_tecno = str(fp.IdFormaPago)
            nombre = fp.FormaPago.strip()
            cuenta = fp.Cuenta
            paym = PayMode.search([('id_tecno', '=', id_tecno)])
            if paym:
                paym, = paym
                paym.name = nombre
                cls.add_account(paym, cuenta)
                paym.save()
            else:
                #Diario por defecto del plan contable
                journal, = Journal.search([('code', '=', 'CASH')])
                paymode = PayMode()
                paymode.id_tecno = id_tecno
                paymode.name = nombre
                paymode.payment_type = 'cash'
                paymode.kind = 'both'
                paymode.journal = journal
                sequence_payment = cls.find_seq('Voucher Payment')
                sequence_multipayment = cls.find_seq('Voucher Multipayment')
                sequence_receipt = cls.find_seq('Voucher Receipt')
                paymode.sequence_payment = sequence_payment[0]
                paymode.sequence_multipayment = sequence_multipayment[0]
                paymode.sequence_receipt = sequence_receipt[0]
                cls.add_account(paym, cuenta)
                #Codigo clasificacion tipo de pago ('10' => 'Efectivo')
                paymode.payment_means_code = 10
                to_save.append(paymode)
                #paym.save()
        PayMode.save(to_save)
        actualizacion.save()
        print('FINISH FORMAS DE PAGO')


    #Se busca la cuenta del modo de pago y se asigna en caso de existir
    @classmethod
    def add_account(cls, paymode, cuenta):
        Account = Pool().get('account.account')
        account = Account.search([('code', '=', str(cuenta))])
        if account:
            paymode.account = account[0]


    #Función encargada de consultar la secuencia de un voucher dado
    @classmethod
    def find_seq(cls, name):
        Sequence = Pool().get('ir.sequence')
        seq = Sequence.__table__()
        cursor = Transaction().connection.cursor()
        cursor.execute(*seq.select(where=(seq.name == name)))
        result = cursor.fetchall()
        return result[0]
