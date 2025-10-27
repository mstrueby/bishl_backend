dev:
	uvicorn main:app --reload --host 0.0.0.0

prod:
	uvicorn main:app --host 0.0.0.0

dev:
	uvicorn main:app --host 0.0.0.0 --port 8080 --reload

backup-dev:


# Code Quality
format:
	black .
	ruff check --fix .

lint:
	ruff check .

type-check:
	mypy .

quality: format lint type-check

# Pre-commit
setup-hooks:
	pre-commit install

check-all:
	pre-commit run --all-files

	python backup_db.py

backup-prod:
	python backup_db.py --prod

restore:
	@echo "Usage: python restore_db.py --backup <backup_dir>"