import unittest

from logic.image_model import age_limit_minutes


class TestAgeLimit(unittest.TestCase):
    def test_limit_is_value_times_unit(self):
        self.assertEqual(age_limit_minutes(5, "minutes"), 5)
        self.assertEqual(age_limit_minutes(2, "hours"), 120)
        self.assertEqual(age_limit_minutes(1, "days"), 1440)

    def test_one_day_excludes_older_files(self):
        limit = age_limit_minutes(1, "days")
        self.assertTrue(1439 < limit)        # 23h59m old: shown
        self.assertFalse(1440 < limit)       # 24h old: hidden
        self.assertFalse(2000 < limit)       # used to pass (limit was 2 days)


if __name__ == "__main__":
    unittest.main()
