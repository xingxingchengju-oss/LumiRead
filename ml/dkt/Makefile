# Invoke from the repository root with make -f ml/dkt/Makefile TARGET.
PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)
TRAIN_PYTHON ?= .cache/dkt/venv/bin/python
DEVICE ?= cpu
OUT ?= artifacts/dkt
export MPLCONFIGDIR := $(CURDIR)/.cache/dkt/matplotlib

.PHONY: setup prepare train evaluate check check-cuda

setup:
	$(PYTHON) -m venv .cache/dkt/venv
	$(TRAIN_PYTHON) -m pip install -r ml/dkt/requirements.txt -c ml/dkt/cpu-reference.txt

prepare:
	$(PYTHON) -m ml.dkt.prepare

train: prepare
	$(TRAIN_PYTHON) -m ml.dkt.train --device "$(DEVICE)" --out "$(OUT)"

evaluate: prepare
	$(TRAIN_PYTHON) -m ml.dkt.evaluate --out "$(OUT)" --check-serving

check:
	$(PYTHON) -m ml.dkt.verify --out "$(OUT)"

check-cuda:
	$(PYTHON) -m ml.dkt.verify --out "$(OUT)" --require-cuda

FED_OUT ?= artifacts/federated
ARCHIVE ?= .cache/dkt/assistments2009.zip
.PHONY: demo-accounts check-demo-accounts federated-train federated-evaluate federated-check

demo-accounts:
	$(PYTHON) -m ml.dkt.demo_accounts --archive "$(ARCHIVE)"

check-demo-accounts:
	$(PYTHON) -m ml.dkt.demo_accounts --archive "$(ARCHIVE)" --check

federated-train: prepare
	$(TRAIN_PYTHON) -m ml.dkt.federated --out "$(FED_OUT)"

federated-evaluate: prepare
	$(TRAIN_PYTHON) -m ml.dkt.fed_evaluate --out "$(FED_OUT)"

federated-check:
	$(PYTHON) -m ml.dkt.fed_verify --out "$(FED_OUT)"
