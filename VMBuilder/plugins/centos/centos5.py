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
import os
import logging
import suite
import tempfile
import VMBuilder.disk as disk
from   VMBuilder.util import run_cmd
from   VMBuilder.plugins.centos.centos4 import Centos4

class Centos5(Centos4):
    valid_flavours = { 'i386' :  ['kernel', 'kernel-PAE', 'kernel-xen'],
                       'amd64' : ['kernel', 'kernel-xen']}
    rinse_conf = '''
[%s]
mirror       = %s/5/os/i386/CentOS/
mirror.amd64 = %s/5/os/x86_64/CentOS/
'''

