# globals
VERSION := $(shell uvx --from=toml-cli toml get --toml-path=pyproject.toml project.version)
GH := $(shell command -v gh 2> /dev/null)

define PRINT_HELP_PYSCRIPT
import re, sys

print("Please use 'make <target>' where <target> is one of\n")
for line in sys.stdin:
	match = re.match(r'^([a-zA-Z_-]+):.*?## (.*)$$', line)
	if match:
		target, help = match.groups()
		print("%-20s %s" % (target, help))
print("\nCheck the Makefile for more information")
endef
export PRINT_HELP_PYSCRIPT

define check_gh
    @if [ -z $(GH) ]; then echo "gh could not be found. See https://cli.github.com/"; exit 2; fi
endef

.PHONY: help
.DEFAULT_GOAL := help
help:
	@python3 -c "$$PRINT_HELP_PYSCRIPT" < $(MAKEFILE_LIST)

install-uv:
	@echo "Installing uv package manager..."
	curl -LsSf https://astral.sh/uv/install.sh | sh

requirements: ## install dependencies
	@echo "Installing project dependencies..."
	uv sync --all-extras --dev

apply-style:
	@echo "Applying style..."
	uv run ruff check --select I --fix --unsafe-fixes
	uv run ruff format

style-check:
	@echo "Running checks..."
	uv run ruff check --fix

type-check:
	@echo "Running type checks..."
	uv run mypy biar

checks: style-check type-check  ## run all code checks

test:
	@echo "Running tests..."
	uv run pytest tests/

.PHONY: version
version: ## package version
	@echo '${VERSION}'

build:
	@echo "Building package..."
	uv build
