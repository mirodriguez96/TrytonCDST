# This file is part of trytond-permissions-cdst.
# Licensed under the GNU General Public License v3 or later (GPLv3+).
# The COPYRIGHT file at the top level of this repository contains the
# full copyright notices and license terms.
# SPDX-License-Identifier: GPL-3.0-or-later

from trytond.pool import Pool
from . import permissions

__all__ = ['register']


def register():
    Pool.register(
                permissions.Permissions,
                permissions.LinePermissions,
        module='permissions_cdst', type_='model')
    Pool.register(
        module='permissions_cdst', type_='wizard')
    Pool.register(
        module='permissions_cdst', type_='report')
