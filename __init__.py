from trytond.pool import Pool

#import wiz
import conector
import party
import product
import sale
import configuration
import voucher
from . import electronic_payroll_wizard
from . import company

def register():
    Pool.register(
        company.Company,
        conector.Actualizacion,
        party.Party,
        party.PartyAddress,
        party.ContactMechanism,
        party.Cron,
        product.Product,
        product.ProductCategory,
        product.Cron,
        sale.Sale,
        sale.SaleLine,
        sale.Location,
        sale.Cron,
        configuration.Configuration,
        voucher.Cron,
        voucher.Voucher,
        voucher.VoucherPayMode,
        module='conector', type_='model')

    Pool.register(
        electronic_payroll_wizard.PayrollElectronicCdst,
        module='conector', type_='wizard')

