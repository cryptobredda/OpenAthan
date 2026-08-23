# OpenAthan Design

## Direction

OpenAthan is a theme-native operational timetable. It should feel like a first-party Omarchy panel: precise, compact, calm, and immediately scannable rather than decorative or app-like.

## Visual System

- Use `Color`, `Style`, and the active bar's foreground/font bindings for every surface.
- Use the popup background and border supplied by `KeyboardPanel`; do not add an independent card shell.
- Use the active Omarchy accent only for the next prayer, the current-time emphasis, and the SVG mark.
- Secondary information is a darker derivative of the active foreground, never a fixed gray.
- The OpenAthan SVG is monochrome and rendered into cache with the current theme accent or foreground.

## Composition

- The header joins the OpenAthan mark, next prayer, countdown, and exact time in one horizontal read.
- Location and Hijri date share a quiet information rail directly below the header.
- Prayer rows form one aligned timetable with name, exact time, and relative interval columns.
- The next prayer receives a theme-derived selection fill and one hairline marker.
- Method, school, and location source remain in a low-emphasis footer.

## Typography And Spacing

- Inherit Omarchy's configured font family and `Style.font` scale.
- Use bold weight for the next prayer and exact times; do not introduce a display typeface.
- Use `Style.space`, `Style.spacing`, and `Style.cornerRadius` so density and geometry adapt with shell settings.

## Interaction

- Left click toggles the panel; middle click refreshes.
- `R` refreshes and `Esc` closes while the panel has focus.
- Keep the last good schedule visible during refreshes or transient network failures.
- Errors name the recovery action: connection or location settings.
