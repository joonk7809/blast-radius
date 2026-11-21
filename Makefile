IMAGE ?= blast-radius-entry
SAMPLE ?= $(CURDIR)/sample
OUTPUT ?= $(CURDIR)/output.jsonl
RUN_FLAGS := --rm --platform linux/amd64 --network none --cpus 2 \
	--memory 4096m --memory-swap 4096m --pids-limit 256 --read-only \
	--tmpfs /tmp:rw,size=64m,mode=1777 --cap-drop ALL \
	--security-opt no-new-privileges --user 65534:65534 --env HOME=/tmp \
	--volume $(SAMPLE)/commits:/data/commits:ro \
	--volume $(SAMPLE)/tests.json:/data/tests.json:ro

build-local:
	sed 's|^COPY requirements.lock /tmp/requirements.lock|COPY requirements.lock /tmp/requirements.lock\nCOPY ca.crt /tmp/ca.crt\nENV PIP_CERT=/tmp/ca.crt SSL_CERT_FILE=/tmp/ca.crt|' Dockerfile > Dockerfile.local
	cp /root/.ccr/ca-bundle.crt ca.crt
	docker build -q -f Dockerfile.local --tag $(IMAGE) .

sample:
	docker run --name br-run $(RUN_FLAGS) $(IMAGE) > $(OUTPUT)
	python3 tools/score.py $(SAMPLE) $(SAMPLE)/answers.json $(OUTPUT)
