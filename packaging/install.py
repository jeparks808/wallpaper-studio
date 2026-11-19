#!/usr/bin/env python3
"""Install this personal AppImage and Cinnamon autostart entry (no root needed)."""
from pathlib import Path
import datetime, os, shutil, subprocess
kit=Path(__file__).resolve().parent
image=kit.parent/'WallpaperEngine-Mint22-x86_64.AppImage'
if not image.is_file(): raise SystemExit(f'Build the image first: {image}')
home=Path.home()
app=home/'Applications/WallpaperEngine-Mint22-x86_64.AppImage'
config=Path(os.environ.get('XDG_CONFIG_HOME',home/'.config'))
data=Path(os.environ.get('XDG_DATA_HOME',home/'.local/share'))
bin_dir=home/'.local/bin'
icon=data/'icons/hicolor/scalable/apps/linux-wallpaperengine.svg'
launcher=bin_dir/'start-wallpaperengine-appimage'
settings=config/'linux-wallpaperengine/settings.conf'
menu=data/'applications/linux-wallpaperengine-appimage.desktop'
autostart=config/'autostart/linux-wallpaperengine-appimage.desktop'
stamp=datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
def backup(path):
    if path.exists(): shutil.copy2(path,path.with_name(path.name+'.backup-'+stamp))
def write(path,text,mode=0o644):
    path.parent.mkdir(parents=True,exist_ok=True); backup(path); path.write_text(text); path.chmod(mode)
app.parent.mkdir(parents=True,exist_ok=True)
backup(app)
pending=app.with_name(app.name+'.pending-'+stamp)
shutil.copy2(image,pending); pending.chmod(0o755); pending.replace(app)
icon.parent.mkdir(parents=True,exist_ok=True); backup(icon); shutil.copy2(kit/'linux-wallpaperengine.svg',icon)
write(launcher,'''#!/bin/bash
set -euo pipefail
app="$HOME/Applications/WallpaperEngine-Mint22-x86_64.AppImage"
# Normal launches mount the AppImage. Extraction is a slower fallback without FUSE.
if [[ ! -r /dev/fuse || ! -w /dev/fuse ]]; then
    export APPIMAGE_EXTRACT_AND_RUN=1
fi
exec "$app" "$@"
''',0o755)
if not settings.exists():
    write(settings,'''# Bash settings for the personal Wallpaper Engine launcher.
SCREEN=eDP-1
FPS=30
WORKSHOP="$HOME/.steam/debian-installation/steamapps/workshop/content/431960"
WALLPAPER=1866954236
''')
# Desktop Exec is not a shell command. Quote and escape the absolute executable.
def quote_exec(value):
    return '"'+str(value).replace('\\','\\\\').replace('"','\\"').replace('`','\\`').replace('$','\\$').replace('%','%%')+'"'
base=f'''[Desktop Entry]
Type=Application
Name=Wallpaper Studio
Comment=Browse and control your Steam Workshop wallpapers
Exec={quote_exec(launcher)}
Icon=linux-wallpaperengine
Terminal=false
StartupNotify=false
Categories=Graphics;
'''
write(menu,base)
write(autostart,base.replace(f'Exec={quote_exec(launcher)}',f'Exec={quote_exec(launcher)} --autostart')+'''OnlyShowIn=X-Cinnamon;
X-GNOME-Autostart-enabled=true
X-GNOME-Autostart-Delay=8
Hidden=false
''')
for path in (menu,autostart): subprocess.run(['desktop-file-validate',str(path)],check=True)
if shutil.which('update-desktop-database'): subprocess.run(['update-desktop-database',str(menu.parent)],check=True)
for path in [app,launcher,settings,menu,autostart,icon]: print(path)
print('Autostart enabled. Log out and back into Cinnamon/X11 to verify login startup.')
