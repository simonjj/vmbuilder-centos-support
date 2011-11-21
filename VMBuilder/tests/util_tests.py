import unittest

import VMBuilder
from VMBuilder.util import run_cmd

class TestUtils(unittest.TestCase):
    def test_run_cmd(self):
        self.assertTrue("foobarbaztest" in run_cmd("env", env={'foobarbaztest' : 'bar' }))


