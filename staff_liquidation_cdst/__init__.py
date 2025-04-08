# This file is part of trytond-staff-liquidation-cdst.
# Licensed under the GNU General Public License v3 or later (GPLv3+).
# The COPYRIGHT file at the top level of this repository contains the
# full copyright notices and license terms.
# SPDX-License-Identifier: GPL-3.0-or-later

from trytond.pool import Pool

__all__ = ['register']

from . import liquidation


def register():
    Pool.register(
        liquidation.Liquidation,
        liquidation.LiquidationLine,
        liquidation.AnalyticAccountEntry,
        module='staff_liquidation_cdst', type_='model')

    Pool.register(
        liquidation.MoveProvisionBonusService,
        liquidation.LiquidationGroup,
        liquidation.LiquidationDetail,
        module='staff_liquidation_cdst', type_='wizard')

    Pool.register(
        liquidation.LiquidationReport,
        liquidation.LiquidationDetailReport,
        module='staff_liquidation_cdst', type_='report')
