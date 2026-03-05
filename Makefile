.PHONY: export
export:
	uv export --no-hashes --no-dev -o requirements.txt

.PHONY: lint
lint:
	uv run pre-commit run --all-files
