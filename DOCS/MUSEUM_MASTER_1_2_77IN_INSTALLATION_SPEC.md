# 77-inch 4K installation specification

## Display geometry

- Landscape 16:9 display with a native 3840×2160 signal and 100% browser scaling.
- Recommended viewing distance: 8–12 feet.
- Starting centerline: 57 inches above finished floor, adjusted for seating, sightlines, accessibility, and local code.
- Use a hardware-neutral flush mount rated for the display mass, wall assembly, seismic conditions, and service method. Follow the display and mount manufacturers' instructions where they exceed this rider.

## Wall, power, data, and player

- Provide a recessed, code-compliant power/data box that does not force the display off the wall plane or pinch connectors.
- Keep mains power and low-voltage data separated as required by code. Provide strain relief, labeled service loops, and bend radii suitable for every cable.
- Conceal the player in a ventilated, serviceable cavity or adjacent equipment location. Do not seal a player, power supply, or network device inside an unventilated wall void.
- Maintain all manufacturer ventilation clearances. Keep intake/exhaust paths open and verify temperatures after at least two hours at exhibition brightness.
- Preserve tool-safe access to the mount release, power disconnect, player, network adapter, and cable terminations without removing finished wall material.

## Environment

- Use diffuse ambient light; avoid direct sun, spot reflections, HVAC discharge, fireplaces, and heat-producing luminaires near the panel.
- Calibrate room lighting before raising screen brightness. Use the lowest profile that preserves the intended bronze, tobacco, parchment, black, and muted-teal separation at 8–12 feet.
- Keep panel-level logo luminance adjustment, static-content detection, pixel refresh, and other manufacturer OLED protection enabled.

## Network and power behavior

- On network loss, retain the authored fail-closed architecture and visible `UNAVAILABLE` safety state. Never substitute recorded activity as live truth.
- Power restoration order: network equipment, player, display, truth health check, Wall Art Mode, then human-confirmed fullscreen.
- After browser or player interruption, reopen the approved URL, verify checkpoint identity and truth safety, select Wall Art Mode, and confirm fullscreen. Do not automate credential entry.
- For shutdown, exit fullscreen, close the browser, stop any local display server with the supplied stop script, shut down the player cleanly, and then power down the display according to its manufacturer guidance.
