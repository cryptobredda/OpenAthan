#!/usr/bin/env python3
"""
OpenAthan - Islamic Prayer Times for Waybar
A CLI tool that outputs JSON for Waybar custom module
Uses Aladhan API for accurate prayer times
"""

import json
import sys
import os
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess
import urllib.request
import urllib.error
import time

# =============================================================================
# Configuration
# =============================================================================

CONFIG_DIR = Path.home() / ".config" / "openAthan"
CONFIG_FILE = CONFIG_DIR / "config.json"
LOCATION_FILE = CONFIG_DIR / "location.json"
STATE_FILE = CONFIG_DIR / "state.json"
TIMINGS_CACHE_FILE = CONFIG_DIR / "timings_cache.json"
SOUND_FILE = CONFIG_DIR / "athan.wav"

# Aladhan API calculation methods
# See: https://aladhan.com/calculation-methods
ALADHAN_METHODS = {
    "MWL": 1,                 # Muslim World League
    "ISNA": 2,                # Islamic Society of North America
    "Egypt": 3,                # Egyptian General Authority of Survey
    "Makkah": 4,              # Umm Al-Qura University, Makkah
    "Karachi": 5,              # University of Islamic Sciences, Karachi
    "Tehran": 7,              # Institute of Geophysics, University of Tehran
    "Gulf": 8,                # Gulf Region
    "Kuwait": 9,              # Kuwait
    "Qatar": 10,               # Qatar
    "Singapore": 11,            # Majlis Ugama Islam Singapura, Singapore
    "France": 12,              # Union Organization islamic de France
    "Turkey": 13,              # Diyanet Isleri Baskanligi, Turkey
    "Russia": 14,              # Spiritual Administration of Muslims of Russia
    "Moonsighting": 15,         # Moonsighting Committee Worldwide
    "Dubai": 16,              # Dubai (custom research)
    "JAKIM": 17,             # Jabatan Kemajuan Islam Malaysia (JAKIM)
    "Tunisia": 18,            # Tunisia
    "Algeria": 19,            # Algeria
    "Kemenag": 20,             # Kementerian Agama Republik Indonesia
    "Morocco": 21,             # Morocco
    "Portugal": 22,            # Comunidade Islamica de Lisboa (Portugal)
    "Jafari": 0,               # Shia Ithna-Ashari (Jafari)
}

# Asr methods for Aladhan API
ALADHAN_ASR_METHODS = {
    "Shafi": 0,    # Shafi (standard)
    "Hanafi": 1,   # Hanafi (double shadow length)
}

# Default configuration
DEFAULT_CONFIG = {
    "calculation_method": "MWL",
    "asr_method": "Shafi",
    "adjustments": {  # Manual time adjustments in minutes
        "fajr": 0,
        "dhuhr": 0,
        "asr": 0,
        "maghrib": 0,
        "isha": 0
    },
    "notifications_enabled": True,
    "sound_enabled": True,
    "notification_sound": str(SOUND_FILE),
    "show_hijri_date": True,
    "language": "en"  # en or ar
}

# =============================================================================
# Prayer Names
# =============================================================================

PRAYER_NAMES = {
    "en": {
        "fajr": "Fajr",
        "dhuhr": "Dhuhr",
        "asr": "Asr",
        "maghrib": "Maghrib",
        "isha": "Isha",
        "sunrise": "Sunrise"
    },
    "ar": {
        "fajr": "الفجر",
        "dhuhr": "الظهر",
        "asr": "العصر",
        "maghrib": "المغرب",
        "isha": "العشاء",
        "sunrise": "الشروق"
    }
}

# =============================================================================
# Aladhan API Functions
# =============================================================================

