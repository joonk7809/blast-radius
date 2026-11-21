import json, os, shutil, subprocess, sys, time
import xml.etree.ElementTree as ET
HERE = os.path.dirname(os.path.abspath(__file__))
MUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, '..', 'mutants')
LAB = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, '..', 'labels')
BASE = '/tmp/claude-0/mut/base'
WORK = '/tmp/claude-0/mut/work'
IDS = [l.strip() for l in open('/home/user/ids.txt')]
NUM = {t: i for i, t in enumerate(IDS)}

def junit_failures(path):
    r = ET.parse(path).getroot()
    fail = set()
    bad_files = set()
    for tc in r.iter('testcase'):
        if not any((ch.tag in ('failure', 'error') for ch in tc)):
            continue
        cls, name = (tc.get('classname', ''), tc.get('name', ''))
        parts = cls.split('.')
        for k in range(len(parts), 0, -1):
            f = '/'.join(parts[:k]) + '.py'
            if os.path.exists(os.path.join(BASE, f)):
                tid = '::'.join([f] + parts[k:] + [name.split('[')[0]])
                break
        else:
            tid = None
        if tid in NUM:
            fail.add(NUM[tid])
        else:
            bad_files.add((cls, name))
    for cls, name in bad_files:
        f = (cls or name).replace('.', '/')
        f = f if f.endswith('.py') else f + '.py'
        for t, i in NUM.items():
            if t.startswith(f + '::') or t.startswith(name + '::'):
                fail.add(i)
    return (sorted(fail), sorted(map(list, bad_files)))

def run_one(patch):
    if os.path.exists(WORK):
        shutil.rmtree(WORK)
    shutil.copytree(BASE, WORK)
    r = subprocess.run(['patch', '-p1', '-s', '-d', WORK, '-i', patch], capture_output=True, text=True)
    if r.returncode:
        return {'error': 'patch failed: ' + r.stdout + r.stderr}
    t0 = time.time()
    cmd = ['docker', 'run', '--rm', '--cpus', '1', '-v', f'{WORK}:/sqlglot', 'brdev', 'python', '-m', 'pytest', '-q', '-p', 'no:cacheprovider', 'tests', '-n', '1', '--timeout=120', '--junitxml=/sqlglot/out.xml']
    p = subprocess.run(cmd, capture_output=True, text=True)
    out = {'wall': time.time() - t0, 'rc': p.returncode, 'tail': p.stdout[-600:]}
    xmlp = os.path.join(WORK, 'out.xml')
    if os.path.exists(xmlp):
        out['failing'], out['unmapped'] = junit_failures(xmlp)
    else:
        out['error'] = 'no junit'
    return out

def main():
    os.makedirs(LAB, exist_ok=True)
    pats = sorted((f for f in os.listdir(MUT) if f.endswith('.patch')))
    for f in pats:
        pr = os.path.join(LAB, 'PRIORITY.sh')
        if os.path.exists(pr):
            os.rename(pr, pr + '.running')
            subprocess.run(['bash', pr + '.running'])
            os.rename(pr + '.running', pr + '.done')
        name = f[:-6]
        dst = os.path.join(LAB, name + '.json')
        if os.path.exists(dst):
            continue
        res = run_one(os.path.join(MUT, f))
        json.dump(res, open(dst, 'w'))
        print(name, len(res.get('failing', [])), res.get('error', ''), '%.0fs' % res.get('wall', 0), flush=True)
if __name__ == '__main__':
    main()
