# This file is part of trytond-conector-cdst.
# Licensed under the GNU General Public License v3 or later (GPLv3+).
# The COPYRIGHT file at the top level of this repository contains the
# full copyright notices and license terms.
# SPDX-License-Identifier: GPL-3.0-or-later

from trytond.pool import Pool

__all__ = ['register']

from . import conector, conector_log


def register():
    Pool.register(
        conector.Actualizacion,
        conector.Email,
        conector.ImportedDocument,
        conector_log.ConectorLog,
        module='conector_cdst', type_='model')

    Pool.register(
        conector.ImportedDocumentWizard,
        conector_log.DeleteImportRecords,
        module='conector_cdst', type_='wizard')

    Pool.register(
        module='conector_cdst', type_='report')
