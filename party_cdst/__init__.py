# This file is part of trytond-party-cdst.
# Licensed under the GNU General Public License v3 or later (GPLv3+).
# The COPYRIGHT file at the top level of this repository contains the
# full copyright notices and license terms.
# SPDX-License-Identifier: GPL-3.0-or-later

from trytond.pool import Pool

__all__ = ['register']

from . import party, cron


def register():
    Pool.register(
        cron.Cron,
        party.CheckVIESResult,
        party.Party,
        party.PartyAddress,
        party.ContactMechanism,
        module='party_cdst', type_='model')

    Pool.register(
        party.CheckVIES,
        module='party_cdst', type_='wizard')

    Pool.register(
        module='party_cdst', type_='report')
