IMAGE=$1
SAMPLE=$2
OUT=${3:-output.jsonl}
docker run --rm --platform linux/amd64 --network none --cpus 2 --memory 4096m --memory-swap 4096m --pids-limit 256 --read-only \
  --tmpfs /tmp:rw,size=64m,mode=1777 --cap-drop ALL --security-opt no-new-privileges --user 65534:65534 --env HOME=/tmp \
  --volume "$SAMPLE/commits:/data/commits:ro" --volume "$SAMPLE/tests.json:/data/tests.json:ro" \
  $(env | grep "^BR_" | sed "s/^/--env /") "$IMAGE" python -c "import subprocess,resource,sys;subprocess.run([sys.executable,'/app/selector.py']);r=resource.getrusage(resource.RUSAGE_CHILDREN);print('CPU',r.ru_utime+r.ru_stime,file=sys.stderr)" > "$OUT" 2> "$OUT.stderr"
CPU=$(grep '^CPU ' "$OUT.stderr" | awk '{print $2}')
python3 tools/score.py "$SAMPLE" "$SAMPLE/answers.json" "$OUT" "$CPU"
