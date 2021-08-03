from trytond.pool import Pool

import conector
import wiz


def register():
    Pool.register(
        conector.Terceros,
        conector.Party,
        conector.ContactMechanism,
        conector.ProductCategory,
        conector.Cron,
        wiz.CargarVentas,
        module='conector', type_='model')

    Pool.register(
        wiz.ActualizarVentas,
        module='conector', type_='wizard')

