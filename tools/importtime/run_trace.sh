#!/bin/bash
# Full-suite attribute-read trace in docker brdev (single core). Output: /tmp/claude-0/tr_full/reads.json.gz
set -x
rm -rf /tmp/claude-0/mut/trace; cp -r /tmp/claude-0/mut/base /tmp/claude-0/mut/trace
time docker run --rm --cpus 1 -v /tmp/claude-0/mut/trace:/sqlglot -v /home/user/work/importtime:/it:ro \
  -v /home/user/ids.txt:/ids.txt:ro -v /tmp/claude-0/tr_full:/out \
  -e IT_DIR=/it -e IDS=/ids.txt -e TRACE_OUT=/out -e PYTHONPATH=/sqlglot:/it/build \
  brdev python -m pytest -q -p no:cacheprovider -p no:xdist -p attrtrace tests --timeout=1200 > /tmp/claude-0/tr_full/log.txt 2>&1
