# This file is part of trytond-account-invoice-cdst.
# Licensed under the GNU General Public License v3 or later (GPLv3+).
# The COPYRIGHT file at the top level of this repository contains the
# full copyright notices and license terms.
# SPDX-License-Identifier: GPL-3.0-or-later

from trytond.tests.test_tryton import ModuleTestCase


class AccountInvoiceCdstTestCase(ModuleTestCase):
    "Test Account Invoice Cdst module"
    module = 'account_invoice_cdst'


del ModuleTestCase
