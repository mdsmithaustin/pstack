import unittest

from check import grade

RULE, CASE = "fork-shared-helper", "payroll-overtime"


class PayrollOvertimeTests(unittest.TestCase):
    def test_payroll_threshold_of_its_own_passes(self):
        self.assertEqual(grade(RULE, CASE, "good.md"), [])

    def test_changing_the_shared_constant_fails(self):
        self.assertEqual(grade(RULE, CASE, "bad.md"), ["the compliance hours report changed"])
