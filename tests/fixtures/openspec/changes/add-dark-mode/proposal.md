# Proposal: Add Dark Mode

## Intent
Users have requested a dark mode option to reduce eye strain during nighttime usage and to
match system preferences.

## Scope
In scope:
- Theme toggle in settings
- System preference detection
- Persist preference in localStorage

Out of scope:
- Custom color themes (future work)
- Per-page theme overrides

## Approach
Use CSS custom properties for theming with a small theme context for state, detecting the
system preference on first load.
