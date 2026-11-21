import gzip
import json
import os
import sys
root, out_p = sys.argv[1:3]
root = os.path.abspath(root)
sys.path.insert(0, root)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import importtime as IT
names = IT.module_names(root)
pref = os.path.join(root, 'sqlglot') + os.sep
hits = {}

def owner_module(frame):
    f = frame
    while f is not None:
        co = f.f_code
        if co.co_name == '<module>' and co.co_filename.startswith(pref):
            return f.f_globals.get('__name__')
        f = f.f_back
    return None

def tracer(frame, event, arg):
    if event != 'call':
        return None
    co = frame.f_code
    if not co.co_filename.startswith(pref) or not co.co_flags & 1:
        return None
    mod = owner_module(frame)
    if mod is None:
        return None
    fn = co.co_filename

    def local(fr, ev, a):
        if ev == 'line':
            hits.setdefault((fn, fr.f_lineno), set()).add(mod)
        return local
    hits.setdefault((fn, co.co_firstlineno), set()).add(mod)
    return local
sys.settrace(tracer)
IT.import_all(names)
sys.settrace(None)
files = {}
for (fn, ln), mods in hits.items():
    rel = os.path.relpath(fn, root)
    files.setdefault(rel, {})[str(ln)] = sorted(mods)
with gzip.open(out_p, 'wt') as f:
    json.dump({'files': files}, f, separators=(',', ':'))
print('files', len(files), 'lines', len(hits), file=sys.stderr)
