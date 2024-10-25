# This file is part of Tryton.  The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.
from trytond.model import fields
from trytond.pool import Pool, PoolMeta
from trytond.transaction import Transaction

PAYMENT_TYPE = [
    ('', ''),
    ('1', 'Contado'),
    ('2', 'Credito'),
]


class PaymentTerm(metaclass=PoolMeta):
    __name__ = 'account.invoice.payment_term'

    payment_type = fields.Selection(PAYMENT_TYPE,
                                    'Payment Type',
                                    required=True)
    id_tecno = fields.Char('Id Tabla Sqlserver', required=False)

    @staticmethod
    def default_payment_type():
        return '1'

    # Función encargada de importar los plazos de pago de SqlSqerver (TecnoCarnes)
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
        logs = {}
        for condicion in condiciones_pago:
            try:
                id_tecno = condicion.IdCondiciones_pago
                nombre = condicion.Condiciones_pago.strip()
                dias_vcto = int(condicion.dias_vcto)
                payment_type = '2'
                if dias_vcto == 0:
                    payment_type = '1'
                existe = PaymentTerm.search([('id_tecno', '=', id_tecno)])
                if existe:
                    line, = existe[0].lines
                    delta, = line.relativedeltas
                    if (existe[0].name != nombre
                        or existe[0].payment_type != payment_type
                        or delta.days != dias_vcto
                            ):
                        delta.days = dias_vcto
                        existe[0].name = nombre
                        existe[0].payment_type = payment_type
                        existe[0].save()
                        logs[id_tecno] = "SE ACTUALIZO EL PLAZO DE PAGO"
                else:
                    # Se crea un nuevo plazo de pago
                    plazo_pago = PaymentTerm()
                    plazo_pago.id_tecno = id_tecno
                    plazo_pago.name = nombre
                    plazo_pago.payment_type = payment_type
                    # delta es quien se le indica los días del plazo de pago
                    delta = Delta()
                    delta.days = dias_vcto
                    # line es quien se le indica el tipo del plazo de pago
                    line = Line()
                    line.type = 'remainder'
                    line.relativedeltas = [delta]
                    plazo_pago.lines = [line]
                    PaymentTerm.save([plazo_pago])
            except Exception as error:
                Transaction().rollback()
                logs[id_tecno] = f"EXCEPCION: {error}"
        actualizacion.add_logs(logs)
