#
#    Uncomplicated VM Builder
#    Copyright (C) 2007-2010 Canonical Ltd.
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
import os
import shutil
import stat
import VMBuilder
from   VMBuilder           import register_distro, Distro
from   VMBuilder.util      import run_cmd
from   VMBuilder.exception import VMBuilderUserError, VMBuilderException

class Ubuntu(Distro):
    name = 'Ubuntu'
    arg = 'ubuntu'
    suites = ['dapper', 'gutsy', 'hardy', 'intrepid', 'jaunty', 
              'karmic', 'lucid', 'maverick', 'natty', 'oneiric',
              'precise' ]

    # Maps host arch to valid guest archs
    valid_archs = { 'amd64' : ['amd64', 'i386', 'lpia' ],
                    'i386' : [ 'i386', 'lpia' ],
                    'lpia' : [ 'i386', 'lpia' ] }

    xen_kernel = ''

    def register_options(self):
        group = self.setting_group('Package options')
        group.add_setting('addpkg', type='list', metavar='PKG', help='Install PKG into the guest (can be specified multiple times).')
        group.add_setting('removepkg', type='list', metavar='PKG', help='Remove PKG from the guest (can be specified multiple times)')
        group.add_setting('seedfile', metavar="SEEDFILE", help='Seed the debconf database with the contents of this seed file before installing packages')

        group = self.setting_group('General OS options')
        self.host_arch = run_cmd('dpkg', '--print-architecture').rstrip()
        group.add_setting('arch', extra_args=['-a'], default=self.host_arch, help='Specify the target architecture.  Valid options: amd64 i386 lpia (defaults to host arch)')
        group.add_setting('hostname', default='ubuntu', help='Set NAME as the hostname of the guest. Default: ubuntu. Also uses this name as the VM name.')

        group = self.setting_group('Installation options')
        group.add_setting('suite', default='lucid', help='Suite to install. Valid options: %s [default: %%default]' % ' '.join(self.suites))
        group.add_setting('flavour', extra_args=['--kernel-flavour'], help='Kernel flavour to use. Default and valid options depend on architecture and suite')
        group.add_setting('variant', metavar='VARIANT', help='Passed to debootstrap --variant flag; use minbase, buildd, or fakechroot.')
        group.add_setting('iso', metavar='PATH', help='Use an iso image as the source for installation of file. Full path to the iso must be provided. If --mirror is also provided, it will be used in the final sources.list of the vm.  This requires suite and kernel parameter to match what is available on the iso, obviously.')
        group.add_setting('mirror', metavar='URL', help='Use Ubuntu mirror at URL instead of the default, which is http://archive.ubuntu.com/ubuntu for official arches and http://ports.ubuntu.com/ubuntu-ports otherwise')
        group.add_setting('proxy', metavar='URL', help='Use proxy at URL for cached packages')
        group.add_setting('install-mirror', metavar='URL', help='Use Ubuntu mirror at URL for the installation only. Apt\'s sources.list will still use default or URL set by --mirror')
        group.add_setting('security-mirror', metavar='URL', help='Use Ubuntu security mirror at URL instead of the default, which is http://security.ubuntu.com/ubuntu for official arches and http://ports.ubuntu.com/ubuntu-ports otherwise.')
        group.add_setting('install-security-mirror', metavar='URL', help='Use the security mirror at URL for installation only. Apt\'s sources.list will still use default or URL set by --security-mirror')
        group.add_setting('components', type='list', metavar='COMPS', help='A comma seperated list of distro components to include (e.g. main,universe).')
        group.add_setting('ppa', metavar='PPA', type='list', help='Add ppa belonging to PPA to the vm\'s sources.list.')
        group.add_setting('lang', metavar='LANG', default=get_locale(), help='Set the locale to LANG [default: %default]')
        group.add_setting('timezone', metavar='TZ', default='UTC', help='Set the timezone to TZ in the vm. [default: %default]')

        group = self.setting_group('Settings for the initial user')
        group.add_setting('user', default='ubuntu', help='Username of initial user [default: %default]')
        group.add_setting('name', default='Ubuntu', help='Full name of initial user [default: %default]')
        group.add_setting('pass', default='ubuntu', help='Password of initial user [default: %default]')
        group.add_setting('rootpass', help='Initial root password (WARNING: this has strong security implications).')
        group.add_setting('uid', type='int', help='Initial UID value.')
        group.add_setting('gid', help='Initial GID value.')
        group.add_setting('lock-user', type='bool', default=False, help='Lock the initial user [default: %default]')

        group = self.setting_group('Other options')
        group.add_setting('ssh-key', metavar='PATH', help='Add PATH to root\'s ~/.ssh/authorized_keys (WARNING: this has strong security implications).')
        group.add_setting('ssh-user-key', help='Add PATH to the user\'s ~/.ssh/authorized_keys.')
        group.add_setting('manifest', metavar='PATH', help='If passed, a manifest will be written to PATH')

    def set_defaults(self):
        arch = self.get_setting('arch')

        if arch == 'lpia':
            self.set_setting_default('mirror', 'http://ports.ubuntu.com/ubuntu-ports')
            self.set_setting_default('security-mirror', 'http://ports.ubuntu.com/ubuntu-ports')
        else:
            self.set_setting_default('mirror', 'http://archive.ubuntu.com/ubuntu')
            self.set_setting_default('security-mirror', 'http://security.ubuntu.com/ubuntu')

        self.set_setting_default('components',  ['main', 'restricted', 'universe'])

    def preflight_check(self):
        """While not all of these are strictly checks, their failure would inevitably
        lead to failure, and since we can check them before we start setting up disk
        and whatnot, we might as well go ahead an do this now."""

        suite = self.get_setting('suite') 
        if not suite in self.suites:
            raise VMBuilderUserError('Invalid suite: "%s". Valid suites are: %s' % (suite, ' '.join(self.suites)))
        
        modname = 'VMBuilder.plugins.ubuntu.%s' % (suite, )
        mod = __import__(modname, fromlist=[suite])
        self.suite = getattr(mod, suite.capitalize())(self)

        arch = self.get_setting('arch') 
        if arch not in self.valid_archs[self.host_arch] or  \
            not self.suite.check_arch_validity(arch):
            raise VMBuilderUserError('%s is not a valid architecture. Valid architectures are: %s' % (arch,
                                                                                                      ' '.join(self.valid_archs[self.host_arch])))

        components = self.get_setting('components')
        if not components:
            self.set_config_value_list = ['main', 'restricted', 'universe']
        else:
            if type(components) is str:
                self.vm.components = self.vm.components.split(',')

        self.context.virtio_net = self.use_virtio_net()

        # check if the seedfile exists if one is to be used
        seedfile = self.context.get_setting('seedfile')
        if seedfile and not os.path.exists(seedfile):
            raise VMBuilderUserError("Seedfile '%s' does not exist" % seedfile)

        lang = self.get_setting('lang')

