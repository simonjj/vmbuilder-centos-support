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
import VMBuilder.disk as disk
from   VMBuilder.util import run_cmd
from   VMBuilder.plugins.ubuntu.intrepid import Intrepid

class Jaunty(Intrepid):
    valid_flavours = { 'i386' :  ['generic', 'server', 'virtual'],
                       'amd64' : ['generic', 'server', 'virtual'],
                       'lpia'  : ['lpia', 'lpiacompat'] }
    xen_kernel_flavour = 'server'
    ec2_kernel_info = { 'i386' : 'aki-c553b4ac', 'amd64' : 'aki-d653b4bf' }
    ec2_ramdisk_info = { 'i386' : 'ari-c253b4ab', 'amd64' : 'ari-d753b4be' }
    chpasswd_cmd= [ 'chpasswd' ]

    def install_ec2(self):
        self.run_in_target('apt-get', '--force-yes', '-y', 'install', 'server^')
        self.install_from_template('/etc/update-motd.d/51_update-motd', '51_update-motd')
        # lucid and later wont have an /etc/ec2-init, so only write
        # that file if the dir exists
        if os.path.isdir("/etc/ec2-init"):
            self.install_from_template('/etc/ec2-init/is-compat-env', 'is-compat-env')
        self.run_in_target('chmod', '755', '/etc/update-motd.d/51_update-motd')
