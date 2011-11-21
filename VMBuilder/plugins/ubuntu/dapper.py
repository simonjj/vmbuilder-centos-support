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
import glob
import logging
import os
import suite
import shutil
import tempfile
import VMBuilder.disk as disk
from   VMBuilder.util import run_cmd
from   VMBuilder.exception import VMBuilderException

class Dapper(suite.Suite):
    updategrub = "/sbin/update-grub"
    grubroot = "/lib/grub"
    valid_flavours = { 'i386' :  ['386', '686', '686-smp', 'k7', 'k7-smp', 'server', 'server-bigiron'],
                       'amd64' : ['amd64-generic', 'amd64-k8', 'amd64-k8-smp', 'amd64-server', 'amd64-xeon']}
    default_flavour = { 'i386' : 'server', 'amd64' : 'amd64-server' }
    disk_prefix = 'hd'
    xen_kernel_flavour = None
    virtio_net = False
    chpasswd_cmd = [ 'chpasswd', '--md5' ]
    preferred_filesystem = 'ext3'

    def pre_install(self):
        pass

    def check_kernel_flavour(self, arch, flavour):
        return flavour in self.valid_flavours[arch]

    def check_arch_validity(self, arch):
        return arch in self.valid_flavours.keys()

    def install(self, destdir):
        raise VMBuilderException('Do not call this method!')

        # These are still missing after the refactoring.
        logging.debug("Creating device.map")
        self.install_device_map()

        logging.debug("Copy host settings")
        self.copy_settings()

        if hasattr(self.context, 'ec2') and self.context.ec2:
            logging.debug("Configuring for ec2")
            self.install_ec2()

    def create_manifest(self):
        manifest = self.context.get_setting('manifest')
        if manifest:
            logging.debug("Creating manifest")
            manifest_contents = self.run_in_target('dpkg-query', '-W', '--showformat=${Package} ${Version}\n')
            fp = open(manifest, 'w')
            fp.write(manifest_contents)
            fp.close
            self.call_hook('fix_ownership', manifest)

    def update(self):
        self.run_in_target('apt-get', '-y', '--force-yes', 'dist-upgrade',
                           env={ 'DEBIAN_FRONTEND' : 'noninteractive' })

    def install_authorized_keys(self):
        ssh_key = self.context.get_setting('ssh-key')
        if ssh_key:
            os.mkdir('%s/root/.ssh' % self.context.chroot_dir, 0700)
            shutil.copy(ssh_key, '%s/root/.ssh/authorized_keys' % self.context.chroot_dir)
            os.chmod('%s/root/.ssh/authorized_keys' % self.context.chroot_dir, 0644)

        user = self.context.get_setting('user')
        ssh_user_key = self.context.get_setting('ssh-user-key')
        if ssh_user_key:
            os.mkdir('%s/home/%s/.ssh' % (self.context.chroot_dir, user), 0700)
            shutil.copy(ssh_user_key, '%s/home/%s/.ssh/authorized_keys' % (self.context.chroot_dir, user))
            os.chmod('%s/home/%s/.ssh/authorized_keys' % (self.context.chroot_dir, user), 0644)
            self.run_in_target('chown', '-R', '%s:%s' % ((user,)*2), '/home/%s/.ssh/' % (user)) 

        if ssh_user_key or ssh_key:
            addpkg = self.context.get_setting('addpkg')
            addpkg += ['openssh-server']
            self.context.set_setting('addpkg', addpkg)

    def mount_dev_proc(self):
        run_cmd('mount', '--bind', '/dev', '%s/dev' % self.context.chroot_dir)
        self.context.add_clean_cb(self.unmount_dev)

        run_cmd('mount', '--bind', '/dev/pts', '%s/dev/pts' % self.context.chroot_dir)
        self.context.add_clean_cb(self.unmount_dev_pts)

        self.run_in_target('mount', '-t', 'proc', 'proc', '/proc')
        self.context.add_clean_cb(self.unmount_proc)

    def unmount_proc(self):
        self.context.cancel_cleanup(self.unmount_proc)
        run_cmd('umount', '%s/proc' % self.context.chroot_dir)

    def unmount_dev_pts(self):
        self.context.cancel_cleanup(self.unmount_dev_pts)
        run_cmd('umount', '%s/dev/pts' % self.context.chroot_dir)

    def unmount_dev(self):
        self.context.cancel_cleanup(self.unmount_dev)
        run_cmd('umount', '%s/dev' % self.context.chroot_dir)

    def update_passwords(self):
        # Set the user password, using md5
        user   = self.context.get_setting('user')
        passwd = self.context.get_setting('pass')
        self.run_in_target(stdin=('%s:%s\n' % (user, passwd)), *self.chpasswd_cmd)

        # Lock root account only if we didn't set the root password
        rootpass = self.context.get_setting('rootpass')
        if rootpass:
            self.run_in_target(stdin=('%s:%s\n' % ('root', rootpass)), *self.chpasswd_cmd)
        else:
            self.run_in_target('usermod', '-L', 'root')

        lock_user = self.context.get_setting('lock-user')
        if lock_user:
            logging.info('Locking %s' % (user, ))
            self.run_in_target('usermod', '-L', user)

    def create_initial_user(self):
        uid  = self.context.get_setting('uid')
        name = self.context.get_setting('name')
        user = self.context.get_setting('user')
        if uid:
            self.run_in_target('adduser', '--disabled-password', '--uid', uid, '--gecos', name, user)
        else:
            self.run_in_target('adduser', '--disabled-password', '--gecos', name, user)

        self.run_in_target('addgroup', '--system', 'admin')
        self.run_in_target('adduser', user, 'admin')

        self.install_from_template('/etc/sudoers', 'sudoers')
        for group in ['adm', 'audio', 'cdrom', 'dialout', 'floppy', 'video', 'plugdev', 'dip', 'netdev', 'powerdev', 'lpadmin', 'scanner']:
            self.run_in_target('adduser', user, group, ignore_fail=True)

        self.update_passwords()

    def kernel_name(self):
        flavour = self.context.get_setting('flavour')
        arch = self.context.get_setting('arch')
        return 'linux-image-%s' % (flavour or self.default_flavour[arch],)

    def config_host_and_domainname(self):
        hostname = self.context.get_setting('hostname')
        domain = self.context.get_setting('domain')
        self.context.install_file('/etc/hostname', hostname)
        self.install_from_template('/etc/hosts', 'etc_hosts', { 'hostname' : hostname, 'domain' : domain }) 

    def config_interfaces(self, nics):
        self.install_from_template('/etc/network/interfaces', 'interfaces',
                                   { 'ip' : nics[0].type == 'dhcp' and 'dhcp' or nics[0].ip,
                                     'mask' : nics[0].netmask,
                                     'net' : nics[0].network,
                                     'bcast' : nics[0].broadcast,
                                     'gw' : nics[0].gateway,
                                     'dns' : nics[0].dns,
                                     'domain' : self.context.get_setting('domain') })

    def unprevent_daemons_starting(self):
        os.unlink('%s/usr/sbin/policy-rc.d' % self.context.chroot_dir)

    def prevent_daemons_starting(self):
        os.chmod(self.install_from_template('/usr/sbin/policy-rc.d', 'nostart-policy-rc.d'), 0755)

    def seed(self, seedfile):
        """Seed debconf with the contents of a seedfile"""
        logging.info('Seeding with "%s"' % seedfile)

        self.run_in_target('debconf-set-selections', stdin=open(seedfile, 'r').read())

    def install_extras(self):
        seedfile = self.context.get_setting('seedfile')
        if seedfile:
            self.seed(seedfile)

        addpkg = self.context.get_setting('addpkg')
        removepkg = self.context.get_setting('removepkg')
        if not addpkg and not removepkg:
            return

        cmd = ['apt-get', 'install', '-y', '--force-yes']
        cmd += addpkg or []
        cmd += ['%s-' % pkg for pkg in removepkg or []]
        self.run_in_target(env={ 'DEBIAN_FRONTEND' : 'noninteractive' }, *cmd)

    def unmount_volatile(self):
        for mntpnt in glob.glob('%s/lib/modules/*/volatile' % self.context.chroot_dir):
            logging.debug("Unmounting %s" % mntpnt)
            run_cmd('umount', mntpnt)

    def install_menu_lst(self, disks):
        self.run_in_target(self.updategrub, '-y')
        self.mangle_grub_menu_lst(disks)
        self.run_in_target(self.updategrub)
        self.run_in_target('grub-set-default', '0')

    def mangle_grub_menu_lst(self, disks):
        bootdev = disk.bootpart(disks)
        run_cmd('sed', '-ie', 's/^# kopt=root=\([^ ]*\)\(.*\)/# kopt=root=\/dev\/hd%s%d\\2/g' % (bootdev.disk.devletters(), bootdev.get_index()+1), '%s/boot/grub/menu.lst' % self.context.chroot_dir)
        run_cmd('sed', '-ie', 's/^# groot.*/# groot %s/g' % bootdev.get_grub_id(), '%s/boot/grub/menu.lst' % self.context.chroot_dir)
        run_cmd('sed', '-ie', '/^# kopt_2_6/ d', '%s/boot/grub/menu.lst' % self.context.chroot_dir)

    def install_sources_list(self, final=False):
        if final:
            mirror = updates_mirror = self.context.get_setting('mirror')
            security_mirror = self.context.get_setting('security-mirror')
        else:
            mirror, updates_mirror, security_mirror = self.install_mirrors()

        components = self.context.get_setting('components')
        ppa        = self.context.get_setting('ppa')
        suite      = self.context.get_setting('suite')
        self.install_from_template('/etc/apt/sources.list', 'sources.list', { 'mirror' : mirror,
                                                                              'security_mirror' : security_mirror,
                                                                              'updates_mirror' : updates_mirror,
                                                                              'components' : components,
                                                                              'ppa' : ppa,
                                                                              'suite' : suite })

        # If setting up the final mirror, allow apt-get update to fail
        # (since we might be on a complete different network than the
        # final vm is going to be on).
        self.run_in_target('apt-get', 'update', ignore_fail=final)

    def install_apt_proxy(self):
        proxy = self.context.get_setting('proxy')
        if proxy is not None:
            self.context.install_file('/etc/apt/apt.conf', '// Proxy added by vmbuilder\nAcquire::http { Proxy "%s"; };' % proxy)

    def install_fstab(self, disks, filesystems):
        self.install_from_template('/etc/fstab', 'dapper_fstab', { 'parts' : disk.get_ordered_partitions(disks), 'prefix' : self.disk_prefix })

    def install_device_map(self):
        self.install_from_template('/boot/grub/device.map', 'devicemap', { 'prefix' : self.disk_prefix })

    def debootstrap(self):
        arch = self.context.get_setting('arch')
        cmd = ['/usr/sbin/debootstrap', '--arch=%s' % arch]

        variant = self.context.get_setting('variant')
        if variant:
            cmd += ['--variant=%s' % variant]

        suite = self.context.get_setting('suite')
        cmd += [suite, self.context.chroot_dir, self.debootstrap_mirror()]
        kwargs = { 'env' : { 'DEBIAN_FRONTEND' : 'noninteractive' } }

        proxy = self.context.get_setting('proxy')
        if proxy:
            kwargs['env']['http_proxy'] = proxy
        run_cmd(*cmd, **kwargs)
    
    def debootstrap_mirror(self):
        iso = self.context.get_setting('iso')
        if iso:
            isodir = tempfile.mkdtemp()
            self.context.add_clean_cb(lambda:os.rmdir(isodir))
            run_cmd('mount', '-o', 'loop', '-t', 'iso9660', iso, isodir)
            self.context.add_clean_cmd('umount', isodir)
            self.iso_mounted = True

            return 'file://%s' % isodir
        else:
            return self.install_mirrors()[0]


    def install_mirrors(self):
        install_mirror = self.context.get_setting('install-mirror')
        if install_mirror:
            mirror = install_mirror
        else:
            mirror = self.context.get_setting('mirror')

        updates_mirror = mirror

        install_security_mirror = self.context.get_setting('install-security-mirror')
        if install_security_mirror:
            security_mirror = install_security_mirror
        else:
            security_mirror = self.context.get_setting('security-mirror')

        return (mirror, updates_mirror, security_mirror)

    def install_kernel(self, destdir):
        run_cmd('chroot', destdir, 'apt-get', '--force-yes', '-y', 'install', self.kernel_name(), env={ 'DEBIAN_FRONTEND' : 'noninteractive' })

    def install_grub(self, chroot_dir):
        self.install_from_template('/etc/kernel-img.conf', 'kernelimg', { 'updategrub' : self.updategrub })
        arch = self.context.get_setting('arch')
        self.run_in_target('apt-get', '--force-yes', '-y', 'install', 'grub', env={ 'DEBIAN_FRONTEND' : 'noninteractive' })
        run_cmd('rsync', '-a', '%s%s/%s/' % (chroot_dir, self.grubroot, arch == 'amd64' and 'x86_64-pc' or 'i386-pc'), '%s/boot/grub/' % chroot_dir) 

    def create_devices(self):
        pass