def fetch_prayer_times_from_api(city, country, method, asr_method):
    """Fetch prayer times from Aladhan API."""
    # Map method names to API method numbers
    method_id = ALADHAN_METHODS.get(method, 1)
    asr_id = ALADHAN_ASR_METHODS.get(asr_method, 0)

    # Build API URL - use city and country
    url = f"https://api.aladhan.com/v1/timingsByCity"
    params = {
        "city": city,
        "country": country,
        "method": method_id,
        "school": asr_id,  # Asr school (0=Shafi, 1=Hanafi)
    }

    # Add query string
    query_string = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
    full_url = f"{url}?{query_string}"

    try:
        with urllib.request.urlopen(full_url, timeout=10) as response:
            data = json.loads(response.read().decode())

            if data.get("code") == 200:
                timings_data = data["data"]["timings"]
                hijri_data = data["data"]["date"]["hijri"]

                # Parse times into decimal hours
                # API returns capitalized keys, map to lowercase
                times = {}
                prayer_key_map = {
                    "Fajr": "fajr", "Dhuhr": "dhuhr", "Asr": "asr",
                    "Maghrib": "maghrib", "Isha": "isha", "Sunrise": "sunrise"
                }
                for api_key, prayer in prayer_key_map.items():
                    time_str = timings_data.get(api_key)
                    if time_str and time_str != "---":
                        # Parse "HH:MM" format
                        parts = time_str.split(":")
                        if len(parts) == 2:
                            times[prayer] = int(parts[0]) + int(parts[1]) / 60.0

                return {
                    "times": times,
                    "hijri": {
                        "day": int(hijri_data["day"]),
                        "month": hijri_data["month"]["en"],
                        "month_ar": hijri_data["month"]["ar"],
                        "year": int(hijri_data["year"]),
                    },
                    "date_readable": data["data"]["date"]["readable"],
                    "timezone": data["data"]["meta"]["timezone"]
                }
    except Exception as e:
        print(f"API error: {e}", file=sys.stderr)

    return None

# =============================================================================
# Location Detection
# =============================================================================

def get_ip_based_location():
    """Get location using IP-based geolocation."""
    apis = [
        ("https://ipapi.co/json/", lambda d: ({
            "city": d.get("city"),
            "country": d.get("country_name"),
            "country_code": d.get("country_code")
        })),
        ("http://ip-api.com/json/?fields=status,message,country,countryCode,city,timezone", lambda d: ({
            "city": d.get("city"),
            "country": d.get("country"),
            "country_code": d.get("countryCode")
        })),
    ]

    for url, parser in apis:
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                data = json.loads(response.read().decode())
                location = parser(data)
                if location and location.get("city"):
                    location["timestamp"] = datetime.now().isoformat()
                    return location
        except Exception as e:
            continue

    # Fallback to London if nothing works
    return {"city": "London", "country": "United Kingdom", "country_code": "GB", "timestamp": datetime.now().isoformat()}

def load_location(force_refresh=False):
    """Load location from cache or fetch new location."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    if not force_refresh and LOCATION_FILE.exists():
        try:
            with open(LOCATION_FILE, "r") as f:
                return json.load(f)
        except:
            pass

    location = get_ip_based_location()
    if location:
        with open(LOCATION_FILE, "w") as f:
            json.dump(location, f, indent=2)
        return location

    return None

def set_manual_location(city, country=None, latitude=None, longitude=None):
    """Manually set location by city name."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    location = {
        "city": city,
        "timestamp": datetime.now().isoformat(),
        "manual": True
    }

    if country:
        location["country"] = country
    else:
        location["country"] = ""

    if latitude and longitude:
        location["latitude"] = latitude
        location["longitude"] = longitude

    with open(LOCATION_FILE, "w") as f:
        json.dump(location, f, indent=2)

    print(f"Location set to {city}")
    reload_waybar()
    return location

# =============================================================================
# Prayer Times
# =============================================================================

def get_prayer_times_for_date(location, config):
    """Get prayer times for today from API or cache."""
    # Check cache first (valid for 1 hour)
    now = datetime.now()
    cache_valid = False

    if TIMINGS_CACHE_FILE.exists():
        try:
            with open(TIMINGS_CACHE_FILE, "r") as f:
                cache = json.load(f)
                cache_time = datetime.fromisoformat(cache.get("timestamp", "2000-01-01"))
                # Cache is valid for 4 hours
                if (now - cache_time).total_seconds() < 4 * 3600:
                    cache_valid = True
                    # Check if config matches
                    if (cache.get("method") == config["calculation_method"] and
                        cache.get("asr_method") == config.get("asr_method", "Shafi") and
                        cache.get("city") == location.get("city")):
                        return cache["data"], cache.get("hijri", {})
        except:
            pass

    if not cache_valid:
        # Fetch from API
        city = location.get("city", "London")
        country = location.get("country", "United Kingdom")

        result = fetch_prayer_times_from_api(
            city, country,
            config["calculation_method"],
            config.get("asr_method", "Shafi")
        )

        if result:
            times = result["times"]
            hijri = result["hijri"]

            # Apply manual adjustments
            for prayer, adj in config["adjustments"].items():
                if prayer in times:
                    times[prayer] += adj / 60.0

            # Save to cache
            cache_data = {
                "timestamp": now.isoformat(),
                "method": config["calculation_method"],
                "asr_method": config.get("asr_method", "Shafi"),
                "city": location.get("city"),
                "data": times,
                "hijri": hijri
            }
            with open(TIMINGS_CACHE_FILE, "w") as f:
                json.dump(cache_data, f, indent=2)

            return times, hijri

    return {}, {}

