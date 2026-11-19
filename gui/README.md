# Frontend source

- `app.py`: GTK 3 library, inspector, settings, tray, single-instance command handling.
- `model.py`: safe Workshop manifest parsing, per-wallpaper settings and migration.
- `controller.py`: renderer ownership, private MPV IPC, pause/resume, shutdown and bounded logs.
- `style.css`: Midnight styling, with Ocean/Light variants applied by the app.
- `mpv-ipc.patch`: minimal renderer change enabling an optional IPC endpoint.
- `build-renderer.py`: compiles the changed adapter and relinks with existing objects, without modifying the original source/build.
- `test_model.py`: tests malformed/missing media handling, path containment, preference persistence, migration and disconnected IPC handling.

Run the focused tests from the deliverable directory:

```bash
python3 -m unittest discover -s gui -p test_model.py -v
```

These tests require local Unix-domain socket access. The application additionally needs a live Cinnamon/X11 session, Python GTK bindings and Pillow. See the parent README for installation and runtime behavior.
