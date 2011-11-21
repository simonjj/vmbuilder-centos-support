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
from   VMBuilder.plugins.ubuntu.edgy import Edgy

class Feisty(Edgy):
    updategrub = "/usr/sbin/update-grub"
    grubroot = "/usr/lib/grub"
    valid_flavours = { 'i386' :  ['386', '686', '686-smp', 'generic', 'k7', 'k7-smp', 'server', 'server-bigiron', 'lowlatency'],
                       'amd64' : ['amd64-generic', 'amd64-k8', 'amd64-k8-smp', 'amd64-server', 'amd64-xeon', 'server']}
    disk_prefix = 'sd'
