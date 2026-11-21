# Blast Radius working notes (shared between agents)

Track rules (from SCORING.md / README of the starter kit):
- Input: /data/commits/<id>.patch (unified diff vs sqlglot @ eb11aec4be8cb2122afe713a4816662c3f0fb2fa), /data/tests.json
  {"tests":[{"number","id","file","seconds"}], "skipped":[ids]}. 1620 numbered tests (pytest collection order).
- Output: one JSON line per commit {"commit": id, "workers": [[nums],[nums]]}. <=8 workers.
- Cost per commit: max worker load (recorded seconds, ms-rounded) + 2s per non-empty worker; 0 if no workers.
  +300s if any failing test not selected. Plus total CPU seconds of the container (all processes). Middle of 3 runs.
- Run limits: no network, 2 cores, 4 GB, 3 min whole batch (practice ~40 commits; final ~60 commits / 4.5 min),
  read-only FS, 64 MB /tmp, user nobody, <=256 procs.
- "Fails" = pytest failure/error/timeout or file import error. Labels made with SKIP_INTEGRATION=0 on
  python:3.13-slim@sha256:e48f59cd... with requirements.lock. Final includes kinds of change not seen in practice.
- Allowed: running sqlglot tests at runtime (CPU charged), maps built from pinned commit. Forbidden: patch->answer tables.

Local setup:
- /home/user/sqlglot = pristine checkout at the pinned commit. DO NOT MODIFY. Copy it if you need to mutate.
- docker image `brdev` = scorer base image + requirements.lock + coverage; ENV PYTHONPATH=/sqlglot SKIP_INTEGRATION=0, WORKDIR /sqlglot.
  Mount a sqlglot tree at /sqlglot. dockerd is already running.
- /home/user/ids.txt = 1620 test ids in number order.
- sample/: 30 sample commits + answers.json (failing test numbers + kind: code/fixture/comment/multi).
- maps/covmap.json.gz: coverage map (shared-session coverage, per-test contexts). tools/cand.py = naive candidate finder.

Known findings:
- Recorded test seconds total 103s; heavy: 1490 test_max_nodes 28.8s, 1106 test_execute_tpcds 21.5s,
  1224 test_generator_memory 6.7s, 1107 tpch 3.9s, 1123 optimized_tpch 3.5s.
- Naive line coverage misses: multi-line statements (coverage records statement start line), import-time lines
  (class attrs / dict tables / constants), and cached computations (a test can depend on a line only another test executed).
