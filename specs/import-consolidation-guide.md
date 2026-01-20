
# Import Scripts Consolidation Guide

## Overview

The import system has been consolidated into a unified framework to reduce code duplication and provide better error handling, rollback support, and progress tracking.

## Architecture

### Core Components

1. **ImportService** (`services/import_service.py`)
   - Centralized database connection management
   - API authentication handling
   - Automatic rollback on failures
   - Environment-aware (dev/prod) configuration

2. **ImportCLI** (`scripts/import_cli.py`)
   - Unified command-line interface
   - Supports all import operations
   - Dry-run mode for testing
   - Progress tracking and error reporting

### Key Features

- ✅ **Unified Connection Logic**: Single point for DB and API connections
- ✅ **Automatic Rollback**: Failed imports restore previous state
- ✅ **Progress Tracking**: Visual feedback for long-running imports
- ✅ **Error Handling**: Comprehensive logging with correlation IDs
- ✅ **Dry-Run Mode**: Test imports without modifying data
- ✅ **Environment Safety**: Production confirmations to prevent accidents

## Usage

### Basic Import

```bash
# Import players to development database
python scripts/import_cli.py players

# Import to production (with confirmation)
python scripts/import_cli.py players --prod

# Import with custom file
python scripts/import_cli.py schedule --file data/schedule_2026.csv
```

### Advanced Options

```bash
# Dry run to preview changes
python scripts/import_cli.py tournaments --dry-run

# Delete existing data before import
python scripts/import_cli.py players --delete-all --import-all

# Production import with automatic confirmation
python scripts/import_cli.py schedule --prod --import-all
```

### Available Entities

- `players` - Player records
- `tournaments` - Tournament structure
- `schedule` - Match schedules
- `teams` - Team information
- `team-assignments` - Player team assignments
- `hobby-players` - Hobby league players
- `referees` - Referee accounts

## Migration from Old Scripts

### Before (Old Way)

```bash
python import_players.py --prod --importAll
python import_schedule.py --prod
python import_tournaments.py --importAll
```

### After (New Way)

```bash
python scripts/import_cli.py players --prod --import-all
python scripts/import_cli.py schedule --prod
python scripts/import_cli.py tournaments --import-all
```

## Implementation Status

### ✅ Completed
- Core `ImportService` infrastructure
- Unified CLI framework
- Error handling and rollback
- Progress tracking
- Documentation

### 🚧 In Progress (Pending Migration)
- [ ] Players import logic
- [ ] Tournaments import logic
- [ ] Schedule import logic
- [ ] Teams import logic
- [ ] Team assignments import logic
- [ ] Hobby players import logic
- [ ] Referees import logic

### Migration Checklist

For each import script:
1. Copy business logic to appropriate handler in `import_cli.py`
2. Remove duplicate connection/auth code
3. Use `ImportProgress` for tracking
4. Test with `--dry-run`
5. Test actual import in dev
6. Mark old script as deprecated
7. Update documentation

## Error Handling

### Automatic Rollback

If an import fails, the system automatically:
1. Logs the error with full traceback
2. Restores the backup of affected collection
3. Reports rollback status

Example:
```
ERROR: Import failed with error: Duplicate key error
INFO: Rolling back changes...
INFO: Rollback completed
Import failed: Duplicate key error (rolled back)
```

### Partial Success Handling

For imports that process multiple records:
- Errors are logged individually
- Progress continues for remaining records
- Final summary shows success/error counts

## Best Practices

1. **Always test with --dry-run first**
   ```bash
   python scripts/import_cli.py players --dry-run
   ```

2. **Use production carefully**
   ```bash
   # System will ask for confirmation
   python scripts/import_cli.py schedule --prod
   ```

3. **Monitor logs**
   ```bash
   tail -f logs/import.log
   ```

4. **Backup before large imports**
   ```bash
   python backup_db.py --prod
   python scripts/import_cli.py players --prod --import-all
   ```

## Extending the System

### Adding a New Import Type

1. Add handler method to `ImportCLI`:
```python
def import_my_entity(self) -> tuple[bool, str]:
    """Import my custom entity"""
    logger.info("Starting import...")
    
    csv_path = self.get_csv_path('my-entity')
    collection = self.service.get_collection('my_collection')
    
    data = self.read_csv(csv_path)
    progress = ImportProgress(len(data), "Importing")
    
    for row in data:
        # Your import logic here
        progress.update()
    
    return True, f"Imported {len(data)} records"
```

2. Register in handlers dict:
```python
self.handlers = {
    # ... existing handlers ...
    'my-entity': self.import_my_entity,
}
```

3. Add to entity choices in parser

## Next Steps

1. **Migrate existing scripts** one by one to the new system
2. **Add unit tests** for import service
3. **Create import templates** for common patterns
4. **Add validation** before import (schema checks)
5. **Improve progress UI** with rich/tqdm library

## Troubleshooting

### Authentication Fails
- Verify `SYS_ADMIN_EMAIL` and `SYS_ADMIN_PASSWORD` in secrets
- Check API is running: `curl $BE_API_URL/`

### Database Connection Issues
- Verify `DB_URL` or `DB_URL_PROD` in secrets
- Check network connectivity
- Verify database credentials

### Import Hangs
- Check CSV file encoding (should be UTF-8)
- Verify CSV format matches expected structure
- Check logs for specific errors

---

*Last Updated: 2025-01-21*
*Status: Phase 1 Complete - Core Framework Ready*
