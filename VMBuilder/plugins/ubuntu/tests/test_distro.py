import os
import unittest

from VMBuilder.plugins.ubuntu import distro

class TestUbuntuDistro(unittest.TestCase):
    def test_get_locale(self):
        os.environ['LANG'] = 'foo'
        self.assertEqual(distro.get_locale(), 'foo')
        os.environ['LANG'] = 'foo.utf8'
        self.assertEqual(distro.get_locale(), 'foo.UTF-8')
        del os.environ['LANG']
        self.assertEqual(distro.get_locale(), 'C')

