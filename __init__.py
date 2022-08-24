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
from . import account

def register():
    Pool.register(
        account.Account,
        account.BalanceStockStart,
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
        voucher.Note,
        pay_mode.Cron,
        pay_mode.VoucherPayMode,
        payment_term.PaymentTerm,
        payment_term.Cron,
        purchase.Cron,
        purchase.Purchase,
        invoice.Invoice,
        invoice.Cron,
        tax.Tax,
        production.Production,
        production.Cron,
        voucher.VoucherConfiguration,
        wiz.CreateAdjustmentNotesParameters,
        wiz.AddCenterOperationLineP,
        #report.PortfolioStatusStart,
        report.PayrollExportStart,
        module='conector', type_='model')

    Pool.register(
        account.BalanceStock,
        electronic_payroll_wizard.PayrollElectronicCdst,
        invoice.UpdateInvoiceTecno,
        invoice.UpdateNoteDate,
        wiz.DeleteVoucherTecno,
        wiz.VoucherMoveUnreconcile,
        wiz.ReverseProduction,
        wiz.DeleteImportRecords,
        wiz.DeleteAccountType,
        wiz.CheckImportedDoc,
        wiz.MarkImportMulti,
        wiz.MoveFixParty,
        wiz.ForceDraftVoucher,
        wiz.FixBugsConector,
        wiz.UnreconcilieMulti,
        wiz.CreateAdjustmentNotes,
        wiz.AddCenterOperationLine,
        #report.PortfolioStatus,
        report.PayrollExport,
        module='conector', type_='wizard')

    Pool.register(
        #report.PortfolioStatusReport,
        report.PayrollExportReport,
        module='conector', type_='report')