# FIXME
#        if getattr(self.vm, 'ec2', False):
#            self.get_ec2_kernel()
#            self.get_ec2_ramdisk()
#            self.apply_ec2_settings()

    def bootstrap(self):
        self.suite.debootstrap()
        self.suite.pre_install()

    def configure_os(self):
        self.suite.install_sources_list()
        self.suite.install_apt_proxy()
        self.suite.create_devices()
        self.suite.prevent_daemons_starting()
        self.suite.mount_dev_proc()
        self.suite.install_extras()
        self.suite.create_initial_user()
        self.suite.install_authorized_keys()
        self.suite.set_timezone()
        self.suite.set_locale()
        self.suite.update()
        self.suite.install_sources_list(final=True)
        self.suite.run_in_target('apt-get', 'clean');
        self.suite.unmount_volatile()
        self.suite.unmount_proc()
        self.suite.unmount_dev_pts()
        self.suite.unmount_dev()
        self.suite.unprevent_daemons_starting()
        self.suite.create_manifest()

    def configure_networking(self, nics):
        self.suite.config_host_and_domainname()
        self.suite.config_interfaces(nics)

    def configure_mounting(self, disks, filesystems):
        self.suite.install_fstab(disks, filesystems)

    def install(self, destdir):
        self.destdir = destdir
        self.suite.install(destdir)

    def install_vmbuilder_log(self, logfile, rootdir):
        self.suite.install_vmbuilder_log(logfile, rootdir)

    def post_mount(self, fs):
        self.suite.post_mount(fs)

    def use_virtio_net(self):
        return self.suite.virtio_net

    def install_bootloader_cleanup(self, chroot_dir):
        self.context.cancel_cleanup(self.install_bootloader_cleanup)
        tmpdir = '%s/tmp/vmbuilder-grub' % chroot_dir
        for disk in os.listdir(tmpdir):
            if disk != 'device.map':
                run_cmd('umount', os.path.join(tmpdir, disk))
        shutil.rmtree(tmpdir)

    def install_kernel(self, destdir):
        self.suite.install_kernel(destdir)

    def install_bootloader(self, chroot_dir, disks):
        root_dev = VMBuilder.disk.bootpart(disks).get_grub_id()

        tmpdir = '/tmp/vmbuilder-grub'
        os.makedirs('%s%s' % (chroot_dir, tmpdir))
        self.context.add_clean_cb(self.install_bootloader_cleanup)
        devmapfile = os.path.join(tmpdir, 'device.map')
        devmap = open('%s%s' % (chroot_dir, devmapfile), 'w')
        for (disk, id) in zip(disks, range(len(disks))):
            new_filename = os.path.join(tmpdir, os.path.basename(disk.filename))
            open('%s%s' % (chroot_dir, new_filename), 'w').close()
            run_cmd('mount', '--bind', disk.filename, '%s%s' % (chroot_dir, new_filename))
            st = os.stat(disk.filename)
            if stat.S_ISBLK(st.st_mode):
                for (part, part_id) in zip(disk.partitions, range(len(disk.partitions))):
                    part_mountpnt = '%s%s%d' % (chroot_dir, new_filename, part_id+1)
                    open(part_mountpnt, 'w').close()
                    run_cmd('mount', '--bind', part.filename, part_mountpnt)
            devmap.write("(hd%d) %s\n" % (id, new_filename))
        devmap.close()
        run_cmd('cat', '%s%s' % (chroot_dir, devmapfile))
        self.suite.install_grub(chroot_dir)
        self.run_in_target('grub', '--device-map=%s' % devmapfile, '--batch',  stdin='''root %s
setup (hd0)
EOT''' % root_dev) 
        self.suite.install_menu_lst(disks)
        self.install_bootloader_cleanup(chroot_dir)

    def xen_kernel_version(self):
        if self.suite.xen_kernel_flavour:
            # if this is ec2, do not call rmadison.
            # this could be replaced with a method to get most recent
            # stable kernel, but really, this is not used at all for ec2
            if hasattr(self.context, 'ec2') and self.context.ec2:
                logging.debug("selecting ec2 kernel")
                self.xen_kernel = "2.6.ec2-kernel"
                return self.xen_kernel
            if not self.xen_kernel:
                rmad = run_cmd('rmadison', 'linux-image-%s' % self.suite.xen_kernel_flavour)
                version = ['0', '0','0', '0']

                for line in rmad.splitlines():
                    sline = line.split('|')

                    if sline[2].strip().startswith(self.context.get_setting('suite')):
                        vt = sline[1].strip().split('.')
                        for i in range(4):
                            if int(vt[i]) > int(version[i]):
                                version = vt
                                break

                if version[0] == '0':
                    raise VMBuilderException('Something is wrong, no valid xen kernel for the suite %s found by rmadison' % self.context.suite)

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
            return self.suite.ec2_kernel_info[self.context.arch]
        else:
            raise VMBuilderUserError('EC2 is not supported for the suite selected')

    def get_ec2_ramdisk(self):
        if self.suite.ec2_ramdisk_info:
            return self.suite.ec2_ramdisk_info[self.context.arch]
        else:
            raise VMBuilderUserError('EC2 is not supported for the suite selected')

    def disable_hwclock_access(self):
        return self.suite.disable_hwclock_access()

    def apply_ec2_settings(self):
        return self.suite.apply_ec2_settings()

    def has_256_bit_inode_ext3_support(self):
        return self.suite.has_256_bit_inode_ext3_support()

    def preferred_filesystem(self):
        return self.suite.preferred_filesystem

def get_locale():
    lang = os.getenv('LANG')
    if lang is None:
        return 'C'
    # People's $LANG looks different since lucid, but locale-gen still
    # wants the old format.
    if lang.endswith('utf8'):
        return lang[:-4] + 'UTF-8'
    return lang

register_distro(Ubuntu)
