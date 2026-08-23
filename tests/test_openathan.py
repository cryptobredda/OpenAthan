import importlib.util
import unittest
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo


SPEC = importlib.util.spec_from_file_location("openathan", Path(__file__).parents[1] / "openathan.py")
openathan = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(openathan)


class OpenAthanTests(unittest.TestCase):
    def test_country_method_recommendations(self):
        self.assertEqual(openathan.recommended_method("GB"), "Moonsighting")
        self.assertEqual(openathan.recommended_method("SA"), "Makkah")
        self.assertEqual(openathan.recommended_method("XX"), "MWL")

    def test_explicit_method_wins(self):
        self.assertEqual(openathan.select_method("ISNA", "GB"), ("ISNA", 2, False))

    def test_schedule_marks_next_prayer(self):
        timings = {
            "date": date(2026, 8, 23).isoformat(),
            "timings": {
                "fajr": "04:20",
                "sunrise": "06:02",
                "dhuhr": "13:10",
                "asr": "17:04",
                "maghrib": "20:16",
                "isha": "21:26",
            },
        }
        now = datetime(2026, 8, 23, 14, 24, tzinfo=ZoneInfo("Europe/London"))
        rows, next_prayer = openathan.build_schedule(timings, now)
        self.assertEqual(next_prayer["name"], "Asr")
        self.assertEqual(next_prayer["countdown"], "in 2h 40m")
        self.assertEqual(next(row for row in rows if row["key"] == "asr")["status"], "next")
        self.assertEqual(next(row for row in rows if row["key"] == "dhuhr")["status"], "past")

    def test_after_isha_rolls_to_tomorrow(self):
        timings = {
            "date": "2026-08-23",
            "timings": {
                "fajr": "04:20",
                "sunrise": "06:02",
                "dhuhr": "13:10",
                "asr": "17:04",
                "maghrib": "20:16",
                "isha": "21:26",
            },
        }
        now = datetime(2026, 8, 23, 23, 0, tzinfo=ZoneInfo("Europe/London"))
        _, next_prayer = openathan.build_schedule(timings, now)
        self.assertEqual(next_prayer["name"], "Fajr")
        self.assertEqual(next_prayer["dayLabel"], "Tomorrow")

    def test_stale_previous_day_still_rolls_forward(self):
        timings = {
            "date": "2026-08-22",
            "timings": {
                "fajr": "04:20",
                "sunrise": "06:02",
                "dhuhr": "13:10",
                "asr": "17:04",
                "maghrib": "20:16",
                "isha": "21:26",
            },
        }
        now = datetime(2026, 8, 23, 23, 0, tzinfo=ZoneInfo("Europe/London"))
        _, next_prayer = openathan.build_schedule(timings, now)
        self.assertEqual(next_prayer["time"], "04:20")
        self.assertEqual(next_prayer["dayLabel"], "Tomorrow")
        self.assertTrue(next_prayer["countdown"].startswith("in "))


if __name__ == "__main__":
    unittest.main()
