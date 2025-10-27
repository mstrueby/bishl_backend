# Deployment Checklist

## Pre-Deployment (Feature Branch → Main)

- [ ] All feature tests pass locally
- [ ] Code review completed
- [ ] No merge conflicts with main
- [ ] `.env` variables documented (if new ones added)
- [ ] Database migrations tested (if applicable)
- [ ] API documentation updated (if endpoints changed)
- [ ] Database indexes created/verified: `python scripts/create_indexes.py --prod`

## Backup (Before Merge)

- [ ] Run backup script: `python backup_db.py --prod`
- [ ] Verify backup in `backups/` directory
- [ ] Commit backup metadata to separate backup branch (optional)

## Deployment Steps

1. **Merge to Main**
   ```bash
   git checkout main
   git merge feature/<feature-name>
   git push origin main
   ```

2. **Tag Release**
   ```bash
   git tag -a v1.x.x -m "Release description"
   git push origin v1.x.x
   ```

3. **Deploy via Replit Publishing**
   - Navigate to Publishing tab
   - Verify build/run commands
   - Click "Redeploy"
   - Monitor deployment logs

4. **Post-Deployment Verification**
   - [ ] Health check endpoint responds (GET /)
   - [ ] Sample API requests work (GET /players?limit=5)
   - [ ] Authentication flow works (POST /login)
   - [ ] Database connection stable
   - [ ] No errors in production logs
   - [ ] CORS configured correctly

### Error Handling Verification

- [ ] 404 errors return standard format with correlation_id
- [ ] 401 errors return on expired token with proper message
- [ ] 403 errors return on insufficient permissions
- [ ] 500 errors logged with correlation_id and traceback
- [ ] Error logs written to logs/errors.log
- [ ] Log rotation working (check file sizes)
- [ ] All error responses include timestamp and path
- [ ] No print() statements in error handling code

## Rollback Procedure

If deployment fails:

1. **Quick Rollback**
   ```bash
   git revert <commit-hash>
   git push origin main
   ```

2. **Restore Database** (if needed)
   ```bash
   python restore_db.py --backup backups/<timestamp>
   ```

3. **Redeploy** previous stable version via Publishing

## Post-Deployment

- [ ] Update changelog
- [ ] Notify team/users of new features
- [ ] Archive old backups (keep last 5)
- [ ] Monitor error logs for 24 hours