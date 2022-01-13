from trytond.pool import Pool

#import wiz
import conector
import party
import product
import sale
import sale_device
import configuration
import voucher
import pay_mode
from . import electronic_payroll_wizard
from . import company
from . import payment_term
import purchase
import location
import invoice
import tax

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
        sale.Cron,
        sale_device.SaleDevice,
        sale_device.Journal,
        sale_device.Cron,
        location.Location,
        location.Cron,
        configuration.Configuration,
        voucher.Cron,
        voucher.Voucher,
        pay_mode.Cron,
        pay_mode.VoucherPayMode,
        payment_term.PaymentTerm,
        payment_term.Cron,
        purchase.Cron,
        purchase.Purchase,
        invoice.Invoice,
        tax.Tax,
        module='conector', type_='model')

    Pool.register(
        electronic_payroll_wizard.PayrollElectronicCdst,
        module='conector', type_='wizard')

