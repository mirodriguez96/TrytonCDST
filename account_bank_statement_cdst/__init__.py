# This file is part of trytond-account-bank-statement-cdst.
# Licensed under the GNU General Public License v3 or later (GPLv3+).
# The COPYRIGHT file at the top level of this repository contains the
# full copyright notices and license terms.
# SPDX-License-Identifier: GPL-3.0-or-later

from trytond.pool import Pool

__all__ = ['register']
from . import (statement, bank)


def register():
    Pool.register(
        bank.Bank,
        statement.BankStatement,
        statement.BankStatementLine,
        statement.BankStatementBankLine,
        statement.BankStatementLineRelation,
        statement.CreateBankLineParameters,
        statement.StatementLine,
        module='account_bank_statement_cdst', type_='model')
    Pool.register(
        statement.StatementMoveValidate,
        statement.CreateBankLine,
        module='account_bank_statement_cdst', type_='wizard')
    Pool.register(
        module='account_bank_statement_cdst', type_='report')
