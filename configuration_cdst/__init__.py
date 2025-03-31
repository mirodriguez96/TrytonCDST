# This file is part of trytond-configuration-cdst.
# Licensed under the GNU General Public License v3 or later (GPLv3+).
# The COPYRIGHT file at the top level of this repository contains the
# full copyright notices and license terms.
# SPDX-License-Identifier: GPL-3.0-or-later

from trytond.pool import Pool

__all__ = ['register']
from . import configuration


def register():
    Pool.register(
        configuration.Configuration,
        module='configuration_cdst', type_='model')
    Pool.register(
        module='configuration_cdst', type_='wizard')
    Pool.register(
        module='configuration_cdst', type_='report')
