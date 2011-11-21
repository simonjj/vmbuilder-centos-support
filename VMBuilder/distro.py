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
#    Distro super class

import logging
import os

from   VMBuilder.util    import run_cmd, call_hooks
import VMBuilder.plugins

class Context(VMBuilder.plugins.Plugin):
    def __init__(self):
        self._config = {}
        super(Context, self).__init__(self)
        self.plugins = [plugin_class(self) for plugin_class in self.plugin_classes]
        self.plugins.sort(key=lambda x:x.priority)
        self._cleanup_cbs = []
        self.hooks = {}
        self.template_dirs = [os.path.expanduser('~/.vmbuilder/%s'),
                              os.path.dirname(__file__) + '/plugins/%s/templates',
                              '/etc/vmbuilder/%s']
        self.overwrite = False

    # Cleanup 
    def cleanup(self):
        logging.info("Cleaning up")
        while len(self._cleanup_cbs) > 0:
            self._cleanup_cbs.pop(0)()

    def add_clean_cb(self, cb):
        self._cleanup_cbs.insert(0, cb)

    def add_clean_cmd(self, *argv, **kwargs):
        cb = lambda : run_cmd(*argv, **kwargs)
        self.add_clean_cb(cb)
        return cb

    def cancel_cleanup(self, cb):
        try:
            self._cleanup_cbs.remove(cb)
        except ValueError:
            # Wasn't in there. No worries.
            pass

    # Hooks
    def register_hook(self, hook_name, func):
        self.hooks[hook_name] = self.hooks.get(hook_name, []) + [func]

    def call_hooks(self, *args, **kwargs):
        try:
            call_hooks(self, *args, **kwargs)
        except Exception:
            self.cleanup()
            raise

class Distro(Context):
    def __init__(self):
        self.plugin_classes = VMBuilder._distro_plugins
        super(Distro, self).__init__()

    def set_chroot_dir(self, chroot_dir):
        self.chroot_dir = chroot_dir 

    def build_chroot(self):
        self.call_hooks('preflight_check')
        self.call_hooks('set_defaults')
        self.call_hooks('bootstrap')
        self.call_hooks('configure_os')
	self.cleanup()
        
    def has_xen_support(self):
        """Install the distro into destdir"""
        raise NotImplemented('Distro subclasses need to implement the has_xen_support method')
    
    def install(self, destdir):
        """Install the distro into destdir"""
        raise NotImplemented('Distro subclasses need to implement the install method')

    def post_mount(self, fs):
        """Called each time a filesystem is mounted to let the distro add things to the filesystem"""

    def install_vmbuilder_log(self, logfile):
        """Let the distro copy the install logfile to the guest"""
