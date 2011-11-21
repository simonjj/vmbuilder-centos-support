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
from   VMBuilder      import register_hypervisor, Hypervisor
from   VMBuilder.util import run_cmd
import VMBuilder
import VMBuilder.hypervisor
import logging
import os.path

class Xen(Hypervisor):
    name = 'Xen'
    arg = 'xen'
    preferred_storage = VMBuilder.hypervisor.STORAGE_FS_IMAGE
    needs_bootloader = False

    def register_options(self):
        group = self.setting_group('Xen options')
        group.add_setting('xen-kernel', metavar='PATH', help='Path to the kernel to use (e.g.: /boot/vmlinux-2.6.27-7-server). Default depends on distribution and suite')
        group.add_setting('xen-ramdisk', metavar='PATH', help='Path to the ramdisk to use (e.g.: /boot/initrd.img-2.6.27-7-server). Default depends on distribution and suite.')
        group.add_setting('mem', extra_args=['-m'], type='int', default=128, help='Assign MEM megabytes of memory to the guest vm. [default: %default]')

    def convert(self, filesystems, destdir):
        destimages = []
        for filesystem in filesystems:
            if not filesystem.preallocated:
                destfile = '%s/%s' % (destdir, os.path.basename(filesystem.filename))
                logging.info('Moving %s to %s' % (filesystem.filename, destfile))
                run_cmd('cp', '--sparse=always', filesystem.filename, destfile)
                self.call_hooks('fix_ownership', destfile)
                os.unlink(filesystem.filename)
                filesystem.filename = os.path.abspath(destfile)
                destimages.append(destfile)

        if not self.context.get_setting('xen-kernel'):
            self.context.xen_kernel = self.context.distro.xen_kernel_path()
        if not self.context.get_setting('xen-ramdisk'):
            self.context.xen_ramdisk = self.context.distro.xen_ramdisk_path()

        xenconf = '%s/xen.conf' % destdir
        fp = open(xenconf, 'w')
        fp.write("""
# Configuration file for the Xen instance %s, created
# by VMBuilder
kernel = '%s'
ramdisk = '%s'
memory = %d

root = '/dev/xvda1 ro'
disk = [
%s
]

name = '%s'

dhcp    = 'dhcp'
vif = ['']

on_poweroff = 'destroy'
on_reboot   = 'restart'
on_crash    = 'restart'

extra = 'xencons=tty console=tty1 console=hvc0'

"""  %   (self.context.distro.get_setting('hostname'),
          self.context.get_setting('xen-kernel'),
          self.context.get_setting('xen-ramdisk'),
          self.context.get_setting('mem'),
          ',\n'.join(["'tap:aio:%s,xvda%d,w'" % (os.path.abspath(img), id+1) for (img, id) in zip(destimages, range(len(destimages)))]),
          self.context.distro.get_setting('hostname')))
        fp.close()
        self.call_hooks('fix_ownership', xenconf)

register_hypervisor(Xen)
