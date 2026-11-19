#!/usr/bin/env python3
"""Wallpaper Studio: a native GTK library and a tray controller for Cinnamon/X11."""
import argparse,json,os,signal,subprocess,sys,time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import gi
gi.require_version('Gtk','3.0'); gi.require_version('Gdk','3.0')
from gi.repository import Gtk,Gdk,GdkPixbuf,Gio,GLib,Pango
from model import Settings,scan_library,PRESETS,COLOR_KEYS,DEFAULT_PROFILE
from controller import Controller

BASE=Path(__file__).resolve().parent
APPDIR=Path(os.environ.get('APPDIR',BASE.parents[2]))
if '--appdir' in sys.argv:
    at=sys.argv.index('--appdir'); APPDIR=Path(sys.argv[at+1]); del sys.argv[at:at+2]

def label(text,cls=None):
    w=Gtk.Label(label=text,xalign=0); w.set_line_wrap(True); w.set_max_width_chars(38)
    if cls: w.get_style_context().add_class(cls)
    return w

def button(text,callback,primary=False):
    w=Gtk.Button(label=text); w.connect('clicked',lambda _:callback())
    if primary: w.get_style_context().add_class('suggested-action')
    return w

def box(vertical=True,spacing=8,cls=None):
    w=Gtk.Box(orientation=Gtk.Orientation.VERTICAL if vertical else Gtk.Orientation.HORIZONTAL,spacing=spacing)
    if cls: w.get_style_context().add_class(cls)
    return w

