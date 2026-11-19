#!/usr/bin/env python3
"""Package the user's existing build; no source/build-tree writes or system installs."""
import argparse, hashlib, json, os, re, shutil, subprocess, sys
from pathlib import Path
p = argparse.ArgumentParser()
p.add_argument('--source', type=Path, default=Path.home()/'linux-wallpaperengine')
p.add_argument('--assets', type=Path, default=Path.home()/'.steam/debian-installation/steamapps/common/wallpaper_engine/assets')
p.add_argument('--stage', type=Path, required=True)
p.add_argument('--tool', type=Path, required=True)
p.add_argument('--runtime', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
a=p.parse_args()
a.stage=a.stage.resolve(); a.source=a.source.resolve()
a.output=a.output.resolve(); a.tool=a.tool.resolve(); a.runtime=a.runtime.resolve()
if a.stage.exists(): raise SystemExit('Stage already exists; supply a new empty stage path.')
source=a.source/'build/output'; payload=a.stage/'usr/lib/linux-wallpaperengine'; libs=a.stage/'usr/lib'
shutil.copytree(source,payload,symlinks=False)
shutil.copytree(a.assets,payload/'assets',symlinks=False)
kit=Path(__file__).resolve().parent
for name in ['AppRun','linux-wallpaperengine.desktop','linux-wallpaperengine.svg','linux-wallpaperengine.png']:
    shutil.copy2(kit/name,a.stage/name)
(a.stage/'AppRun').chmod(0o755)
(a.stage/'.DirIcon').symlink_to('linux-wallpaperengine.png')
# Preserve the original CEF/ANGLE layout. Do not expose the bundled unversioned
# libEGL/libGLESv2 as host-driver replacements.
# Leave libc and driver interfaces on the Mint 22.x host.
exclude=re.compile(r'^(?:ld-linux.*|lib(?:c|m|mvec|dl|pthread|rt|resolv|util|anl)\.so\..*|lib(?:GL|GLX|GLdispatch|OpenGL|EGL|GLESv[12]|gbm|drm[^.]*|va(?:-[^.]+)?|vdpau|vulkan|OpenCL)\.so\..*)$')
for dirname in ['pipewire-0.3','spa-0.2']:
    shutil.copytree(Path('/usr/lib/x86_64-linux-gnu')/dirname,libs/dirname,symlinks=False)
shutil.copytree('/usr/share/pipewire',a.stage/'usr/share/pipewire')
# NSS loads these by name rather than via DT_NEEDED.
for name in ['libsoftokn3.so','libfreeblpriv3.so','libnssckbi.so']:
    shutil.copy2(Path('/usr/lib/x86_64-linux-gnu')/name,libs/name)
manifest={}; host={}
def elf(path):
    with path.open('rb') as f: return f.read(4)==b'\x7fELF'
# ldd walks the full dependency closure. Also scan dlopened audio and CEF plugins.
initial=[x for x in a.stage.rglob('*') if x.is_file() and elf(x)]
# Resolve using original build paths before removing them.
env=os.environ.copy(); env['LD_LIBRARY_PATH']=f'{payload}:{libs}:{a.source}/build/lib'
for path in initial:
    result=subprocess.run(['ldd',str(path)],env=env,text=True,capture_output=True)
    if 'not found' in result.stdout: raise SystemExit(f'Missing dependencies: {path}\n{result.stdout}')
    for name, loc in re.findall(r'^\s*(\S+) => (/\S+) \(',result.stdout,re.M):
        if exclude.match(name): host[name]=loc; continue
        if (payload/name).exists() or (libs/name).exists(): continue
        shutil.copy2(loc,libs/name); manifest[name]=loc
# Compile the small MPV control adapter and include the native Mint GTK frontend.
gui=kit.parent/'gui'
renderer_work=a.stage.parent/(a.stage.name+'-renderer-build')
subprocess.run([sys.executable,str(gui/'build-renderer.py'),'--source',str(a.source),'--work',str(renderer_work)],check=True)
shutil.copy2(renderer_work/'liblinux-wallpaperengine-lib.so',payload/'liblinux-wallpaperengine-lib.so')
frontend=a.stage/'usr/share/wallpaper-studio'; frontend.mkdir(parents=True,exist_ok=True)
for name in ['app.py','model.py','controller.py','style.css']:
    shutil.copy2(gui/name,frontend/name)
shutil.copy2(renderer_work/'mpv-ipc.patch',frontend/'mpv-ipc.patch')

# Use CMake's ELF editor on copies only, replacing any development RPATH.
for path in a.stage.rglob('*'):
    if not path.is_file() or not elf(path): continue
    dynamic=subprocess.check_output(['readelf','-d',str(path)],text=True)
    match=re.search(r'\((?:RUNPATH|RPATH)\).*?\[(.*?)\]',dynamic)
    if match and '/home/' in match[1]:
        script=a.stage.parent/'relocate.cmake'
        script.write_text(f'file(RPATH_CHANGE FILE [[{path}]] OLD_RPATH [[{match[1]}]] NEW_RPATH [[$ORIGIN:$ORIGIN/..]])\n')
        subprocess.run(['cmake','-P',str(script)],check=True)
licenses=a.stage/'usr/share/licenses/linux-wallpaperengine'; licenses.mkdir(parents=True)
shutil.copy2(a.source/'LICENSE',licenses/'ENGINE-LICENSE')
cef_license=next((a.source/'build/cef').glob('*/LICENSE.txt'))
shutil.copy2(cef_license,licenses/'CEF-LICENSE.txt')
# Keep installed dependency copyright notices in the personal bundle.
for name,loc in manifest.items():
    candidates=[loc,str(Path(loc).resolve())]
    if loc.startswith('/lib/'): candidates.append('/usr'+loc)
    result=subprocess.run(['dpkg-query','-S',*candidates],capture_output=True,text=True)
    for line in result.stdout.splitlines():
        package=line.split(': ',1)[0]
        cp=Path('/usr/share/doc')/package.split(':')[0]/'copyright'
        if cp.exists(): shutil.copy2(cp,licenses/(package.replace(':','_')+'-copyright'))
record={'gui':'Wallpaper Studio 2.0','renderer_patch':'usr/share/wallpaper-studio/mpv-ipc.patch','gui_host_requirements':['python3','python3-gi','gir1.2-gtk-3.0','python3-pil'],'source_commit':subprocess.check_output(['git','-C',str(a.source),'rev-parse','HEAD'],text=True).strip(),
        'source':str(a.source),'target':'Linux Mint 22.x x86_64 / Ubuntu 24.04 ABI',
        'bundled_libraries':manifest,'host_libraries':host,
        'runtime_sha256':hashlib.sha256(a.runtime.read_bytes()).hexdigest(),
        'tool_sha256':hashlib.sha256(a.tool.read_bytes()).hexdigest()}
(a.stage/'manifest.json').write_text(json.dumps(record,indent=2)+'\n')
subprocess.run(['desktop-file-validate',str(a.stage/'linux-wallpaperengine.desktop')],check=True)
subprocess.run([str(a.tool),'--no-appstream','--runtime-file',str(a.runtime),'--comp','zstd',
                '--mksquashfs-opt','-processors','--mksquashfs-opt','2',
                '--mksquashfs-opt','-Xcompression-level','--mksquashfs-opt','6',str(a.stage),str(a.output)],check=True,env={**os.environ,'ARCH':'x86_64'})
shutil.copy2(a.stage/'manifest.json',a.output.with_suffix('.manifest.json'))
print(f'Built {a.output}; runtime tests still required.')
