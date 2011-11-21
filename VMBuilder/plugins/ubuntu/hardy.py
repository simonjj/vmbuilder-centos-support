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
from VMBuilder.plugins.ubuntu.gutsy import Gutsy

class Hardy(Gutsy):
    virtio_net = True
    ec2_kernel_info = { 'i386' : 'aki-6e709707', 'amd64' : 'aki-6f709706' }
    ec2_ramdisk_info = { 'i386' : 'ari-6c709705', 'amd64' : 'ari-61709708' }

    def apply_ec2_settings(self):
        self.context.addpkg += ['ec2-init',
                          'openssh-server',
                          'ec2-modules',
                          'standard^',
                          'ec2-ami-tools',
                          'update-motd']

        if not self.context.ppa:
            self.context.ppa = []

        self.context.ppa += ['ubuntu-on-ec2/ppa']

    def install_ec2(self):

        if self.context.arch == 'i386':
            self.run_in_target('apt-get' ,'--force-yes', '-y', 'install', 'libc6-xen')
            self.run_in_target('apt-get','--purge','--force-yes', '-y', 'remove', 'libc6-i686')
            self.install_from_template('/etc/ld.so.conf.d/libc6-xen.conf', 'xen-ld-so-conf')
        self.install_from_template('/etc/event.d/xvc0', 'upstart', { 'console' : 'xvc0' })
        self.run_in_target('update-rc.d', '-f', 'hwclockfirst.sh', 'remove')
        self.install_from_template('/etc/update-motd.d/51_update-motd', '51_update-motd-hardy')
        self.run_in_target('chmod', '755', '/etc/update-motd.d/51_update-motd')
        self.install_from_template('/etc/ec2-init/is-compat-env', 'is-compat-env')

    def xen_kernel_path(self):
        return '/boot/vmlinuz-2.6.24-19-xen'

    def xen_ramdisk_path(self):
        return '/boot/initrd.img-2.6.24-19-xen'

    def has_256_bit_inode_ext3_support(self):
        return True
