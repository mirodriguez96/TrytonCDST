from trytond.pool import Pool

import conector
#import wiz
import sale


def register():
    Pool.register(
        conector.Terceros,
        conector.Party,
        conector.ContactMechanism,
        conector.ProductCategory,
        conector.Cron,
        #wiz.ActualizarVentas,
        sale.Sale,
        sale.SaleLine,
        sale.Cron,
        module='conector', type_='model')

    Pool.register(
        #wiz.ActualizarVentas,
        module='conector', type_='wizard')

