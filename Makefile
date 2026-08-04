.PHONY: backend-test backend-lint compose-config demo

backend-test:
	cd backend && pytest ../tests/backend

backend-lint:
	cd backend && ruff check app ../tests/backend && mypy app

compose-config:
	docker compose config

demo:
	docker compose exec -T backend python -m app.scripts.bootstrap_demo
