#
#    Uncomplicated VM Builder
#    Copyright (C) 2010 Canonical Ltd.
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
from   VMBuilder.plugins.ubuntu.lucid import Lucid

class Maverick(Lucid):
    valid_flavours = { 'i386' :  ['generic', 'generic-pae', 'virtual'],
                       'amd64' : ['generic', 'server', 'virtual'] }
