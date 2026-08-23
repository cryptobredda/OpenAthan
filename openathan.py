#!/usr/bin/env python3
"""Fetch and format location-aware prayer data for the OpenAthan QML plugin."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


PLUGIN_DIR = Path(__file__).resolve().parent
STATE_DIR = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "openathan"
CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "openathan"
LOCATION_CACHE = STATE_DIR / "location.json"
TIMINGS_CACHE = CACHE_DIR / "timings.json"
NOTIFICATION_STATE = STATE_DIR / "notifications.json"
THEMED_ICON = CACHE_DIR / "openathan.svg"
THEME_PATH = Path.home() / ".local/state/omarchy/current/theme/colors.toml"

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


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, ValueError):
        return None


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=True, indent=2)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def request_json(url: str, timeout: float = 8) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "OpenAthan/2.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError, urllib.error.URLError) as error:
        raise OpenAthanError(f"Network request failed: {error}") from error
    if not isinstance(payload, dict):
        raise OpenAthanError("The location or prayer service returned invalid data.")
    return payload


def normalize_location(raw: dict[str, Any], source: str) -> dict[str, Any]:
    city = str(raw.get("city") or raw.get("name") or "").strip()
    country = str(raw.get("country") or raw.get("country_name") or "").strip()
    country_code = str(raw.get("country_code") or raw.get("countryCode") or "").upper().strip()
    latitude = raw.get("latitude") if raw.get("latitude") is not None else raw.get("lat")
    longitude = raw.get("longitude") if raw.get("longitude") is not None else raw.get("lon")
    timezone = str(raw.get("timezone") or "").strip()
    try:
        latitude = float(latitude)
        longitude = float(longitude)
    except (TypeError, ValueError) as error:
        raise OpenAthanError("The detected location did not include usable coordinates.") from error
    if not city:
        raise OpenAthanError("The detected location did not include a city.")
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
    if not isinstance(results, list) or not results:
        raise OpenAthanError(f"No location was found for {query}.")

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
    match = re.search(r"\b(\d{1,2}):(\d{2})\b", str(value or ""))
    if not match:
        raise OpenAthanError("The prayer service returned an invalid time.")
    return f"{int(match.group(1)):02d}:{int(match.group(2)):02d}"


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
    raw_timings = data.get("timings", {})
    timings = {key: parse_api_time(raw_timings.get(api_key)) for key, _, api_key in PRAYERS}
    hijri = data.get("date", {}).get("hijri", {})
    month = hijri.get("month", {}) if isinstance(hijri, dict) else {}
    timezone_name = str(data.get("meta", {}).get("timezone") or location.get("timezone") or "")
    return {
        "date": day.isoformat(),
        "timings": timings,
        "hijri": {
            "day": str(hijri.get("day") or ""),
            "month": str(month.get("en") or ""),
            "year": str(hijri.get("year") or ""),
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
        colors = THEME_PATH.read_text(encoding="utf-8")
    except OSError:
        return "#c9c7cd"
    for key in ("accent", "foreground", "color7"):
        match = re.search(rf"^\s*{key}\s*=\s*[\"']?(#[0-9a-fA-F]{{6}})", colors, re.MULTILINE)
        if match:
            return match.group(1).lower()
    return "#c9c7cd"


def render_themed_icon() -> Path:
    ensure_dirs()
    source = (PLUGIN_DIR / "assets/openathan.svg").read_text(encoding="utf-8")
    rendered = source.replace("currentColor", theme_color())
    try:
        if THEMED_ICON.read_text(encoding="utf-8") == rendered:
            return THEMED_ICON
    except OSError:
        pass
    THEMED_ICON.write_text(rendered, encoding="utf-8")
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
