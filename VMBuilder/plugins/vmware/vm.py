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
from   VMBuilder import register_hypervisor, Hypervisor
import VMBuilder
import VMBuilder.hypervisor
import os
import os.path
import stat
from shutil import move
from math import floor

class VMWare(Hypervisor):
    filetype = 'vmdk'
    preferred_storage = VMBuilder.hypervisor.STORAGE_DISK_IMAGE
    needs_bootloader = True
    vmxtemplate = 'vmware'

    def register_options(self):
        group = self.setting_group('VM settings')
        group.add_setting('mem', extra_args=['-m'], default='128', help='Assign MEM megabytes of memory to the guest vm. [default: %default]')
        group.add_setting('cpus', type='int', default=1, help='Assign NUM cpus to the guest vm. [default: %default]')

    def convert(self, disks, destdir):
        self.imgs = []
        for disk in self.get_disks():
            img_path = disk.convert(destdir, self.filetype)
            self.imgs.append(img_path)
            self.call_hooks('fix_ownership', img_path)

    def get_disks(self):
        return self.disks

    def deploy(self, destdir):
        mem = self.context.get_setting('mem')
        cpus = self.context.get_setting('cpus')
        hostname = self.context.distro.get_setting('hostname')
        arch = self.context.distro.get_setting('arch')
        mac = self.context.get_setting('mac')
        vmdesc = VMBuilder.util.render_template('vmware',
                                                self.context,
                                                self.vmxtemplate,
                                                { 'disks' : self.get_disks(),
                                                  'vmhwversion' : self.vmhwversion,
                                                  'mem' : mem,
                                                  'numvcpus' : cpus,
                                                  'hostname' : hostname,
                                                  'arch' : arch,
                                                  'mac' : mac,
                                                  'guestos' : (arch == 'amd64' and 'ubuntu-64' or 'ubuntu') })

        vmx = '%s/%s.vmx' % (destdir, hostname)
        fp = open(vmx, 'w')
        fp.write(vmdesc)
        fp.close()
        os.chmod(vmx, stat.S_IRWXU | stat.S_IRWXU | stat.S_IROTH | stat.S_IXOTH)
        self.call_hooks('fix_ownership', vmx)

class VMWareWorkstation6(VMWare):
    name = 'VMWare Workstation 6'
    arg = 'vmw6'
    vmhwversion = 6

class VMWareServer(VMWare):
    name = 'VMWare Server'
    arg = 'vmserver'
    vmhwversion = 4

class VMWareEsxi(VMWare):
    name = 'VMWare ESXi'
    arg = 'esxi'
    vmhwversion = 4
    adaptertype = 'lsilogic' # lsilogic | buslogic, ide is not supported by ESXi
    vmxtemplate = 'esxi.vmx'

    vmdks = [] # vmdk filenames used when deploying vmx file

    def convert(self, disks, destdir):
        self.imgs = []
        for disk in disks:

            # Move raw image to <imagename>-flat.vmdk
            diskfilename = os.path.basename(disk.filename)
            if '.' in diskfilename:
                diskfilename = diskfilename[:diskfilename.rindex('.')]

            flat = '%s/%s-flat.vmdk' % (destdir, diskfilename)
            self.vmdks.append(diskfilename)

            move(disk.filename, flat)

            self.call_hooks('fix_ownership', flat)

            # Create disk descriptor file
            sectorTotal = disk.size * 2048
            sector = int(floor(sectorTotal / 16065)) # pseudo geometry

            diskdescriptor = VMBuilder.util.render_template('vmware', self.context, 'flat.vmdk',  { 'adaptertype' : self.adaptertype, 'sectors' : sector, 'diskname' : os.path.basename(flat), 'disksize' : sectorTotal })
            vmdk = '%s/%s.vmdk' % (destdir, diskfilename)

            fp = open(vmdk, 'w')
            fp.write(diskdescriptor)
            fp.close()
            os.chmod(vmdk, stat.S_IRWXU | stat.S_IRWXU | stat.S_IROTH | stat.S_IXOTH)

            self.call_hooks('fix_ownership', vmdk)

    def get_disks(self):
        return self.vmdks

register_hypervisor(VMWareServer)
register_hypervisor(VMWareWorkstation6)
register_hypervisor(VMWareEsxi)
