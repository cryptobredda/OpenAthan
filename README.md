# OpenAthan

A minimal, lightweight Islamic prayer times application for Waybar on Hyprland/Wayland. Displays the next prayer with countdown in your status bar, with a hover tooltip showing all prayer times for the day.

## Features

- **Waybar Integration** - Outputs JSON for Waybar custom modules
- **Accurate Prayer Times** - Uses the [Aladhan API](https://aladhan.com/) for precise calculations
- **22 Calculation Methods** - MWL, ISNA, Egypt, Makkah, Karachi, Tehran, Gulf, Kuwait, Qatar, Singapore, France, Turkey, Russia, Moonsighting, Dubai, JAKIM, Tunisia, Algeria, Kemenag, Morocco, Portugal, Jafari
- **City-Based Location** - Set location by city name (no latitude/longitude required)
- **Auto Location Detection** - IP-based geolocation fallback
- **Asr Methods** - Supports both Shafi and Hanafi schools
- **Hijri Date** - Displays Islamic calendar date from API
- **Desktop Notifications** - Optional prayer time notifications
- **Sound Support** - Optional Adhan sound at prayer times
- **Offline Capable** - Caches API responses for offline use
- **Lightweight** - Pure Python, minimal dependencies

## Installation

```bash
# Clone the repository
git clone https://github.com/cryptobredda/OpenAthan.git
cd OpenAthan

# Make executable
chmod +x openathan.py

# Install to ~/.local/bin (optional)
cp openathan.py ~/.local/bin/openathan
chmod +x ~/.local/bin/openathan
```

## Waybar Configuration

Add the following to your Waybar config (`~/.config/waybar/config.jsonc`):

```json
"custom/openathan": {
    "exec": "openathan",
    "return-type": "json",
    "interval": 60,
    "tooltip": true
}
```

Add to your modules list:

```json
"modules-center": ["custom/openathan"]
```

### Example Output

```
Dhuhr - 2h 47m
```

**Tooltip shows:**
```
Next: Dhuhr in 2h 47m

📅 25 Sha'ban 1447

Today's Prayer Times:
  Fajr: 05:51
  Sunrise: 07:28
Dhuhr: 12:22
  Asr: 14:44
  Maghrib: 17:17
  Isha: 18:43

Location: Birmingham, United Kingdom
Method: MWL
```

## Usage

```bash
# Show prayer times (default - outputs JSON for Waybar)
openathan

# Set location by city
openathan --set-location "London" "United Kingdom"
openathan --set-location "Makkah"
openathan --set-location "Dubai" "UAE"

# Set calculation method
openathan --set-method MWL
openathan --set-method ISNA
openathan --set-method Makkah

# List all available methods
openathan --list-methods

# Set Asr school (Shafi or Hanafi)
openathan --set-asr Hanafi

# Adjust individual prayer times (in minutes)
openathan --adjust maghrib 5
openathan --adjust fajr -2

# Refresh location from IP
openathan --refresh-location

# Toggle notifications
openathan --toggle-notifications

# Toggle sound
openathan --toggle-sound

# Start notification daemon (background)
openathan --daemon

# Stop daemon
openathan --stop-daemon

# Show help
openathan --help
```

## Calculation Methods

| Method | Description |
|--------|-------------|
| MWL | Muslim World League |
| ISNA | Islamic Society of North America |
| Egypt | Egyptian General Authority of Survey |
| Makkah | Umm Al-Qura University, Makkah |
| Karachi | University of Islamic Sciences, Karachi |
| Tehran | Institute of Geophysics, University of Tehran |
| Gulf | Gulf Region |
| Kuwait | Kuwait |
| Qatar | Qatar |
| Singapore | Majlis Ugama Islam Singapura |
| France | Union Organization islamique de France |
| Turkey | Diyanet Isleri Baskanligi |
| Russia | Spiritual Administration of Muslims of Russia |
| Moonsighting | Moonsighting Committee Worldwide |
| Dubai | Dubai (custom research) |
| JAKIM | Jabatan Kemajuan Islam Malaysia |
| Tunisia | Tunisia |
| Algeria | Algeria |
| Kemenag | Kementerian Agama Republik Indonesia |
| Morocco | Morocco |
| Portugal | Comunidade Islamica de Lisboa |
| Jafari | Shia Ithna-Ashari |

## Configuration

Configuration is stored in `~/.config/openAthan/config.json`:

```json
{
  "calculation_method": "MWL",
  "asr_method": "Shafi",
  "adjustments": {
    "fajr": 0,
    "dhuhr": 0,
    "asr": 0,
    "maghrib": 0,
    "isha": 0
  },
  "notifications_enabled": true,
  "sound_enabled": false,
  "notification_sound": "~/.config/openAthan/athan.wav",
  "show_hijri_date": true,
  "language": "en"
}
```

## Files

| File | Location | Description |
|------|----------|-------------|
| Config | `~/.config/openAthan/config.json` | User settings |
| Location | `~/.config/openAthan/location.json` | Cached location |
| Cache | `~/.config/openAthan/timings_cache.json` | API response cache |
| State | `~/.config/openAthan/state.json` | Notification state |
| Sound | `~/.config/openAthan/athan.wav` | Custom Adhan sound |

## Daemon Mode

Run the notification daemon to receive desktop notifications at prayer times:

```bash
# Start daemon
openathan --daemon

# Stop daemon
openathan --stop-daemon
```

The daemon runs in the background and checks prayer times every 30 seconds.

## Requirements

- Python 3.6+
- No external Python packages required (uses only standard library)

## API

OpenAthan uses the [Aladhan Prayer Times API](https://aladhan.com/prayer-times-api) for accurate prayer time calculations.

## License

MIT License

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
