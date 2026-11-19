"""Library and settings. Workshop files are data, never executable configuration."""
import copy,json,os,shlex
from dataclasses import dataclass
from pathlib import Path

DEFAULT_ROOT=str(Path.home()/'.steam/debian-installation/steamapps/workshop/content/431960')
DEFAULT_PROFILE={'fps':20,'scaling':'fill','volume':35,'muted':True,'speed':1.0,
                 'brightness':0,'contrast':0,'saturation':0,'gamma':0,'hue':0,
                 'sharpen':0.0,'filter':'Original','properties':{}}
DEFAULTS={'version':2,'folder':DEFAULT_ROOT,'selected':'1866954236','screen':'eDP-1',
          'enabled':True,'paused':False,'theme':'Midnight','favorites':[],
          'pause_battery':False,'pause_fullscreen':True,'profiles':{}}
PRESETS={
 'Original':{},'Vivid':{'contrast':10,'saturation':20,'gamma':2},
 'Soft':{'contrast':-10,'saturation':-12,'brightness':3},
 'Monochrome':{'saturation':-100},'Night':{'brightness':-25,'gamma':-10,'saturation':-15},
 'Warm':{'hue':-8,'saturation':8,'gamma':3},
}
COLOR_KEYS=('brightness','contrast','saturation','gamma','hue','sharpen')
@dataclass
class Wallpaper:
    id:str
    title:str
    kind:str
    directory:Path
    preview:Path|None
    properties:dict
    error:str=''
    @property
    def supported(self): return self.kind in ('video','scene') and not self.error

def inside(directory,value):
    if not isinstance(value,str) or not value: return None
    target=(directory/value).resolve()
    if not target.is_relative_to(directory.resolve()) or not target.is_file(): return None
    return target

def scan_library(folder):
    root=Path(folder).expanduser()
    if not root.is_dir(): raise ValueError('Choose a Workshop folder containing wallpaper subfolders.')
    wallpapers=[]
    for path in sorted(root.glob('*/project.json')):
        try:
            if path.stat().st_size>2_000_000: continue
            d=json.loads(path.read_text(encoding='utf-8-sig'))
            kind=str(d.get('type','preset')).lower()
            error=''
            if kind=='video' and not inside(path.parent,d.get('file')): error='The video file is missing. Finish the Steam download, then refresh.'
            props=d.get('general',{}).get('properties',{})
            wallpapers.append(Wallpaper(path.parent.name,str(d.get('title',path.parent.name)),kind,path.parent,
                          inside(path.parent,d.get('preview')),props if isinstance(props,dict) else {},error))
        except (OSError,ValueError,TypeError,AttributeError):
            wallpapers.append(Wallpaper(path.parent.name,path.parent.name,'invalid',path.parent,None,{},'Invalid project.json'))
    return sorted(wallpapers,key=lambda x:x.title.casefold())

class Settings:
    def __init__(self,path=None):
        self.path=Path(path) if path else Path(os.environ.get('XDG_CONFIG_HOME',Path.home()/'.config'))/'linux-wallpaperengine/gui.json'
        self.data=copy.deepcopy(DEFAULTS); self.warning=''
        if self.path.exists():
            try:
                d=json.loads(self.path.read_text())
                if not isinstance(d,dict): raise ValueError('Expected a settings object')
                self.data.update({k:v for k,v in d.items() if k in DEFAULTS})
            except (OSError,ValueError): self.warning='Saved settings could not be read; defaults are in use.'
        else:
            old=self.path.with_name('settings.conf')
            if old.exists():
                for line in old.read_text().splitlines():
                    try:
                        words=shlex.split(line,comments=True)
                        if len(words)!=1 or '=' not in words[0]: continue
                        k,v=words[0].split('=',1); v=v.replace('${HOME}',str(Path.home())).replace('$HOME',str(Path.home()))
                        key={'SCREEN':'screen','WORKSHOP':'folder','WALLPAPER':'selected'}.get(k)
                        if key: self.data[key]=v
                    except ValueError: pass
        self.validate()
    def validate(self):
        for k in ('folder','selected','screen','theme'):
            if not isinstance(self.data[k],str): self.data[k]=DEFAULTS[k]
        for k in ('enabled','paused','pause_battery','pause_fullscreen'):
            if not isinstance(self.data[k],bool): self.data[k]=DEFAULTS[k]
        if self.data['theme'] not in ('Midnight','Ocean','Light'): self.data['theme']='Midnight'
        if not isinstance(self.data['profiles'],dict): self.data['profiles']={}
        if not isinstance(self.data['favorites'],list): self.data['favorites']=[]
        self.data['favorites']=[v for v in self.data['favorites'] if isinstance(v,str)]
    def profile(self,id):
        p=copy.deepcopy(DEFAULT_PROFILE)
        saved=self.data['profiles'].get(id,{})
        if isinstance(saved,dict): p.update({k:v for k,v in saved.items() if k in p})
        for k,lo,hi in [('fps',5,60),('volume',0,100),('speed',.25,2),('sharpen',0,1)]+[(k,-100,100) for k in COLOR_KEYS if k!='sharpen']:
            try: p[k]=max(lo,min(hi,float(p[k])))
            except (TypeError,ValueError): p[k]=DEFAULT_PROFILE[k]
        p['fps']=int(p['fps']); p['muted']=bool(p['muted'])
        if p['scaling'] not in ('fill','fit','stretch'): p['scaling']='fill'
        if not isinstance(p['properties'],dict): p['properties']={}
        return p
    def save_profile(self,id,p): self.data['profiles'][id]=copy.deepcopy(p); self.save()
    def save(self):
        self.path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        tmp=self.path.with_suffix('.tmp'); tmp.write_text(json.dumps(self.data,indent=2)+'\n'); tmp.chmod(0o600); tmp.replace(self.path)
