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
#    Virtual disk management

import fcntl
import logging
import os
import os.path
import re
import stat
import string
import time
from   VMBuilder.util      import run_cmd 
from   VMBuilder.exception import VMBuilderUserError, VMBuilderException
from   struct              import unpack

TYPE_EXT2 = 0
TYPE_EXT3 = 1
TYPE_XFS = 2
TYPE_SWAP = 3
TYPE_EXT4 = 4

class Disk(object):
    """
    Virtual disk.

    @type  vm: Hypervisor
    @param vm: The Hypervisor to which the disk belongs
    @type  filename: string
    @param filename: filename of the disk image
    @type  size: string or number
    @param size: The size of the disk image to create (passed to
        L{parse_size}). If specified and filename already exists,
        L{VMBuilderUserError} will be raised. Otherwise, a disk image of
        this size will be created once L{create}() is called.
    """
    
    def __init__(self, vm, filename, size=None):
        self.vm = vm
        "The hypervisor to which the disk belongs."

        self.filename = filename
        "The filename of the disk image."

        self.partitions = []
        "The list of partitions on the disk. Is kept in order by L{add_part}."

        self.preallocated = False
        "Whether the file existed already (True if it did, False if we had to create it)."

        self.size = 0
        "The size of the disk. For preallocated disks, this is detected."

        if not os.path.exists(self.filename):
            if not size:
                raise VMBuilderUserError('%s does not exist, but no size was given.' % (self.filename))
            self.size = parse_size(size)
        else:
            if size:
                raise VMBuilderUserError('%s exists, but size was given.' % (self.filename))
            self.preallocated = True
            self.size = detect_size(self.filename)

        self.format_type = None
        "The format type of the disks. Only used for converted disks."

    def devletters(self):
        """
        @rtype: string
        @return: the series of letters that ought to correspond to the device inside
                 the VM. E.g. the first disk of a VM would return 'a', while the 702nd would return 'zz'
        """

        return index_to_devname(self.vm.disks.index(self))

    def create(self):
        """
        Creates the disk image (if it doesn't already exist).

        Once this method returns succesfully, L{filename} can be
        expected to points to point to whatever holds the virtual disk
        (be it a file, partition, logical volume, etc.).
        """
        if not os.path.exists(self.filename):
            logging.info('Creating disk image: "%s" of size: %dMB' % (self.filename, self.size))
            run_cmd(qemu_img_path(), 'create', '-f', 'raw', self.filename, '%dM' % self.size)

    def partition(self):
        """
        Partitions the disk image. First adds a partition table and then
        adds the individual partitions.

        Should only be called once and only after you've added all partitions.
        """

        logging.info('Adding partition table to disk image: %s' % self.filename)
        run_cmd('parted', '--script', self.filename, 'mklabel', 'msdos')

        # Partition the disk 
        for part in self.partitions:
            part.create(self)

    def map_partitions(self):
        """
        Create loop devices corresponding to the partitions.

        Once this has returned succesfully, each partition's map device
        is set as its L{filename<Disk.Partition.filename>} attribute.

        Call this after L{partition}.
        """
        logging.info('Creating loop devices corresponding to the created partitions')
        self.vm.add_clean_cb(lambda : self.unmap(ignore_fail=True))
        kpartx_output = run_cmd('kpartx', '-av', self.filename)
        parts = []
        for line in kpartx_output.split('\n'):
            if line == "" or line.startswith("gpt:") or line.startswith("dos:"):
                continue
            if line.startswith("add"):
                parts.append(line)
                continue
            logging.error('Skipping unknown line in kpartx output (%s)' % line)
        mapdevs = []
        for line in parts:
            mapdevs.append(line.split(' ')[2])
        for (part, mapdev) in zip(self.partitions, mapdevs):
            part.set_filename('/dev/mapper/%s' % mapdev)

    def mkfs(self):
        """
        Creates the partitions' filesystems
        """
        logging.info("Creating file systems")
        for part in self.partitions:
            part.mkfs()

    def get_grub_id(self):
        """
        @rtype:  string
        @return: name of the disk as known by grub
        """
        return '(hd%d)' % self.get_index()

    def get_index(self):
        """
        @rtype:  number
        @return: index of the disk (starting from 0 for the hypervisor's first disk)
        """
        return self.vm.disks.index(self)

    def unmap(self, ignore_fail=False):
        """
        Destroy all mapping devices

        Unsets L{Partition}s' and L{Filesystem}s' filename attribute
        """
        # first sleep to give the loopback devices a chance to settle down
        time.sleep(3)

        tries = 0
        max_tries = 3
        while tries < max_tries:
            try:
                run_cmd('kpartx', '-d', self.filename, ignore_fail=False)
                break
            except:
                pass
            tries += 1
            time.sleep(3)

            if tries >= max_tries:
                # try it one last time
                logging.info("Could not unmap '%s' after '%d' attempts. Final attempt" % (self.filename, tries))
        run_cmd('kpartx', '-d', self.filename, ignore_fail=ignore_fail)

        for part in self.partitions:
            part.set_filename(None)

    def add_part(self, begin, length, type, mntpnt):
        """
        Add a partition to the disk

        @type  begin: number
        @param begin: Start offset of the new partition (in megabytes)
        @type  length: 
        @param length: Size of the new partition (in megabytes)
        @type  type: string
        @param type: Type of the new partition. Valid options are: ext2 ext3 xfs swap linux-swap
        @type  mntpnt: string
        @param mntpnt: Intended mountpoint inside the guest of the new partition
        """
        length = parse_size(length)
        end = begin+length-1
        logging.debug("add_part - begin %d, length %d, end %d, type %s, mntpnt %s" % (begin, length, end, type, mntpnt))
        for part in self.partitions:
            if (begin >= part.begin and begin <= part.end) or \
                (end >= part.begin and end <= part.end):
                raise VMBuilderUserError('Partitions are overlapping')
        if begin < 0 or end > self.size:
            raise VMBuilderUserError('Partition is out of bounds. start=%d, end=%d, disksize=%d' % (begin,end,self.size))
        part = self.Partition(disk=self, begin=begin, end=end, type=str_to_type(type), mntpnt=mntpnt)
        self.partitions.append(part)

        # We always keep the partitions in order, so that the output from kpartx matches our understanding
        self.partitions.sort(cmp=lambda x,y: x.begin - y.begin)

    def convert(self, destdir, format):
        """
        Convert the disk image

        @type  destdir: string
        @param destdir: Target location of converted disk image
        @type  format: string
        @param format: The target format (as understood by qemu-img or vdi)
        @rtype:  string
        @return: the name of the converted image
        """
        if self.preallocated:
            # We don't convert preallocated disk images. That would be silly.
            return self.filename

        filename = os.path.basename(self.filename)
        if '.' in filename:
            filename = filename[:filename.rindex('.')]
        destfile = '%s/%s.%s' % (destdir, filename, format)

        logging.info('Converting %s to %s, format %s' % (self.filename, format, destfile))
        if format == 'vdi':
            run_cmd(vbox_manager_path(), 'convertfromraw', '-format', 'VDI', self.filename, destfile)
        else:
            run_cmd(qemu_img_path(), 'convert', '-O', format, self.filename, destfile)
        os.unlink(self.filename)
        self.filename = os.path.abspath(destfile)
        self.format_type = format
        return destfile

    class Partition(object):
        def __init__(self, disk, begin, end, type, mntpnt):
            self.disk = disk
            "The disk on which this Partition resides."

            self.begin = begin
            "The start of the partition"

            self.end = end
            "The end of the partition"

            self.type = type
            "The partition type"

            self.mntpnt = mntpnt
            "The destined mount point"

            self.filename = None
            "The filename of this partition (the map device)"

            self.fs = Filesystem(vm=self.disk.vm, type=self.type, mntpnt=self.mntpnt)
            "The enclosed filesystem"

        def set_filename(self, filename):
            self.filename = filename
            self.fs.filename = filename

        def parted_fstype(self):
            """
            @rtype: string
            @return: the filesystem type of the partition suitable for passing to parted
            """
            return { TYPE_EXT2: 'ext2', TYPE_EXT3: 'ext2', TYPE_EXT4: 'ext2', TYPE_XFS: 'ext2', TYPE_SWAP: 'linux-swap(new)' }[self.type]

        def create(self, disk):
            """Adds partition to the disk image (does not mkfs or anything like that)"""
            logging.info('Adding type %d partition to disk image: %s' % (self.type, disk.filename))
	    if self.begin == 0:
		logging.info('Partition at beginning of disk - reserving first cylinder')
		partition_start = "63s"
	    else:
	    	partition_start = self.begin
            run_cmd('parted', '--script', '--', disk.filename, 'mkpart', 'primary', self.parted_fstype(), partition_start, self.end)

        def mkfs(self):
            """Adds Filesystem object"""
            self.fs.mkfs()

        def get_grub_id(self):
            """The name of the partition as known by grub"""
            return '(hd%d,%d)' % (self.disk.get_index(), self.get_index())

        def get_suffix(self):
            """Returns 'a4' for a device that would be called /dev/sda4 in the guest. 
               This allows other parts of VMBuilder to set the prefix to something suitable."""
            return '%s%d' % (self.disk.devletters(), self.get_index() + 1)

        def get_index(self):
            """Index of the disk (starting from 0)"""
            return self.disk.partitions.index(self)

        def set_type(self, type):
            try:
                if int(type) == type:
                    self.type = type
                else:
                    self.type = str_to_type(type)
            except ValueError:
                self.type = str_to_type(type)

