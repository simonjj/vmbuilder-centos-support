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
import unittest

from VMBuilder.exception import VMBuilderUserError
from VMBuilder.plugins import network

class TestNetworkPlugin(unittest.TestCase):
    def test_validate_mac(self):
        valid_macs = ['11:22:33:44:55:66',
                      'ff:ff:ff:ff:ff:ff',
                      '00:00:00:00:00:00']
        invalid_macs = ['g1:22:33:44:55:66',
                        '11:ff:ff:ff:ff:ff:ff',
                        'ffffffffffff']
        for mac in valid_macs:
            self.assertTrue(network.validate_mac(mac), '%s was not considered a valid MAC address' % mac)
        for mac in invalid_macs:
            self.assertFalse(network.validate_mac(mac), '%s was not considered an invalid MAC address' % mac)

    def test_dotted_to_numeric_ip(self):
        valid_ips = ['192.168.1.1',
                     '1.1.1.1',
                     '10.0.0.1',
                     '255.255.255.255']

        invalid_ips = ['this is not a valid IP',
                       '256.1.1.1']

        for ip in valid_ips:
            self.assertTrue(network.dotted_to_numeric_ip(ip), '%s was considered a valid IP address' % ip)
        for ip in invalid_ips:
            self.assertRaises(VMBuilderUserError, network.dotted_to_numeric_ip, ip)

    def test_guess_mask_from_ip(self):
        known_correct_values = [('10.0.0.1', 0xFF),
                                ('127.0.0.1', 0xFF),
                                ('172.17.0.1', 0xFFFF),
                                ('192.168.1.1', 0xFFFFFF)]
        
        for ip, nummask in known_correct_values:
            numip = network.dotted_to_numeric_ip(ip)
            self.assertEqual(network.guess_mask_from_ip(numip), nummask, "Incorrect netmask guessed")

        self.assertRaises(VMBuilderUserError, network.guess_mask_from_ip, network.dotted_to_numeric_ip('230.0.0.0'))

    def test_calculate_net_address_from_ip_and_netmask(self):
        known_correct_values = [(('192.168.1.1', '255.255.255.0'), '192.168.1.0'),
                                (('192.168.1.1', '255.255.0.0'),   '192.168.0.0'),
                                (('192.168.1.1', '255.0.0.0'),       '192.0.0.0'),
                                (('192.168.1.1', '255.242.255.0'), '192.160.1.0'),
                                (('192.168.1.1', '0.255.255.0'),     '0.168.1.0')]

        for ((ip, netmask), expected_network) in known_correct_values:
            numip               = network.dotted_to_numeric_ip(ip)
            numnetmask          = network.dotted_to_numeric_ip(netmask)
            self.assertEqual(network.calculate_net_address_from_ip_and_netmask(numip, numnetmask),
                             network.dotted_to_numeric_ip(expected_network))

    def test_calculate_broadcast_address_from_ip_and_netmask(self):
        known_correct_values = [(('192.168.1.0', '255.255.255.0'), '192.168.1.255'),
                                (('192.168.0.0', '255.255.0.0'),   '192.168.255.255'),
                                (('192.0.0.0', '255.0.0.0'),       '192.255.255.255'),
                                (('192.160.1.0', '255.242.255.0'), '192.173.1.255'),
                                (('0.168.1.0', '0.255.255.0'),   '255.168.1.255')]

        for ((ip, netmask), expected_bcast) in known_correct_values:
            numip               = network.dotted_to_numeric_ip(ip)
            numnetmask          = network.dotted_to_numeric_ip(netmask)
            guessed_broadcast   = network.calculate_broadcast_address_from_ip_and_netmask(numip, numnetmask)
            self.assertEqual(guessed_broadcast,
                             network.dotted_to_numeric_ip(expected_bcast),
                             "%s %s made %s, but expected %s" % (ip,
                                                                 netmask,
                                                                 network.numeric_to_dotted_ip(guessed_broadcast),
                                                                 expected_bcast))

    def test_ip_conversion(self):
        for x in xrange(256*256):
            self.assertEqual(x*x, network.dotted_to_numeric_ip(network.numeric_to_dotted_ip(x*x)))
