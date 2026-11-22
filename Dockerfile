FROM python:3.13-slim@sha256:e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90
COPY requirements.lock /tmp/requirements.lock
RUN pip install --no-cache-dir -r /tmp/requirements.lock && python -m compileall -q -j 0 /usr/local/lib/python3.13 >/dev/null
RUN python -c "import io,tarfile,urllib.request;tarfile.open(fileobj=io.BytesIO(urllib.request.urlopen('https://github.com/tobymao/sqlglot/archive/eb11aec4be8cb2122afe713a4816662c3f0fb2fa.tar.gz').read())).extractall('/opt')" \
 && mv /opt/sqlglot-eb11aec4be8cb2122afe713a4816662c3f0fb2fa /sqlglot \
 && cd /sqlglot && python -m compileall -q sqlglot tests >/dev/null \
 && chmod -R a+rX /sqlglot
COPY src /app
RUN python -c "import gzip,lzma,shutil;shutil.copyfileobj(lzma.open('/app/covsets.bin.xz'),open('/app/covsets.bin','wb'));shutil.copyfileobj(gzip.open('/app/covmeta.json.gz'),open('/app/covmeta.json','wb'))" \
 && rm /app/covsets.bin.xz /app/covmeta.json.gz \
 && cd /app && python -c "import json,selector;selector.build_setup_cache('/app/setupidx.pkl',sorted({t.split('::')[0] for t in json.load(open('/app/covmeta.json'))['tests']}))" \
 && mkdir /app/tpc && (python /app/ckbuild.py /sqlglot /app/tpc/ck & python -c "import selector;selector.build_tpc_cache('/app/tpc')" && python /app/memo.py /sqlglot /app/tpc/memo.pkl && python /app/memo.py state /sqlglot /app/tpc/memo.pkl /app/tpc/state.pkl; s=$?; wait $! && exit $s) \
 && python -c "import glob,gzip,shutil;[shutil.copyfileobj(gzip.open(f),open(f[:-3],'wb')) for f in glob.glob('/app/itmaps/*.json.gz')]" \
 && python -c "import glob,json,marshal;[open(f + '.m','wb').write(marshal.dumps(json.load(open(f)))) for f in glob.glob('/app/itmaps/*.json') + ['/app/covmeta.json']]" \
 && python -m compileall -q /app >/dev/null \
 && chmod -R a+rX /app
ENV SKIP_INTEGRATION=0 PYTHONDONTWRITEBYTECODE=1
CMD ["python", "/app/run.py"]