class Filesystem(object):
    def __init__(self, vm=None, size=0, type=None, mntpnt=None, filename=None, devletter='a', device='', dummy=False):
        self.vm = vm
        self.filename = filename
        self.size = parse_size(size)
        self.devletter = devletter
        self.device = device
        self.dummy = dummy

        self.set_type(type)

        self.mntpnt = mntpnt

        self.preallocated = False
        "Whether the file existed already (True if it did, False if we had to create it)."

    def create(self):
        logging.info('Creating filesystem: %s, size: %d, dummy: %s' % (self.mntpnt, self.size, repr(self.dummy)))
        if not os.path.exists(self.filename):
            logging.info('Not preallocated, so we create it.')
            if not self.filename:
                if self.mntpnt:
                    self.filename = re.sub('[^\w\s/]', '', self.mntpnt).strip().lower()
                    self.filename = re.sub('[\w/]', '_', self.filename)
                    if self.filename == '_':
                        self.filename = 'root'
                elif self.type == TYPE_SWAP:
                    self.filename = 'swap'
                else:
                    raise VMBuilderException('mntpnt not set')

                self.filename = '%s/%s' % (self.vm.workdir, self.filename)
                while os.path.exists('%s.img' % self.filename):
                    self.filename += '_'
                self.filename += '.img'
                logging.info('A name wasn\'t specified either, so we make one up: %s' % self.filename)
            run_cmd(qemu_img_path(), 'create', '-f', 'raw', self.filename, '%dM' % self.size)
        self.mkfs()

    def mkfs(self):
        if not self.filename:
            raise VMBuilderException('We can\'t mkfs if filename is not set. Did you forget to call .create()?')
        if not self.dummy:
            cmd = self.mkfs_fstype() + [self.filename]
            run_cmd(*cmd)
            # Let udev have a chance to extract the UUID for us
            run_cmd('udevadm', 'settle')
            if os.path.exists("/sbin/vol_id"):
                self.uuid = run_cmd('vol_id', '--uuid', self.filename).rstrip()
            elif os.path.exists("/sbin/blkid"):
                self.uuid = run_cmd('blkid', '-c', '/dev/null', '-sUUID', '-ovalue', self.filename).rstrip()

    def mkfs_fstype(self):
        map = { TYPE_EXT2: ['mkfs.ext2', '-F'], TYPE_EXT3: ['mkfs.ext3', '-F'], TYPE_EXT4: ['mkfs.ext4', '-F'], TYPE_XFS: ['mkfs.xfs'], TYPE_SWAP: ['mkswap'] }

        if not self.vm.distro.has_256_bit_inode_ext3_support():
            map[TYPE_EXT3] = ['mkfs.ext3', '-I 128', '-F']

        return map[self.type]

    def fstab_fstype(self):
        return { TYPE_EXT2: 'ext2', TYPE_EXT3: 'ext3', TYPE_EXT4: 'ext4', TYPE_XFS: 'xfs', TYPE_SWAP: 'swap' }[self.type]

    def fstab_options(self):
        return 'defaults'

    def mount(self, rootmnt):
        if (self.type != TYPE_SWAP) and not self.dummy:
            logging.debug('Mounting %s', self.mntpnt) 
            self.mntpath = '%s%s' % (rootmnt, self.mntpnt)
            if not os.path.exists(self.mntpath):
                os.makedirs(self.mntpath)
            run_cmd('mount', '-o', 'loop', self.filename, self.mntpath)
            self.vm.add_clean_cb(self.umount)

    def umount(self):
        self.vm.cancel_cleanup(self.umount)
        if (self.type != TYPE_SWAP) and not self.dummy:
            logging.debug('Unmounting %s', self.mntpath) 
            run_cmd('umount', self.mntpath)

    def get_suffix(self):
        """Returns 'a4' for a device that would be called /dev/sda4 in the guest..
           This allows other parts of VMBuilder to set the prefix to something suitable."""
        if self.device:
            return self.device
        else:
            return '%s%d' % (self.devletters(), self.get_index() + 1)

    def devletters(self):
        """
        @rtype: string
        @return: the series of letters that ought to correspond to the device inside
                 the VM. E.g. the first filesystem of a VM would return 'a', while the 702nd would return 'zz'
        """
        return self.devletter
        
    def get_index(self):
        """Index of the disk (starting from 0)"""
        return self.vm.filesystems.index(self)

    def set_type(self, type):
        try:
            if int(type) == type:
                self.type = type
            else:
                self.type = str_to_type(type)
        except ValueError:
            self.type = str_to_type(type)

