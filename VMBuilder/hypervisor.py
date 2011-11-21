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
#    Hypervisor super class

import logging
import os
import VMBuilder.distro
import VMBuilder.disk
from   VMBuilder.util    import run_cmd, tmpdir

STORAGE_DISK_IMAGE = 0
STORAGE_FS_IMAGE = 1

class Hypervisor(VMBuilder.distro.Context):
    preferred_storage = STORAGE_DISK_IMAGE

    def __init__(self, distro):
        self.plugin_classes = VMBuilder._hypervisor_plugins
        super(Hypervisor, self).__init__()
        self.plugins += [distro]
        self.distro = distro
        self.filesystems = []
        self.disks = []
        self.nics = []

    def add_filesystem(self, *args, **kwargs):
        """Adds a filesystem to the virtual machine"""
        from VMBuilder.disk import Filesystem

        fs = Filesystem(self, *args, **kwargs)
        self.filesystems.append(fs)
        return fs

    def add_disk(self, *args, **kwargs):
        """Adds a disk image to the virtual machine"""
        from VMBuilder.disk import Disk

        disk = Disk(self, *args, **kwargs)
        self.disks.append(disk)
        return disk

    def install_os(self):
        self.nics = [self.NIC()]
        self.call_hooks('preflight_check')
        self.call_hooks('configure_networking', self.nics)
        self.call_hooks('configure_mounting', self.disks, self.filesystems)

        self.chroot_dir = tmpdir()
        self.call_hooks('mount_partitions', self.chroot_dir)
        run_cmd('rsync', '-aHA', '%s/' % self.distro.chroot_dir, self.chroot_dir)
        self.distro.set_chroot_dir(self.chroot_dir)
        if self.needs_bootloader:
            self.call_hooks('install_bootloader', self.chroot_dir, self.disks)
        self.call_hooks('install_kernel', self.chroot_dir)
        self.distro.call_hooks('post_install')
        self.call_hooks('unmount_partitions')
        os.rmdir(self.chroot_dir)

    def finalise(self, destdir):
        self.call_hooks('convert', 
                        self.preferred_storage == STORAGE_DISK_IMAGE and self.disks or self.filesystems,
                        destdir)
        self.call_hooks('deploy', destdir)

    def mount_partitions(self, mntdir):
        """Mounts all the vm's partitions and filesystems below .rootmnt"""
        logging.info('Mounting target filesystems')
        for fs in self.filesystems:
            fs.create()
            fs.mkfs()
        for disk in self.disks:
            disk.create()
            disk.partition()
            disk.map_partitions()
            disk.mkfs()
        fss = VMBuilder.disk.get_ordered_filesystems(self)
        for fs in fss:
            fs.mount(mntdir)
            self.distro.post_mount(fs)

    def unmount_partitions(self):
        """Unmounts all the vm's partitions and filesystems"""
        logging.info('Unmounting target filesystem')
        fss = VMBuilder.disk.get_ordered_filesystems(self)
        fss.reverse()
        for fs in fss:
            fs.umount()
        for disk in self.disks:
            disk.unmap()

    def convert_disks(self, disks, destdir):
        for disk in disks:
            disk.convert(destdir, self.filetype)

    class NIC(object):
        def __init__(self, type='dhcp', ip=None, network=None, netmask=None,
                           broadcast=None, dns=None, gateway=None):
            self.type = type
            self.ip = ip
            self.network = network
            self.netmask = netmask
            self.broadcast = broadcast
            self.dns = dns
            self.gateway = gateway

