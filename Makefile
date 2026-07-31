.PHONY: test smoke qa qa-one auth-status auth-youtube auth-tiktok help

help:
	@echo "make test    — full unit suite, free, no API. Run per commit."
	@echo "make smoke   — generate 1 real artifact per type + QA gate."
	@echo "               COSTS MONEY (~\$$0.50, ~10 min). Run before a release."
	@echo "               make smoke TYPES=quiz,educational  for a subset."
	@echo "make qa      — run the QA gate over the whole artifact corpus."
	@echo "make qa-one  — one artifact: make qa-one F=output/audio/quiz/x.json"
	@echo ""
	@echo "make auth-status   — stored OAuth token state, local only, no network"
	@echo "make auth-youtube  — run ONLY the YouTube OAuth flow"
	@echo "make auth-tiktok   — run ONLY the TikTok OAuth flow"

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

# OAuth only. No upload, no generation, no API spend. Before this existed the
# only way to trigger OAuth was a full pipeline run with upload enabled —
# generating and paying for a video in order to authenticate.
auth-status:
	cd src && python3 -m uploader status

auth-youtube:
	cd src && python3 -m uploader auth --platform youtube

auth-tiktok:
	cd src && python3 -m uploader auth --platform tiktok

qa-one:
	@test -n "$(F)" || (echo "usage: make qa-one F=<artifact.json>" && exit 2)
	python3 src/qa_gate.py $(F)
