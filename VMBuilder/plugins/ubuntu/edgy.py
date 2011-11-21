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
import shutil
import os
import VMBuilder.disk as disk
from   VMBuilder.util import run_cmd
from   VMBuilder.plugins.ubuntu.dapper import Dapper

class Edgy(Dapper):
    valid_flavours = { 'i386' :  ['386', '686', '686-smp', 'generic', 'k7', 'k7-smp', 'server', 'server-bigiron'],
                       'amd64' : ['amd64-generic', 'amd64-k8', 'amd64-k8-smp', 'amd64-server', 'amd64-xeon', 'server']}
    default_flavour = { 'i386' : 'server', 'amd64' : 'server' }
    disk_prefix = 'sd'

    def mangle_grub_menu_lst(self, disks):
        bootdev = disk.bootpart(disks)
        run_cmd('sed', '-ie', 's/^# kopt=root=\([^ ]*\)\(.*\)/# kopt=root=UUID=%s\\2/g' % bootdev.fs.uuid,
                '%s/boot/grub/menu.lst' % self.context.chroot_dir)
        run_cmd('sed', '-ie', 's/^# groot.*/# groot %s/g' % bootdev.get_grub_id(),
                '%s/boot/grub/menu.lst' % self.context.chroot_dir)
        run_cmd('sed', '-ie', '/^# kopt_2_6/ d', '%s/boot/grub/menu.lst' %
                self.context.chroot_dir)

    def fstab(self):
        retval = '''# /etc/fstab: static file system information.
#
# <file system>                                 <mount point>   <type>  <options>       <dump>  <pass>
proc                                            /proc           proc    defaults        0       0
'''
        parts = disk.get_ordered_partitions(self.context.disks)
        for part in parts:
            retval += "UUID=%-40s %15s %7s %15s %d       %d\n" % (part.fs.uuid, part.fs.mntpnt, part.fs.fstab_fstype(), part.fs.fstab_options(), 0, 0)
        return retval

    def copy_settings(self):
        if os.path.exists('/etc/default/locale'):
            self.copy_to_target('/etc/default/locale', '/etc/default/locale')
        csdir = '%s/etc/console-setup' % self.destdir
        have_cs = os.path.isdir(csdir)
        if have_cs:
            shutil.rmtree(csdir)
            self.copy_to_target('/etc/console-setup', '/etc/console-setup')
            self.copy_to_target('/etc/default/console-setup', '/etc/default/console-setup')
        self.run_in_target('dpkg-reconfigure', '-fnoninteractive', '-pcritical', 'tzdata')
        self.run_in_target('locale-gen', 'en_US')
        if self.context.lang:
            self.run_in_target('locale-gen', self.context.lang)
            self.install_from_template('/etc/default/locale', 'locale', { 'lang' : self.context.lang })
        self.run_in_target('dpkg-reconfigure', '-fnoninteractive', '-pcritical', 'locales')
        if have_cs:
            self.run_in_target('dpkg-reconfigure', '-fnoninteractive', '-pcritical', 'console-setup')

    def set_timezone(self):
        timezone = self.context.get_setting('timezone')
        if timezone:
            self.install_from_template('/etc/timezone', 'timezone', { 'timezone' : timezone })
        self.run_in_target('dpkg-reconfigure', '-fnoninteractive', '-pcritical', 'tzdata')

    def prevent_daemons_starting(self):
        super(Edgy, self).prevent_daemons_starting()
        initctl = '%s/sbin/initctl' % (self.context.chroot_dir,)
        os.rename(initctl, '%s.REAL' % (initctl,))
        self.install_from_template('/sbin/initctl', 'initctl-stub', mode=0755)

    def unprevent_daemons_starting(self):
        super(Edgy, self).unprevent_daemons_starting()
        initctl = '%s/sbin/initctl' % (self.context.chroot_dir,)
        os.rename('%s.REAL' % (initctl,), initctl)
