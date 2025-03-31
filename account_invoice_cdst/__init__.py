# This file is part of trytond-account-invoice-cdst.
# Licensed under the GNU General Public License v3 or later (GPLv3+).
# The COPYRIGHT file at the top level of this repository contains the
# full copyright notices and license terms.
# SPDX-License-Identifier: GPL-3.0-or-later

from trytond.pool import Pool

__all__ = ['register']

from . import invoice


def register():
    Pool.register(
        invoice.Invoice,
        invoice.InvoiceLine,
        invoice.UpdateInvoiceTecnoStart,
        invoice.AnalyticAccountEntry,
        module='account_invoice_cdst', type_='model')

    Pool.register(
        invoice.UpdateInvoiceTecno,
        invoice.UpdateNoteDate,
        invoice.CreditInvoice,
        invoice.AdvancePayment,
        module='account_invoice_cdst', type_='wizard')

    Pool.register(
        invoice.InvoicesReport,
        module='account_invoice_cdst', type_='report')
