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
import os
import re
import shutil

import VMBuilder
import VMBuilder.util as util
from VMBuilder.exception import VMBuilderException

def load_plugins():
    for plugin in find_plugins():
        exec "import %s" % plugin

def find_plugins():
    retval = []
    for plugin_dir in __path__:
        for p in os.listdir(plugin_dir):
            path = '%s/%s' % (plugin_dir, p)
            if os.path.isdir(path) and os.path.isfile('%s/__init__.py' % path):
                retval.append("VMBuilder.plugins.%s" % p)
    return retval

class Plugin(object):
    priority = 10

    def __init__(self, context):
        self.context = context
        self._setting_groups = []
        self.register_options()

    def register_options(self):
        pass
    
    def set_defaults(self):
        pass

    def preflight_check(self):
        """
        Override this method with checks for anything that might cause the VM creation to fail
        
        raise an exception if you can see already that this won't work
        """
        pass

    def post_install(self):
        """
        This is called just after the distro is installed, before it gets copied to the fs images.
        """
        pass

    def install_file(self, path, contents=None, source=None, mode=None):
        fullpath = '%s%s' % (self.context.chroot_dir, path)
        if not os.path.isdir(os.path.dirname(fullpath)):
            os.makedirs(os.path.dirname(fullpath))
        if source and not contents:
            shutil.copy(source, fullpath) 
        else:
            fp = open(fullpath, 'w')
            fp.write(contents)
            fp.close()
        if mode:
            os.chmod(fullpath, mode)
        return fullpath

    def install_from_template(self, path, tmplname, context=None, mode=None):
        return self.install_file(path, VMBuilder.util.render_template(self.__module__.split('.')[2], self.context, tmplname, context), mode=mode)

    def run_in_target(self, *args, **kwargs):
        return util.run_cmd('chroot', self.chroot_dir, *args, **kwargs)

    def call_hooks(self, *args, **kwargs):
        return util.call_hooks(self.context, *args, **kwargs)

    # Settings
    class SettingGroup(object):
        def __init__(self, plugin, context, name):
            # The plugin that owns this setting
            self.plugin = plugin
            # The VM object
            self.context = context
            # Name of the Setting Group
            self.name = name
            # A list of Setting objects
            self._settings = []

        def add_setting(self, *args, **kwargs):
            # kwarg['type'] is used to determine which type of Setting object to create
            # but we don't want to pass it on to its __init__.
            if 'type' in kwargs:
                type = kwargs['type']
                del kwargs['type']
            else:
                type = 'str'

            if type == 'str':
                setting = self.plugin.StringSetting(self, *args, **kwargs)
            elif type == 'bool':
                setting = self.plugin.BooleanSetting(self, *args, **kwargs)
            elif type == 'list':
                setting = self.plugin.ListSetting(self, *args, **kwargs)
            elif type == 'int':
                setting = self.plugin.IntSetting(self, *args, **kwargs)
            else:
                raise VMBuilderException("Unknown setting type: '%s' (Plugin: '%s', Setting group: '%s', Setting: '%s')" % 
                                            (type,
                                             self.plugin.__module__,
                                             self.name,
                                             args[0]))
            self._settings.append(setting)

    class Setting(object):
        default = None

        def __init__(self, setting_group, name, metavar=None, help=None, extra_args=None, valid_options=None, action=None, **kwargs):
            # The Setting Group object that owns this Setting
            self.setting_group = setting_group
            # The name if the setting
            name_regex = '[a-z0-9-]+$'
            if not re.match(name_regex, name):
                raise VMBuilderException('Invalid name for Setting: %s. Must match regex: %s' % (name, name_regex))
            else:
                self.name = name

            self.default = kwargs.get('default', self.default)
            self.help = help
            # Alternate names (for the CLI)
            self.extra_args = extra_args or []
            self.metavar = metavar
            self.value = None
            self.value_set = False
            self.valid_options = valid_options

            if self.name in self.setting_group.context._config:
                raise VMBuilderException("Setting named %s already exists. Previous definition in %s/%s/%s." % 
                                            (self.name,
                                             self.setting_group.plugin.__name__,
                                             self.setting_group.plugin._config[self.name].setting_group.name,
                                             self.setting_group.plugin._config[self.name].name))

            self.setting_group.context._config[self.name] = self

        def get_value(self):
            """
            If a value has previously been set, return it.
            If not, return the default value.
            """

            if self.value_set:
                return self.value
            else:
                return self.default

        def do_check_value(self, value):
            """
            Checks the value's validity.
            """
            if self.valid_options is not None:
                if value not in self.valid_options:
                    raise VMBuilderException('%r is not a valid option for %s. Valid options are: %s' % (value, self.name, ' '.join(self.valid_options)))
            else:
                return self.check_value(value)

        def get_valid_options(self):
            return self.valid_options

        def set_valid_options(self, valid_options):
            """
            Set the list of valid options for this setting.
            """
            if not type(valid_options) == list and valid_options is not None:
                raise VMBuilderException('set_valid_options only accepts lists or None')
            if valid_options:
                for option in valid_options:
                    self.check_value(option)
            self.valid_options = valid_options

        def get_default(self):
            """
            Return the default value.
            """
            return self.default

        def set_default(self, value):
            """
            Set a new default value.
            """
            value = self.do_check_value(value)
            self.default = value

        def set_value_fuzzy(self, value):
            """
            Set new value.

            Contrary to L{set_value}, L{set_value_fuzzy} will attempt
            to turn L{value} into the target type. E.g. turning '10' 
            into 10, "main,universe,multiverse" into ['main',
            'universe', 'multiverse']
            """
            return self.set_value(value)

        def set_value(self, value):
            """
            Set a new value.
            """
            value = self.do_check_value(value)
            self.value = value
            self.value_set = True

    class ListSetting(Setting):
        def __init__(self, *args, **kwargs):
            self.default = []
            super(Plugin.ListSetting, self).__init__(*args, **kwargs)

        def set_value_fuzzy(self, value):
            if len(value) == 1 and type(value[0]) == str:
                value = value[0]
            if type(value) == str:
                if value == '':
                    return self.set_value([])
                for sep in [':', ',']:
                    if sep in value:
                        split_regex = re.compile("\s*%s\s*" % sep)
                        return self.set_value(split_regex.split(value))
                value = [value]
                self.set_value(value)
            return self.set_value(value)

        def check_value(self, value):
            if not type(value) == list:
                raise VMBuilderException('%r is type %s, expected list.' % (value, type(value)))
            return value

    class IntSetting(Setting):
        def set_value_fuzzy(self, value):
            if type(value) != int:
                try:
                    value = int(value)
                except ValueError:
                    raise VMBuilderException('Could not interpret %r as an int.' % (value,))
            return self.set_value(value)

        def check_value(self, value):
            if not type(value) == int:
                raise VMBuilderException('%r is type %s, expected int.' % (value, type(value)))
            return value

    class BooleanSetting(Setting):
        def set_value_fuzzy(self, value):
            if type(value) == str:
                if value.lower() in ['no', 'false', 'off', '0']:
                    value = False
                elif value.lower() in ['yes', 'true', 'on', '1']:
                    value = True
                else:
                    raise VMBuilderException('Could not interpret %r as a boolean value.' % (value,))
            return self.set_value(value)

        def check_value(self, value):
            if not type(value) == bool:
                raise VMBuilderException('%r is type %s, expected bool.' % (value, type(value)))
            return value

    class StringSetting(Setting):
        def check_value(self, value):
            if not type(value) == str:
                raise VMBuilderException('%r is type %s, expected str.' % (value, type(value)))
            return value

    def setting_group(self, name):
        setting_group = self.SettingGroup(self, self.context, name)
        self._setting_groups.append(setting_group)
        return setting_group

    def has_setting(self, name):
        return name in self.context._config

    def get_setting(self, name):
        if not name in self.context._config:
            raise VMBuilderException('Unknown config key: %s' % name)
        return self.context._config[name].get_value()

    def set_setting_fuzzy(self, name, value):
        if not name in self.context._config:
            raise VMBuilderException('Unknown config key: %s' % name)
#        print 'fuzzy setting of %s: %r' % (name, value)
        self.context._config[name].set_value_fuzzy(value)

    def set_setting(self, name, value):
        if not name in self.context._config:
            raise VMBuilderException('Unknown config key: %s' % name)
        self.context._config[name].set_value(value)

    def set_setting_default(self, name, value):
        if not name in self.context._config:
            raise VMBuilderException('Unknown config key: %s' % name)
        self.context._config[name].set_default(value)

    def get_setting_default(self, name):
        if not name in self.context._config:
            raise VMBuilderException('Unknown config key: %s' % name)
        return self.context._config[name].get_default()

    def get_setting_valid_options(self, name):
        if not name in self.context._config:
            raise VMBuilderException('Unknown config key: %s' % name)
        return self.context._config[name].get_valid_options()

    def set_setting_valid_options(self, name, valid_options):
        if not name in self.context._config:
            raise VMBuilderException('Unknown config key: %s' % name)
        self.context._config[name].set_valid_options(valid_options)

