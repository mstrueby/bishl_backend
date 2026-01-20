
# Manual Testing Checklist - Stats Service Refactoring

## Before Running Tests

- [ ] Backup production database: `python backup_db.py --prod`
- [ ] Set `DEBUG_LEVEL=1` in environment to enable detailed logging
- [ ] Ensure server is running: workflow "Run"

## Automated Validation

Run the validation script:
```bash
python validate_stats_refactoring.py
```

Expected output:
- ✓ All match stats scenarios pass
- ✓ Standings team counts match
- ✓ Roster stats totals match
- ✓ Performance logging active

## Manual Smoke Tests

### Test 1: Match Stats Calculation
**Scenario:** Update a match score

1. [ ] Navigate to a finished match in the UI
2. [ ] Note current standings
3. [ ] Update score via API/UI
4. [ ] Check console for `[MATCH_STATS]` log
5. [ ] Verify standings updated correctly
6. [ ] Check that no errors appear in logs

**Expected:** Match stats calculated, standings updated, performance logged

---

### Test 2: Standings Aggregation
**Scenario:** Recalculate round standings

1. [ ] Identify a round with `createStandings=true`
2. [ ] Make a score change in any match
3. [ ] Check console for `[STANDINGS]` logs
4. [ ] Verify execution time is logged
5. [ ] Compare standings with expected results

**Expected:** Standings recalculated in <2s, correct team order

---

### Test 3: Roster Stats
**Scenario:** Add a goal to a match

1. [ ] Navigate to a match with roster
2. [ ] Add a goal via scores endpoint
3. [ ] Check console for `[ROSTER]` logs
4. [ ] Verify player's goals/assists updated
5. [ ] Check roster in match document

**Expected:** Player stats updated correctly, timing logged

---

### Test 4: Player Card Stats
**Scenario:** Trigger player stats recalculation

1. [ ] Update a roster (mark player as "called")
2. [ ] Check console for `[PLAYER_STATS]` logs
3. [ ] Verify player document has updated stats
4. [ ] Check for called teams processing logs

**Expected:** Player stats updated, called teams logic runs if applicable

---

### Test 5: Performance Monitoring
**Scenario:** Check performance under load

1. [ ] Set `DEBUG_LEVEL=10` for detailed logs
2. [ ] Update multiple matches in sequence
3. [ ] Check console for timing data
4. [ ] Verify no slowdowns or timeouts

**Expected:** Each operation logs execution time, no degradation

---

## Edge Cases to Test

- [ ] Match with status SCHEDULED (should skip stats)
- [ ] Overtime finish (check OT points calculated)
- [ ] Shootout finish (check SO points calculated)
- [ ] Match with no roster (should not crash)
- [ ] Empty standings (new round with no matches)
- [ ] Player with 5+ called matches (assignedTeams update)

## Performance Benchmarks

| Operation | Expected Time | Actual Time | Status |
|-----------|---------------|-------------|--------|
| Match stats calculation | <0.1s | ___ | [ ] |
| Round standings (20 matches) | <2s | ___ | [ ] |
| Matchday standings (5 matches) | <1s | ___ | [ ] |
| Roster stats update | <0.5s | ___ | [ ] |
| Player card stats (10 players) | <3s | ___ | [ ] |

## Data Consistency Checks

After testing, verify:
- [ ] No duplicate stats entries in player documents
- [ ] Standings totals match sum of match stats
- [ ] Roster totals match scoreboard/penaltysheet
- [ ] No null/undefined values in calculated stats

## Rollback Plan

If issues found:
1. Restore database: `python restore_db.py --backup backups/<timestamp>`
2. Revert code: `git revert <commit-hash>`
3. Document issues in GitHub issue
4. Fix and re-test

## Sign-off

- [ ] All automated validations pass
- [ ] All manual smoke tests pass
- [ ] Edge cases handled correctly
- [ ] Performance meets benchmarks
- [ ] No data inconsistencies found
- [ ] Logs provide useful debugging info

**Tested by:** ___________  
**Date:** ___________  
**Notes:** ___________
