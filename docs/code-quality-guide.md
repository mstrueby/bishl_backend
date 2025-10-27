
# Code Quality Guide

## Overview

This project uses several code quality tools to maintain consistent, bug-free code:

- **Black**: Code formatter
- **Ruff**: Fast Python linter
- **Mypy**: Static type checker
- **Pre-commit**: Git hook framework

## Setup

### Initial Setup

1. Install pre-commit hooks:
   ```bash
   make setup-hooks
   ```

2. Run all checks manually:
   ```bash
   make check-all
   ```

## Usage

### Before Committing

Pre-commit hooks will automatically run when you commit. They will:
- Format code with Black
- Lint and fix issues with Ruff
- Check types with Mypy (on core files only)
- Verify file integrity

### Manual Commands

#### Format Code
```bash
make format
```
Runs Black and Ruff with auto-fix.

#### Lint Only
```bash
make lint
```
Runs Ruff without auto-fixing.

#### Type Check
```bash
make type-check
```
Runs Mypy on the codebase.

#### Run All Quality Checks
```bash
make quality
```
Runs format, lint, and type-check in sequence.

#### Check All Files (Pre-commit)
```bash
make check-all
```
Runs all pre-commit hooks on all files.

## Configuration

### Black
- **Line length**: 100 characters
- **Target version**: Python 3.12
- **Config**: `[tool.black]` in `pyproject.toml`

### Ruff
- **Line length**: 100 characters
- **Selected rules**: 
  - E/W: pycodestyle errors/warnings
  - F: pyflakes
  - I: isort (import sorting)
  - B: bugbear
  - C4: comprehensions
  - UP: pyupgrade
- **Config**: `[tool.ruff]` in `pyproject.toml`

### Mypy
- **Python version**: 3.12
- **Mode**: Moderate strictness (allowing gradual typing)
- **Excluded modules**: Third-party packages without type stubs
- **Config**: `[tool.mypy]` in `pyproject.toml`

### Pre-commit
- **Config file**: `.pre-commit-config.yaml`
- **Excluded from type checking**: Import scripts, validation scripts, utilities

## Skipping Hooks (Emergency Only)

If you absolutely need to skip pre-commit hooks:
```bash
git commit --no-verify
```

**Warning**: Only use this in emergencies. Always fix issues properly.

## IDE Integration

### VS Code
Install these extensions:
- Python (Microsoft)
- Black Formatter
- Ruff
- Mypy Type Checker

Add to `.vscode/settings.json`:
```json
{
  "python.formatting.provider": "black",
  "python.linting.ruffEnabled": true,
  "python.linting.mypyEnabled": true,
  "editor.formatOnSave": true
}
```

### PyCharm
1. Install Black plugin
2. Enable Ruff in Settings → Tools → External Tools
3. Enable Mypy in Settings → Languages & Frameworks → Python → Mypy

## Troubleshooting

### Pre-commit Hook Fails
```bash
# Update hooks
pre-commit autoupdate

# Clear cache
pre-commit clean

# Reinstall
pre-commit uninstall
pre-commit install
```

### Mypy Errors on Third-party Packages
Already configured to ignore missing imports for common packages. If you need to add more:

Edit `pyproject.toml`:
```toml
[[tool.mypy.overrides]]
module = ["new_package.*"]
ignore_missing_imports = true
```

### Ruff Auto-fix Changes Too Much
Review changes before committing:
```bash
git diff
```

If needed, adjust rules in `pyproject.toml` under `[tool.ruff.lint]`.

## Best Practices

1. **Run quality checks before pushing**
   ```bash
   make quality
   ```

2. **Fix issues incrementally** - Don't disable checks, fix the code

3. **Use type hints** where possible for better mypy coverage

4. **Keep imports sorted** - Ruff handles this automatically

5. **Follow PEP 8** - Black and Ruff enforce this

## CI/CD Integration (Future)

When setting up CI/CD, add this step:
```bash
make quality
```

This ensures all code quality checks pass before deployment.
