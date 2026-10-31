# Delta for Persistence

## ADDED Requirements

### Requirement: Theme persistence
The system MUST store the chosen theme in localStorage under the key `theme`.

#### Scenario: Reload keeps the theme
- GIVEN a user who picked dark mode
- WHEN the page is reloaded
- THEN the app renders dark mode without a flash of light theme
