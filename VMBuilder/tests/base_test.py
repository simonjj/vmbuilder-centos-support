import unittest

import VMBuilder
import VMBuilder.plugins
from VMBuilder.exception import VMBuilderUserError

class TestBaseModule(unittest.TestCase):
    def test_register_distro(self):
        class TestDistro():
            arg = 'test'

        VMBuilder.register_distro(TestDistro)
        self.assertEqual(TestDistro, VMBuilder.get_distro('test'))

    def test_register_hypervisor(self):
        class TestHypervisor():
            arg = 'test'

        VMBuilder.register_hypervisor(TestHypervisor)
        self.assertEqual(TestHypervisor, VMBuilder.get_hypervisor('test'))

    def register_hypervisor_or_distro_plugin(self, plugin_attr_name, register_function):
        class Plugin(object):
            priority = 10

        class PluginA(Plugin):
            pass

        class PluginB(Plugin):
            priority = 5

        class PluginC(Plugin):
            priority = 15

        saved_plugins = getattr(VMBuilder, plugin_attr_name)
        setattr(VMBuilder, plugin_attr_name, [])
        register_function(PluginA)
        register_function(PluginB)
        register_function(PluginC)
        self.assertEqual(getattr(VMBuilder, plugin_attr_name)[0], PluginB)
        self.assertEqual(getattr(VMBuilder, plugin_attr_name)[1], PluginA)
        self.assertEqual(getattr(VMBuilder, plugin_attr_name)[2], PluginC)
        setattr(VMBuilder, plugin_attr_name, saved_plugins)

    def test_register_hypervisor_plugin(self):
        self.register_hypervisor_or_distro_plugin('_hypervisor_plugins', VMBuilder.register_hypervisor_plugin)

    def test_register_distro_plugin(self):
        self.register_hypervisor_or_distro_plugin('_distro_plugins', VMBuilder.register_distro_plugin)

    def test_unknown_distro(self):
        self.assertRaises(VMBuilderUserError, VMBuilder.get_distro, 'unknown')

    def test_unknown_hypervisor(self):
        self.assertRaises(VMBuilderUserError, VMBuilder.get_hypervisor, 'unknown')

    def test_set_console_log_level(self):
        for x in range(50):
            VMBuilder.set_console_loglevel(x)
            self.assertEquals(VMBuilder.log.console.level, x)

    def test_get_version_info(self):
        info = VMBuilder.get_version_info()
        self.assertTrue('major' in info)
        self.assertTrue('minor' in info)
        self.assertTrue('micro' in info)
        self.assertTrue('revno' in info)
