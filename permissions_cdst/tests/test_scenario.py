# This file is part of trytond-permissions-cdst.
# Licensed under the GNU General Public License v3 or later (GPLv3+)..
# The COPYRIGHT file at the top level of this repository contains the
# full copyright notices and license terms.
# SPDX-License-Identifier: GPL-3.0-or-later

import doctest

from trytond.tests.test_tryton import doctest_checker, doctest_teardown
from trytond.tests.test_tryton import suite as test_suite


def load_tests(*args, **kwargs):
    suite = test_suite()
    suite.addTests(doctest.DocFileSuite(
            'scenario_permissions_cdst.rst',
            tearDown=doctest_teardown,
            encoding='utf-8',
            optionflags=doctest.REPORT_ONLY_FIRST_FAILURE,
            checker=doctest_checker))
    return suite
