# This file is part of trytond-contract-cdst.
# Licensed under the GNU General Public License v3 or later (GPLv3+).
# The COPYRIGHT file at the top level of this repository contains the
# full copyright notices and license terms.
# SPDX-License-Identifier: GPL-3.0-or-later

from trytond.pool import Pool

__all__ = ['register']

from . import contract


def register():
    Pool.register(
        contract.Contract,
        contract.UpdateFuthermoreView,
        module='contract_cdst', type_='model')
    Pool.register(
        contract.ContractExportAvaliableVacation,
        contract.UpdateFuthermoreWizard,
        module='contract_cdst', type_='wizard')
    Pool.register(
        contract.ContractExportAvaliableVacationReport,
        module='contract_cdst', type_='report')
