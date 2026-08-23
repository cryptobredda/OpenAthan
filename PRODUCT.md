# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Muslim Omarchy users worldwide who want prayer times visible in their desktop bar without opening a separate application. English is the initial interface language.

## Product Purpose

OpenAthan provides the next prayer and its countdown in the Omarchy bar, a complete daily prayer schedule in a click-open panel, and timely desktop notifications. Success means a fresh install can determine a useful city-level location and show accurate local prayer times without setup.

## Positioning

OpenAthan is an Omarchy-native prayer companion: it combines automatic city-level location, region-aware calculation defaults, a theme-integrated shell panel, and prayer notifications in one installable plugin repository.

## Operating Context

The plugin runs continuously as an Omarchy bar widget. Users glance at the next prayer in the bar, open the panel to inspect the full day, and may override their city, country, calculation method, or Asr school through plugin settings.

## Capabilities and Constraints

- Installable through `omarchy plugin add` with no privileged install hook.
- Automatic location uses IP geolocation at city-level precision and must support a manual override.
- Prayer times come from the Aladhan API and are cached for resilience.
- Calculation methods are recommended by country unless explicitly overridden.
- The initial release is English-only.
- Python 3 and standard Linux desktop notification/audio tools may be used; no third-party Python package is required.
- Network-derived location and prayer data must retain the last known good cache during transient failures.

## Brand Commitments

The product name is OpenAthan. Its mark is an SVG whose rendered color follows the active Omarchy theme. The interface must use Omarchy shell typography, spacing, colors, borders, and panel behavior rather than introducing a separate visual theme.

## Evidence on Hand

- Existing Waybar prayer-time implementation in `openathan.py`.
- Existing Aladhan API integration and prayer notification behavior.
- Existing screenshots supplied by the user show the current tooltip and missing notification icon.
- No testimonials, usage metrics, or accuracy claims are available and none should be fabricated.

## Product Principles

- Useful without setup, configurable without friction.
- Show the next decision first, then the complete day.
- Respect location privacy by using only city-level automatic detection.
- Stay visually native to the user’s active Omarchy theme.
- Fail softly by retaining last-known good information.
