# This file is part of trytond-report-cdst.
# Licensed under the GNU General Public License v3 or later (GPLv3+).
# The COPYRIGHT file at the top level of this repository contains the
# full copyright notices and license terms.
# SPDX-License-Identifier: GPL-3.0-or-later

from trytond.pool import Pool

from . import report

__all__ = ['register']


def register():
    Pool.register(
                report.PayrollExportStart,
                report.CDSSaleIncomeDailyStart,
        module='report_cdst', type_='model')
    Pool.register(
                report.PayrollExport,
                report.CDSSaleIncomeDaily,
        module='report_cdst', type_='wizard')
    Pool.register(
                report.PayrollExportReport,
                report.CDSSaleIncomeDailyReport,
                report.LoanFormatReport,
        module='report_cdst', type_='report')
