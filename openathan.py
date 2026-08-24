#!/usr/bin/env python3
"""Fetch and format location-aware prayer data for the OpenAthan QML plugin."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import stat
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


PLUGIN_DIR = Path(__file__).resolve().parent
STATE_DIR = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state") / "openathan"
CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "openathan"
LOCATION_CACHE = STATE_DIR / "location.json"
TIMINGS_CACHE = CACHE_DIR / "timings.json"
NOTIFICATION_STATE = STATE_DIR / "notifications.json"
THEMED_ICON = CACHE_DIR / "openathan.svg"
THEME_PATH = Path.home() / ".local/state/omarchy/current/theme/colors.toml"

HTTP_MAX_BYTES = 256 * 1024
CACHE_MAX_BYTES = 128 * 1024
THEME_MAX_BYTES = 64 * 1024
SVG_MAX_BYTES = 64 * 1024
READ_CHUNK_BYTES = 16 * 1024
JSON_MAX_DEPTH = 8
JSON_MAX_ITEMS = 512
JSON_MAX_CONTAINER_ITEMS = 64
JSON_MAX_STRING_LENGTH = 512

METHODS = {
    "Jafari": 0,
    "MWL": 1,
    "ISNA": 2,
    "Egypt": 3,
    "Makkah": 4,
    "Karachi": 5,
    "Tehran": 7,
    "Gulf": 8,
    "Kuwait": 9,
    "Qatar": 10,
    "Singapore": 11,
    "France": 12,
    "Turkey": 13,
    "Russia": 14,
    "Moonsighting": 15,
    "Dubai": 16,
    "JAKIM": 17,
    "Tunisia": 18,
    "Algeria": 19,
    "Kemenag": 20,
    "Morocco": 21,
    "Portugal": 22,
}

# A conservative country recommendation. Users can override it in plugin settings.
COUNTRY_METHODS = {
    "AE": "Dubai",
    "BD": "Karachi",
    "CA": "ISNA",
    "DZ": "Algeria",
    "EG": "Egypt",
    "FR": "France",
    "GB": "Moonsighting",
    "ID": "Kemenag",
    "IN": "Karachi",
    "IR": "Tehran",
    "KW": "Kuwait",
    "MA": "Morocco",
    "MY": "JAKIM",
    "PK": "Karachi",
    "PT": "Portugal",
    "QA": "Qatar",
    "RU": "Russia",
    "SA": "Makkah",
    "SG": "Singapore",
    "TN": "Tunisia",
    "TR": "Turkey",
    "US": "ISNA",
}

PRAYERS = (
    ("fajr", "Fajr", "Fajr"),
    ("sunrise", "Sunrise", "Sunrise"),
    ("dhuhr", "Dhuhr", "Dhuhr"),
    ("asr", "Asr", "Asr"),
    ("maghrib", "Maghrib", "Maghrib"),
    ("isha", "Isha", "Isha"),
)
PRAYER_KEYS = {"fajr", "dhuhr", "asr", "maghrib", "isha"}


class OpenAthanError(RuntimeError):
    """An expected error suitable for showing in the plugin."""


def ensure_dirs() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    for path in (STATE_DIR, CACHE_DIR):
        directory_fd = open_directory(path)
        os.close(directory_fd)


def read_limited(stream: Any, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = stream.read(min(READ_CHUNK_BYTES, max_bytes - total + 1))
        if not chunk:
            return b"".join(chunks)
        total += len(chunk)
        if total > max_bytes:
            raise OpenAthanError("Input exceeded the allowed size.")
        chunks.append(chunk)


def open_directory(path: Path) -> int:
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW
    directory_fd = os.open(path, flags)
    try:
        metadata = os.fstat(directory_fd)
        if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.getuid():
            raise OpenAthanError("A local data directory is not a safe user-owned directory.")
        return directory_fd
    except Exception:
        os.close(directory_fd)
        raise


def read_text_limited(path: Path, max_bytes: int) -> str:
    directory_fd = open_directory(path.parent)
    file_fd = -1
    try:
        flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
        file_fd = os.open(path.name, flags, dir_fd=directory_fd)
        metadata = os.fstat(file_fd)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid():
            raise OpenAthanError("A local data file is not a safe user-owned regular file.")
        if metadata.st_size > max_bytes:
            raise OpenAthanError("Input exceeded the allowed size.")
        with os.fdopen(file_fd, "rb") as stream:
            file_fd = -1
            return read_limited(stream, max_bytes).decode("utf-8")
    finally:
        if file_fd >= 0:
            os.close(file_fd)
        os.close(directory_fd)


def atomic_write_text(path: Path, value: str, max_bytes: int) -> None:
    payload = value.encode("utf-8")
    if len(payload) > max_bytes:
        raise OpenAthanError("Output exceeded the allowed size.")

    directory_fd = open_directory(path.parent)
    temporary = f".{path.name}.{secrets.token_hex(8)}"
    file_fd = -1
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW
        file_fd = os.open(temporary, flags, 0o600, dir_fd=directory_fd)
        with os.fdopen(file_fd, "wb") as stream:
            file_fd = -1
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path.name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
        os.fsync(directory_fd)
    finally:
        if file_fd >= 0:
            os.close(file_fd)
        try:
            os.unlink(temporary, dir_fd=directory_fd)
        except FileNotFoundError:
            pass
        os.close(directory_fd)


def validate_json_shape(value: Any) -> None:
    item_count = 0

    def visit(item: Any, depth: int) -> None:
        nonlocal item_count
        item_count += 1
        if item_count > JSON_MAX_ITEMS or depth > JSON_MAX_DEPTH:
            raise OpenAthanError("JSON data exceeded the allowed complexity.")
        if isinstance(item, str):
            if len(item) > JSON_MAX_STRING_LENGTH:
                raise OpenAthanError("JSON data contained an oversized string.")
        elif isinstance(item, dict):
            if len(item) > JSON_MAX_CONTAINER_ITEMS:
                raise OpenAthanError("JSON data contained too many fields.")
            for key, child in item.items():
                if not isinstance(key, str) or len(key) > 64:
                    raise OpenAthanError("JSON data contained an invalid field name.")
                visit(child, depth + 1)
        elif isinstance(item, list):
            if len(item) > JSON_MAX_CONTAINER_ITEMS:
                raise OpenAthanError("JSON data contained too many entries.")
            for child in item:
                visit(child, depth + 1)
        elif item is not None and not isinstance(item, (bool, int, float)):
            raise OpenAthanError("JSON data contained an unsupported value.")

    visit(value, 0)


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(read_text_limited(path, CACHE_MAX_BYTES))
        validate_json_shape(value)
        return value if isinstance(value, dict) else None
    except (OSError, UnicodeError, ValueError, OpenAthanError):
        return None


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(value, ensure_ascii=True, indent=2) + "\n"
    atomic_write_text(path, rendered, CACHE_MAX_BYTES)


def request_json(url: str, timeout: float = 8) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "OpenAthan/2.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content_length = response.headers.get("Content-Length")
            if content_length is not None and int(content_length) > HTTP_MAX_BYTES:
                raise OpenAthanError("The remote service returned too much data.")
            payload = json.loads(read_limited(response, HTTP_MAX_BYTES).decode("utf-8"))
            validate_json_shape(payload)
    except OpenAthanError:
        raise
    except (OSError, UnicodeError, ValueError, urllib.error.URLError) as error:
        raise OpenAthanError(f"Network request failed: {error}") from error
    if not isinstance(payload, dict):
        raise OpenAthanError("The location or prayer service returned invalid data.")
    return payload


def provider_text(
    value: Any, field: str, max_length: int, *, required: bool = False
) -> str:
    if value is None or value == "":
        if required:
            raise OpenAthanError(f"The remote service did not include {field}.")
        return ""
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        raise OpenAthanError(f"The remote service returned an invalid {field}.")
    text = str(value).strip()
    if len(text) > max_length or (required and not text):
        raise OpenAthanError(f"The remote service returned an invalid {field}.")
    return text


def normalize_location(raw: dict[str, Any], source: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise OpenAthanError("The location service returned invalid data.")
    city = provider_text(raw.get("city") or raw.get("name"), "city", 128, required=True)
    country = provider_text(raw.get("country") or raw.get("country_name"), "country", 128)
    country_code = provider_text(
        raw.get("country_code") or raw.get("countryCode"), "country code", 2
    ).upper()
    latitude = raw.get("latitude") if raw.get("latitude") is not None else raw.get("lat")
    longitude = raw.get("longitude") if raw.get("longitude") is not None else raw.get("lon")
    raw_timezone = raw.get("timezone")
    if isinstance(raw_timezone, dict):
        raw_timezone = raw_timezone.get("id")
    timezone = provider_text(raw_timezone, "timezone", 64)
    try:
        if isinstance(latitude, bool) or isinstance(longitude, bool):
            raise ValueError
        latitude = float(latitude)
        longitude = float(longitude)
    except (TypeError, ValueError) as error:
        raise OpenAthanError("The detected location did not include usable coordinates.") from error
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise OpenAthanError("The detected location included invalid coordinates.")
    return {
        "city": city,
        "country": country,
        "countryCode": country_code,
        "latitude": latitude,
        "longitude": longitude,
        "timezone": timezone,
        "source": source,
        "cachedAt": datetime.now().astimezone().isoformat(),
    }


def location_cache_fresh(location: dict[str, Any], max_age: timedelta = timedelta(hours=6)) -> bool:
    try:
        cached_at = datetime.fromisoformat(str(location["cachedAt"]))
        if cached_at.tzinfo is None:
            cached_at = cached_at.astimezone()
        effective_age = timedelta(minutes=10) if location.get("stale", False) else max_age
        return datetime.now().astimezone() - cached_at < effective_age
    except (KeyError, TypeError, ValueError):
        return False


def detect_location() -> dict[str, Any]:
    providers = (
        (
            "https://ipwho.is/",
            lambda value: value if value.get("success", True) else {},
        ),
        (
            "https://ipapi.co/json/",
            lambda value: value,
        ),
    )
    errors: list[str] = []
    for url, parser in providers:
        try:
            return normalize_location(parser(request_json(url, timeout=5)), "auto")
        except OpenAthanError as error:
            errors.append(str(error))
    raise OpenAthanError("Automatic city detection failed. Set a manual city in the plugin settings.")


def geocode_location(city: str, country: str) -> dict[str, Any]:
    query = ", ".join(part for part in (city.strip(), country.strip()) if part)
    if not city.strip():
        raise OpenAthanError("Manual location needs a city in the plugin settings.")
    params = urllib.parse.urlencode({"name": query, "count": 8, "language": "en", "format": "json"})
    payload = request_json(f"https://geocoding-api.open-meteo.com/v1/search?{params}")
    results = payload.get("results")
    if not isinstance(results, list) or not results or len(results) > 8:
        raise OpenAthanError(f"No location was found for {query}.")
    if not all(isinstance(result, dict) for result in results):
        raise OpenAthanError("The location service returned invalid results.")

    wanted = country.strip().lower()
    selected = results[0]
    if wanted:
        for result in results:
            names = {
                str(result.get("country") or "").lower(),
                str(result.get("country_code") or "").lower(),
            }
            if wanted in names:
                selected = result
                break
    return normalize_location(selected, "manual")


def get_location(mode: str, city: str, country: str) -> dict[str, Any]:
    ensure_dirs()
    cached = read_json(LOCATION_CACHE)
    wanted_source = "manual" if mode.lower() == "manual" else "auto"
    same_requested_location = False
    if cached and cached.get("source") == wanted_source:
        same_requested_location = (
            wanted_source != "manual"
            or (
                str(cached.get("requestedCity", "")).casefold() == city.strip().casefold()
                and str(cached.get("requestedCountry", "")).casefold() == country.strip().casefold()
            )
        )
        if same_requested_location and location_cache_fresh(cached):
            return cached

    try:
        location = geocode_location(city, country) if wanted_source == "manual" else detect_location()
        if wanted_source == "manual":
            location["requestedCity"] = city.strip()
            location["requestedCountry"] = country.strip()
        write_json(LOCATION_CACHE, location)
        return location
    except OpenAthanError:
        if cached and cached.get("source") == wanted_source and same_requested_location:
            cached["stale"] = True
            cached["cachedAt"] = datetime.now().astimezone().isoformat()
            write_json(LOCATION_CACHE, cached)
            return cached
        raise


def recommended_method(country_code: str) -> str:
    return COUNTRY_METHODS.get(country_code.upper(), "MWL")


def select_method(configured: str, country_code: str) -> tuple[str, int, bool]:
    automatic = configured == "Auto" or configured not in METHODS
    label = recommended_method(country_code) if automatic else configured
    return label, METHODS[label], automatic


def location_key(location: dict[str, Any]) -> str:
    material = "|".join(
        (
            f"{float(location['latitude']):.4f}",
            f"{float(location['longitude']):.4f}",
            str(location.get("timezone", "")),
        )
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def parse_api_time(value: Any) -> str:
    raw = provider_text(value, "prayer time", 32, required=True)
    match = re.search(r"\b(\d{1,2}):(\d{2})\b", raw)
    if not match:
        raise OpenAthanError("The prayer service returned an invalid time.")
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        raise OpenAthanError("The prayer service returned an invalid time.")
    return f"{hour:02d}:{minute:02d}"


def fetch_timings(
    location: dict[str, Any], method_id: int, school: str, day: date
) -> dict[str, Any]:
    params = urllib.parse.urlencode(
        {
            "latitude": location["latitude"],
            "longitude": location["longitude"],
            "method": method_id,
            "school": 1 if school == "Hanafi" else 0,
        }
    )
    endpoint = f"https://api.aladhan.com/v1/timings/{day.strftime('%d-%m-%Y')}?{params}"
    payload = request_json(endpoint)
    if payload.get("code") != 200 or not isinstance(payload.get("data"), dict):
        raise OpenAthanError("The prayer service could not calculate times for this location.")
    data = payload["data"]
    raw_timings = data.get("timings")
    if not isinstance(raw_timings, dict):
        raise OpenAthanError("The prayer service returned invalid timings.")
    timings = {key: parse_api_time(raw_timings.get(api_key)) for key, _, api_key in PRAYERS}
    date_data = data.get("date")
    hijri = date_data.get("hijri", {}) if isinstance(date_data, dict) else {}
    month = hijri.get("month", {}) if isinstance(hijri, dict) else {}
    meta = data.get("meta")
    timezone_value = meta.get("timezone") if isinstance(meta, dict) else None
    timezone_name = provider_text(
        timezone_value or location.get("timezone"), "timezone", 64
    )
    return {
        "date": day.isoformat(),
        "timings": timings,
        "hijri": {
            "day": provider_text(hijri.get("day"), "Hijri day", 2),
            "month": provider_text(month.get("en"), "Hijri month", 32),
            "year": provider_text(hijri.get("year"), "Hijri year", 4),
        },
        "timezone": timezone_name,
        "fetchedAt": datetime.now().astimezone().isoformat(),
    }


def get_timings(
    location: dict[str, Any], method_id: int, school: str, day: date
) -> dict[str, Any]:
    ensure_dirs()
    cache = read_json(TIMINGS_CACHE) or {}
    key = f"{day.isoformat()}|{location_key(location)}|{method_id}|{school}"
    records = cache.get("records", {})
    if isinstance(records, dict) and isinstance(records.get(key), dict):
        return records[key]
    try:
        result = fetch_timings(location, method_id, school, day)
        records = records if isinstance(records, dict) else {}
        records[key] = result
        # At most one week of small responses is useful offline.
        if len(records) > 7:
            records = dict(list(records.items())[-7:])
        write_json(TIMINGS_CACHE, {"records": records})
        return result
    except OpenAthanError:
        candidates = [
            value
            for record_key, value in records.items()
            if f"|{location_key(location)}|{method_id}|{school}" in record_key
            and isinstance(value, dict)
        ]
        if candidates:
            fallback = dict(candidates[-1])
            fallback["stale"] = True
            return fallback
        raise


def timezone_for(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name) if name else ZoneInfo("UTC")
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def datetime_for(day: date, clock: str, timezone: ZoneInfo) -> datetime:
    hour, minute = (int(part) for part in clock.split(":"))
    return datetime.combine(day, time(hour, minute), timezone)


def duration_text(delta: timedelta, past: bool = False) -> str:
    total_minutes = max(0, int(abs(delta.total_seconds()) // 60))
    hours, minutes = divmod(total_minutes, 60)
    if hours:
        amount = f"{hours}h" + (f" {minutes}m" if minutes else "")
    else:
        amount = f"{max(1, minutes)}m"
    return f"{amount} ago" if past else f"in {amount}"


def build_schedule(timings: dict[str, Any], now: datetime) -> tuple[list[dict[str, str]], dict[str, str]]:
    schedule_day = date.fromisoformat(str(timings["date"]))
    timezone = now.tzinfo or ZoneInfo("UTC")
    prayer_moments = {
        key: datetime_for(schedule_day, str(timings["timings"][key]), timezone)
        for key, _, _ in PRAYERS
    }

    next_key = ""
    next_moment: datetime | None = None
    for key, _, _ in PRAYERS:
        if key not in PRAYER_KEYS:
            continue
        moment = prayer_moments[key]
        if moment > now:
            next_key, next_moment = key, moment
            break
    day_label = "Today"
    if next_moment is None:
        next_key = "fajr"
        next_moment = prayer_moments["fajr"]
        while next_moment <= now:
            next_moment += timedelta(days=1)
        day_label = "Tomorrow" if next_moment.date() > now.date() else "Today"

    rows: list[dict[str, str]] = []
    for key, name, _ in PRAYERS:
        moment = prayer_moments[key]
        is_next = key == next_key and day_label == "Today"
        rows.append(
            {
                "key": key,
                "name": name,
                "time": str(timings["timings"][key]),
                "relative": duration_text(moment - now, past=moment <= now),
                "status": "next" if is_next else ("past" if moment <= now else "later"),
            }
        )

    next_name = next(name for key, name, _ in PRAYERS if key == next_key)
    return rows, {
        "key": next_key,
        "name": next_name,
        "time": next_moment.strftime("%H:%M"),
        "countdown": duration_text(next_moment - now),
        "dayLabel": day_label,
    }


def theme_color() -> str:
    try:
        colors = read_text_limited(THEME_PATH, THEME_MAX_BYTES)
    except (OSError, UnicodeError, OpenAthanError):
        return "#c9c7cd"
    for key in ("accent", "foreground", "color7"):
        match = re.search(rf"^\s*{key}\s*=\s*[\"']?(#[0-9a-fA-F]{{6}})", colors, re.MULTILINE)
        if match:
            return match.group(1).lower()
    return "#c9c7cd"


def render_themed_icon() -> Path:
    ensure_dirs()
    try:
        source = read_text_limited(PLUGIN_DIR / "assets/openathan.svg", SVG_MAX_BYTES)
    except (OSError, UnicodeError, OpenAthanError) as error:
        raise OpenAthanError("The OpenAthan icon could not be read safely.") from error
    rendered = source.replace("currentColor", theme_color())
    try:
        if read_text_limited(THEMED_ICON, SVG_MAX_BYTES) == rendered:
            return THEMED_ICON
    except (OSError, UnicodeError, OpenAthanError):
        pass
    atomic_write_text(THEMED_ICON, rendered, SVG_MAX_BYTES)
    return THEMED_ICON


def send_notification_if_due(
    schedule: list[dict[str, str]], location: dict[str, Any], now: datetime, icon_path: Path
) -> None:
    state = read_json(NOTIFICATION_STATE) or {"sent": {}}
    sent = state.get("sent", {})
    sent = sent if isinstance(sent, dict) else {}
    today_key = now.date().isoformat()
    today_sent = sent.get(today_key, [])
    today_sent = today_sent if isinstance(today_sent, list) else []

    for prayer in schedule:
        if prayer["key"] not in PRAYER_KEYS or prayer["key"] in today_sent:
            continue
        prayer_time = datetime_for(now.date(), prayer["time"], now.tzinfo or ZoneInfo("UTC"))
        if timedelta(0) <= now - prayer_time < timedelta(minutes=2):
            city = str(location.get("city") or "your location")
            command = [
                "notify-send",
                "--app-name=OpenAthan",
                f"--icon={icon_path}",
                f"Prayer time · {prayer['name']}",
                f"{prayer['name']} begins now at {prayer['time']} in {city}.",
            ]
            try:
                subprocess.run(command, check=False, timeout=5)
            except (OSError, subprocess.SubprocessError):
                return
            today_sent.append(prayer["key"])
            sent = {today_key: today_sent}
            write_json(NOTIFICATION_STATE, {"sent": sent})
            return


def format_hijri(value: dict[str, Any]) -> str:
    parts = (str(value.get("day", "")), str(value.get("month", "")), str(value.get("year", "")))
    return " ".join(part for part in parts if part)


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    location = get_location(args.location_mode, args.city, args.country)
    method_label, method_id, method_auto = select_method(args.method, str(location.get("countryCode", "")))

    # The API timezone is authoritative; the location provider is a fallback for the first request.
    initial_timezone = timezone_for(str(location.get("timezone", "")))
    initial_now = datetime.now(initial_timezone)
    timings = get_timings(location, method_id, args.school, initial_now.date())
    timezone = timezone_for(str(timings.get("timezone", "")))
    now = datetime.now(timezone)
    if date.fromisoformat(str(timings["date"])) != now.date():
        timings = get_timings(location, method_id, args.school, now.date())

    schedule, next_prayer = build_schedule(timings, now)
    icon_path = render_themed_icon()
    if args.notify and not timings.get("stale", False):
        send_notification_if_due(schedule, location, now, icon_path)

    country = str(location.get("country") or "").strip()
    city = str(location.get("city") or "Unknown city").strip()
    return {
        "ok": True,
        "generatedAt": now.isoformat(),
        "iconPath": str(icon_path),
        "location": {
            "city": city,
            "country": country,
            "label": f"{city}, {country}" if country else city,
            "source": location.get("source", "auto"),
            "stale": bool(location.get("stale", False)),
        },
        "method": {"label": method_label, "automatic": method_auto},
        "school": args.school,
        "hijri": format_hijri(timings.get("hijri", {})),
        "stale": bool(timings.get("stale", False)),
        "next": next_prayer,
        "prayers": schedule,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="OpenAthan prayer data service")
    parser.add_argument("--location-mode", choices=("auto", "manual"), default="auto")
    parser.add_argument("--city", default="")
    parser.add_argument("--country", default="")
    parser.add_argument("--method", choices=("Auto", *METHODS.keys()), default="Auto")
    parser.add_argument("--school", choices=("Shafi", "Hanafi"), default="Shafi")
    parser.add_argument("--notify", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        report = build_report(parse_args(argv))
        print(json.dumps(report, ensure_ascii=True, separators=(",", ":")))
        return 0
    except OpenAthanError as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=True))
        return 1
    except Exception as error:  # Keep the shell alive if an unexpected provider shape lands.
        print(json.dumps({"ok": False, "error": f"OpenAthan failed: {error}"}, ensure_ascii=True))
        return 1


if __name__ == "__main__":
    sys.exit(main())
