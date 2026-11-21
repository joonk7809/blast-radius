#!/bin/bash
# Pristine fingerprint map, built in the scorer-like image so bytecode matches.
docker run --rm --cpus 1 -v /tmp/claude-0/mut/base:/sqlglot:ro -v /home/user/work/importtime:/it brdev \
  python -I /it/importtime.py --snapshot /sqlglot /it/maps/fp.json.gz > /tmp/claude-0/snap_docker.log 2>&1
