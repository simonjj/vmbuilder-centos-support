#
#    Uncomplicated VM Builder
#    Copyright (C) 2007-2009 Canonical Ltd.
#    
#    See AUTHORS for list of contributors
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License version 3, as
#    published by the Free Software Foundation.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
#    Tests, tests, tests, and more tests

import logging
import unittest

import VMBuilder

from VMBuilder.plugins.ubuntu.distro import Ubuntu
from VMBuilder.exception import VMBuilderUserError
from VMBuilder import set_console_loglevel

class TestUbuntuPlugin(unittest.TestCase):
    def setUp(self):
        set_console_loglevel(logging.INFO)

    def test_invalid_suite_raises_UserError(self):
        'Building Ubuntu VMs with an invalid suite raises UserError'

        ubuntu = Ubuntu()
        ubuntu.set_setting('suite', 'foo')
        self.assertRaises(VMBuilderUserError, ubuntu.preflight_check)