def get_next_prayer(times, current_time):
    """Find the next prayer time."""
    current_minutes = current_time.hour * 60 + current_time.minute

    prayer_order = ["fajr", "dhuhr", "asr", "maghrib", "isha"]
    for prayer in prayer_order:
        if prayer not in times:
            continue
        prayer_hours = int(times[prayer])
        prayer_minutes = int((times[prayer] - prayer_hours) * 60)
        prayer_total_minutes = prayer_hours * 60 + prayer_minutes

        if prayer_total_minutes > current_minutes:
            time_until = prayer_total_minutes - current_minutes
            return prayer, time_until

    # Next prayer is Fajr tomorrow
    fajr_hours = int(times["fajr"])
    fajr_minutes = int((times["fajr"] - fajr_hours) * 60)
    fajr_total_minutes = fajr_hours * 60 + fajr_minutes
    time_until = (24 * 60 - current_minutes) + fajr_total_minutes
    return "fajr", time_until

def time_to_hours_minutes(decimal_hours):
    """Convert decimal hours to hours:minutes."""
    hours = int(decimal_hours)
    minutes = int(round((decimal_hours - hours) * 60))
    if minutes == 60:
        minutes = 0
        hours += 1
    return f"{hours:02d}:{minutes:02d}"

def format_time_until(minutes):
    """Format time until next prayer."""
    if minutes >= 60:
        hours = minutes // 60
        mins = minutes % 60
        return f"{hours}h {mins}m"
    return f"{minutes}m"

# =============================================================================
# Hijri Date
# =============================================================================

def format_hijri_date(hijri_data, language="en"):
    """Format Hijri date from API data."""
    if not hijri_data:
        return "Unknown"

    day = hijri_data.get("day", 1)
    month = hijri_data.get("month", "Muharram") if language == "en" else hijri_data.get("month_ar", "محرم")
    year = hijri_data.get("year", 1447)

    if language == "ar":
        return f"{day} {month} {year}"
    return f"{day} {month} {year}"

# =============================================================================
# Configuration Management
# =============================================================================

def load_config():
    """Load configuration from file or create default."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    if not CONFIG_FILE.exists():
        with open(CONFIG_FILE, "w") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2)
        return DEFAULT_CONFIG.copy()

    try:
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)
            # Merge with defaults
            for key, value in DEFAULT_CONFIG.items():
                if key not in config:
                    config[key] = value
            return config
    except:
        return DEFAULT_CONFIG.copy()

def save_config(config):
    """Save configuration to file."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)

# =============================================================================
# State Management
# =============================================================================

def load_state():
    """Load state from file."""
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    return {"notified_prayers": {}}

def save_state(state):
    """Save state to file."""
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

def mark_prayer_notified(date_str, prayer):
    """Mark a prayer as notified for the day."""
    state = load_state()
    if date_str not in state["notified_prayers"]:
        state["notified_prayers"][date_str] = []
    if prayer not in state["notified_prayers"][date_str]:
        state["notified_prayers"][date_str].append(prayer)
        save_state(state)

def was_prayer_notified(date_str, prayer):
    """Check if a prayer was already notified."""
    state = load_state()
    return (date_str in state["notified_prayers"] and
            prayer in state["notified_prayers"][date_str])

def clear_timings_cache():
    """Clear the timings cache to force API refresh."""
    if TIMINGS_CACHE_FILE.exists():
        TIMINGS_CACHE_FILE.unlink()

# =============================================================================
# Notifications
# =============================================================================

