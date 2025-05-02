# This file is part of trytond-production-cdst.
# Licensed under the GNU General Public License v3 or later (GPLv3+).
# The COPYRIGHT file at the top level of this repository contains the
# full copyright notices and license terms.
# SPDX-License-Identifier: GPL-3.0-or-later

from trytond.pool import Pool

from . import production
__all__ = ['register']


def register():
    Pool.register(
        production.Production,
        production.ProductionDetailedStart,
        module='production_cdst', type_='model')
    Pool.register(
        production.ProductionDetailed,
        production.ProductionForceDraft,
        module='production_cdst', type_='wizard')
    Pool.register(
        production.ProductionDetailedReport,
        module='production_cdst', type_='report')
