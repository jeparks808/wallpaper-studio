# Wallpaper Studio GUI verification — 2 November 2026

## Built and installed

The native GTK GUI update was packaged as a type-2 x86_64 AppImage and installed in `~/Applications/WallpaperEngine-Mint22-x86_64.AppImage`. Its SHA-256 matches the deliverable:

`74096b558d818c8382855929f097012e2e69bd850c9d91b4d8755a5845136371`

Size: 514.0 MiB. Existing installed files were backed up with timestamp suffixes. The original engine source/build was not modified. The installed renderer includes the small bundled MPV IPC adapter patch.

The menu entry is now **Wallpaper Studio**; Cinnamon autostart invokes `--autostart` after an eight-second delay. The GUI was left open with Hawaii Beach Wave running on eDP-1, muted, at the balanced 20 FPS rendering cap.

## Passed checks

- Four focused automated tests: media path containment/missing files, settings round-trip and numeric limits, migration of legacy settings without executing them, and prompt failure when an IPC connection closes.
- Python and launcher syntax checks and desktop-entry validation.
- Library scan: 46 installed entries, with 3 videos and 15 scenes; unsupported web/preset entries clearly marked.
- Native window displayed and visually inspected. Static Steam GIF thumbnails decode their first frame despite incomplete later animation frames. See [interface preview](Wallpaper-Studio-preview.png).
- Live MPV properties read back correctly after changing brightness, contrast, saturation, gamma, hue, sharpening, speed, volume and mute. A video screenshot was written successfully with a separate long timeout for that operation.
- Pause suspended the renderer into Linux process state T. The three-second paused sample recorded zero CPU ticks. Resume advanced video playback again. Stop exited the renderer cleanly.
- Finished installed AppImage: one GUI and one renderer. Opening it again presented the existing application rather than starting duplicate playback.
- Installed command-line pause/resume passed after fixing GTK option handling. Saved settings showed `enabled: true`, `paused: false`, 20 FPS and muted audio after the test.
- Hardware video decoding reported `vaapi-copy`. GUI resident memory with the library loaded was approximately 102.5 MiB.
- Installed-copy checksum matches the delivered AppImage.

## Performance and compatibility limits

A short active-video sample at 20 FPS used 42.25% of one logical CPU, approximately 10.6% of total CPU capacity across 4 logical CPUs. This is a brief process sample, not a controlled battery benchmark or proof of a specific improvement over the earlier screenshot. The renderer still copies frames through X11. The GUI itself adds memory overhead; it does not eliminate the renderer's work.

The Pixels scene stayed alive for seven seconds, but its log contained unsupported script-call errors. Scene metadata controls are available; complete visual compatibility with every scene is **not** verified.

Web wallpapers remain unavailable because of the engine's CEF load-order/subprocess failures, consistent with [upstream issue #628](https://github.com/Almamu/linux-wallpaperengine/issues/628). The GUI does not claim to fix those engine integrations. Standalone presets are also unavailable.

No fresh logout/login, battery-discharge transition, fullscreen application transition, or second machine was exercised. Autostart configuration and its installed command were checked within the current Cinnamon/X11 session. Log out and back in when convenient to verify a real login.

See [the user guide](README.md) for all controls, themes, the Workshop folder, settings, CPU tradeoffs and rebuilding.
