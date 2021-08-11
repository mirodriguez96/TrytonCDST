from trytond.pool import Pool

#import wiz
import conector
import party
import products
import sale


def register():
    Pool.register(
        conector.Actualizacion,
        party.Party,
        party.PartyAddress,
        party.ContactMechanism,
        party.Cron,
        products.Products,
        products.ProductCategory,
        products.Cron,
        sale.Sale,
        sale.SaleLine,
        sale.Cron,
        #wiz.ActualizarVentas,
        module='conector', type_='model')

    Pool.register(
        #wiz.ActualizarVentas,
        module='conector', type_='wizard')