def parse_size(size_str):
    """Takes a size like qemu-img would accept it and returns the size in MB"""
    try:
        return int(size_str)
    except ValueError:
        pass

    try:
        num = int(size_str[:-1])
    except ValueError:
        raise VMBuilderUserError("Invalid size: %s" % size_str)

    if size_str[-1:] == 'g' or size_str[-1:] == 'G':
        return num * 1024
    if size_str[-1:] == 'm' or size_str[-1:] == 'M':
        return num
    if size_str[-1:] == 'k' or size_str[-1:] == 'K':
        return num / 1024

str_to_type_map = { 'ext2': TYPE_EXT2,
                 'ext3': TYPE_EXT3,
                 'ext4': TYPE_EXT4,
                 'xfs': TYPE_XFS,
                 'swap': TYPE_SWAP,
                 'linux-swap': TYPE_SWAP }

def str_to_type(type):
    try:
        return str_to_type_map[type]
    except KeyError:
        raise Exception('Unknown partition type: %s' % type)
        
def rootpart(disks):
    """Returns the partition which contains the root dir"""
    return path_to_partition(disks, '/')

def bootpart(disks):
    """Returns the partition which contains /boot"""
    return path_to_partition(disks, '/boot/foo')

def path_to_partition(disks, path):
    parts = get_ordered_partitions(disks)
    parts.reverse()
    for part in parts:
        if path.startswith(part.mntpnt):
            return part
    raise VMBuilderException("Couldn't find partition path %s belongs to" % path)

