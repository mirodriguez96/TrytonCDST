# This file is part of Tryton.  The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.
from trytond.pool import Pool, PoolMeta
from trytond.model import fields
from trytond.exceptions import UserError


PAYMENT_TYPE = [
    ('', ''),
    ('1', 'Contado'),
    ('2', 'Credito'),
]

__all__ = [
    'Cron',
    "Location"
    ]

class Cron(metaclass=PoolMeta):
    'Cron'
    __name__ = 'ir.cron'

    @classmethod
    def __setup__(cls):
        super().__setup__()
        cls.method.selection.append(
            ('account.invoice.payment_term|import_payment_term', "Importar plazos de pago"),
            )

class PaymentTerm(metaclass=PoolMeta):
    __name__ = 'account.invoice.payment_term'

    payment_type = fields.Selection(PAYMENT_TYPE, 'Payment Type', required=True)
    id_tecno = fields.Char('Id Tabla Sqlserver', required=False)

    @staticmethod
    def default_payment_type():
        return '1'

    @classmethod
    def import_payment_term(cls):
        payment_term = Pool().get('account.invoice.payment_term')
        condiciones_pago = cls.get_data_table('TblCondiciones_pago')
        columns = cls.get_columns_db_tecno('TblCondiciones_pago')

        for condiciones in condiciones_pago:
            id_tecno = condiciones[columns.index('IdCondiciones_pago')]
            nombre = condiciones[columns.index('Condiciones_pago')].strip()
            dias = int(condiciones[columns.index('dias_vcto')])
            contado = '2'
            if dias == 0:
                contado = '1'

            existe = payment_term.search([('id_tecno', '=', id_tecno)])

            if existe:
                existe[0].name = nombre
                existe[0].payment_type = contado
                #existe[0].lines.relativedeltas.days = dias
                line, = existe[0].lines
                delta, = line.relativedeltas
                delta.days = dias
                existe[0].save()
            else:
                payment_term_line = Pool().get('account.invoice.payment_term.line')
                payment_term_line_delta = Pool().get('account.invoice.payment_term.line.delta')
                #Se crea un nuevo plazo de pago
                plazo_pago = payment_term()
                plazo_pago.id_tecno = id_tecno
                plazo_pago.name = nombre
                plazo_pago.payment_type = contado
                #delta es quien se le indica los días del plazo de pago
                delta = payment_term_line_delta()
                delta.days = dias
                #line es quien se le indica el tipo del plazo de pago
                line = payment_term_line()
                line.type = 'remainder'
                line.relativedeltas = [delta]
                plazo_pago.lines = [line]
                plazo_pago.save()


    @classmethod
    def get_data_table(cls, table):
        data = []
        try:
            Config = Pool().get('conector.configuration')
            conexion = Config.conexion()
            with conexion.cursor() as cursor:
                query = cursor.execute("SELECT * FROM dbo."+table+"")
                data = list(query.fetchall())
        except Exception as e:
            print(("ERROR QUERY get_data_table: ", e))
            raise UserError('ERROR QUERY get_data_table: ', str(e))
        return data

    #Función encargada de consultar las columnas pertenecientes a 'x' tabla de la bd
    @classmethod
    def get_columns_db_tecno(cls, table):
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