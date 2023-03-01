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
from . import payroll
from . import cron

def register():
    Pool.register(
        account.Account,
        account.BalanceStockStart,
        company.Company,
        conector.Actualizacion,
        party.Party,
        party.PartyAddress,
        party.ContactMechanism,
        product.Product,
        product.ProductCategory,
        sale.Sale,
        sale.SaleLine,
        sale.Statement,
        sale_device.SaleDevice,
        sale_device.Journal,
        location.Location,
        configuration.Configuration,
        voucher.Voucher,
        voucher.MultiRevenue,
        voucher.Note,
        pay_mode.VoucherPayMode,
        payment_term.PaymentTerm,
        # purchase.Configuration,
        purchase.Purchase,
        purchase.PurchaseLine,
        invoice.Invoice,
        tax.Tax,
        tax.MiddleModel,
        tax.TaxRuleLine,
        production.Production,
        voucher.VoucherConfiguration,
        wiz.CreateAdjustmentNotesParameters,
        wiz.AddCenterOperationLineP,
        #report.PortfolioStatusStart,
        report.PayrollExportStart,
        report.CDSSaleIncomeDailyStart,
        payroll.Bank,
        payroll.PayrollPaymentStartBcl,
        payroll.StaffEvent,
        payroll.Payroll,
        payroll.PayslipSendStart,
        payroll.Liquidation,
        payroll.LiquidationPaymentStartBcl,
        payroll.SettlementSendStart,
        cron.Cron,
        wiz.DocumentsForImportParameters,
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
        wiz.ReimportExcepcionDocument,
        #report.PortfolioStatus,
        report.PayrollExport,
        report.CDSSaleIncomeDaily,
        payroll.PayrollPaymentBcl,
        payroll.PayslipSend,
        payroll.LiquidationPaymentBcl,
        payroll.SettlementSend,
        wiz.DocumentsForImport,
        wiz.ConfirmLinesBankstatement,
        wiz.GroupMultirevenueLines,
        module='conector', type_='wizard')

    Pool.register(
        #report.PortfolioStatusReport,
        report.PayrollExportReport,
        report.CDSSaleIncomeDailyReport,
        payroll.PayrollPaymentReportBcl,
        payroll.LiquidationPaymentReportBcl,
        payroll.PayrollReport,
        module='conector', type_='report')