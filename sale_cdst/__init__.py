# This file is part of trytond-sale-cdst.
# Licensed under the GNU General Public License v3 or later (GPLv3+).
# The COPYRIGHT file at the top level of this repository contains the
# full copyright notices and license terms.
# SPDX-License-Identifier: GPL-3.0-or-later

from trytond.pool import Pool

from . import sale, sale_device, suscription

__all__ = ['register']


def register():
    Pool.register(
                sale.Sale,
                sale.Statement,
                sale.SaleShopDetailedCDSStart,
                sale.SaleInvoiceValueCdstStart,
                sale_device.SaleDevice,
                sale_device.Journal,
                suscription.Subscription,
                module='sale_cdst', type_='model')

    Pool.register(
                sale.SaleShopDetailedCDS,
                sale.SaleInvoiceValueCdst,
                module='sale_cdst', type_='wizard')
    Pool.register(
                sale.SaleShopDetailedCDSReport,
                sale.SaleInvoiceValueCdstReport,
                sale.SaleDetailedReport,
                module='sale_cdst', type_='report')
