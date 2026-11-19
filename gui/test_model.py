import tempfile,unittest,json,socket,threading
from pathlib import Path
from model import Settings,scan_library,inside
from controller import Controller
class Tests(unittest.TestCase):
 def test_library_types_and_safe_paths(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d); wp=root/'123'; wp.mkdir(); (root/'secret.mp4').touch()
   (wp/'project.json').write_text(json.dumps({'type':'Video','title':'Ocean','file':'../secret.mp4'}))
   result=scan_library(root); self.assertEqual(result[0].kind,'video'); self.assertFalse(result[0].supported)
   (wp/'video.mp4').touch(); (wp/'project.json').write_text(json.dumps({'type':'video','file':'video.mp4'}))
   self.assertTrue(scan_library(root)[0].supported)
 def test_settings_roundtrip_and_limits(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'gui.json'; s=Settings(path); p=s.profile('123'); p.update(fps=500,volume=-2,saturation=400)
   s.save_profile('123',p); p=Settings(path).profile('123'); self.assertEqual((p['fps'],p['volume'],p['saturation']),(60,0,100))
 def test_migration_does_not_execute_shell(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d); (root/'settings.conf').write_text('SCREEN=eDP-1\nWORKSHOP="$HOME/test folder"\nWALLPAPER=123\nFPS=30\n')
   s=Settings(root/'gui.json'); self.assertEqual(s.data['selected'],'123'); self.assertTrue(s.data['folder'].endswith('/test folder')); self.assertEqual(s.profile('123')['fps'],20)
 def test_ipc_closed_connection_fails(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d); c=Controller(root,root/'state',root/'runtime'); sock=socket.socket(socket.AF_UNIX); sock.bind(str(c.socket_path)); sock.listen()
   def server():
    conn,_=sock.accept(); conn.recv(4096); conn.close()
   t=threading.Thread(target=server); t.start()
   with self.assertRaises(RuntimeError): c.ipc(['get_property','volume'])
   t.join(); sock.close()
if __name__=='__main__': unittest.main()
