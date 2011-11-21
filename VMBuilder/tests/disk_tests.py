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
import os
import stat
import tempfile
import unittest
import testtools

import VMBuilder
from VMBuilder.disk import detect_size, parse_size, index_to_devname, devname_to_index, Disk
from VMBuilder.exception import VMBuilderException, VMBuilderUserError
from VMBuilder.util import run_cmd

TestSkipped = testtools.testcase.TestSkipped
TestCase = testtools.TestCase

def get_temp_filename():
    (fd, tmpfile) = tempfile.mkstemp()
    os.close(fd)
    return tmpfile

class MockDistro(object):
    def has_256_bit_inode_ext3_support(self):
        return True

class MockHypervisor(object):
    def __init__(self):
        self.disks = []
        self.distro = MockDistro()

    def add_clean_cb(self, *args, **kwargs):
        pass

    def add_disk(self, *args, **kwargs):
        disk = Disk(self, *args, **kwargs)
        self.disks.append(disk)
        return disk

class TestSizeParser(TestCase):
    def test_suffixesAreCaseInsensitive(self):
        "Suffixes in size strings are case-insensitive"

        for letter in ['K', 'M', 'G']:
            self.assertEqual(parse_size('1%s' % letter), parse_size('1%s' % letter.lower()))

    def test_suffixless_counts_as_megabytes(self):
        "Suffix-less size string are counted as megabytes"
        self.assertEqual(parse_size(10), 10)
        self.assertEqual(parse_size('10'), 10)

    def test_M_suffix_counts_as_megabytes(self):
        "Sizes with M suffix are counted as megabytes"
        self.assertEqual(parse_size('10M'), 10)

    def test_G_suffix_counts_as_gigabytes(self):
        "1G is counted as 1024 megabytes"
        self.assertEqual(parse_size('1G'), 1024)

    def test_K_suffix_counts_as_kilobytes(self):
        "1024K is counted as 1 megabyte"
        self.assertEqual(parse_size('1024K'), 1)

    def test_rounds_size_to_nearest_megabyte(self):
        "parse_size rounds to nearest MB"
        self.assertEqual(parse_size('1025K'), 1)
        self.assertEqual(parse_size('10250K'), 10)

class TestSequenceFunctions(TestCase):
    def test_index_to_devname(self):
        self.assertEqual(index_to_devname(0), 'a')
        self.assertEqual(index_to_devname(26), 'aa')
        self.assertEqual(index_to_devname(18277), 'zzz')

    def test_devname_to_index(self):
        self.assertEqual(devname_to_index('a'), 0)
        self.assertEqual(devname_to_index('b'), 1)
        self.assertEqual(devname_to_index('aa'), 26)
        self.assertEqual(devname_to_index('ab'), 27)
        self.assertEqual(devname_to_index('z'), 25)
        self.assertEqual(devname_to_index('zz'), 701)
        self.assertEqual(devname_to_index('zzz'), 18277)

    def test_index_to_devname_and_back(self):
        for i in range(18277):
            self.assertEqual(i, devname_to_index(index_to_devname(i)))

class TestDetectSize(TestCase):
    def setUp(self):
        TestCase.setUp(self)
        self.tmpfile = get_temp_filename()
        run_cmd('qemu-img', 'create', self.tmpfile, '5G')
        self.imgdev = None

    def test_detect_size_file(self):
        self.assertTrue(detect_size(self.tmpfile), 5*1024)

    @testtools.skipIf(os.geteuid() != 0, 'Needs root to run')
    def test_detect_size_loopback_dev(self):
        self.imgdev = run_cmd('losetup', '-f', '--show', self.tmpfile).strip()
        self.assertTrue(detect_size(self.imgdev), 5*1024)

    def test_detect_size_fifo(self):
        os.unlink(self.tmpfile)
        os.mkfifo(self.tmpfile)
        self.assertRaises(VMBuilderException, detect_size, self.tmpfile)

    def tearDown(self):
        TestCase.tearDown(self)
        run_cmd('udevadm', 'settle')
        if self.imgdev:
            run_cmd('losetup', '-d', self.imgdev)
        os.unlink(self.tmpfile)

