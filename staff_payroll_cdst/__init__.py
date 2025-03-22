# This file is part of trytond-staff-payroll-cdst.
# Licensed under the GNU General Public License v3 or later (GPLv3+).
# The COPYRIGHT file at the top level of this repository contains the
# full copyright notices and license terms.
# SPDX-License-Identifier: GPL-3.0-or-later

from trytond.pool import Pool

__all__ = ['register']

from . import payroll


def register():
    Pool.register(
        payroll.StaffConfiguration,
        payroll.PayrollSheetStart,
        payroll.PayrollGlobalStart,
        payroll.WageType,
        payroll.PayrollPaymentStartBcl,
        payroll.StaffEvent,
        payroll.Payroll,
        payroll.PayslipSendStart,
        payroll.LiquidationPaymentStartBcl,
        payroll.SettlementSendStart,
        payroll.PayrollElectronic,
        payroll.PayrollLine,
        payroll.CertificateOfIncomeAndWithholdingSendStart,
        payroll.PayrollIBCView,
        payroll.PayrollElectronicCDS,
        payroll.LineLiquidationEvent,
        payroll.PayrollGroupStart,
        module='staff_payroll_cdst', type_='model')

    Pool.register(
        payroll.PayrollSheet,
        payroll.PayrollGlobal,
        payroll.PayrollGroup,
        payroll.PayrollPaymentBcl,
        payroll.PayslipSend,
        payroll.LiquidationPaymentBcl,
        payroll.SettlementSend,
        payroll.SendCertificateOfIncomeAndWithholding,
        payroll.PayrollIBCWizard,
        module='staff_payroll_cdst', type_='wizard')

    Pool.register(
        payroll.PayrollSheetReport,
        payroll.PayrollPaymentReportBcl,
        payroll.LiquidationPaymentReportBcl,
        payroll.PayrollGlobalReport,
        payroll.PayrollReport,
        payroll.PayrollExo2276,
        payroll.PayrollIBCReport,
        payroll.PayrollPaycheckReportExten,
        payroll.IncomeWithholdingsReport,
        module='staff_payroll_cdst', type_='report')
