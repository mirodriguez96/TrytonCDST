# This file is part of trytond-voucher-cdst.
# Licensed under the GNU General Public License v3 or later (GPLv3+).
# The COPYRIGHT file at the top level of this repository contains the
# full copyright notices and license terms.
# SPDX-License-Identifier: GPL-3.0-or-later

from trytond.pool import Pool
from . import voucher

__all__ = ['register']


def register():
    Pool.register(
        voucher.Voucher,
        voucher.MultiRevenue,
        voucher.VoucherConfiguration,
        module='voucher_cdst', type_='model')

    Pool.register(
        voucher.SelectMoveLines,
        module='voucher_cdst', type_='wizard')

    Pool.register(
        module='voucher_cdst', type_='report')
