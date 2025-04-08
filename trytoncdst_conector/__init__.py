"""--------INIT MODULE---------"""


from trytond.pool import Pool


from . import (collection,
               cron, currency,
               email_, exogena, line,
               pay_mode, payment_bank, payment_term,
               product, report)


def register():
    """Function that register model view, wizard and reports with pool"""
    Pool.register(collection.Tracking,
                  currency.Cron,
                  currency.CurrencyRate,
                  cron.Cron,
                  email_.Email,
                  line.Line,
                  pay_mode.VoucherPayMode,
                  payment_bank.PaymentBankGroupStart,
                  payment_bank.AccountBankParty,
                  payment_bank.BankPayment,
                  payment_term.PaymentTerm,
                  product.Product,
                  product.ProductCategory,
                  product.CategoryAccount,
                  product.Template,
                  product.CostPriceRevision,
                  report.PayrollExportStart,
                  report.CDSSaleIncomeDailyStart,
                  module='conector',
                  type_='model')

    Pool.register(payment_bank.PaymentBankGroup,
                  report.PayrollExport,
                  report.CDSSaleIncomeDaily,
                  module='conector',
                  type_='wizard')

    Pool.register(collection.PortfolioStatusReport,
                  exogena.TemplateExogena,
                  exogena.F1001,
                  exogena.F1003,
                  exogena.F1005,
                  exogena.F1006,
                  exogena.F1007,
                  exogena.F1008,
                  exogena.F1009,
                  exogena.F1011,
                  exogena.F1012,
                  exogena.F1043,
                  exogena.F1045,
                  exogena.F2015,
                  exogena.F2276,
                  exogena.F5247,
                  exogena.F5248,
                  exogena.F5249,
                  exogena.F5250,
                  exogena.F5251,
                  exogena.F5252,
                  payment_bank.PaymentBankGroupReport,
                  payment_bank.BankReportBancolombia,
                  report.PayrollExportReport,
                  report.CDSSaleIncomeDailyReport,
                  report.LoanFormatReport,
                  module='conector',
                  type_='report')
