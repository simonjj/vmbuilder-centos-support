#!/usr/bin/python
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
#    The publically exposed bits of VMBuilder
#
import logging
import VMBuilder.log
import VMBuilder.plugins
from   VMBuilder.distro     import Distro
from   VMBuilder.hypervisor import Hypervisor
from   VMBuilder.plugins    import Plugin
from   VMBuilder.exception  import VMBuilderException, VMBuilderUserError

# Internal bookkeeping
distros = {}
hypervisors = {}
_distro_plugins = []
_hypervisor_plugins = []

# This is meant to be populated by plugins. It should contain a list of the files that we give back to the user.

def register_hypervisor(cls):
    """
    Register a hypervisor class with VMBuilder

    @type cls: Hypervisor
    @param cls: The new Hypervisor subclass to be registered with VMBuilder
    """
    hypervisors[cls.arg] = cls

def get_hypervisor(name):
    """
    Get Hypervisor subclass by name

    @type name: string
    @param name: Name of the Hypervisor subclass (defined by its .arg attribute)
    """
    if name in hypervisors:
        return hypervisors[name]
    else:
        raise VMBuilderUserError('No such hypervisor. Available hypervisors: %s' % (' '.join(hypervisors.keys())))

def register_distro(cls):
    """
    Register a distro class with VMBuilder

    @type cls: Distro
    @param cls: The new Distro subclass to be registered with VMBuilder
    """
    distros[cls.arg] = cls

def get_distro(name):
    """
    Get Distro subclass by name

    @type name: string
    @param name: Name of the Distro subclass (defined by its .arg attribute)
    """
    if name in distros:
        return distros[name]
    else:
        raise VMBuilderUserError('No such distro. Available distros: %s' % (' '.join(distros.keys())))

def register_distro_plugin(cls):
    """
    Register a distro plugin with VMBuilder

    B{Note}: A "distro plugin" is not a plugin that implements a new
    Distro.  It's a plugin that pertains to Distro's.  If you want to
    register a new Distro, use register_distro.

    @type cls: Plugin
    @param cls: The Plugin class to registered as a distro plugin
    """
    _distro_plugins.append(cls)
    _distro_plugins.sort(key=lambda x: x.priority)

def register_hypervisor_plugin(cls):
    """
    Register a hypervisor plugin with VMBuilder

    B{Note}: A "hypervisor plugin" is not a plugin that implements a new
    Hypervisor.  It's a plugin that pertains to Hypervisor's.  If you
    want to register a new Hypervisor, use register_hypervisor.

    @type cls: Plugin
    @param cls: The Plugin class to registered as a hypervisor plugin
    """
    _hypervisor_plugins.append(cls)
    _hypervisor_plugins.sort(key=lambda x: x.priority)

def set_console_loglevel(level):
    """
    Adjust the loglevel that will be sent to the console.

    @type level: number
    @param level: See the standard logging module
    """
    VMBuilder.log.console.setLevel(level)

def get_version_info():
    """
    Return a dict containing version information for VMBuilder.

    @return: A dict with (at least) the following keys:
             - major: Major version number.
             - minor: Minor version number.
             - micro: Micro version number.
             - revno: The revision number of the current branch or the branch from which the tarball was created.
    """
    import vcsversion
    info = vcsversion.version_info
    info['major'] = 0
    info['minor'] = 12
    info['micro'] = 4
    return info

logging.debug('Loading plugins')
VMBuilder.plugins.load_plugins()
