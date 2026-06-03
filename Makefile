.PHONY: test coverage coverage-xml

PYTEST = pytest -m "not integration"

test:
	$(PYTEST)

coverage:
	$(PYTEST) --cov --cov-report=term-missing --cov-report=html

coverage-xml:
	$(PYTEST) --cov --cov-report=xml --cov-report=term-missing
