#!/bin/bash
# Rebuild all import-time maps from the pristine tree. Docker steps use one core (--cpus 1).
#   BASE = clean copy of the pinned sqlglot checkout (no .git); never point this at /home/user/sqlglot
#   COV  = the lead's coverage map (per-line test sets), used for function bodies / module globals
set -e
HERE=$(cd "$(dirname "$0")/.." && pwd)
BASE=${BASE:-/tmp/claude-0/mut/base}
COV=${COV:-/home/user/blast-radius/maps/covmap.json.gz}
TR=${TR:-/tmp/claude-0/tr_full}
mkdir -p "$TR" "$HERE/maps"
# 1. pristine fingerprints (in the scorer-like image so bytecode of lambdas matches)
docker run --rm --cpus 1 -v "$BASE":/sqlglot:ro -v "$HERE":/it brdev python -I /it/importtime.py --snapshot /sqlglot /it/maps/fp.json.gz
# 2. per-test attribute/key read trace of the full suite (~4 min on one core)
rm -rf /tmp/claude-0/mut/trace && cp -r "$BASE" /tmp/claude-0/mut/trace
docker run --rm --cpus 1 -v /tmp/claude-0/mut/trace:/sqlglot -v "$HERE":/it:ro -v /home/user/ids.txt:/ids.txt:ro -v "$TR":/out \
  -e IT_DIR=/it -e IDS=/ids.txt -e TRACE_OUT=/out -e PYTHONPATH=/sqlglot:/it/build \
  brdev python -m pytest -q -p no:cacheprovider -p no:xdist -p attrtrace tests --timeout=1200
# 3. inverted read map (+ name-based coverage search for module globals)
python3 "$HERE/build/build_readmap.py" "$TR/reads.json.gz" "$HERE/maps/fp.json.gz" "$COV" "$BASE" "$HERE/maps/readmap.json.gz"
# 4. static index of import-time statements
python3 "$HERE/build/build_spans.py" "$BASE" "$HERE/maps/fp.json.gz" "$HERE/maps/spans.json.gz"
# 5. function-body lines executed during import, and table lookups made by modules that parse at import
PYTHONDONTWRITEBYTECODE=1 python3 -I "$HERE/build/build_importexec.py" "$BASE" "$HERE/maps/importexec.json.gz"
PYTHONDONTWRITEBYTECODE=1 python3 -I "$HERE/build/build_importreaders.py" "$BASE" "$HERE/maps/importexec.json.gz" "$HERE/maps/importreaders.json.gz"
