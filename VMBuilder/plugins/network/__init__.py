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
#    Virtual network management

import logging
import re
import struct
import socket

from   VMBuilder           import register_hypervisor_plugin, register_distro_plugin
from   VMBuilder.plugins   import Plugin
from   VMBuilder.exception import VMBuilderUserError

def validate_mac(mac):
    valid_mac_address = re.compile("^([0-9a-f]{2}:){5}([0-9a-f]{2})$", re.IGNORECASE)
    if not valid_mac_address.match(mac):
        return False
    else:
        return True

def numeric_to_dotted_ip(numeric_ip):
    return socket.inet_ntoa(struct.pack('I', numeric_ip))

def dotted_to_numeric_ip(dotted_ip):
    try:
        return struct.unpack('I', socket.inet_aton(dotted_ip))[0] 
    except socket.error:
        raise VMBuilderUserError('%s is not a valid ip address' % dotted_ip)

def guess_mask_from_ip(numip):
    first_octet = numip & 0xFF

    if (first_octet > 0) and (first_octet <= 127):
        return 0xFF
    elif (first_octet > 128) and (first_octet < 192):
        return 0xFFFF
    elif (first_octet < 224):
        return 0xFFFFFF
    else:
        raise VMBuilderUserError('Could not guess network class of: %s' % numeric_to_dotted_ip(numip))

def calculate_net_address_from_ip_and_netmask(ip, netmask):
    return ip & netmask

def calculate_broadcast_address_from_ip_and_netmask(net, mask):
    return net + (mask ^ 0xFFFFFFFF)

def guess_gw_from_ip(ip):
    return ip + 0x01000000

class NetworkDistroPlugin(Plugin):
    def register_options(self):
        group = self.setting_group('Network')
        domainname = '.'.join(socket.gethostbyname_ex(socket.gethostname())[0].split('.')[1:]) or "defaultdomain"
        group.add_setting('domain', metavar='DOMAIN', default=domainname, help='Set DOMAIN as the domain name of the guest [default: %default].')

    def preflight_check(self):
        domain = self.context.get_setting('domain')
        if domain == '':
            raise VMBuilderUserError('Domain is undefined and host has no domain set.')

class NetworkHypervisorPlugin(Plugin):
    def register_options(self):
        group = self.setting_group('Network')
        group.add_setting('ip', metavar='ADDRESS', default='dhcp', help='IP address in dotted form [default: %default].')
        group.add_setting('mac', metavar='MAC', help='MAC address of the guest [default: random].')
        group.add_setting('mask', metavar='VALUE', help='IP mask in dotted form [default: based on ip setting]. Ignored if ip is not specified.')
        group.add_setting('net', metavar='ADDRESS', help='IP net address in dotted form [default: based on ip setting]. Ignored if ip is not specified.')
        group.add_setting('bcast', metavar='VALUE', help='IP broadcast in dotted form [default: based on ip setting]. Ignored if ip is not specified.')
        group.add_setting('gw', metavar='ADDRESS', help='Gateway (router) address in dotted form [default: based on ip setting (first valid address in the network)]. Ignored if ip is not specified.')
        group.add_setting('dns', metavar='ADDRESS', help='DNS address in dotted form [default: based on ip setting (first valid address in the network)] Ignored if ip is not specified.')


    def preflight_check(self):
        """
        Validate the ip configuration given and set defaults
        """

        ip = self.context.get_setting('ip')
        logging.debug("ip: %s" % ip)
        
        mac = self.context.get_setting('mac')
        if mac:
            if not validate_mac(mac):
                raise VMBuilderUserError("Malformed MAC address entered: %s" % mac)

        if ip != 'dhcp':
            # num* are numeric representations
            numip = dotted_to_numeric_ip(ip)
            
            mask = self.context.get_setting('mask')
            if not mask:
                nummask = guess_mask_from_ip(numip)
            else:
                nummask = dotted_to_numeric_ip(mask)

            numnet = calculate_net_address_from_ip_and_netmask(numip, nummask)

            net = self.context.get_setting('net')
            if not net:
                self.context.set_setting_default('net', numeric_to_dotted_ip(numnet))

            bcast = self.context.get_setting('bcast')
            if not bcast:
                numbcast = calculate_broadcast_address_from_ip_and_netmask(numnet, nummask)
                self.context.set_setting_default('bcast', numeric_to_dotted_ip(numbcast))

            gw = self.context.get_setting('gw')
            if not gw:
                numgw = guess_gw_from_ip(numip)
                self.context.set_setting_default('gw', numeric_to_dotted_ip(numgw))

            dns = self.context.get_setting('dns')
            if not dns:
                self.context.set_setting_default('dns', self.context.get_setting('gw'))

            self.context.set_setting_default('mask', numeric_to_dotted_ip(nummask))

            logging.debug("net: %s" % self.context.get_setting('net'))
            logging.debug("netmask: %s" % self.context.get_setting('mask'))
            logging.debug("broadcast: %s" % self.context.get_setting('bcast'))
            logging.debug("gateway: %s" % self.context.get_setting('gw'))
            logging.debug("dns: %s" % self.context.get_setting('dns'))

    def configure_networking(self, nics):
        if len(nics) > 0:
            nic = nics[0]
        
        ip = self.get_setting('ip')
        if ip == 'dhcp':
            nic.type = 'dhcp'
        else:
            nic.type = 'static'
            nic.ip = ip
            nic.network = self.context.get_setting('net')
            nic.netmask = self.context.get_setting('mask')
            nic.broadcast = self.context.get_setting('bcast')
            nic.gateway = self.context.get_setting('gw')
            nic.dns = self.context.get_setting('dns')
        
register_distro_plugin(NetworkDistroPlugin)
register_hypervisor_plugin(NetworkHypervisorPlugin)
