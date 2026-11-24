PY := .venv/bin/python
UV ?= $(shell command -v uv 2>/dev/null || echo $(HOME)/.local/bin/uv)
PYTHON ?= 3.11
.PHONY: bootstrap web doctor demo test-contract test-vision-live verify-iphone-run contract test-m1
bootstrap:
	"$(UV)" sync --cache-dir .cache/uv --frozen --python "$(PYTHON)"
	./scripts/web.sh install --frozen-lockfile --store-dir ../../.cache/pnpm
	$(MAKE) web
web:
	./scripts/web.sh run build
doctor:
	$(PY) scripts/check.py doctor
contract:
	$(PY) scripts/check.py contract
	./scripts/web.sh exec openapi-typescript ../../packages/contracts/openapi.json -o ../../packages/contracts/types.ts
test-contract:
	$(PY) -m pytest -q tests
test-m1: web test-contract
test-vision-live:
	$(PY) scripts/check.py live $(if $(PHOTO),--photo "$(PHOTO)")
verify-iphone-run:
	$(PY) scripts/verify_phone.py $(if $(SESSION),--session "$(SESSION)")
demo:
	$(PY) scripts/desktop.py

demo-legacy:
	$(PY) scripts/serve.py
.PHONY: demo-public
demo-public:
	$(PY) scripts/serve.py --public
.PHONY: test-browser
test-browser: web
	./scripts/web.sh exec playwright test
.PHONY: stop
stop:
	$(PY) scripts/stop.py
.PHONY: phone-room
phone-room:
	./scripts/web.sh exec node scripts/host-room.mjs

.PHONY: evaluate-ml verify-models test-sensors test-ui test-grading eval-vision test-learning-loop test-realtime test-e2e test-phone-ui test-accessibility test-all verify-online-demo verify-release package verify-submission vision-labels evidence record-replay rehearsal-start rehearsal-finish verify-lan-latency verify-sensor-trials clean-reproduce
evaluate-ml:
	$(MAKE) -f ml/dkt/Makefile evaluate
verify-models:
	$(MAKE) -f ml/dkt/Makefile check-cuda
test-grading:
	$(PY) -m pytest -q tests/test_m1.py
test-learning-loop:
	$(PY) -m pytest -q tests/test_learning.py
test-sensors:
	$(PY) -m pytest -q tests/test_sensors.py
	$(MAKE) -C ml/vision test
test-realtime:
	$(PY) -m pytest -q tests/test_public_phone.py tests/test_sensors.py
test-ui: web
	./scripts/web.sh exec playwright test e2e/notebook.spec.ts
test-phone-ui: web
	./scripts/web.sh exec playwright test -g 'camera|mobile|无 WebGL|fallback|窄屏|模拟'
test-accessibility: web
	./scripts/web.sh exec playwright test e2e/accessibility.spec.ts
test-e2e: test-browser
eval-vision:
	$(PY) scripts/vision_eval.py evaluate $(if $(LABELS),--labels "$(LABELS)")
vision-labels:
	$(PY) scripts/vision_eval.py labels
evidence:
	$(PY) scripts/evidence.py
test-all: doctor verify-models test-contract test-clouclip federated-check test-e2e
record-replay: web
	$(PY) scripts/record_replay.py $(if $(PHOTO),"$(PHOTO)")
rehearsal-start:
	$(PY) scripts/rehearsal.py start $(if $(SESSION),--session "$(SESSION)")
rehearsal-finish:
	$(PY) scripts/rehearsal.py finish $(if $(VIDEO),--video "$(VIDEO)")
verify-online-demo:
	$(PY) scripts/verify_desktop.py
verify-lan-latency:
	$(PY) scripts/rehearsal.py latency $(if $(SESSION),--session "$(SESSION)")
verify-sensor-trials:
	$(MAKE) -C ml/vision verify-physical SID="$(SESSION)"
.PHONY: field-capture verify-field-capture field-eyecare verify-field-eyecare
field-capture:
	$(PY) ml/vision/physical.py --sid "$(SESSION)" --phase capture --guide
verify-field-capture:
	$(PY) ml/vision/physical.py --sid "$(SESSION)" --phase verify-capture
field-eyecare:
	$(PY) ml/vision/physical.py --sid "$(SESSION)" --phase eyecare --guide
verify-field-eyecare:
	$(PY) ml/vision/physical.py --sid "$(SESSION)" --phase verify-eye

# Export the committed public sources, including the repository's license.
package:
	git cat-file -e HEAD:LICENSE
	mkdir -p release
	@archive=$$(mktemp release/.LumiRead-source.XXXXXX) && \
		trap 'rm -f "$$archive"' EXIT && \
		git archive --format=zip --prefix=LumiRead/ --output="$$archive" HEAD && \
		mv "$$archive" release/LumiRead-source.zip
	@echo "Created release/LumiRead-source.zip"

# The local course submission uses the full evidence set and LumiRead_MVP.zip.
.PHONY: course-package
course-package:
	$(PY) scripts/release.py pack
verify-release: verify-models federated-check
	$(PY) scripts/verify_desktop.py
	$(PY) scripts/release.py check
clean-reproduce:
	$(PY) scripts/release.py reproduce
verify-submission: verify-release clean-reproduce
	$(PY) scripts/release.py verify

.PHONY: demo-legacy demo-accounts federated-train federated-evaluate federated-check test-accounts test-clouclip evaluate-desktop-vision rehearse-desktop
demo-accounts federated-train federated-evaluate federated-check:
	$(MAKE) -f ml/dkt/Makefile $@
test-accounts:
	$(PY) -m pytest -q tests/test_demo_accounts.py
test-clouclip:
	$(PY) -m pytest -q tests/test_clouclip*.py
evaluate-desktop-vision:
	$(PY) scripts/desktop_eval.py
rehearse-desktop:
	$(PY) scripts/desktop_rehearsal.py

.PHONY: benchmark-alerts
benchmark-alerts:
	./scripts/web.sh exec node scripts/alert-benchmark.mjs
	$(PY) scripts/latency_report.py
