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
from   VMBuilder import register_hypervisor, Hypervisor
import VMBuilder
import os
import stat

class KVM(Hypervisor):
    name = 'KVM'
    arg = 'kvm'
    filetype = 'qcow2'
    preferred_storage = VMBuilder.hypervisor.STORAGE_DISK_IMAGE
    needs_bootloader = True

    def register_options(self):
        group = self.setting_group('VM settings')
        group.add_setting('mem', extra_args=['-m'], type='int', default=128, help='Assign MEM megabytes of memory to the guest vm. [default: %default]')
        group.add_setting('cpus', type='int', default=1, help='Assign NUM cpus to the guest vm. [default: %default]')

    def convert(self, disks, destdir):
        self.imgs = []
        self.cmdline = ['kvm', '-m', str(self.context.get_setting('mem'))]
        self.cmdline += ['-smp', str(self.context.get_setting('cpus'))]
        for disk in disks:
            img_path = disk.convert(destdir, self.filetype)
            self.imgs.append(img_path)
            self.call_hooks('fix_ownership', img_path)
            self.cmdline += ['-drive', 'file=%s' % os.path.basename(img_path)]

        self.cmdline += ['"$@"']

    def deploy(self, destdir):
        # No need create run script if vm is registered with libvirt
        if self.context.get_setting('libvirt'):
            return
        
        script = '%s/run.sh' % destdir
        fp = open(script, 'w')
        fp.write("#!/bin/sh\n\nexec %s\n" % ' '.join(self.cmdline))
        fp.close()
        os.chmod(script, stat.S_IRWXU | stat.S_IRWXG | stat.S_IROTH | stat.S_IXOTH)
        self.call_hooks('fix_ownership', script)

    def libvirt_domain_type_name(self):
        return 'kvm'

class QEMu(KVM):
    name = 'QEMu'
    arg = 'qemu'

    def libvirt_domain_type_name(self):
        return 'qemu'

register_hypervisor(KVM)
register_hypervisor(QEMu)
