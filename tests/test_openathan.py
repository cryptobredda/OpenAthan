import importlib.util
import io
import json
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo


SPEC = importlib.util.spec_from_file_location("openathan", Path(__file__).parents[1] / "openathan.py")
openathan = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(openathan)


class OpenAthanTests(unittest.TestCase):
    def test_limited_reader_rejects_oversized_input(self):
        with self.assertRaises(openathan.OpenAthanError):
            openathan.read_limited(io.BytesIO(b"12345"), 4)

    def test_json_cache_rejects_oversized_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cache.json"
            path.write_bytes(b" " * (openathan.CACHE_MAX_BYTES + 1))
            self.assertIsNone(openathan.read_json(path))

    def test_limited_file_reader_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "target.txt"
            link = root / "link.txt"
            target.write_text("private", encoding="utf-8")
            link.symlink_to(target)
            with self.assertRaises(OSError):
                openathan.read_text_limited(link, 32)

    def test_limited_file_reader_rejects_special_file_without_blocking(self):
        with tempfile.TemporaryDirectory() as directory:
            fifo = Path(directory) / "input.fifo"
            fifo.parent.chmod(0o700)
            openathan.os.mkfifo(fifo)
            with self.assertRaises(openathan.OpenAthanError):
                openathan.read_text_limited(fifo, 32)

    def test_atomic_write_replaces_symlink_without_touching_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            root.chmod(0o700)
            target = root / "target.txt"
            output = root / "output.txt"
            target.write_text("unchanged", encoding="utf-8")
            output.symlink_to(target)

            openathan.atomic_write_text(output, "generated", 32)

            self.assertFalse(output.is_symlink())
            self.assertEqual(output.read_text(encoding="utf-8"), "generated")
            self.assertEqual(target.read_text(encoding="utf-8"), "unchanged")

    def test_file_access_rejects_symlinked_parent_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            real = root / "real"
            link = root / "link"
            real.mkdir()
            link.symlink_to(real, target_is_directory=True)
            (real / "data.txt").write_text("value", encoding="utf-8")
            with self.assertRaises(OSError):
                openathan.read_text_limited(link / "data.txt", 32)

    def test_json_shape_rejects_excessive_entries(self):
        value = list(range(openathan.JSON_MAX_CONTAINER_ITEMS + 1))
        with self.assertRaises(openathan.OpenAthanError):
            openathan.validate_json_shape(value)

    def test_request_json_streams_with_a_byte_limit(self):
        class Response(io.BytesIO):
            headers = {}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                self.close()

        response = Response(json.dumps({"city": "Bristol"}).encode())
        with mock.patch.object(openathan.urllib.request, "urlopen", return_value=response):
            self.assertEqual(openathan.request_json("https://example.test")["city"], "Bristol")

    def test_location_fields_and_coordinates_are_bounded(self):
        base = {
            "city": "Bristol",
            "country": "United Kingdom",
            "country_code": "GB",
            "latitude": 51.45,
            "longitude": -2.58,
            "timezone": "Europe/London",
        }
        self.assertEqual(openathan.normalize_location(base, "auto")["city"], "Bristol")
        with self.assertRaises(openathan.OpenAthanError):
            openathan.normalize_location({**base, "city": "x" * 129}, "auto")
        with self.assertRaises(openathan.OpenAthanError):
            openathan.normalize_location({**base, "latitude": 91}, "auto")

    def test_prayer_time_range_is_validated(self):
        with self.assertRaises(openathan.OpenAthanError):
            openathan.parse_api_time("25:00")

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
