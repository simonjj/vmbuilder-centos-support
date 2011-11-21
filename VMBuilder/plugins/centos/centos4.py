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
import glob
import logging
import os
import suite
import shutil
import socket
import tempfile
import VMBuilder
import VMBuilder.disk as disk
from   VMBuilder.util import run_cmd

class Centos4(suite.Suite):
    grubroot = "/usr/share/grub"
    # FIXME: do we need i586 kernel support?
    valid_flavours = { 'i386' :  ['kernel', 'kernel-hugemem', 'kernel-smp', 'kernel-xenU'],
                       'amd64' : ['kernel', 'kernel-largesmp', 'kernel-smp', 'kernel-xenU']}
    default_flavour = { 'i386' : 'kernel', 'amd64' : 'kernel' }
    kernel_version = ''

    disk_prefix = 'hd'
    xen_kernel_flavour = None
    virtio_net = False
    chpasswd_cmd = [ 'chpasswd' ]
    preferred_filesystem = 'ext3'
    rinse_conf = '''
[%s]
mirror       = %s/4/os/i386/CentOS/RPMS/
mirror.amd64 = %s/4/os/x86_64/CentOS/RPMS/
'''

    def pre_install(self):
        pass

    def check_kernel_flavour(self, arch, flavour):
        return flavour in self.valid_flavours[arch]

    def check_arch_validity(self, arch):
        return arch in self.valid_flavours.keys()
        
    def install(self, destdir):
        self.destdir = destdir

        logging.debug("Launching Rinse")
        self.rinse()

        self.pre_install()

        logging.debug("Setting up Yum config")
        self.install_yum_conf()

        logging.debug('Binding /dev and /proc filesystems')
        self.mount_dev_proc()
    
        logging.debug("Setting up Yum proxy")
        self.install_yum_proxy()

        logging.debug("Installing core packages")
        self.install_core()

        logging.debug("Installing fstab")
        self.install_fstab()

        logging.debug("Creating devices")
        self.create_devices()

        if self.vm.hypervisor.needs_bootloader:
            logging.debug("Installing grub")
            self.install_grub()

        logging.debug("Configuring guest networking")
        self.config_network()

        if self.vm.hypervisor.needs_bootloader:
            logging.debug("Installing kernel")
            self.install_kernel()

            logging.debug("Installing menu.list")
            self.install_menu_lst()

            logging.debug("Creating device.map")
            self.install_device_map()

            logging.debug("Updating initrd")
            self.update_initrd()


        logging.debug("Installing extra packages")
        self.install_extras()

        logging.debug("Creating initial user")
        self.create_initial_user()

        logging.debug("Installing ssh keys")
        self.install_authorized_keys()

        logging.debug("Copy host settings")
        self.copy_settings()

        logging.debug("Setting timezone")
        self.set_timezone()

        logging.debug("Setting up final Yum config")
        self.install_yum_conf(final=True)

        logging.debug("cleaning apt")
        self.run_in_target('yum', 'clean', 'all');

        logging.debug("Force SELinux autorelabel")
        self.selinux_autorelabel()

        logging.debug("Unmounting volatile lrm filesystems")
        self.unmount_volatile()

        logging.debug('Unbinding /dev and /proc filesystems')
        self.unmount_dev_proc()

        if hasattr(self.vm, 'ec2') and self.vm.ec2:
            logging.debug("Configuring for ec2")
            self.install_ec2()

        if self.vm.manifest:
            logging.debug("Creating manifest")
            manifest_contents = self.run_in_target('rpm', '-qa', '--pipe', 'sort')
            fp = open(self.vm.manifest, 'w')
            fp.write(manifest_contents)
            fp.close

    def install_authorized_keys(self):
        if self.vm.ssh_key:
            os.mkdir('%s/root/.ssh' % self.destdir, 0700)
            shutil.copy(self.vm.ssh_key, '%s/root/.ssh/authorized_keys' % self.destdir)
            os.chmod('%s/root/.ssh/authorized_keys' % self.destdir, 0644)
        if self.vm.ssh_user_key:
            os.mkdir('%s/home/%s/.ssh' % (self.destdir, self.vm.user), 0700)
            shutil.copy(self.vm.ssh_user_key, '%s/home/%s/.ssh/authorized_keys' % (self.destdir, self.vm.user))
            os.chmod('%s/home/%s/.ssh/authorized_keys' % (self.destdir, self.vm.user), 0644)
            self.run_in_target('chown', '-R', '%s:%s' % (self.vm.user,)*2, '/home/%s/.ssh/' % (self.vm.user)) 

        if self.vm.ssh_user_key or self.vm.ssh_key:
            if not self.vm.addpkg:
                self.vm.addpkg = []
            self.vm.addpkg += ['openssh-server']

    def mount_dev_proc(self):
        run_cmd('mount', '--bind', '/dev', '%s/dev' % self.destdir)
        self.vm.add_clean_cmd('umount', '%s/dev' % self.destdir, ignore_fail=True)

        run_cmd('mount', '--bind', '/dev/pts', '%s/dev/pts' % self.destdir)
        self.vm.add_clean_cmd('umount', '%s/dev/pts' % self.destdir, ignore_fail=True)

        self.run_in_target('mount', '-t', 'proc', 'proc', '/proc')
        self.vm.add_clean_cmd('umount', '%s/proc' % self.destdir, ignore_fail=True)

    def unmount_dev_proc(self):
    	run_cmd('umount', '%s/dev/pts' % self.destdir)
        run_cmd('umount', '%s/dev' % self.destdir)
        run_cmd('umount', '%s/proc' % self.destdir)

    def update_passwords(self):
        # Set the user password
        self.run_in_target(stdin=('%s:%s\n' % (self.vm.user, getattr(self.vm, 'pass'))), *self.chpasswd_cmd)

        # Set the root password
        self.run_in_target(stdin=('%s:%s\n' % ('root', self.vm.rootpass)), *self.chpasswd_cmd)

        if self.vm.lock_user:
            logging.info('Locking %s' %(self.vm.user))
            self.run_in_target('usermod', '-L', self.vm.user)

    def create_initial_user(self):
        # Make sure we have a shadow file
        self.run_in_target('pwconv')
        if self.vm.uid:
            self.run_in_target('useradd', '-u', self.vm.uid, '-c', self.vm.name, self.vm.user)
        else:
            self.run_in_target('useradd', '-c', self.vm.name, self.vm.user)

        self.update_passwords()

    def kernel_name(self):
        return '%s' % (self.vm.flavour or self.default_flavour[self.vm.arch],)

    def config_network(self):
        self.install_from_template('/etc/sysconfig/network', 'network', { 'hostname' : self.vm.hostname }) 
        self.install_from_template('/etc/hosts', 'etc_hosts', { 'hostname' : self.vm.hostname, 'domain' : self.vm.domain }) 

        # FIXME: missing static ip configuration in template
        self.install_from_template('/etc/sysconfig/network-scripts/ifcfg-eth0', 'ifcfg-eth0')

    def install_extras(self):
        if not self.vm.addpkg and not self.vm.removepkg:
            return

        cmd = ['yum', '-y', 'remove']
        cmd += self.vm.removepkg or []
        self.run_in_target(*cmd)

        cmd = ['yum', '-y', 'install']
        cmd += self.vm.addpkg or []
        self.run_in_target(*cmd)
        
    def unmount_volatile(self):
        for mntpnt in glob.glob('%s/lib/modules/*/volatile' % self.destdir):
            logging.debug("Unmounting %s" % mntpnt)
            run_cmd('umount', mntpnt)

    def install_menu_lst(self):
        bootdev = disk.bootpart(self.vm.disks)
        bootdevice = '/dev/%s%s%d' % (self.disk_prefix, bootdev.disk.devletters(), bootdev.get_index()+1)
        grubdevice = bootdev.get_grub_id()

        self.install_from_template('/boot/grub/grub.conf', 'grub.conf', { 'kernel_version' : self.kernel_version, 'bootdevice' : bootdevice, 'grubdevice' : grubdevice })
        
        self.run_in_target('ln', '-s', '/boot/grub/grub.conf', '/boot/grub/menu.lst')

    def install_yum_conf(self, final=False):
        if final:
                mirror = self.vm.mirror
        else:
                mirror = self.vm.install_mirror

        if mirror:
            self.install_from_template('/etc/yum.repos.d/CentOS-Base.repo', 'base.repo.mirror', { 'mirror' : mirror })
        else:
            self.install_from_template('/etc/yum.repos.d/CentOS-Base.repo', 'base.repo', { })

    def install_core(self):
        self.run_in_target('yum', '-y', 'clean', 'all')
        self.run_in_target('yum', '-y', 'groupinstall', 'core')

    def install_yum_proxy(self):
        if self.vm.proxy is not None:
            fp = open('%s/etc/yum.conf' % self.destdir, 'a')
            fp.write('proxy=%s' % self.vm.proxy)
            fp.close()

    def install_fstab(self):
        if self.vm.hypervisor.preferred_storage == VMBuilder.hypervisor.STORAGE_FS_IMAGE:
            self.install_from_template('/etc/fstab', 'fstab_fsimage', { 'fss' : disk.get_ordered_filesystems(self.vm), 'prefix' : self.disk_prefix })
        else:
            self.install_from_template('/etc/fstab', 'fstab', { 'parts' : disk.get_ordered_partitions(self.vm.disks), 'prefix' : self.disk_prefix })

    def install_device_map(self):
        self.install_from_template('/boot/grub/device.map', 'devicemap', { 'prefix' : self.disk_prefix })

    def rinse(self):
        # Work around bug in rinse: it doesn't set the rpm platform file,
        # so yum uses os.uname to get $arch and tries to install packages
        # for the wrong architecture
        os.mkdir('%s/etc' % self.destdir, 0755)
        os.mkdir('%s/etc/rpm' % self.destdir, 0755)

        if self.vm.arch == 'amd64':
            self.vm.install_file('/etc/rpm/platform', 'x86_64-redhat-linux')
        else:
            self.vm.install_file('/etc/rpm/platform', 'i686-redhat-linux')

        # Let's select a mirror for installation
        if not self.vm.install_mirror:
            if self.vm.mirror:
                self.vm.install_mirror = self.vm.mirror
            else:
                self.vm.install_mirror = 'http://mirror.bytemark.co.uk/centos'

        # Create temporary rinse config file so we can force a mirror
        # Of course, rinse will only use the mirror to download the
        # initial packages itself, once it spawns yum in the chroot, yum
        # uses the default config file.
        (rinse_conf_handle, rinse_conf_name) = tempfile.mkstemp()
        self.vm.add_clean_cb(lambda:os.remove(rinse_conf_name))
        os.write(rinse_conf_handle, self.rinse_conf % (self.vm.suite, self.vm.install_mirror, self.vm.install_mirror))

        self.vm.add_clean_cmd('umount', '%s/proc' % self.destdir, ignore_fail=True)
        cmd = ['/usr/sbin/rinse', '--config', rinse_conf_name, '--arch', self.vm.arch, '--distribution', self.vm.suite, '--directory', self.destdir ]
        run_cmd(*cmd)

    def install_kernel(self):
        self.run_in_target('yum', '-y', 'install', self.kernel_name())

        # Get the kernel version
        self.kernel_version = self.run_in_target('rpm', '-q', '--qf', '%{V}-%{R}', self.kernel_name())

    def update_initrd(self):
        self.run_in_target('mkinitrd', '-f', '/boot/initrd-' + self.kernel_version + '.img', self.kernel_version)

    def install_grub(self):
        self.run_in_target('yum', '-y', 'install', 'grub')

        run_cmd('rsync', '-a', '%s%s/%s/' % (self.destdir, self.grubroot, self.vm.arch == 'amd64' and 'x86_64-redhat' or 'i386-redhat'), '%s/boot/grub/' % self.destdir)

    def selinux_autorelabel(self):
        self.run_in_target('touch', '/.autorelabel')

    def create_devices(self):
        import VMBuilder.plugins.xen

        if isinstance(self.vm.hypervisor, VMBuilder.plugins.xen.Xen):
            self.run_in_target('mknod', '/dev/xvda', 'b', '202', '0')
            self.run_in_target('mknod', '/dev/xvda1', 'b', '202', '1')
            self.run_in_target('mknod', '/dev/xvda2', 'b', '202', '2')
            self.run_in_target('mknod', '/dev/xvda3', 'b', '202', '3')
            self.run_in_target('mknod', '/dev/xvc0', 'c', '204', '191')

    def install_from_template(self, *args, **kwargs):
        return self.vm.distro.install_from_template(*args, **kwargs)

    def run_in_target(self, *args, **kwargs):
        return self.vm.distro.run_in_target(*args, **kwargs)

    def copy_to_target(self, infile, destpath):
        logging.debug("Copying %s on host to %s in guest" % (infile, destpath))
        dir = '%s/%s' % (self.destdir, os.path.dirname(destpath))
        if not os.path.isdir(dir):
            os.makedirs(dir)
        if os.path.isdir(infile):
            shutil.copytree(infile, '%s/%s' % (self.destdir, destpath))
        else:
            shutil.copy(infile, '%s/%s' % (self.destdir, destpath))

    def post_mount(self, fs):
        if fs.mntpnt == '/':
            logging.debug("Creating /var/run in root filesystem")
            os.makedirs('%s/var/run' % fs.mntpath)
            logging.debug("Creating /var/lock in root filesystem")
            os.makedirs('%s/var/lock' % fs.mntpath)

    def copy_settings(self):
        if not self.vm.lang:
            locale = '/etc/default/locale'
            if os.path.exists(locale):
                locale_file=open(locale)
                for line in locale_file.readline():
                    if line.startswith("LANG="):
                        self.vm.lang = line
            else:
                self.vm.lang = 'en_US.UTF-8'

        # Is this a unicode LANG?
        if '.' in self.vm.lang:
            supported=self.vm.lang + ':' + self.vm.lang.split('.')[0] + ':' + self.vm.lang.split('_')[0]
        else:
            supported=self.vm.lang + ':' + self.vm.lang.split('_')[0]

        # FIXME: Probably need to set a SYSFONT also
        self.install_from_template('/etc/sysconfig/i18n', 'i18n', { 'lang' : self.vm.lang, 'supported' : supported })

    def install_vmbuilder_log(self, logfile, rootdir):
        shutil.copy(logfile, '%s/var/log/vmbuilder-install.log' % (rootdir,))

    def set_timezone(self):
        if self.vm.timezone:
            os.unlink('%s/etc/localtime' % self.destdir)
            shutil.copy('%s/usr/share/zoneinfo/%s' % (self.destdir, self.vm.timezone), '%s/etc/localtime' % (self.destdir,))
            
    def has_256_bit_inode_ext3_support(self):
        return True
        

    def install_ec2(self):
        if self.vm.ec2:
            logging.debug('This suite does not support ec2')

    # FIXME: Do we need to do something for CentOS?
    def disable_hwclock_access(self):
        pass

