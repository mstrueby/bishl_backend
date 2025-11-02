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

# Testing
test:
	pytest tests/ -v

test-unit:
	pytest tests/unit/ -v

test-integration:
	pytest tests/integration/ -v

test-cov:
	pytest tests/ -v --cov=. --cov-report=html --cov-report=term

clean-test-db:
	python -c "from motor.motor_asyncio import AsyncIOMotorClient; import asyncio; from tests.test_config import TestSettings; settings = TestSettings(); async def clean(): client = AsyncIOMotorClient(settings.DB_URL); db = client[settings.DB_NAME]; collections = await db.list_collection_names(); [await db[col].drop() for col in collections]; print(f'Dropped {len(collections)} collections from {settings.DB_NAME}'); client.close(); asyncio.run(clean())"

test-e2e:
	pytest tests/e2e/ -v

test-watch:
	pytest-watch

	python backup_db.py

backup-prod:
	python backup_db.py --prod

restore:
	@echo "Usage: python restore_db.py --backup <backup_dir>"