def send_notification(title, message, sound_file=None):
    """Send desktop notification with optional sound."""
    try:
        notify_cmd = ["notify-send", "-i", "clock", title, message]
        subprocess.run(notify_cmd, check=True)

        if sound_file and Path(sound_file).exists():
            for player in ["aplay", "paplay", "mpg123", "mpv", "ffplay"]:
                try:
                    if player == "mpg123":
                        subprocess.run([player, "-q", str(sound_file)],
                                     stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
                    elif player == "mpv":
                        subprocess.run([player, "--really-quiet", "--no-video", str(sound_file)],
                                     stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
                    elif player == "ffplay":
                        subprocess.run([player, "-nodisp", "-autoexit", "-loglevel", "quiet", str(sound_file)],
                                     stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
                    else:
                        subprocess.run([player, str(sound_file)],
                                     stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
                    break
                except:
                    continue
    except:
        pass

# =============================================================================
# JSON Output for Waybar
# =============================================================================

def output_waybar_json(location, config):
    """Output JSON for Waybar custom module."""
    local_now = datetime.now()
    today = local_now.date()

    times, hijri_data = get_prayer_times_for_date(location, config)

    if not times:
        print(json.dumps({"text": "Error", "tooltip": "Could not fetch prayer times"}))
        return

    # Find next prayer
    next_prayer, minutes_until = get_next_prayer(times, local_now)

    mosque_icon = ""
    names = PRAYER_NAMES[config.get("language", "en")]
    next_prayer_name = names[next_prayer]

    # Build tooltip
    lines = []
    lines.append(f"Next: {next_prayer_name} in {format_time_until(minutes_until)}")
    lines.append("")

    if config.get("show_hijri_date", True) and hijri_data:
        lines.append(f"📅 {format_hijri_date(hijri_data, config.get('language', 'en'))}")
        lines.append("")

    lines.append("Today's Prayer Times:")
    for prayer in ["fajr", "sunrise", "dhuhr", "asr", "maghrib", "isha"]:
        if prayer in times:
            prayer_name = names[prayer]
            time_str = time_to_hours_minutes(times[prayer])
            is_next = prayer == next_prayer
            prefix = "  " if not is_next else ""
            lines.append(f"{prefix}{prayer_name}: {time_str}")

    loc_city = location.get('city', 'Unknown')
    loc_country = location.get('country', 'Unknown')
    location_info = f"\nLocation: {loc_city}, {loc_country}"
    method_info = f"Method: {config['calculation_method']}"

    tooltip = "\n".join(lines) + location_info + "\n" + method_info

    output = {
        "text": f"{mosque_icon} {next_prayer_name} - {format_time_until(minutes_until)}",
        "tooltip": tooltip,
        "class": "next-prayer",
        "alt": next_prayer
    }

    print(json.dumps(output))

# =============================================================================
# Daemon Mode
# =============================================================================

daemon_running = True

def check_prayer_times(location, config):
    """Check if it's time for prayer and send notification."""
    local_now = datetime.now()
    date_str = local_now.strftime("%Y-%m-%d")

    times, _ = get_prayer_times_for_date(location, config)
    current_minutes = local_now.hour * 60 + local_now.minute

    names = PRAYER_NAMES[config.get("language", "en")]

    for prayer in ["fajr", "dhuhr", "asr", "maghrib", "isha"]:
        if prayer not in times:
            continue

        prayer_hours = int(times[prayer])
        prayer_minutes = int((times[prayer] - prayer_hours) * 60)
        prayer_total_minutes = prayer_hours * 60 + prayer_minutes

        if abs(current_minutes - prayer_total_minutes) <= 1:
            if not was_prayer_notified(date_str, prayer):
                mark_prayer_notified(date_str, prayer)

                if config.get("notifications_enabled", True):
                    time_str = time_to_hours_minutes(times[prayer])
                    title = f"Prayer Time: {names[prayer]}"
                    message = f"It is time for {names[prayer]} prayer at {time_str}"

                    sound = config.get("sound_enabled", False)
                    sound_file = config["notification_sound"] if sound else None
                    send_notification(title, message, sound_file)

def daemon_main(location, config):
    """Main daemon loop."""
    global daemon_running
    while daemon_running:
        check_prayer_times(location, config)
        time.sleep(30)

def run_daemon(location, config):
    """Run daemon in background."""
    pid_file = CONFIG_DIR / "openathan.pid"

    if pid_file.exists():
        try:
            with open(pid_file, "r") as f:
                pid = int(f.read().strip())
            try:
                os.kill(pid, 0)
            except OSError:
                pass
        except:
            pass

    pid = os.fork()
    if pid > 0:
        with open(pid_file, "w") as f:
            f.write(str(pid))
        print(f"Started daemon with PID {pid}")
        return
    else:
        os.setsid()
        os.umask(0)
        with open(os.devnull, 'r') as f_in:
            os.dup2(f_in.fileno(), 0)
            os.dup2(f_in.fileno(), 1)
            os.dup2(f_in.fileno(), 2)
        daemon_main(location, config)

def stop_daemon():
    """Stop running daemon."""
    pid_file = CONFIG_DIR / "openathan.pid"

    if not pid_file.exists():
        print("Daemon is not running")
        return

    try:
        with open(pid_file, "r") as f:
            pid = int(f.read().strip())
        os.kill(pid, 15)
        pid_file.unlink()
        print(f"Stopped daemon (PID {pid})")
    except Exception as e:
        print(f"Error stopping daemon: {e}")

# =============================================================================
# Waybar Management
# =============================================================================

def reload_waybar():
    """Reload waybar to apply changes."""
    try:
        subprocess.run(["killall", "waybar"], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
        subprocess.Popen(["waybar"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    except:
        pass

# =============================================================================
# CLI Interface
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="OpenAthan - Islamic Prayer Times for Waybar")
    parser.add_argument("--refresh", action="store_true",
                        help="Force refresh waybar module immediately")
    parser.add_argument("--refresh-location", action="store_true",
                        help="Refresh location from IP geolocation")
    parser.add_argument("--set-location", nargs="+", metavar="CITY [COUNTRY]",
                        help="Manually set location by city (e.g., --set-location \"Birmingham\" \"UK\")")
    parser.add_argument("--daemon", action="store_true",
                        help="Run notification daemon in background")
    parser.add_argument("--stop-daemon", action="store_true",
                        help="Stop notification daemon")
    parser.add_argument("--set-method", metavar="METHOD",
                        choices=list(ALADHAN_METHODS.keys()),
                        help="Set calculation method")
    parser.add_argument("--set-asr", metavar="METHOD",
                        choices=["Shafi", "Hanafi"],
                        help="Set Asr calculation method (Shafi or Hanafi)")
    parser.add_argument("--toggle-notifications", action="store_true",
                        help="Toggle prayer time notifications")
    parser.add_argument("--toggle-sound", action="store_true",
                        help="Toggle notification sound")
    parser.add_argument("--adjust", nargs=2, metavar=("PRAYER", "MINUTES"),
                        help="Adjust prayer time by minutes (e.g., --adjust maghrib 2)")
    parser.add_argument("--list-methods", action="store_true",
                        help="List available calculation methods")

    args = parser.parse_args()

    # Handle special commands
    if args.list_methods:
        print("Available calculation methods:")
        for name, method_id in ALADHAN_METHODS.items():
            print(f"  {name}")
        return

    if args.set_location:
        parts = args.set_location
        city = parts[0]
        country = parts[1] if len(parts) > 1 else None
        set_manual_location(city, country)
        clear_timings_cache()  # Force refresh with new location
        return

    if args.stop_daemon:
        stop_daemon()
        return

    # Load config and location
    config = load_config()
    location = load_location(force_refresh=args.refresh_location)

    if not location:
        print("Error: Could not determine location", file=sys.stderr)
        sys.exit(1)

    # Handle configuration changes
    config_changed = False

    if args.set_method:
        config["calculation_method"] = args.set_method
        config_changed = True
        clear_timings_cache()  # Force refresh with new method

    if args.set_asr:
        config["asr_method"] = args.set_asr
        config_changed = True
        clear_timings_cache()  # Force refresh with new method

    if args.toggle_notifications:
        config["notifications_enabled"] = not config.get("notifications_enabled", True)
        status = "enabled" if config["notifications_enabled"] else "disabled"
        print(f"Notifications {status}")
        config_changed = True

    if args.toggle_sound:
        config["sound_enabled"] = not config.get("sound_enabled", True)
        status = "enabled" if config["sound_enabled"] else "disabled"
        print(f"Sound {status}")
        config_changed = True

    if args.adjust:
        prayer, minutes = args.adjust
        try:
            minutes = int(minutes)
            if prayer in config["adjustments"]:
                config["adjustments"][prayer] = minutes
                config_changed = True
                print(f"{prayer.capitalize()} adjusted by {minutes} minutes")
                clear_timings_cache()
            else:
                print(f"Invalid prayer name: {prayer}")
        except ValueError:
            print("Minutes must be a number")

    if config_changed:
        save_config(config)
        reload_waybar()

    if args.refresh_location:
        clear_timings_cache()

    # Handle daemon mode
    if args.daemon:
        run_daemon(location, config)
        return

    # Default: output JSON for Waybar
    output_waybar_json(location, config)

if __name__ == "__main__":
    import urllib.parse
    main()
