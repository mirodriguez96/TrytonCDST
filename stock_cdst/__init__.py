# This file is part of trytond-stock-cdst.
# Licensed under the GNU General Public License v3 or later (GPLv3+).
# The COPYRIGHT file at the top level of this repository contains the
# full copyright notices and license terms.
# SPDX-License-Identifier: GPL-3.0-or-later

from trytond.pool import Pool

from . import stock

__all__ = ['register']


def register():
    Pool.register(
        stock.Configuration,
        stock.Location,
        stock.ShipmentIn,
        stock.ShipmentInternal,
        stock.ShipmentDetailedStart,
        stock.WarehouseKardexStockStartCds,
        stock.Move,
        stock.Inventory,
        stock.BOMInput,
        stock.BOMOutput,
        module='stock_cdst', type_='model')

    Pool.register(
        stock.ModifyCostPrice,
        stock.WarehouseKardexStockCds,
        module='stock_cdst', type_='wizard')

    Pool.register(
        stock.ShipmentDetailedReport,
        stock.WarehouseCdsKardexReport,
        stock.WarehouseReport,
        module='stock_cdst', type_='report')