class TestDiskPlugin(TestCase):
    def test_disk_filename(self):
        tmpfile = get_temp_filename()
        os.unlink(tmpfile)

        disk = Disk(MockHypervisor(), tmpfile, size='1G')
        disk.create()
        self.assertTrue(os.path.exists(tmpfile))
        os.unlink(tmpfile)

    def test_disk_size(self):
        # parse_size only deals with MB resolution
        K = 1024
        M = K*1024
        G = M*1024
        sizes = [('10G', 10*G),
                 ('400M', 400*M),
                 ('345', 345*M),
                 ('10240k', 10*M),
                 ('10250k', 10*M),
                 ('10230k', 9*M)]

        for (sizestr, size) in sizes:
            tmpfile = get_temp_filename()
            os.unlink(tmpfile)

            disk = Disk(MockHypervisor(), filename=tmpfile, size=sizestr)
            disk.create()
            actual_size = os.stat(tmpfile)[stat.ST_SIZE]
            self.assertEqual(size, actual_size, 'Asked for %s, expected %d, got %d' % (sizestr, size, actual_size))
            os.unlink(tmpfile)

    def test_disk_no_size_given(self):
        tmpname = get_temp_filename()
        os.unlink(tmpname)

        self.assertRaises(VMBuilderUserError, Disk, MockHypervisor(), filename=tmpname)

    def test_disk_size_given_file_exists(self):
        tmpname = get_temp_filename()

        self.assertRaises(VMBuilderUserError, Disk, MockHypervisor(), filename=tmpname, size='1G')

    def test_existing_image_no_overwrite(self):
        tmpfile = get_temp_filename()

        fp = open(tmpfile, 'w')
        fp.write('canary')
        fp.close()

        disk = Disk(MockHypervisor(), tmpfile)
        disk.create()
        fp = open(tmpfile, 'r')
        self.assertEqual(fp.read(), 'canary')
        fp.close()
        os.unlink(tmpfile)

    def test_devletters(self):
        from string import ascii_lowercase

        hypervisor = MockHypervisor()
        for (expected_devletter, index) in zip(ascii_lowercase, range(len(ascii_lowercase))):
            tmpname = get_temp_filename()
            disk = hypervisor.add_disk(filename=tmpname)
            devletters = disk.devletters()
            self.assertEqual(devletters, expected_devletter, 'Disk no. %d returned %s, expected %s.' % (index, devletters, expected_devletter))

class TestDiskPartitioningPlugin(TestCase):
    def setUp(self):
        TestCase.setUp(self)
        self.tmpfile = get_temp_filename()
        os.unlink(self.tmpfile)

        self.vm = MockHypervisor()
        self.disk = self.vm.add_disk(self.tmpfile, size='1G')
        self.disk.create()

    def tearDown(self):
        TestCase.tearDown(self)
        os.unlink(self.tmpfile)

    def test_partition_overlap(self):
        self.disk.add_part(1, 512, 'ext3', '/')
        self.assertRaises(VMBuilderUserError, self.disk.add_part, 512, 512, 'ext3', '/mnt')

    def test_partition_extends_beyond_disk(self):
        self.assertRaises(VMBuilderUserError, self.disk.add_part, 512, 514, 'ext3', '/')

    def test_partition_table_empty(self):
        from VMBuilder.util import run_cmd

        file_output = run_cmd('file', self.tmpfile)
        self.assertEqual('%s: data' % self.tmpfile, file_output.strip())
        self.disk.partition()
        file_output = run_cmd('file', self.tmpfile)
        self.assertEqual('%s: x86 boot sector, code offset 0xb8' % self.tmpfile, file_output.strip())

        file_output = run_cmd('parted', '--script', self.tmpfile, 'print')
        self.assertEqual('''Model:  (file)
Disk %s: 1074MB
Sector size (logical/physical): 512B/512B
Partition Table: msdos

Number  Start  End  Size  Type  File system  Flags''' % self.tmpfile, file_output.strip())

    def test_partition_table_nonempty(self):
        from VMBuilder.util import run_cmd

        self.disk.add_part(1, 1023, 'ext3', '/')
        self.disk.partition()
        file_output = run_cmd('parted', '--script', self.tmpfile, 'print')
        self.assertEqual('''Model:  (file)
Disk %s: 1074MB
Sector size (logical/physical): 512B/512B
Partition Table: msdos

Number  Start   End     Size    Type     File system  Flags
 1      1049kB  1023MB  1022MB  primary''' % self.tmpfile, file_output.strip())

    @testtools.skipIf(os.geteuid() != 0, 'Needs root to run')
    def test_map_partitions(self):
        self.disk.add_part(1, 1023, 'ext3', '/')
        self.disk.partition()
        self.disk.map_partitions()
        try:
            from VMBuilder.disk import detect_size
            self.assertEqual(detect_size(self.disk.partitions[0].filename), 1023000576)
        except:
            raise
        finally:
            self.disk.unmap()

    @testtools.skipIf(os.geteuid() != 0, 'Needs root to run')
    def test_mkfs(self):
        self.disk.add_part(1, 1023, 'ext3', '/')
        self.disk.partition()
        self.disk.map_partitions()
        try:
            self.disk.mkfs()
        except:
            raise
        finally:
            self.disk.unmap()

    def test_get_grub_id(self):
        self.assertEqual(self.disk.get_grub_id(), '(hd0)')

        tmpfile2 = get_temp_filename()
        os.unlink(tmpfile2)
        disk2 = self.vm.add_disk(tmpfile2, '1G')
        self.assertEqual(self.disk.get_grub_id(), '(hd0)')
        self.assertEqual(disk2.get_grub_id(), '(hd1)')

    def test_get_index(self):
        self.assertEqual(self.disk.get_index(), 0)

        tmpfile2 = get_temp_filename()
        os.unlink(tmpfile2)
        disk2 = self.vm.add_disk(tmpfile2, '1G')
        self.assertEqual(self.disk.get_index(), 0)
        self.assertEqual(disk2.get_index(), 1)
