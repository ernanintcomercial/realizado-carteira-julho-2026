import unittest
from datetime import date
from calendario import previous_business_day, last_business_day


class CalendarTests(unittest.TestCase):
    def test_holiday_month_change(self):
        self.assertEqual(previous_business_day('2026-11-03', {'2026-11-02'}), date(2026,10,30))
        self.assertEqual(previous_business_day('2026-11-04', {'2026-11-02'}), date(2026,11,3))

    def test_monday(self):
        self.assertEqual(previous_business_day('2026-10-26', set()), date(2026,10,23))

    def test_month_end(self):
        self.assertEqual(last_business_day('2026-10-31', set()), date(2026,10,30))


if __name__ == '__main__':
    unittest.main()
