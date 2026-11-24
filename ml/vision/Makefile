ROOT := ../..
PYTHON ?= $(ROOT)/.venv/bin/python
WEB := ./scripts/web.sh
.PHONY: test test-ui verify-assets fetch-gesture fetch-lux gesture lux physical verify-physical

test: verify-assets
	cd $(ROOT) && $(WEB) exec node --test ../../tests/test_sensors.mjs
	$(PYTHON) lux_eval.py

verify-assets:
	cd $(ROOT)/apps/web/public/vision && shasum -a 256 -c SHA256SUMS

fetch-gesture:
	$(PYTHON) fetch_data.py gesture

fetch-lux:
	$(PYTHON) fetch_data.py lux

gesture: fetch-gesture verify-assets
	cd legacy/assets && shasum -a 256 -c SHA256SUMS
	cd $(ROOT) && $(WEB) exec node ../../ml/vision/browser_eval.mjs

test-ui:
	cd $(ROOT) && $(WEB) exec node ../../tests/test_sensors_camera.mjs $(if $(filter webkit,$(BROWSER)),--webkit)

lux:
	$(PYTHON) lux_eval.py

physical:
	$(PYTHON) physical.py --sid "$(SID)" --phase "$(PHASE)" $(if $(filter 1,$(GUIDE)),--guide)

verify-physical:
	$(PYTHON) physical.py --sid "$(SID)" --phase verify
