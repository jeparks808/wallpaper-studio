# Wallpaper Studio — native GUI update

Wallpaper Studio is a personal Linux Mint 22.x x86_64 AppImage for browsing and applying your existing Steam Workshop wallpapers. The interface uses GTK, with a dark thumbnail library and a settings panel inspired by Wallpaper Engine. Steam handles downloads; Studio reads the installed files directly.

## Open and control it

Open **Wallpaper Studio** from the Mint application menu. The tray icon also opens the library and offers **Pause / Resume**, **Turn wallpaper off**, **Turn wallpaper on**, and **Quit**.

- **Apply wallpaper:** select a thumbnail and press Apply, or double-click a thumbnail.
- **Pause:** freezes the current wallpaper and suspends the renderer, including decoding. Resume continues from the same position.
- **Turn off:** stops the renderer and asks Cinnamon to restore its static wallpaper. The controller stays available in the tray. Off is remembered across logins.
- **Close window:** hides the library; wallpaper playback and the tray remain active.
- **Quit:** exits the controller and stops the wallpaper.

The installed AppImage remains at `~/Applications/WallpaperEngine-Mint22-x86_64.AppImage`. The existing Cinnamon autostart entry now launches Studio into the tray without opening the library. Startup remains delayed by eight seconds, with retries while the display becomes available.

## Your library

The initial folder is:

```text
~/.steam/debian-installation/steamapps/workshop/content/431960
```

Use **Settings → Library folder** to change it. Choose the `431960` folder containing the individual Workshop-ID folders. **Refresh** rereads downloads after Steam finishes. New top-level folder changes also trigger a refresh; an in-progress download may still need a manual refresh when complete.

Search by title or Workshop ID. Use **Videos**, **Scenes**, or **Favorites** to narrow the collection. Favorite a wallpaper from the settings panel. Thumbnails are static; animated previews do not keep running in the library.

The inspected collection has 46 entries: 3 videos, 15 scenes, 13 web projects and 15 presets. Web projects and standalone presets are shown as unavailable rather than being offered as playable backgrounds.

## Playback and appearance

Each wallpaper remembers its own settings.

| Control | Behavior |
|---|---|
| Frame limit | 15, 20, 24, 30 or 60 FPS; press Apply to restart with the new rendering cap |
| Scaling | Fill, Fit or Stretch; press Apply |
| Mute / volume | Live for the active video; apply to restart scenes |
| Playback speed | Live video speed from 0.25× to 2× |
| Color sliders | Live video brightness, contrast, saturation, gamma and hue |
| Sharpen | Live MPV sharpening adjustment |
| Looks | Original, Vivid, Soft, Monochrome, Night and Warm color presets |
| Scene properties | Editable sliders, toggles, colors and choices exposed in the scene's project metadata; press Apply |

Live adjustments affect the selected wallpaper only when it is also the active video. Adjustments made to another selection are saved for its next launch. While paused, pending video adjustments are sent after resume.

The FPS setting caps desktop rendering; it does not speed up or slow down a source video. Use the separate playback-speed slider to change timing. The Warm look is a hue/saturation preset, not a calibrated white-balance control. Looks are color/sharpening adjustments; this release does not include arbitrary shader/filter plugins.

## Settings and efficiency

**Settings** provides:

- The Workshop library folder and connected display.
- **Midnight**, **Ocean** and **Light** interface themes.
- Automatic pause while running on battery, checked about every 15 seconds.
- The renderer's automatic pause behind fullscreen applications; press Apply after changing this setting.

The initial profile uses **20 FPS**, muted audio and fill scaling. Video hardware decoding remains enabled and was verified as `vaapi-copy` on this MacBook Air. Video wallpapers disable unused audio-reactive processing. The native GUI uses no embedded browser. Thumbnail work uses two workers, and playback logs are truncated if they exceed 5 MiB.

Active animation still consumes CPU because the existing renderer copies each desktop frame through X11. In a short test, the renderer used about 42% of one logical CPU (about 10.6% of total capacity across four logical CPUs) at 20 FPS. This is not a battery-life benchmark. Pausing produced zero renderer CPU ticks during the three-second test. Choose 15 FPS or pause/turn off on battery if resource usage matters more than smoothness.

## Compatibility limits

- Video playback and live controls were tested with Hawaii Beach Wave (`1866954236`).
- Scenes use the existing Linux Wallpaper Engine scene renderer. Custom-property controls are provided, but compatibility varies. The Pixels scene remained running during a smoke test while reporting unsupported script calls; this is not confirmation of complete visual/script compatibility.
- **Web wallpapers remain unavailable.** The original CEF load-order and subprocess failures were not fixed by adding this GUI. CEF resources remain bundled for the existing engine's dependencies. See [upstream issue #628](https://github.com/Almamu/linux-wallpaperengine/issues/628).
- Presets without a standalone supported project cannot be applied directly.
- Other machines, Wayland and older Linux distributions have not been validated. This package targets your Cinnamon/X11 Mint 22.x installation.

