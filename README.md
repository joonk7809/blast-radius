# blast-radius

Entry for the RWX Blast Radius track. For each sqlglot patch in `/data/commits`, `src/selector.py` picks candidate tests from a per-test coverage map built at the pinned sqlglot commit, runs those candidates against the patched tree in forked children of a warmed process, and prints only the tests that fail, split across workers.

## How it works

- `src/covsets.bin.xz`, `src/covmeta.json.gz`: line to sub-test coverage of the pinned sqlglot test suite, recorded with coverage.py. The Docker build decompresses them into `/app`.
- `src/selector.py`: reads each patch, maps changed lines to candidate tests (AST no-op detection, statement expansion, import-time fallback, fixtures), runs the candidates, and writes one JSON line per commit.
- `src/zygote.py`: warms sqlglot once; a child either swaps changed function code objects in place or reimports sqlglot from a patched overlay.
- `src/split.py`: splits the selected tests across up to 8 workers.
- `tools/`: offline scripts that build the maps and score a local run (`tools/measure.sh`).

## Third-party code and libraries

- [sqlglot](https://github.com/tobymao/sqlglot) (MIT): the project under test, downloaded at commit eb11aec4be8cb2122afe713a4816662c3f0fb2fa during the build. Its test suite is run at runtime.
- The Python packages pinned in `requirements.lock` from the starter kit (duckdb, numpy, pandas and others), which the sqlglot tests need.
- [coverage.py](https://github.com/nedbat/coveragepy) (Apache-2.0): used offline by `tools/` to record the coverage maps. Not part of the runtime image.
- Python standard library.

No other prior code is used.
