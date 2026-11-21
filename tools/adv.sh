S=$1
IMAGE=${2:-blast-radius-entry}
docker run --rm --platform linux/amd64 --network none --cpus 2 --memory 4096m --memory-swap 4096m --pids-limit 256 --read-only --tmpfs /tmp:rw,size=64m,mode=1777 --cap-drop ALL --security-opt no-new-privileges --user 65534:65534 --env HOME=/tmp --volume "$S/commits:/data/commits:ro" --volume "$S/tests.json:/data/tests.json:ro" "$IMAGE" python -c "import subprocess,resource,sys,time;t=time.time();subprocess.run([sys.executable,'/app/selector.py']);r=resource.getrusage(resource.RUSAGE_CHILDREN);print('CPU',r.ru_utime+r.ru_stime,'WALL',time.time()-t,file=sys.stderr)" > $S/out.jsonl 2> $S/out.stderr
python3 tools/advscore.py $S
