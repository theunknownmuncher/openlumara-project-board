# Delta for UI

## ADDED Requirements

### Requirement: Theme selection
The app SHALL let users switch between light and dark themes, defaulting to the system
preference.

#### Scenario: User toggles dark mode
- **WHEN** the user clicks the theme toggle
- **THEN** the app switches to dark mode and persists the choice

#### Scenario: First visit
- **GIVEN** a visitor with no stored preference
- **WHEN** the app loads
- **THEN** the theme follows the operating system setting

## MODIFIED Requirements

### Requirement: Contrast
The system MUST keep text legible in both themes.
(Previously: contrast was only checked in light mode)

#### Scenario: Dark mode body text
- WHEN dark mode is active
- THEN body text keeps a contrast ratio of at least 4.5:1

## REMOVED Requirements

### Requirement: Remember me banner
(Deprecated in favour of persisting the theme silently.)
