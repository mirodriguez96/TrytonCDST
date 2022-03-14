from trytond.pool import Pool
from . import conector
from . import party
from . import product
from . import sale
from . import sale_device
from . import configuration
from . import voucher
from . import pay_mode
from . import electronic_payroll_wizard
from . import company
from . import payment_term
from . import purchase
from . import location
from . import invoice
from . import tax
from . import production
from . import wiz
from . import report

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
        voucher.MultiRevenue,
        pay_mode.Cron,
        pay_mode.VoucherPayMode,
        payment_term.PaymentTerm,
        payment_term.Cron,
        purchase.Cron,
        purchase.Purchase,
        invoice.Invoice,
        tax.Tax,
        production.Production,
        production.Cron,
        voucher.VoucherConfiguration,
        report.PortfolioStatusStart,
        module='conector', type_='model')

    Pool.register(
        electronic_payroll_wizard.PayrollElectronicCdst,
        invoice.UpdateInvoiceTecno,
        invoice.UpdateNoteDate,
        wiz.DeleteVoucherTecno,
        wiz.VoucherMoveUnreconcile,
        wiz.ReverseProduction,
        report.PortfolioStatus,
        module='conector', type_='wizard')

    Pool.register(
        report.PortfolioStatusReport,
        module='conector', type_='report')