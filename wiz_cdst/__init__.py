# This file is part of trytond-wiz-cdst.
# Licensed under the GNU General Public License v3 or later (GPLv3+).
# The COPYRIGHT file at the top level of this repository contains the
# full copyright notices and license terms.
# SPDX-License-Identifier: GPL-3.0-or-later

from trytond.pool import Pool
from . import wiz   

__all__ = ['register']


def register():
    Pool.register(
                wiz.CreateAdjustmentNotesParameters,
                wiz.AddCenterOperationLineP,
                wiz.DocumentsForImportParameters,
                wiz.DeleteVoucherTecnoStart,
                wiz.MarkImportMultiStart,
                wiz.FixBugsConectorView,
                wiz.DeleteLiquidationStart,
                wiz.DeleteEventLiquidationStart,
        module='wiz_cdst', type_='model')
    Pool.register(
                wiz.DeleteVoucherTecno,
                wiz.VoucherMoveUnreconcile,
                wiz.DeleteAccountType,
                wiz.CheckImportedDoc,
                wiz.MarkImportMulti,
                wiz.MoveFixParty,
                wiz.ForceDraftVoucher,
                wiz.UnreconcilieMulti,
                wiz.CreateAdjustmentNotes,
                wiz.AddCenterOperationLine,
                wiz.ReimportExcepcionDocument,
                wiz.DocumentsForImport,
                wiz.ConfirmLinesBankstatement,
                wiz.GroupMultirevenueLines,
                wiz.GroupDatafonoLines,
                wiz.FixBugsConector,
                wiz.DeleteLiquidation,
                wiz.DeleteEventLiquidation,
        module='wiz_cdst', type_='wizard')
    Pool.register(
        module='wiz_cdst', type_='report')
