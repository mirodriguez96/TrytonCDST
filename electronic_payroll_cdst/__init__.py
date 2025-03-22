# This file is part of trytond-electronic-payroll-cdst.
# Licensed under the GNU General Public License v3 or later (GPLv3+).
# The COPYRIGHT file at the top level of this repository contains the
# full copyright notices and license terms.
# SPDX-License-Identifier: GPL-3.0-or-later

from trytond.pool import Pool

__all__ = ['register']

from . import electronic_payroll_wizard


def register():
    Pool.register(
        module='electronic_payroll_cdst', type_='model')
    Pool.register(
        electronic_payroll_wizard.PayrollElectronicCdst,
        module='electronic_payroll_cdst', type_='wizard')
    Pool.register(
        module='electronic_payroll_cdst', type_='report')
