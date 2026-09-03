# Museum Master 1.1 wall-display and installation guide

## Display specification

- Recommended: commercial 55–85 inch 16:9 4K landscape display; 65–75 inches suits most rooms.
- Minimum: sustained 500-nit brightness, strong native contrast, 4K input, hardware scaling disabled where possible.
- Viewing distance: approximately 1.5–2.5 times the display diagonal; verify room labels from the farthest public position.
- Mount level, landscape, with manufacturer clearance on every ventilated edge. Use a rated mount, concealed strain relief, surge protection, and serviceable power/network paths.
- Calibrate toward warm neutral whites, preserved shadow detail, moderate saturation, and disabled motion interpolation.

## Browser and recovery

Use the approved Preview URL or a reviewed local build. Verify the URL and Museum Master identity before manually entering Safari fullscreen. The supplied scripts are reversible helpers: `start_auction_wall_display.sh` opens an allow-listed URL and may supervise only the local Vite process; `stop_auction_wall_display.sh` stops only that recorded local process. They do not install startup agents, change Safari/macOS settings, or close unrelated windows.

After power loss, restart the display and computer, run the start helper manually, verify the artwork, then enter fullscreen. Automatic login or startup requires a future security review and is intentionally not enabled. Network failure must present the fail-closed quiet/unavailable artwork; never inject substitute telemetry.

## Burn-in, sleep, and motion

Use scheduled dimming outside exhibition hours, a daily sleep interval, pixel-shift features supplied by the display, and periodic fullscreen exit for inspection. Avoid maximum brightness in dark rooms. Enable operating-system reduced motion or Pause Scene for sensitive environments. Ambient animation is low-frequency; evidence-path animation is receipt-gated.

## Installation checklist

- [ ] Exact approved deployment and commit recorded
- [ ] Landscape 16:9 mounting, ventilation, power, and network inspected
- [ ] Far-distance room labels, MAX, all three levels, and safety notices readable
- [ ] Gallery default, six modes, room dialogs, Case Theater, and plaque keyboard-tested
- [ ] Wall Art Mode hides controls; fullscreen hides browser chrome
- [ ] Reduced motion and Pause Scene verified
- [ ] Offline/unavailable state freezes activity and retains safety language
- [ ] Scheduled dim/sleep and burn-in inspection cadence documented
- [ ] Photography boundary reviewed with staff

## Troubleshooting

- Blank page: exit fullscreen, verify the exact URL and network, then restart only the display helper.
- Unavailable or stale: this is an authored safe state. Restore the approved read-only source; do not fabricate data.
- Clipped labels: confirm browser zoom is 100%, landscape orientation, and a supported viewport.
- Motion persists after pause: enable reduced motion, record the browser/version, and remove the display from exhibition pending review.
- Browser chrome visible: re-enter fullscreen manually after confirming no unrelated tabs or windows are exposed.
- Heat, image retention, or flicker: power down safely and service the display; do not compensate with unsupported CSS or OS changes.
