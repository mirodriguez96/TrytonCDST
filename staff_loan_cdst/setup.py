#!/usr/bin/env python3
# This file is part of trytond-staff-loan-cdst.
# Licensed under the GNU General Public License v3 or later (GPLv3+).
# The COPYRIGHT file at the top level of this repository contains the
# full copyright notices and license terms.
# SPDX-License-Identifier: GPL-3.0-or-later

from trytoncommunity_setuptools import (
    TrytonCommunityURL, get_prefix_require_version, get_require_version, setup)

MODULE = 'staff_loan_cdst'
PREFIX = 'trytond'
MODULE2PREFIX = {}

requires = []
tests_require = [get_require_version('proteus')]

# additional meta-data
project_urls = {
    'Source Code': TrytonCommunityURL('modules/%s' % MODULE),
    "Bug Tracker": TrytonCommunityURL('modules/%s/-/issues' % MODULE),
    "Documentation": 'https://docs.tryton.org/projects/modules-staff-loan-cdst',
    "Forum": 'https://www.tryton.org/forum',
}

setup(PREFIX, MODULE, module2prefix=MODULE2PREFIX,
      requires=requires, tests_require=tests_require,
      project_urls=project_urls)
