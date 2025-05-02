# This file is part of trytond-stock-lot-cdst.
# Licensed under the GNU General Public License v3 or later (GPLv3+).
# The COPYRIGHT file at the top level of this repository contains the
# full copyright notices and license terms.
# SPDX-License-Identifier: GPL-3.0-or-later

try:
    from trytond.modules.account.tests.test_account import (suite)
except ImportError:
    from .test_electronic_payroll_cdst import suite

__all__ = ['suite']
