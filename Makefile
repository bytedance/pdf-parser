.PHONY: lint
lint:
	uv run pre-commit run --all-files
