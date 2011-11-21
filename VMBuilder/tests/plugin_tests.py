import unittest

import VMBuilder.plugins
from   VMBuilder.exception import VMBuilderException

class TestPluginsSettings(unittest.TestCase):
    class VM(VMBuilder.plugins.Plugin):
        def __init__(self, *args, **kwargs):
            self._config = {}
            self.context = self

    class TestPlugin(VMBuilder.plugins.Plugin):
        pass

    def setUp(self):
        self.vm = self.VM()
        self.plugin = self.TestPlugin(self.vm)
        self.i = 0

    def test_add_setting_group_and_setting(self):
        setting_group = self.plugin.setting_group('Test Setting Group')
        self.assertTrue(setting_group in self.plugin._setting_groups, "Setting not added correctly to plugin's registry of setting groups.")

        setting_group.add_setting('testsetting')
        self.assertEqual(self.vm.get_setting('testsetting'), None, "Setting's default value is not None.")

        self.vm.set_setting_default('testsetting', 'newdefault')
        self.assertEqual(self.vm.get_setting('testsetting'), 'newdefault', "Setting does not return custom default value when no value is set.")
        self.assertEqual(self.vm.get_setting_default('testsetting'), 'newdefault', "Setting does not return custom default value through get_setting_default().")

        self.vm.set_setting('testsetting', 'foo')
        self.assertEqual(self.vm.get_setting('testsetting'), 'foo', "Setting does not return set value.")

        self.vm.set_setting_default('testsetting', 'newerdefault')
        self.assertEqual(self.vm.get_setting('testsetting'), 'foo', "Setting does not return set value after setting new default value.")

    def test_invalid_type_raises_exception(self):
        setting_group = self.plugin.setting_group('Test Setting Group')
        self.assertRaises(VMBuilderException, setting_group.add_setting, 'oddsetting', type='odd')

    def test_valid_options(self):
        setting_group = self.plugin.setting_group('Test Setting Group')

        setting_group.add_setting('strsetting')
        self.assertRaises(VMBuilderException, self.vm.set_setting_valid_options, 'strsetting', '')
        self.vm.set_setting_valid_options('strsetting', ['foo', 'bar'])
        self.assertEqual(self.vm.get_setting_valid_options('strsetting'), ['foo', 'bar'])
        self.vm.set_setting('strsetting', 'foo')
        self.assertRaises(VMBuilderException, self.vm.set_setting, 'strsetting', 'baz')
        self.vm.set_setting_valid_options('strsetting', None)
        self.vm.set_setting('strsetting', 'baz')

    def test_invalid_type_setting_raises_exception(self):
        setting_group = self.plugin.setting_group('Test Setting Group')

        test_table = [{ 'type' : 'str',
                        'good' : [''],
                        'fuzzy': [''],
                        'bad'  : [0, True, ['foo']]
                      },
                      { 'type' : 'int',
                        'good' : [0],
                        'fuzzy': [('0', 0), ('34', 34), (0, 0), (34, 34)],
                        'bad'  : ['', '0', True, ['foo']]
                      },
                      { 'type' : 'bool',
                        'good' : [True],
                        'fuzzy': [(True, True), ('tRuE', True), ('oN', True), ('yEs', True), ('1', True),
                                  (False, False), ('fAlSe', False), ('oFf', False), ('nO', False), ('0', False) ],
                        'bad'  : ['', 0, '0', ['foo'], '1']
                      },
                      { 'type' : 'list',
                        'good' : [['foo']],
                        'fuzzy': [('main    ,        universe,multiverse', ['main', 'universe', 'multiverse']),
                                  ('main:universe:multiverse', ['main', 'universe', 'multiverse']),
                                  ('''main:
                                  universe:multiverse''', ['main', 'universe', 'multiverse']),
                                  ('',  [])],
                        'bad'  : [True, '', 0, '0']
                      }]

        def get_new_setting(setting_type):
            setting_name = '%ssetting%d' % (setting_type, self.i)
            self.i += 1
            setting_group.add_setting(setting_name, type=setting_type)
            return setting_name

        def try_bad_setting(setting_type, bad, setter):
            setting_name = get_new_setting(setting_type)
            self.assertRaises(VMBuilderException, setter, setting_name, bad)

        def try_good_setting(setting_type, good, getter, setter):
            setting_name = get_new_setting(setting_type)
            if type(good) == tuple:
                in_value, out_value = good
            else:
                in_value, out_value = good, good

#            print setting_name, in_value
            setter(setting_name, in_value)
            self.assertEqual(getter(setting_name), out_value)

        for setting_type in test_table:
            for good in setting_type['good']:
                try_good_setting(setting_type['type'], good, self.vm.get_setting, self.vm.set_setting)
                try_good_setting(setting_type['type'], good, self.vm.get_setting, self.vm.set_setting_default)
                try_good_setting(setting_type['type'], good, self.vm.get_setting_default, self.vm.set_setting_default)
                try_good_setting(setting_type['type'], good, self.vm.get_setting, self.vm.set_setting_fuzzy)
            for fuzzy in setting_type['fuzzy']:
                try_good_setting(setting_type['type'], fuzzy, self.vm.get_setting, self.vm.set_setting_fuzzy)
            for bad in setting_type['bad']:
                try_bad_setting(setting_type['type'], bad, self.vm.set_setting)
                try_bad_setting(setting_type['type'], bad, self.vm.set_setting_default)

    def test_set_setting_raises_exception_on_invalid_setting(self):
        self.assertRaises(VMBuilderException, self.vm.set_setting_default, 'testsetting', 'newdefault')

    def test_add_setting(self):
        setting_group = self.plugin.setting_group('Test Setting Group')
