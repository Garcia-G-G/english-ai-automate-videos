.PHONY: test smoke qa qa-one help

help:
	@echo "make test    — full unit suite, free, no API. Run per commit."
	@echo "make smoke   — generate 1 real artifact per type + QA gate."
	@echo "               COSTS MONEY (~\$$0.50, ~10 min). Run before a release."
	@echo "               make smoke TYPES=quiz,educational  for a subset."
	@echo "make qa      — run the QA gate over the whole artifact corpus."
	@echo "make qa-one  — one artifact: make qa-one F=output/audio/quiz/x.json"

test:
	python3 -m pytest tests/ -q

# Generates real audio through the real provider routing. This is the check
# that catches a broken generator, which no free test can: a NameError took
# live educational generation down for two commits while the whole suite
# passed. With BLOCKING on, a broken generator rejects everything for the
# wrong reason, so this matters more, not less.
TYPES ?= quiz,true_false,fill_blank,vocabulary,educational,pronunciation
smoke:
	python3 tests/smoke_generate.py --types $(TYPES)

qa:
	python3 src/qa_gate.py

qa-one:
	@test -n "$(F)" || (echo "usage: make qa-one F=<artifact.json>" && exit 2)
	python3 src/qa_gate.py $(F)