class Studio(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='local.john.WallpaperStudio',flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        for option in ('autostart','quit','pause','stop'):
            self.add_main_option(option,0,GLib.OptionFlags.NONE,GLib.OptionArg.NONE,option,None)
        self.settings=Settings(); self.control=None; self.window=None; self.library=[]; self.selected=None
        self.profile={}; self.filter_kind='All wallpapers'; self.query=''; self.cards={}; self.images={}
        self.generation=0; self.pool=ThreadPoolExecutor(max_workers=2,thread_name_prefix='thumbnail')
        self.updating=False; self.live_timer=0; self.save_timer=0; self.started=False; self.last_error=''; self.monitor=None
        self.tick_count=0; self.battery_paused=False; self.user_paused=self.settings.data['paused']; self.status='Off'
    def do_startup(self):
        Gtk.Application.do_startup(self); self.hold()
        self.control=Controller(APPDIR); self.setup_tray(); self.apply_theme()
        GLib.timeout_add(500,self.tick)
        self.connect('shutdown',self.shutdown)
    def do_command_line(self,command):
        args=command.get_arguments()[1:]
        options=command.get_options_dict()
        has=lambda name: options.contains(name) or '--'+name in args
        if has('quit'): self.control.stop(); self.quit(); return 0
        if has('stop'): self.turn_off(); return 0
        if has('pause'): self.toggle_pause(); return 0
        if not self.started:
            self.started=True; self.refresh_library()
            if self.settings.data['enabled']:
                # Cinnamon invokes autostart after its own eight-second delay.
                GLib.timeout_add(500,self.autostart,0)
        if not has('autostart'): self.show_window()
        return 0
    def setup_tray(self):
        menu=Gtk.Menu()
        for title,action in [('Open Wallpaper Studio',self.show_window),('Pause / Resume',self.toggle_pause),('Turn wallpaper off',self.turn_off),('Turn wallpaper on',self.turn_on),('Quit',self.quit)]:
            item=Gtk.MenuItem(label=title); item.connect('activate',lambda _,fn=action:fn()); menu.append(item)
        menu.show_all(); self.tray_menu=menu
        try:
            gi.require_version('AyatanaAppIndicator3','0.1'); from gi.repository import AyatanaAppIndicator3 as A
            self.indicator=A.Indicator.new('wallpaper-studio',str(APPDIR/'linux-wallpaperengine.svg'),A.IndicatorCategory.APPLICATION_STATUS)
            self.indicator.set_status(A.IndicatorStatus.ACTIVE); self.indicator.set_menu(menu)
        except (ImportError,ValueError):
            self.indicator=Gtk.StatusIcon.new_from_file(str(APPDIR/'linux-wallpaperengine.png'))
            self.indicator.set_tooltip_text('Wallpaper Studio'); self.indicator.connect('activate',lambda _:self.show_window())
            self.indicator.connect('popup-menu',lambda _,b,t:menu.popup(None,None,None,None,b,t))
    def shutdown(self,*_):
        self.flush_profile(); self.control.stop(); self.pool.shutdown(wait=False,cancel_futures=True)
    def apply_theme(self):
        theme=self.settings.data['theme']; css=(BASE/'style.css').read_text()
        if theme=='Ocean': css=css.replace('#101721','#0d2026').replace('#172230','#15313a').replace('#141e2b','#102a32').replace('#2b90c8','#168b88')
        if theme=='Light':
            for a,b in [('#101721','#f2f5fa'),('#e6edf5','#23384c'),('#edf5ff','#23384c'),('#172230','#ffffff'),('#141e2b','#e8eef5'),('#1c2a3a','#ffffff'),('#9aafc4','#536b80'),('#8baac5','#526b82'),('#111c29','#ffffff'),('#223247','#e3ebf5'),('#0d131c','#e3ebf5'),('#8cbbe3','#286494')]: css=css.replace(a,b)
        if hasattr(self,'css'): Gtk.StyleContext.remove_provider_for_screen(Gdk.Screen.get_default(),self.css)
        self.css=Gtk.CssProvider(); self.css.load_from_data(css.encode())
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(),self.css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    def show_window(self):
        if self.window: self.window.present(); return
        self.window=Gtk.ApplicationWindow(application=self); self.window.set_title('Wallpaper Studio'); self.window.set_default_size(1200,770)
        self.window.set_icon_from_file(str(APPDIR/'linux-wallpaperengine.png'))
        self.window.connect('delete-event',self.hide_window)
        header=Gtk.HeaderBar(title='Wallpaper Studio',subtitle='Your Workshop collection · Cinnamon / X11'); header.set_show_close_button(True)
        header.pack_end(button('Settings',self.open_settings)); header.pack_end(button('Refresh',self.refresh_library)); self.window.set_titlebar(header)
        outer=box(); outer.set_spacing(0); self.window.add(outer)
        body=box(False,0); outer.pack_start(body,True,True,0)
        side=box(cls='sidebar'); side.set_size_request(174,-1); body.pack_start(side,False,False,0)
        side.pack_start(label('WORKSHOP','section'),False,False,0)
        self.nav_buttons={}
        for name in ['All wallpapers','Videos','Scenes','Favorites']:
            w=button(name,lambda name=name:self.set_filter(name)); side.pack_start(w,False,False,0); self.nav_buttons[name]=w
        side.pack_start(Gtk.Separator(),False,False,12)
        side.pack_start(label('PLAYBACK','section'),False,False,0)
        self.pause_button=button('Pause',self.toggle_pause); side.pack_start(self.pause_button,False,False,0)
        self.on_button=button('Turn off',self.toggle_power); side.pack_start(self.on_button,False,False,0)
        side.pack_end(button('Open playback log',self.open_log),False,False,0)
        hint=label('Closing this window keeps your wallpaper and tray controls running.','subtitle'); hint.set_max_width_chars(22)
        side.pack_end(hint,False,False,8)
        center=box(cls='library'); body.pack_start(center,True,True,0)
        center.pack_start(label('Installed wallpapers','title'),False,False,0)
        self.count_label=label('Reading your collection…','subtitle'); center.pack_start(self.count_label,False,False,0)
        search=Gtk.SearchEntry(); search.set_placeholder_text('Search titles or Workshop IDs'); search.connect('search-changed',self.search_changed); center.pack_start(search,False,False,6)
        scroll=Gtk.ScrolledWindow(); scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC); center.pack_start(scroll,True,True,0)
        self.flow=Gtk.FlowBox(); self.flow.set_selection_mode(Gtk.SelectionMode.SINGLE); self.flow.set_min_children_per_line(2); self.flow.set_max_children_per_line(3); self.flow.set_homogeneous(True)
        self.flow.connect('selected-children-changed',self.selection_changed); self.flow.connect('child-activated',lambda *_:self.apply_selected())
        self.flow.set_filter_func(self.card_visible); scroll.add(self.flow)
        right_scroll=Gtk.ScrolledWindow(); right_scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC); right_scroll.set_size_request(320,-1)
        self.inspector=box(cls='inspector'); right_scroll.add(self.inspector); body.pack_start(right_scroll,False,False,0)
        bottom=box(False,12,'statusbar'); outer.pack_end(bottom,False,False,0)
        self.status_label=label('Off'); bottom.pack_start(self.status_label,True,True,0)
        self.message_label=label(self.settings.warning,'subtitle'); self.message_label.set_ellipsize(Pango.EllipsizeMode.END); self.message_label.set_max_width_chars(66); bottom.pack_end(self.message_label,False,False,0)
        self.render_cards(); self.window.show_all(); self.select_saved(); self.update_status()
    def hide_window(self,*_):
        self.window.hide(); return True
    def refresh_library(self):
        try: self.library=scan_library(self.settings.data['folder']); self.watch_folder()
        except ValueError as exc: self.library=[]; self.message(str(exc))
        if self.window: self.render_cards(); self.select_saved()
    def watch_folder(self):
        if self.monitor: self.monitor.cancel()
        try:
            self.monitor=Gio.File.new_for_path(self.settings.data['folder']).monitor_directory(Gio.FileMonitorFlags.NONE,None)
            self.monitor.connect('changed',self.folder_changed)
        except GLib.Error: pass
    def folder_changed(self,*_):
        if getattr(self,'refresh_timer',0): GLib.source_remove(self.refresh_timer)
        self.refresh_timer=GLib.timeout_add(1500,self.delayed_refresh)
    def delayed_refresh(self): self.refresh_timer=0; self.refresh_library(); return False
    def render_cards(self):
        self.generation+=1; generation=self.generation
        for c in self.flow.get_children(): self.flow.remove(c)
        self.cards={}; self.images={}
        videos=sum(x.kind=='video' for x in self.library); scenes=sum(x.kind=='scene' for x in self.library)
        self.count_label.set_text(f'{len(self.library)} installed · {videos} videos · {scenes} scenes')
        for wp in self.library:
            card=box(cls='card'); card.set_size_request(174,157)
            preview=Gtk.Image.new_from_icon_name('image-x-generic',Gtk.IconSize.DIALOG); preview.set_size_request(165,94); card.pack_start(preview,False,False,0)
            title=label(wp.title,'card-title'); title.set_ellipsize(Pango.EllipsizeMode.END); title.set_max_width_chars(22); title.set_line_wrap(False); card.pack_start(title,False,False,0)
            favorite='★  ' if wp.id in self.settings.data['favorites'] else ''
            tag=wp.kind.upper()+(' · UNAVAILABLE' if not wp.supported else '')
            card.pack_start(label(favorite+tag,'badge'),False,False,0); card.set_tooltip_text(wp.title+'\nWorkshop '+wp.id)
            child=Gtk.FlowBoxChild(); child.wallpaper=wp; child.add(card); self.flow.add(child); self.cards[wp.id]=child; self.images[wp.id]=preview
            if wp.preview:
                future=self.pool.submit(self.load_thumb,wp.preview,174,96)
                future.add_done_callback(lambda f,id=wp.id,g=generation:GLib.idle_add(self.thumb_ready,id,g,f))
        self.flow.show_all()
    @staticmethod
    def load_thumb(path,width,height):
        try:
            # Steam GIF previews can have incomplete later frames. Decode only
            # their first frame; keep library previews static and inexpensive.
            from PIL import Image,ImageOps
            with Image.open(path) as source:
                im=ImageOps.fit(source.convert('RGB'),(width,height),method=Image.Resampling.LANCZOS)
                return GdkPixbuf.Pixbuf.new_from_bytes(GLib.Bytes.new(im.tobytes()),GdkPixbuf.Colorspace.RGB,False,8,width,height,width*3)
        except Exception:
            try: return GdkPixbuf.Pixbuf.new_from_file_at_scale(str(path),width,height,True)
            except GLib.Error: return None
    def thumb_ready(self,id,generation,future):
        if future.cancelled(): return False
        pix=future.result()
        if generation==self.generation and id in self.images and pix: self.images[id].set_from_pixbuf(pix)
        return False
    def select_saved(self):
        id=self.selected.id if self.selected else self.settings.data['selected']
        child=self.cards.get(id)
        if child: self.flow.select_child(child)
        elif self.library: self.flow.select_child(next(iter(self.cards.values())))
        else:
            for c in self.inspector.get_children(): self.inspector.remove(c)
            self.inspector.pack_start(label('No wallpapers found. Choose your Workshop folder in Settings.','subtitle'),False,False,0); self.inspector.show_all()
    def card_visible(self,child):
        wp=child.wallpaper
        kind={'Videos':'video','Scenes':'scene'}.get(self.filter_kind)
        return (not kind or wp.kind==kind) and (self.filter_kind!='Favorites' or wp.id in self.settings.data['favorites']) and (not self.query or self.query in wp.title.casefold() or self.query in wp.id)
    def set_filter(self,name): self.filter_kind=name; self.flow.invalidate_filter()
    def search_changed(self,entry): self.query=entry.get_text().casefold(); self.flow.invalidate_filter()
    def selection_changed(self,flow):
        children=flow.get_selected_children()
        if not children: return
        self.flush_profile()
        self.selected=children[0].wallpaper; self.profile=self.settings.profile(self.selected.id); self.render_inspector()
    def render_inspector(self):
        self.updating=True
        for c in self.inspector.get_children(): self.inspector.remove(c)
        wp=self.selected; panel=self.inspector
        image=Gtk.Image(); pix=self.load_thumb(wp.preview,274,150) if wp.preview else None
        if pix: image.set_from_pixbuf(pix)
        panel.pack_start(image,False,False,0)
        heading=label(wp.title,'title'); heading.set_max_width_chars(21); panel.pack_start(heading,False,False,0)
        panel.pack_start(label(wp.kind.capitalize()+' · Workshop '+wp.id,'subtitle'),False,False,0)
        self.favorite_button=button('★ Favorited' if wp.id in self.settings.data['favorites'] else '☆ Add favorite',self.toggle_favorite); panel.pack_start(self.favorite_button,False,False,0)
        apply=button('Apply wallpaper',self.apply_selected,True); apply.set_sensitive(wp.supported); panel.pack_start(apply,False,False,4)
        if not wp.supported:
            msg=wp.error or ('Web wallpapers require renderer fixes and cannot be played in this version.' if wp.kind=='web' else 'This entry is a preset or an unsupported project. Select its original video or scene wallpaper.')
            panel.pack_start(label(msg,'warning'),False,False,8); panel.show_all(); self.updating=False; return
        panel.pack_start(label('PLAYBACK','section'),False,False,0)
        self.combo(panel,'Frame limit',[(15,'15 FPS · Eco'),(20,'20 FPS · Balanced'),(24,'24 FPS'),(30,'30 FPS · Smooth'),(60,'60 FPS')],self.profile['fps'],lambda v:self.change('fps',int(v),False))
        self.combo(panel,'Scaling',[('fill','Fill'),('fit','Fit'),('stretch','Stretch')],self.profile['scaling'],lambda v:self.change('scaling',v,False))
        panel.pack_start(label('Render cap and scaling take effect with Apply. Video timing stays unchanged.','subtitle'),False,False,0)
        self.switch(panel,'Mute audio',self.profile['muted'],lambda v:self.change('muted',v,wp.kind=='video'))
        self.slider(panel,'Volume',self.profile['volume'],0,100,1,lambda v:self.change('volume',v,wp.kind=='video'))
        if wp.kind=='video':
            self.slider(panel,'Playback speed',self.profile['speed'],.25,2,.05,lambda v:self.change('speed',round(v,2)),2)
            panel.pack_start(label('COLOR & FILTERS','section'),False,False,0)
            self.look_combo=self.combo(panel,'Look',[(k,k) for k in PRESETS]+[('Custom','Custom')],self.profile.get('filter','Original'),self.choose_preset)
            for key in COLOR_KEYS:
                high=1 if key=='sharpen' else 100; low=0 if key=='sharpen' else -100; step=.05 if key=='sharpen' else 1
                self.slider(panel,key.capitalize(),self.profile[key],low,high,step,lambda v,key=key:self.change(key,round(v,2)),2 if key=='sharpen' else 0)
            panel.pack_start(button('Reset video adjustments',lambda:self.choose_preset('Original')),False,False,8)
            panel.pack_start(label('Audio, speed and colors update live on the active video. Looks use color and sharpening adjustments.','subtitle'),False,False,0)
        else:
            panel.pack_start(label('SCENE PROPERTIES','section'),False,False,0)
            self.scene_properties(panel,wp)
            panel.pack_start(label('Press Apply for scene changes. Scene compatibility varies; some scripts are unsupported. Video color filters apply only to videos.','subtitle'),False,False,0)
        panel.show_all(); self.updating=False
    def combo(self,parent,title,items,current,callback):
        parent.pack_start(label(title,'subtitle'),False,False,0); w=Gtk.ComboBoxText()
        for value,text in items: w.append(str(value),text)
        w.set_active_id(str(current)); w.connect('changed',lambda w:callback(w.get_active_id()) if not self.updating and w.get_active_id()!=None else None)
        parent.pack_start(w,False,False,0); return w
    def slider(self,parent,title,current,low,high,step,callback,digits=0):
        parent.pack_start(label(title,'subtitle'),False,False,0)
        w=Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL,low,high,step); w.set_digits(digits); w.set_value(current); w.set_value_pos(Gtk.PositionType.RIGHT)
        w.connect('value-changed',lambda w:callback(w.get_value()) if not self.updating else None); parent.pack_start(w,False,False,0); return w
    def switch(self,parent,title,current,callback):
        row=box(False); row.pack_start(label(title),True,True,0); w=Gtk.Switch(); w.set_active(current)
        w.connect('notify::active',lambda w,_:callback(w.get_active()) if not self.updating else None); row.pack_end(w,False,False,0); parent.pack_start(row,False,False,0); return w
    def scene_properties(self,parent,wp):
        count=0
        for key,d in sorted(wp.properties.items(),key=lambda kv:kv[1].get('order',0) if isinstance(kv[1],dict) else 0):
            if not isinstance(d,dict) or 'value' not in d: continue
            kind=d.get('type'); value=self.profile['properties'].get(key,d['value']); title=str(d.get('text',key))
            if title.startswith('ui_') or '<' in title: title=key.replace('_',' ').capitalize()
            try:
                if kind=='slider': self.slider(parent,title,float(value),float(d.get('min',0)),float(d.get('max',100)),.1,lambda v,k=key:self.property_change(k,round(v,2)),1)
                elif kind=='bool': self.switch(parent,title,bool(value),lambda v,k=key:self.property_change(k,v))
                elif kind=='combo' and isinstance(d.get('options'),list): self.combo(parent,title,[(str(o['value']),str(o['label'])) for o in d['options'] if 'value' in o and 'label' in o],value,lambda v,k=key:self.property_change(k,v))
                elif kind=='color':
                    parts=[float(x) for x in str(value).split()]; rgba=Gdk.RGBA(red=parts[0],green=parts[1],blue=parts[2],alpha=1)
                    parent.pack_start(label(title,'subtitle'),False,False,0); w=Gtk.ColorButton.new_with_rgba(rgba); w.connect('color-set',lambda w,k=key:self.color_property(k,w.get_rgba())); parent.pack_start(w,False,False,0)
                else: continue
                count+=1
            except (ValueError,TypeError,IndexError): continue
        if not count: parent.pack_start(label('This scene exposes no editable properties.','subtitle'),False,False,0)
    def property_change(self,key,value): self.profile['properties'][key]=value; self.schedule_save(); self.message('Scene change saved. Press Apply wallpaper.')
    def color_property(self,key,c): self.property_change(key,f'{c.red:.4f} {c.green:.4f} {c.blue:.4f}')
    def change(self,key,value,live=True):
        if self.updating: return
        self.profile[key]=value
        if key in COLOR_KEYS:
            self.profile['filter']='Custom'
            self.updating=True; self.look_combo.set_active_id('Custom'); self.updating=False
        self.schedule_save()
        if live and self.control.wallpaper and self.selected.id==self.control.wallpaper.id:
            if self.live_timer: GLib.source_remove(self.live_timer)
            self.live_timer=GLib.timeout_add(100,self.send_live)
        elif not live: self.message('Change saved. Press Apply wallpaper.')
    def send_live(self):
        self.live_timer=0
        try:
            if self.control.wallpaper and self.selected and self.selected.id==self.control.wallpaper.id: self.control.apply_live(dict(self.profile))
        except (OSError,RuntimeError) as exc: self.message('Could not update playback: '+str(exc))
        return False
    def schedule_save(self):
        if self.save_timer: GLib.source_remove(self.save_timer)
        self.save_timer=GLib.timeout_add(350,self.flush_profile)
    def flush_profile(self):
        if self.save_timer: GLib.source_remove(self.save_timer); self.save_timer=0
        if self.selected and self.profile: self.settings.save_profile(self.selected.id,self.profile)
        return False
    def choose_preset(self,name):
        if self.updating: return
        for k in COLOR_KEYS: self.profile[k]=DEFAULT_PROFILE[k]
        self.profile.update(PRESETS.get(name,{})); self.profile['filter']=name; self.schedule_save(); self.send_live(); self.render_inspector()
    def toggle_favorite(self):
        favorites=self.settings.data['favorites']; id=self.selected.id
        if id in favorites: favorites.remove(id)
        else: favorites.append(id)
        self.settings.save(); self.favorite_button.set_label('★ Favorited' if id in favorites else '☆ Add favorite'); self.flow.invalidate_filter()
    def apply_selected(self):
        if not self.selected: return
        self.flush_profile()
        try:
            self.control.start(self.selected,self.profile,self.settings.data)
            self.settings.data.update(selected=self.selected.id,enabled=True,paused=False); self.settings.save(); self.user_paused=False; self.battery_paused=False
            self.message('Applying '+self.selected.title)
        except (OSError,RuntimeError,ValueError,subprocess.SubprocessError) as exc: self.message(str(exc))
        self.update_status()
    def autostart(self,attempt):
        if not self.settings.data['enabled'] or self.control.proc: return False
        wp=next((x for x in self.library if x.id==self.settings.data['selected']),None)
        if not wp or not wp.supported: self.message('Saved wallpaper is unavailable. Open the library to choose another.'); return False
        try: self.control.start(wp,self.settings.profile(wp.id),self.settings.data)
        except (OSError,ValueError,RuntimeError,subprocess.SubprocessError) as exc:
            if attempt<29: GLib.timeout_add(2000,self.autostart,attempt+1)
            else: self.message('Startup failed: '+str(exc))
        return False
    def toggle_pause(self):
        if not self.control.proc: return
        self.user_paused=not self.user_paused; self.settings.data['paused']=self.user_paused; self.settings.save()
        try: self.control.pause(self.user_paused or self.battery_paused,'Paused · battery' if self.battery_paused else 'Paused')
        except (OSError,RuntimeError) as exc: self.message(str(exc))
        self.update_status()
    def turn_off(self):
        self.control.stop(); self.settings.data['enabled']=False; self.settings.data['paused']=False; self.settings.save(); self.user_paused=False; self.status='Off'; self.update_status()
    def turn_on(self):
        self.settings.data.update(enabled=True,paused=False); self.settings.save(); self.user_paused=False; self.autostart(0)
    def toggle_power(self): self.turn_off() if self.control.proc else self.turn_on()
    def tick(self):
        self.status=self.control.tick(); self.tick_count+=1
        if self.tick_count%30==0:
            self.battery_paused=self.settings.data['pause_battery'] and any(p.read_text().strip()=='Discharging' for p in Path('/sys/class/power_supply').glob('BAT*/status'))
        if self.control.proc and self.control.ready:
            try: self.control.pause(self.user_paused or self.battery_paused,'Paused · battery' if self.battery_paused else 'Paused')
            except (OSError,RuntimeError) as exc: self.message(str(exc))
        if self.control.error and self.control.error!=self.last_error: self.last_error=self.control.error; self.message(self.last_error)
        self.update_status(); return True
    def update_status(self):
        if not self.window: return
        state=self.control.pause_reason if self.control.paused else self.status
        title=self.control.wallpaper.title if self.control.proc and self.control.wallpaper else 'No active wallpaper'
        self.status_label.set_text(f'●  {state}   ·   {title}')
        self.pause_button.set_label('Resume' if self.user_paused else 'Pause'); self.pause_button.set_sensitive(bool(self.control.proc))
        self.on_button.set_label('Turn off' if self.control.proc else 'Turn on')
    def message(self,text):
        if self.window: self.message_label.set_text(text); self.message_label.set_tooltip_text(text)
        else: self.settings.warning=text
    def open_log(self): Gio.AppInfo.launch_default_for_uri((self.control.state/'wallpaper.log').as_uri(),None)
    def open_settings(self):
        dialog=Gtk.Dialog(title='Wallpaper Studio Settings',transient_for=self.window,modal=True); dialog.add_buttons('Cancel',Gtk.ResponseType.CANCEL,'Save',Gtk.ResponseType.OK); dialog.set_default_size(520,420)
        content=dialog.get_content_area(); content.set_spacing(14); content.set_border_width(20)
        content.pack_start(label('Library folder','section'),False,False,0)
        folder=Gtk.FileChooserButton(title='Choose Workshop 431960 folder',action=Gtk.FileChooserAction.SELECT_FOLDER); folder.set_filename(self.settings.data['folder']); content.pack_start(folder,False,False,0)
        content.pack_start(label('Select the 431960 folder containing downloaded wallpaper folders. Use Refresh after Steam finishes a download.','subtitle'),False,False,0)
        screens=[]
        try:
            r=subprocess.run(['xrandr','--query'],capture_output=True,text=True,timeout=3)
            screens=[line.split()[0] for line in r.stdout.splitlines() if ' connected' in line]
        except subprocess.SubprocessError: pass
        if not screens: screens=[self.settings.data['screen']]
        screen=self.combo(content,'Display',[(s,s) for s in screens],self.settings.data['screen'],lambda _:None)
        theme=self.combo(content,'Interface theme',[(s,s) for s in ('Midnight','Ocean','Light')],self.settings.data['theme'],lambda _:None)
        battery=self.switch(content,'Pause while on battery',self.settings.data['pause_battery'],lambda _:None)
        fullscreen=self.switch(content,'Pause behind fullscreen apps',self.settings.data['pause_fullscreen'],lambda _:None)
        content.pack_start(label('20 FPS is the balanced default. Lower FPS reduces desktop rendering work; pausing suspends the renderer. No animated library previews run in the background.','subtitle'),False,False,0)
        dialog.show_all(); response=dialog.run()
        if response==Gtk.ResponseType.OK:
            folder_path=folder.get_filename()
            if folder_path:
                self.settings.data.update(folder=folder_path,screen=screen.get_active_id(),theme=theme.get_active_id(),pause_battery=battery.get_active(),pause_fullscreen=fullscreen.get_active()); self.settings.save(); self.apply_theme(); self.refresh_library(); self.message('Settings saved. Apply a wallpaper to update display/fullscreen settings.')
        dialog.destroy()

if __name__=='__main__':
    app=Studio()
    for sig in (signal.SIGTERM,signal.SIGINT): GLib.unix_signal_add(GLib.PRIORITY_DEFAULT,sig,lambda:(app.quit(),False)[1])
    sys.exit(app.run(sys.argv))