def create_filesystems(vm):
    for filesystem in vm.filesystems:
        filesystem.create()

def create_partitions(vm):
    for disk in vm.disks:
        disk.create(vm.workdir)

def get_ordered_filesystems(vm):
    """Returns filesystems (self hosted as well as contained in partitions
    in an order suitable for mounting them"""
    fss = list(vm.filesystems)
    for disk in vm.disks:
        fss += [part.fs for part in disk.partitions]
    fss.sort(lambda x,y: len(x.mntpnt or '')-len(y.mntpnt or ''))
    return fss

def get_ordered_partitions(disks):
    """Returns partitions from disks in an order suitable for mounting them"""
    parts = []
    for disk in disks:
        parts += disk.partitions
    parts.sort(lambda x,y: len(x.mntpnt or '')-len(y.mntpnt or ''))
    return parts

def devname_to_index(devname):
    return devname_to_index_rec(devname) - 1

def devname_to_index_rec(devname):
    if not devname:
        return 0
    return 26 * devname_to_index_rec(devname[:-1]) + (string.ascii_lowercase.index(devname[-1]) + 1) 

def index_to_devname(index, suffix=''):
    if index < 0:
        return suffix
    return index_to_devname(index / 26 -1, string.ascii_lowercase[index % 26]) + suffix

def detect_size(filename):
    st = os.stat(filename)
    if stat.S_ISREG(st.st_mode):
        return st.st_size / 1024*1024
    elif stat.S_ISBLK(st.st_mode): 
        # I really wish someone would make these available in Python
        BLKGETSIZE64 = 2148012658
        fp = open(filename, 'r')
        fd = fp.fileno()
        s = fcntl.ioctl(fd, BLKGETSIZE64, ' '*8)
        return unpack('L', s)[0] / 1024*1024

    raise VMBuilderException('No idea how to find the size of %s' % filename)

def qemu_img_path():
    exes = ['kvm-img', 'qemu-img']
    for dir in os.environ['PATH'].split(os.path.pathsep):
        for exe in exes:
            path = '%s%s%s' % (dir, os.path.sep, exe)
            if os.access(path, os.X_OK):
                return path

def vbox_manager_path():
    exe = 'VBoxManage'
    for dir in os.environ['PATH'].split(os.path.pathsep):
        path = '%s%s%s' % (dir, os.path.sep, exe)
        if os.access(path, os.X_OK):
            return path
