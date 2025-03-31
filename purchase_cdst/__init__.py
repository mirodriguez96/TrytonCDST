# This file is part of trytond-purchase-cdst.
# Licensed under the GNU General Public License v3 or later (GPLv3+).
# The COPYRIGHT file at the top level of this repository contains the
# full copyright notices and license terms.
# SPDX-License-Identifier: GPL-3.0-or-later

from trytond.pool import Pool

from . import purchase

__all__ = ['register']


def register():
    Pool.register(
                purchase.Configuration,
                purchase.Purchase,
                purchase.PurchaseLine,
        module='purchase_cdst', type_='model')
    Pool.register(
        module='purchase_cdst', type_='wizard')
    Pool.register(
        module='purchase_cdst', type_='report')
