# This file is part of trytond-staff-loan-cdst.
# Licensed under the GNU General Public License v3 or later (GPLv3+).
# The COPYRIGHT file at the top level of this repository contains the
# full copyright notices and license terms.
# SPDX-License-Identifier: GPL-3.0-or-later

from trytond.pool import Pool

__all__ = ['register']

from . import loan


def register():
    Pool.register(
        loan.Loan,
        loan.LoanLine,
        module='staff_loan_cdst', type_='model')

    Pool.register(
        loan.LoanForceDraft,
        module='staff_loan_cdst', type_='wizard')

    Pool.register(
        module='staff_loan_cdst', type_='report')
