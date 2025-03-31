# This file is part of trytond-conector-cdst.
# Licensed under the GNU General Public License v3 or later (GPLv3+).
# The COPYRIGHT file at the top level of this repository contains the
# full copyright notices and license terms.
# SPDX-License-Identifier: GPL-3.0-or-later

from trytond.tests.test_tryton import ModuleTestCase


class ConectorCdstTestCase(ModuleTestCase):
    "Test Conector Cdst module"
    module = 'conector_cdst'


del ModuleTestCase
