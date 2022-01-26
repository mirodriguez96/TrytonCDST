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
    'Cron',
    ]

class Cron(metaclass=PoolMeta):
    'Cron'
    __name__ = 'ir.cron'

    @classmethod
    def __setup__(cls):
        super().__setup__()
        cls.method.selection.append(
            ('account.voucher.paymode|update_paymode', "Importar formas de pago"),
            )


class VoucherPayMode(ModelSQL, ModelView):
    'Voucher Pay Mode'
    __name__ = 'account.voucher.paymode'
    id_tecno = fields.Char('Id Tabla Sqlserver', required=False)
    #Campo habilitado y necesario por módulos de psk al desactivar (electronic_invoice_co)
    payment_means_code = fields.Selection(PAYMENT_CODES, 'Payment Means Code', required=True)


    #Funcion encargada de crear o actualizar las formas de pago de TecnoCarnes
    @classmethod
    def update_paymode(cls):
        print('-----RUN FORMAS DE PAGO-----')
        columns_fp = cls.get_columns_db('TblFormaPago')
        forma_pago = cls.get_formapago()
        cls.create_or_update()
        PayMode = Pool().get('account.voucher.paymode')
        Journal = Pool().get('account.journal')
        
        for fp in forma_pago:
            idt = str(fp[columns_fp.index('IdFormaPago')])
            paym = PayMode.search([('id_tecno', '=', idt)])
            nombre = fp[columns_fp.index('FormaPago')].strip()
            cuenta = fp[columns_fp.index('Cuenta')]
            if paym:
                for pm in paym:
                    pm.name = nombre
                    cls.add_account(pm, cuenta)
                    PayMode.save(paym)
            else:
                #Diario por defecto del plan contable
                journal, = Journal.search([('code', '=', 'REV')])
                paym = PayMode()
                paym.id_tecno = idt
                paym.name = nombre
                paym.payment_type = 'cash'
                paym.kind = 'both'
                paym.journal = journal
                sequence_payment = cls.find_seq('Voucher Payment')
                sequence_multipayment = cls.find_seq('Voucher Multipayment')
                sequence_receipt = cls.find_seq('Voucher Receipt')
                paym.sequence_payment = sequence_payment[0]
                paym.sequence_multipayment = sequence_multipayment[0]
                paym.sequence_receipt = sequence_receipt[0]
                cls.add_account(paym, cuenta)
                #Codigo clasificacion tipo de pago ('10' => 'Efectivo')
                paym.payment_means_code = 10
                paym.save()
        print('-----FINISH FORMAS DE PAGO-----')


    #Se busca la cuenta del modo de pago y se asigna en caso de existir
    @classmethod
    def add_account(cls, paymode, cuenta):
        Account = Pool().get('account.account')
        account = Account.search([('code', '=', str(cuenta))])
        if account:
            paymode.account = account[0]

     #Función encargada de consultar las columnas pertenecientes a 'x' tabla de la bd de TecnoCarnes
    @classmethod
    def get_columns_db(cls, table):
        columns = []
        try:
            Config = Pool().get('conector.configuration')
            conexion = Config.conexion()
            with conexion.cursor() as cursor:
                query = cursor.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = '"+table+"' ORDER BY ORDINAL_POSITION")
                for q in query.fetchall():
                    columns.append(q[0])
        except Exception as e:
            print(("ERROR QUERY "+table+": ", e))
        return columns


    #Función encargada de traer las formas de pago de TecnoCarnes
    @classmethod
    def get_formapago(cls):
        data = []
        try:
            Config = Pool().get('conector.configuration')
            conexion = Config.conexion()
            with conexion.cursor() as cursor:
                query = cursor.execute("SELECT * FROM dbo.TblFormaPago")
                data = list(query.fetchall())
        except Exception as e:
            print(("ERROR QUERY get_formapago: ", e))
        return data

    #Función encargada de consultar la secuencia de un voucher dado
    @classmethod
    def find_seq(cls, name):
        Sequence = Pool().get('ir.sequence')
        seq = Sequence.__table__()
        cursor = Transaction().connection.cursor()
        cursor.execute(*seq.select(where=(seq.name == name)))
        result = cursor.fetchall()
        return result[0]


    #Crea o actualiza un registro de la tabla actualización en caso de ser necesario
    @classmethod
    def create_or_update(cls):
        Actualizacion = Pool().get('conector.actualizacion')
        actualizacion = Actualizacion.search([('name', '=','FORMAS DE PAGO')])
        if actualizacion:
            #Se busca un registro con la actualización
            actualizacion, = Actualizacion.search([('name', '=','FORMAS DE PAGO')])
            actualizacion.name = 'FORMAS DE PAGO'
            actualizacion.save()
        else:
            #Se crea un registro con la actualización
            actualizar = Actualizacion()
            actualizar.name = 'FORMAS DE PAGO'
            actualizar.save()