## Saved files and troubleshooting

Settings now live in `~/.config/linux-wallpaperengine/gui.json`. The old `settings.conf` is retained; its folder, wallpaper and screen settings are migrated on first launch. New FPS profiles default to 20 for efficiency. Use the GUI for subsequent changes.

Playback logs are under `~/.local/state/linux-wallpaperengine/`; use **Open playback log** in the library. A failed wallpaper launch is reported in the bottom status area. If a file is still downloading, finish the download and press Refresh. If the screen is unavailable, select a connected screen in Settings.

The control socket is private to your user under `$XDG_RUNTIME_DIR/wallpaper-studio`. GTK's application registration keeps one controller instance; opening Studio again brings up the existing window.

Terminal controls, if needed:

```bash
~/.local/bin/start-wallpaperengine-appimage          # Open library
~/.local/bin/start-wallpaperengine-appimage --pause  # Toggle pause
~/.local/bin/start-wallpaperengine-appimage --stop   # Turn off
~/.local/bin/start-wallpaperengine-appimage --quit   # Stop and exit
```

To disable login startup, turn off **Wallpaper Studio** in Cinnamon's **Startup Applications**. No logout was forced during installation. Verify a real login by logging out and back in when convenient, then checking the tray and wallpaper.

## Bundle and source

The AppImage bundles the renderer, MPV/FFmpeg and their application dependencies, CEF support files, PipeWire/SPA support, shared Wallpaper Engine assets, the GTK frontend's Python source and the renderer patch. Workshop downloads remain external.

Mint supplies Python 3, PyGObject/GTK 3, Pillow for thumbnail decoding, X11, system graphics drivers, glibc, fonts and audio services. The corresponding GUI packages are `python3`, `python3-gi`, `gir1.2-gtk-3.0` and `python3-pil`; they were already available on this machine. Ayatana AppIndicator is used when available, with a GTK tray-icon fallback. Thus portability is scoped to a compatible Mint desktop, not a minimal Linux installation.

`gui/` contains the frontend source, meaningful model/IPC tests, a small MPV IPC patch and `build-renderer.py`. The patch enables an optional private control endpoint. It does not replace the user's original source or compiled build.

`packaging/build.py` now recompiles this single adapter, relinks it with the existing build objects, bundles the frontend and creates the AppImage. It requires the original source tree, populated CMake build (including `compile_commands.json` and object files), C++ toolchain, desktop-file-validate, and official appimagetool/runtime files. Example:

```bash
python3 packaging/build.py \
  --stage /absolute/path/to/new/WallpaperStudio.AppDir \
  --tool /absolute/path/to/extracted-appimagetool/AppRun \
  --runtime /absolute/path/to/runtime-x86_64 \
  --output /absolute/path/to/WallpaperEngine-Mint22-x86_64.AppImage
```

The staging directory must be new. To install a build, keep `packaging/` beside the AppImage and run `python3 packaging/install.py`. Replaced files are backed up with timestamp suffixes; GUI preferences are preserved. The installer itself does not launch the GUI.

This personal bundle includes your installed Wallpaper Engine shared assets. It is not prepared for public redistribution.

References: [engine project](https://github.com/Almamu/linux-wallpaperengine), [MPV controls and properties](https://mpv.io/manual/stable/), [AppImage layout](https://docs.appimage.org/packaging-guide/manual.html).

## Source and rebuilding

- `gui/`: the Wallpaper Studio GTK controller (`app.py`, `controller.py`, `model.py`, `style.css`), its tests, and
  `mpv-ipc.patch`, the small renderer patch that gives the controller an mpv control socket.
- `packaging/`: `build.py` builds the AppImage from a local
  [Almamu/linux-wallpaperengine](https://github.com/Almamu/linux-wallpaperengine) build
  (commit `b016d7d`, see `WallpaperEngine-Mint22-x86_64.manifest.json`); `install.py` installs it with the menu entry and Cinnamon autostart.
- The built AppImage is not in this repo (about 515 MB). It lives at `~/Applications/WallpaperEngine-Mint22-x86_64.AppImage`.

## Credits

Built by jeparks808 with Codex (OpenAI): AppImage packaging, autostart, and the Wallpaper Studio GUI.
Initial setup and build troubleshooting for linux-wallpaperengine came from ChatGPT (OpenAI).
The wallpaper renderer is [linux-wallpaperengine](https://github.com/Almamu/linux-wallpaperengine) by Almamu and contributors.
