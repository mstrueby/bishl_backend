
# Deployment Checklist

## Pre-Deployment (Feature Branch → Main)

- [ ] All feature tests pass locally
- [ ] Code review completed
- [ ] No merge conflicts with main
- [ ] `.env` variables documented (if new ones added)
- [ ] Database migrations tested (if applicable)
- [ ] API documentation updated (if endpoints changed)

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
   - [ ] Check deployment URL is accessible
   - [ ] Verify critical endpoints respond correctly
   - [ ] Check logs for errors
   - [ ] Test one critical user flow

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