# FIXME
#        import VMBuilder.plugins.xen

#        if isinstance(self.context.hypervisor, VMBuilder.plugins.xen.Xen):
#            self.run_in_target('mknod', '/dev/xvda', 'b', '202', '0')
#            self.run_in_target('mknod', '/dev/xvda1', 'b', '202', '1')
#            self.run_in_target('mknod', '/dev/xvda2', 'b', '202', '2')
#            self.run_in_target('mknod', '/dev/xvda3', 'b', '202', '3')
#            self.run_in_target('mknod', '/dev/xvc0', 'c', '204', '191')

    def install_from_template(self, *args, **kwargs):
        return self.context.install_from_template(*args, **kwargs)

    def run_in_target(self, *args, **kwargs):
        return self.context.run_in_target(*args, **kwargs)

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

    def set_locale(self):
        lang = self.context.get_setting('lang')
        if lang:
            self.install_from_template('/etc/default/locale', 'locale', { 'lang' : lang })
            if lang != "C":
                self.run_in_target('locale-gen', lang)
            self.run_in_target('dpkg-reconfigure', '-fnoninteractive', '-pcritical', 'libc6')
            self.run_in_target('dpkg-reconfigure', '-fnoninteractive', '-pcritical', 'locales')

    def install_vmbuilder_log(self, logfile, rootdir):
        shutil.copy(logfile, '%s/var/log/vmbuilder-install.log' % (rootdir,))

    def set_timezone(self):
        timezone = self.context.get_setting('timezone')
        if timezone:
            self.install_from_template('/etc/timezone', 'timezone', { 'timezone' : timezone })
        self.run_in_target('dpkg-reconfigure', '-fnoninteractive', '-pcritical', 'locales')

    def install_ec2(self):
        if self.context.ec2:
            logging.debug('This suite does not support ec2')

    def disable_hwclock_access(self):
        fp = open('%s/etc/default/rcS' % self.destdir, 'a')
        fp.write('HWCLOCKACCESS=no')
        fp.close()

    def has_256_bit_inode_ext3_support(self):
        return False

