# This file is part of trytond-product-cdst.
# Licensed under the GNU General Public License v3 or later (GPLv3+).
# The COPYRIGHT file at the top level of this repository contains the
# full copyright notices and license terms.
# SPDX-License-Identifier: GPL-3.0-or-later

from trytond.pool import Pool

from . import product
__all__ = ['register']


def register():
    Pool.register(
                product.Product,
                product.ProductCategory,
                product.CategoryAccount,
                product.Template,
                product.CostPriceRevision,
        module='product_cdst', type_='model')
    Pool.register(
        module='product_cdst', type_='wizard')
    Pool.register(
        module='product_cdst', type_='report')
