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
import logging
import os, subprocess
import socket
import types
import shutil
import VMBuilder
from   VMBuilder           import register_distro, Distro
from   VMBuilder.util      import run_cmd
from   VMBuilder.exception import VMBuilderUserError, VMBuilderException

class Centos(Distro):
    name = 'Centos'
    arg = 'centos'
    suites = ['centos-4', 'centos-5']
    
    # Maps host arch to valid guest archs
    valid_archs = { 'amd64' : ['amd64', 'i386' ],
                    'i386' : [ 'i386' ],
                    'lpia' : [ 'i386' ] }

    xen_kernel = ''

    def register_options(self):
        group = self.setting_group('Package options')
        group.add_setting('addpkg', action='append', metavar='PKG', help='Install PKG into the guest (can be specfied multiple times).')
        group.add_setting('removepkg', action='append', metavar='PKG', help='Remove PKG from the guest (can be specfied multiple times)')

        group = self.setting_group('General OS options')
        self.host_arch = run_cmd('dpkg', '--print-architecture').rstrip()
        group.add_setting('arch', extra_args=['-a'], default=self.host_arch, help='Specify the target architecture.  Valid options: amd64 i386 (defaults to host arch)')
        group.add_setting('hostname', default='centos', help='Set NAME as the hostname of the guest. Default: centos. Also uses this name as the VM name.')

        group = self.setting_group('Installation options')
        group.add_setting('suite', default='centos-5', help='Suite to install. Valid options: %s [default: %%default]' % ' '.join(self.suites))
        group.add_setting('flavour', extra_args=['--kernel-flavour'], help='Kernel flavour to use. Default and valid options depend on architecture and suite')
        group.add_setting('mirror', metavar='URL', help='Use Centos mirror at URL instead of the default CentOS mirror list')
        group.add_setting('proxy', metavar='URL', help='Use proxy at URL for Yum packages')
        group.add_setting('install-mirror', metavar='URL', help='Use Centos mirror at URL for the installation only. Yum will still use the default or the URL set by --mirror. Default is: http://mirror.bytemark.co.uk/centos')
        group.add_setting('lang', metavar='LANG', default=self.get_locale(), help='Set the locale to LANG [default: %default]')
        group.add_setting('timezone', metavar='TZ', default='UTC', help='Set the timezone to TZ in the vm. [default: %default]')

        group = self.setting_group('Settings for the initial user')
        group.add_setting('user', default='centos', help='Username of initial user [default: %default]')
        group.add_setting('name', default='Centos', help='Full name of initial user [default: %default]')
        group.add_setting('pass', default='centos', help='Password of initial user [default: %default]')
        group.add_setting('rootpass', default='centos', help='Password of root user [default: %default]')
        group.add_setting('uid', help='Initial UID value.')
        group.add_setting('gid', help='Initial GID value.')
        group.add_setting('lock-user', action='store_true', help='Lock the initial user [default %default]')

        group = self.setting_group('Other options')
        group.add_setting('ssh-key', metavar='PATH', help='Add PATH to root\'s ~/.ssh/authorized_keys (WARNING: this has strong security implications).')
        group.add_setting('ssh-user-key', help='Add PATH to the user\'s ~/.ssh/authorized_keys.')
        group.add_setting('manifest', metavar='PATH', help='If passed, a manifest will be written to PATH')

    def set_defaults(self):
        pass

    def get_locale(self):
        return os.getenv('LANG')

    def preflight_check(self):
        """While not all of these are strictly checks, their failure would inevitably
        lead to failure, and since we can check them before we start setting up disk
        and whatnot, we might as well go ahead an do this now."""
        
        mysuite = self.get_setting("suite")

        if not mysuite in self.suites:
            raise VMBuilderUserError('Invalid suite. Valid suites are: %s' % ' '.join(self.suites))
        
        modname = 'VMBuilder.plugins.centos.%s' % (mysuite.replace('-',''), )
        mod = __import__(modname, fromlist=[mysuite.replace('-','')])
        self.suite = getattr(mod, mysuite.replace('-','').capitalize())(self)

        myarch = self.get_setting("arch")
        if myarch not in self.valid_archs[self.host_arch] or  \
            not self.suite.check_arch_validity(myarch):
            raise VMBuilderUserError('%s is not a valid architecture. Valid architectures are: %s' % (myarch, 
                                                                                                      ' '.join(self.valid_archs[self.host_arch])))

        #myhypervisor = self.get_setting('hypervisor')
        #if myhypervisor.name == 'Xen':
        #    logging.info('Xen kernel default: linux-image-%s %s', self.suite.xen_kernel_flavour, self.xen_kernel_version())

        self.virtio_net = self.use_virtio_net()

        mylang = self.get_setting("lang")
        if mylang:
            try:
                run_cmd('locale-gen', '%s' % mylang)
            except VMBuilderException, e:
                msg = "locale-gen does not recognize your locale '%s'" % mylang
                raise VMBuilderUserError(msg)

        # Make sure rinse is installed
        try:
            run_cmd('/usr/sbin/rinse')
        except VMBuilderException, e:
            msg = "The 'rinse' utility doesn't seem to be installed."
            raise VMBuilderUserError(msg)

        if getattr(self, 'ec2', False):
            self.get_ec2_kernel()
            self.get_ec2_ramdisk()
            self.apply_ec2_settings()

    def install(self, destdir):
        self.destdir = destdir
        self.suite.install(destdir)

    def install_vmbuilder_log(self, logfile, rootdir):
        self.suite.install_vmbuilder_log(logfile, rootdir)

    def post_mount(self, fs):
        self.suite.post_mount(fs)

    def use_virtio_net(self):
        return self.suite.virtio_net

    def install_bootloader_cleanup(self):
        self.cancel_cleanup(self.install_bootloader_cleanup)
        tmpdir = '%s/tmp/vmbuilder-grub' % self.destdir
        for disk in os.listdir(tmpdir):
            if disk != 'device.map':
                run_cmd('umount', os.path.join(tmpdir, disk))
        shutil.rmtree(tmpdir)

    def install_bootloader(self, chroot_dir, disks):
        tmpdir = '/tmp/vmbuilder-grub'
        os.makedirs('%s%s' % (chroot_dir, tmpdir))
        self.add_clean_cb(self.install_bootloader_cleanup)
        devmapfile = os.path.join(tmpdir, 'device.map')
        devmap = open('%s%s' % (chroot_dir, devmapfile), 'w')
        for (disk, id) in zip(disks, range(len(disks))):
            new_filename = os.path.join(tmpdir, os.path.basename(disk.filename))
            open('%s%s' % (chroot_dir, new_filename), 'w').close()
            run_cmd('mount', '--bind', disk.filename, '%s%s' % (chroot_dir, new_filename))
            devmap.write("(hd%d) %s\n" % (id, new_filename))
        devmap.close()
        #
        # There are a couple of reasons why grub installation can fail:
        #
        # "Error 2: Bad file or directory type" can be caused by an ext3
        # partition with 256 bit inodes and an older distro. See workaround
        # in disk.py.
        #
        # "Error 18: Selected cylinder exceeds maximum supported by BIOS"
        # can be caused by grub detecting a geometry that may not be
        # compatible with an older BIOS. We work around this below by
        # setting the geometry with bogus values:
        #
        self.run_in_target('grub', '--device-map=%s' % devmapfile, '--batch',  stdin='''root (hd0,0)
geometry (hd0) 800 800 800
setup (hd0)
EOT''')
        self.install_bootloader_cleanup()

    def xen_kernel_version(self):
        if self.suite.xen_kernel_flavour:
            if not self.xen_kernel:
                rmad = run_cmd('rmadison', 'linux-image-%s' % self.suite.xen_kernel_flavour)
                version = ['0', '0','0', '0']

                for line in rmad.splitlines():
                    sline = line.split('|')
                    
                    if sline[2].strip().startswith(self.suite):
                        vt = sline[1].strip().split('.')
                        for i in range(4):
                            if int(vt[i]) > int(version[i]):
                                version = vt
                                break

                if version[0] == '0':
                    raise VMBuilderException('Something is wrong, no valid xen kernel for the suite %s found by rmadison' % self.suite)
                
                self.xen_kernel = '%s.%s.%s-%s' % (version[0],version[1],version[2],version[3])
            return self.xen_kernel
        else:
            raise VMBuilderUserError('There is no valid xen kernel for the suite selected.')

    def xen_kernel_initrd_path(self, which):
        path = '/boot/%s-%s-%s' % (which, self.xen_kernel_version(), self.suite.xen_kernel_flavour)
        return path

    def xen_kernel_path(self):
        return self.xen_kernel_initrd_path('kernel')

    def xen_ramdisk_path(self):
        return self.xen_kernel_initrd_path('ramdisk')

    def get_ec2_kernel(self):
        if self.suite.ec2_kernel_info:
            return self.suite.ec2_kernel_info[self.arch]
        else:
            raise VMBuilderUserError('EC2 is not supported for the suite selected')

    def get_ec2_ramdisk(self):
        if self.suite.ec2_ramdisk_info:
            return self.suite.ec2_ramdisk_info[self.arch]
        else:
            raise VMBuilderUserError('EC2 is not supported for the suite selected')
            
    def preferred_filesystem(self):
        return self.suite.preferred_filesystem
        
    def has_256_bit_inode_ext3_support(self):
        return self.suite.has_256_bit_inode_ext3_support()

    def disable_hwclock_access(self):
        return self.suite.disable_hwclock_access()

    def apply_ec2_settings(self):
        return self.suite.apply_ec2_settings()

register_distro(Centos)
