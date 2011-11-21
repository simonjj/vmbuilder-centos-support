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
import os.path
import stat
import VMBuilder
from   VMBuilder      import register_hypervisor, Hypervisor
from   VMBuilder.disk import vbox_manager_path
import VMBuilder.hypervisor

class VirtualBox(Hypervisor):
    preferred_storage = VMBuilder.hypervisor.STORAGE_DISK_IMAGE
    needs_bootloader = True
    name = 'VirtualBox'
    arg = 'vbox'

    def register_options(self):
        group = self.setting_group('VirtualBox options')
        group.add_setting('mem', extra_args=['-m'], type='int', default=128, help='Assign MEM megabytes of memory to the guest vm. [default: %default]')
        group.add_setting('cpus', type='int', default=1, help='Assign NUM cpus to the guest vm. [default: %default]')
        group.add_setting('vbox-disk-format', metavar='FORMAT', default='vdi', help='Desired disk format. Valid options are: vdi vmdk. [default: %default]')

    def convert(self, disks, destdir):
        self.imgs = []
        for disk in disks:
            img_path = disk.convert(destdir, self.context.get_setting('vbox-disk-format'))
            self.imgs.append(img_path)

    def deploy(self,destdir):
        hostname = self.context.distro.get_setting('hostname')
        mac = self.context.get_setting('mac')
        ip = self.context.get_setting('ip')
        vm_deploy_script = VMBuilder.util.render_template('virtualbox', self.context, 'vm_deploy_script', { 'os_type' : self.context.distro.__class__.__name__, 'vm_name' : hostname, 'vm_disks' : self.imgs, 'memory' : self.context.get_setting('mem'), 'cpus' : self.context.get_setting('cpus') })

        script_file = '%s/deploy_%s.sh' % (destdir, hostname)
        fp = open(script_file, 'w')
        fp.write(vm_deploy_script)
        fp.close()
        os.chmod(script_file, stat.S_IRWXU | stat.S_IRGRP | stat.S_IROTH)
        self.context.result_files.append(script_file)

register_hypervisor(VirtualBox)
