# This file is part of trytond-account-cdst.
# Licensed under the GNU General Public License v3 or later (GPLv3+).
# The COPYRIGHT file at the top level of this repository contains the
# full copyright notices and license terms.
# SPDX-License-Identifier: GPL-3.0-or-later

from trytond.pool import Pool

__all__ = ['register']

from . import account


def register():
    Pool.register(
        account.Account,
        account.Move,
        account.MoveLine,
        account.BalanceStockStart,
        account.BankMoneyTransferStart,
        account.AnalyticAccountEntry,
        account.MoveCloseYearStart,
        account.PartyWithholdingStart,
        account.Period,
        account.Reconciliation,
        account.AuxiliaryPartyStart,
        account.AccountAsset,
        account.AuxiliaryBookStartCDS,
        account.IncomeStatementView,
        module='account_cdst', type_='model')
    Pool.register(
        account.BalanceStock,
        account.BankMoneyTransfer,
        account.PrintAuxiliaryBookCDS,
        account.IncomeStatementWizard,
        account.ActiveForceDraft,
        account.PrintPartyWithholding,
        account.MoveCloseYear,
        module='account_cdst', type_='wizard')
    Pool.register(
        account.AuxiliaryParty,
        account.AuxiliaryBookCDS,
        account.IncomeStatementReport,
        account.IncomeStatement,
        account.TrialBalanceDetailedCds,
        account.PartyWithholding,
        module='account_cdst', type_='report')
