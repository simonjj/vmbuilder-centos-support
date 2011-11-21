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
from   VMBuilder import register_hypervisor_plugin, Plugin, VMBuilderUserError
import VMBuilder.util

class Libvirt(Plugin):
    name = 'libvirt integration'

    def register_options(self):
        group = self.setting_group('libvirt integration')
        group.add_setting('libvirt', metavar='URI', help='Add VM to given URI')
        group.add_setting('bridge', metavar="BRIDGE", help='Set up bridged network connected to BRIDGE.')
        group.add_setting('network', metavar='NETWORK', default='default', help='Set up a network connection to virtual network NETWORK.')

    def all_domains(self):
        # This does not seem to work when any domain is already running
        return self.conn.listDefinedDomains() + [self.conn.lookupByID(id).name() for id in self.conn.listDomainsID()]

    def preflight_check(self):
        libvirt_uri = self.get_setting('libvirt')
        if not libvirt_uri:
            return True

        if not self.context.name == 'KVM' and not self.context.name == 'QEMu':
            raise VMBuilderUserError('The libvirt plugin is only equiped to work with KVM and QEMu at the moment.')

        import libvirt
        import xml.etree.ElementTree

        self.conn = libvirt.open(libvirt_uri)

        e = xml.etree.ElementTree.fromstring(self.conn.getCapabilities())

        if not 'hvm' in [x.text for x in e.getiterator('os_type')]:
            raise VMBuilderUserError('libvirt does not seem to want to accept hvm domains')

        hostname = self.context.distro.get_setting('hostname')
        if hostname in self.all_domains() and not self.context.overwrite:
            raise VMBuilderUserError('Domain %s already exists at %s' % (hostname, libvirt_uri))

    def deploy(self, destdir):
        libvirt_uri = self.get_setting('libvirt')
        if not libvirt_uri:
            # Not for us
            return False

        hostname = self.context.distro.get_setting('hostname')
        tmpl_ctxt = { 'mem': self.context.get_setting('mem'),
                      'cpus': self.context.get_setting('cpus'),
                      'bridge' : self.context.get_setting('bridge'),
                      'mac' : self.context.get_setting('mac'),
                      'network' : self.context.get_setting('network'),
                      'mac' : self.context.get_setting('mac'),
                      'virtio_net' : self.context.distro.use_virtio_net(),
                      'disks' : self.context.disks,
                      'filesystems' : self.context.filesystems,
                      'hostname' : hostname,
                      'domain_type' : self.context.libvirt_domain_type_name() }
        if self.context.preferred_storage == VMBuilder.hypervisor.STORAGE_FS_IMAGE:
            vmxml = VMBuilder.util.render_template('libvirt', self.context, 'libvirtxml_fsimage', tmpl_ctxt)
        else:
            vmxml = VMBuilder.util.render_template('libvirt', self.context, 'libvirtxml', tmpl_ctxt)

        if hostname in self.all_domains() and not self.context.overwrite:
            raise VMBuilderUserError('Domain %s already exists at %s' % (hostname, libvirt_uri))
        else:
            self.conn.defineXML(vmxml)

        return True

register_hypervisor_plugin(Libvirt)
