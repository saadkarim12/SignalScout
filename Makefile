PY=.venv/bin/python
PYTHON ?= python3
setup:
	$(PYTHON) -m venv .venv
	$(PY) -m pip install -r requirements.txt
scan:
	$(PY) -m signalscout.scan
test:
	$(PY) -m pytest -q
web:
	$(PY) -m signalscout.web
bot:
	$(PY) -m signalscout.run_all
alert-preview:
	$(PY) -m signalscout.preview
backtest:
	$(PY) -m signalscout.backtest
trend-backtest:
	$(PY) -m signalscout.backtest_trend
reminders:
	$(PY) -m signalscout.reminders
slack-test:
	$(PY) -m signalscout.reminders --test
