"""Own one renderer; live video controls use a private MPV IPC socket."""
import json,os,signal,socket,subprocess,time
from pathlib import Path
from model import COLOR_KEYS

class Controller:
    def __init__(self,appdir,state=None,runtime=None):
        self.appdir=Path(appdir); self.payload=self.appdir/'usr/lib/linux-wallpaperengine'
        self.state=Path(state) if state else Path(os.environ.get('XDG_STATE_HOME',Path.home()/'.local/state'))/'linux-wallpaperengine'
        self.state.mkdir(parents=True,exist_ok=True)
        self.runtime=Path(runtime) if runtime else Path(os.environ.get('XDG_RUNTIME_DIR',f'/tmp/lwe-{os.getuid()}'))/'wallpaper-studio'
        self.runtime.mkdir(parents=True,exist_ok=True,mode=0o700)
        if self.runtime.stat().st_uid!=os.getuid() or self.runtime.is_symlink(): raise RuntimeError('Unsafe control socket folder')
        self.runtime.chmod(0o700)
        self.socket_path=self.runtime/'mpv.sock'
        if len(os.fsencode(self.socket_path))>103: raise RuntimeError('Control socket path is too long; use a shorter runtime directory.')
        self.proc=None; self.wallpaper=None; self.paused=False; self.pause_reason=''; self.error=''; self.started=0; self.pending_profile=None; self.ready=False; self.log_check=0
    def ipc(self,command,timeout=.35):
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as s:
            s.settimeout(timeout); s.connect(str(self.socket_path))
            s.sendall((json.dumps({'command':command,'request_id':1})+'\n').encode())
            data=b''
            while len(data)<1_000_000:
                chunk=s.recv(65536)
                if not chunk: raise RuntimeError('Player closed the control connection')
                data+=chunk
                while b'\n' in data:
                    line,data=data.split(b'\n',1)
                    reply=json.loads(line)
                    if reply.get('request_id')==1:
                        if reply.get('error')!='success': raise RuntimeError(str(reply.get('error')))
                        return reply.get('data')
            raise RuntimeError('Invalid player response')
    def start(self,wallpaper,profile,settings):
        if not wallpaper.supported: raise ValueError(wallpaper.error or 'This wallpaper type is not supported by this renderer.')
        # Validate first so a bad selection does not stop the current wallpaper.
        screens=subprocess.run(['xrandr','--query'],capture_output=True,text=True,timeout=3)
        if not any(line.startswith(settings['screen']+' connected') for line in screens.stdout.splitlines()):
            raise ValueError(f"Display {settings['screen']} is not connected. Select a connected display in Settings.")
        self.stop(); self.error=''; self.socket_path.unlink(missing_ok=True)
        env=os.environ.copy(); env['LD_LIBRARY_PATH']=f'{self.payload}:{self.appdir}/usr/lib'
        env['PIPEWIRE_MODULE_DIR']=str(self.appdir/'usr/lib/pipewire-0.3'); env['SPA_PLUGIN_DIR']=str(self.appdir/'usr/lib/spa-0.2'); env['PIPEWIRE_CONFIG_DIR']=str(self.appdir/'usr/share/pipewire')
        if wallpaper.kind=='video': env['LWE_MPV_SOCKET']=str(self.socket_path)
        else: env.pop('LWE_MPV_SOCKET',None)
        volume=0 if profile['muted'] else round(profile['volume']*128/100)
        args=[str(self.payload/'linux-wallpaperengine'),'--assets-dir',str(self.payload/'assets'),'--screen-root',settings['screen'],'--bg',str(wallpaper.directory),'--scaling',profile['scaling'],'--fps',str(profile['fps']),'--volume',str(volume),'--noautomute']
        if wallpaper.kind=='video': args+=['--no-audio-processing']
        if not settings['pause_fullscreen']: args+=['--no-fullscreen-pause']
        if wallpaper.kind=='scene':
            for k,v in profile['properties'].items():
                if k in wallpaper.properties and isinstance(v,(str,int,float,bool)):
                    args+=['--set-property',str(k)+'='+('true' if v is True else 'false' if v is False else str(v))]
        log=self.state/'wallpaper.log'
        if log.exists(): log.replace(self.state/'wallpaper.previous.log')
        with log.open('a') as f:
            f.write('Wallpaper Studio renderer started\n'); f.flush()
            self.proc=subprocess.Popen(args,cwd=self.payload,env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True,umask=0o077)
        self.wallpaper=wallpaper; self.started=time.monotonic(); self.pending_profile=dict(profile); self.ready=wallpaper.kind!='video'
    def stop(self):
        had_process=self.proc is not None
        if self.proc and self.proc.poll() is None:
            if self.paused: os.killpg(self.proc.pid,signal.SIGCONT)
            os.killpg(self.proc.pid,signal.SIGTERM)
            try: self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(self.proc.pid,signal.SIGKILL); self.proc.wait(timeout=3)
        self.proc=None; self.paused=False; self.pause_reason=''; self.ready=False; self.pending_profile=None
        self.socket_path.unlink(missing_ok=True)
        # Ask Cinnamon to restore its static wallpaper after the root pixmap is released.
        if not had_process: return
        try:
            from gi.repository import Gio
            bg=Gio.Settings.new('org.cinnamon.desktop.background'); uri=bg.get_string('picture-uri')
            bg.set_string('picture-uri',''); bg.set_string('picture-uri',uri); Gio.Settings.sync()
        except Exception: pass
    def pause(self,paused,reason='Paused'):
        if not self.proc or self.proc.poll() is not None or paused==self.paused: return
        if paused:
            # Drain audio cleanly before suspending both decoding and the render loop.
            if self.ready and self.wallpaper.kind=='video':
                try: self.ipc(['set_property','pause',True])
                except (OSError,RuntimeError): pass
            os.killpg(self.proc.pid,signal.SIGSTOP); self.paused=True; self.pause_reason=reason
        else:
            os.killpg(self.proc.pid,signal.SIGCONT); self.paused=False; self.pause_reason=''
            if self.wallpaper.kind=='video' and self.ready: self.ipc(['set_property','pause',False])
    def apply_live(self,profile):
        if not self.proc or not self.wallpaper or self.wallpaper.kind!='video': return
        self.pending_profile=dict(profile)
        if self.paused or not self.ready: return
        for key in ('muted','volume','speed',*COLOR_KEYS):
            self.ipc(['set_property','mute' if key=='muted' else key,profile[key]])
        self.pending_profile=None
    def tick(self):
        if time.monotonic()-self.log_check>30:
            self.log_check=time.monotonic()
            log=self.state/'wallpaper.log'
            try:
                if log.stat().st_size>5*1024*1024:
                    log.write_text('Log truncated after 5 MiB; repeated renderer messages omitted.\n')
            except OSError: pass
        if not self.proc: return 'Off'
        code=self.proc.poll()
        if code is not None:
            self.error=f'Renderer stopped (exit {code}). Open the playback log for details.'
            self.proc=None; self.ready=False; return 'Error'
        if self.paused: return self.pause_reason
        if self.wallpaper.kind=='video' and not self.ready:
            if self.socket_path.exists():
                try:
                    # The socket appears before the file is ready.
                    if self.ipc(['get_property','path']): self.ready=True
                except (OSError,RuntimeError): pass
            if not self.ready and time.monotonic()-self.started>20:
                self.error='Video controls did not become ready. Check the playback log.'
                return 'Error'
        if self.ready and self.pending_profile:
            try: self.apply_live(self.pending_profile)
            except (OSError,RuntimeError) as exc: self.error='A playback control failed: '+str(exc)
        return 'Playing' if self.ready else 'Starting…'
