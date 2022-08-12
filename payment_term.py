# This file is part of Tryton.  The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.
from trytond.pool import Pool, PoolMeta
from trytond.model import fields


PAYMENT_TYPE = [
    ('', ''),
    ('1', 'Contado'),
    ('2', 'Credito'),
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
        pool = Pool()
        Config = pool.get('conector.configuration')
        PaymentTerm = pool.get('account.invoice.payment_term')
        Line = Pool().get('account.invoice.payment_term.line')
        Delta = Pool().get('account.invoice.payment_term.line.delta')
        Actualizacion = pool.get('conector.actualizacion')
        actualizacion = Actualizacion.create_or_update('PLAZOS DE PAGO')
        condiciones_pago = Config.get_data_table('TblCondiciones_pago')
        to_save = []
        for condicion in condiciones_pago:
            id_tecno = condicion.IdCondiciones_pago
            nombre = condicion.Condiciones_pago.strip()
            dias = int(condicion.dias_vcto)
            contado = '2'
            if dias == 0:
                contado = '1'

            existe = PaymentTerm.search([('id_tecno', '=', id_tecno)])
            if existe:
                existe[0].name = nombre
                existe[0].payment_type = contado
                line, = existe[0].lines
                delta, = line.relativedeltas
                delta.days = dias
                existe[0].save()
            else:
                #Se crea un nuevo plazo de pago
                plazo_pago = PaymentTerm()
                plazo_pago.id_tecno = id_tecno
                plazo_pago.name = nombre
                plazo_pago.payment_type = contado
                #delta es quien se le indica los días del plazo de pago
                delta = Delta()
                delta.days = dias
                #line es quien se le indica el tipo del plazo de pago
                line = Line()
                line.type = 'remainder'
                line.relativedeltas = [delta]
                plazo_pago.lines = [line]
                to_save.append(plazo_pago)
                #plazo_pago.save()
        PaymentTerm.save(to_save)
        actualizacion.save()
