#!/usr/bin/env python3
"""Recompile only the MPV adapter, then relink using the user's existing objects.
Original source and build files are read-only inputs. Outputs stay in --work.
"""
import argparse,json,shlex,subprocess,difflib
from pathlib import Path
p=argparse.ArgumentParser(); p.add_argument('--source',type=Path,default=Path.home()/'linux-wallpaperengine'); p.add_argument('--work',type=Path,required=True)
a=p.parse_args(); src=a.source.resolve(); work=a.work.resolve(); work.mkdir(parents=True,exist_ok=True)
original=src/'src/WallpaperEngine/VideoPlayback/MPV/GLPlayer.cpp'
text=original.read_text().replace('#include <mpv/render_gl.h>','#include <cstdlib>\n#include <mpv/render_gl.h>')
needle='    if (mpv_initialize (this->m_handle) < 0) {'
patch='''    // Optional private IPC endpoint used by the native desktop controller.
    // This adapter is used only for video wallpapers by the controller.
    if (const char* socket = std::getenv ("LWE_MPV_SOCKET")) {
        if (mpv_set_option_string (this->m_handle, "input-ipc-server", socket) < 0) {
            sLog.exception ("Cannot enable the wallpaper control socket");
        }
    }

'''
assert text.count(needle)==1
text=text.replace(needle,patch+needle)
modified=work/'GLPlayer.cpp'; modified.write_text(text)
(work/'mpv-ipc.patch').write_text(''.join(difflib.unified_diff(original.read_text().splitlines(True),text.splitlines(True),fromfile=str(original.relative_to(src)),tofile=str(original.relative_to(src)))))
entry=next(x for x in json.loads((src/'build/compile_commands.json').read_text()) if Path(x['file'])==original)
cmd=shlex.split(entry['command']); cmd[cmd.index('-o')+1]=str(work/'GLPlayer.cpp.o'); cmd[cmd.index('-c')+1]=str(modified)
cmd.extend(['-I',str(original.parent)])
subprocess.run(cmd,cwd=entry['directory'],check=True)
link=shlex.split((src/'build/CMakeFiles/linux-wallpaperengine-lib.dir/link.txt').read_text())
link[link.index('-o')+1]=str(work/'liblinux-wallpaperengine-lib.so')
obj='CMakeFiles/linux-wallpaperengine-lib.dir/src/WallpaperEngine/VideoPlayback/MPV/GLPlayer.cpp.o'
assert obj in link; link[link.index(obj)]=str(work/'GLPlayer.cpp.o')
subprocess.run(link,cwd=src/'build',check=True)
print('Built controller-enabled renderer:',work/'liblinux-wallpaperengine-lib.so')
