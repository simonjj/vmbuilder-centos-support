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
from   VMBuilder.plugins.ubuntu.feisty import Feisty

class Gutsy(Feisty):
    valid_flavours = { 'i386' :  ['386', 'generic', 'rt', 'server', 'virtual'],
                       'amd64' : ['generic', 'rt', 'server'],
                       'lpia'  : ['lpia', 'lpiacompat'] }
    default_flavour = { 'i386' : 'virtual', 'amd64' : 'server', 'lpia' : 'lpia' }
    xen_kernel_flavour = 'xen'
