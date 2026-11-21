import json, os, shutil, subprocess, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
BASE = '/tmp/claude-0/mut/base'
WORK = '/tmp/claude-0/mut/vwork'
IDS = [l.strip() for l in open('/home/user/ids.txt')]
cand = json.load(open(sys.argv[1]))
outp = sys.argv[2]
res = json.load(open(outp)) if os.path.exists(outp) else {}
for name, c in sorted(cand.items()):
    if name in res:
        continue
    part = {IDS[int(t)]: v for t, v in c['units'].items() if v is not None}
    if not part:
        continue
    if os.path.exists(WORK):
        shutil.rmtree(WORK)
    shutil.copytree(BASE, WORK, symlinks=True)
    r = subprocess.CompletedProcess([], 0, '', '') if not os.path.getsize(c['patch']) else subprocess.run(['patch', '-p1', '-s', '-i', os.path.abspath(c['patch'])], cwd=WORK, capture_output=True, text=True)
    if r.returncode:
        res[name] = {'error': r.stdout + r.stderr}
        continue
    io = os.path.join(WORK, '_io')
    os.makedirs(io)
    json.dump({t: None for t in part}, open(os.path.join(io, 'whole.json'), 'w'))
    json.dump(part, open(os.path.join(io, 'part.json'), 'w'))
    shutil.copy(os.path.join(HERE, 'unitrun.py'), io)
    t0 = time.time()
    cmd = ['docker', 'run', '--rm', '--cpus', '1', '-v', f'{WORK}:/sqlglot', '-w', '/sqlglot', 'brdev', 'sh', '-c', 'python _io/unitrun.py _io/whole.json _io/whole.out; python _io/unitrun.py _io/part.json _io/part.out']
    subprocess.run(cmd, capture_output=True, timeout=3600)
    try:
        w = json.load(open(os.path.join(io, 'whole.out')))
        p = json.load(open(os.path.join(io, 'part.out')))
    except Exception as e:
        res[name] = {'error': repr(e)}
        continue
    miss = [t for t in part if w.get(t) and (not p.get(t))]
    res[name] = {'whole_fail': [t for t in part if w.get(t)], 'part_fail': [t for t in part if p.get(t)], 'miss': miss, 'n': len(part), 'wall': time.time() - t0}
    print(name, 'tests', len(part), 'whole_fail', len(res[name]['whole_fail']), 'MISS' if miss else '', miss, flush=True)
    json.dump(res, open(outp, 'w'), indent=0)
json.dump(res, open(outp, 'w'), indent=0)
