import json, os, sys, time
sys.path.insert(0, "/app")
import selector as S
tests = json.load(open("/data/tests.json"))["tests"]
ids = [t["id"] for t in tests]
S.preimport()
job = S.Job("profile", S.SRC, ids, {i: 600.0 for i in ids}, time.monotonic() + 3600)
import select
while not job.done:
    r, _, _ = select.select([job.fd], [], [], 1.0)
    if r:
        job.feed()
print(json.dumps({"tcpu": job.tcpu, "status": job.status, "cpu": job.cpu}))
