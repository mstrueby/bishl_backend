
# Async Testing Best Practices & Event Loop Management

*Created: 2025-01-22*  
*Priority: Critical*  
*Status: Implemented*

---

## Executive Summary

This document captures the critical lessons learned from resolving the "Event loop is closed" issue that affected assignment tests and provides comprehensive guidance for implementing async tests in FastAPI applications using pytest-asyncio and Motor (async MongoDB driver).

---

## The Problem: Event Loop Closed Issue

### Symptom

Tests were failing with `RuntimeError: Event loop is closed` errors, specifically in assignment router tests that used MongoDB transactions.

```python
RuntimeError: Event loop is closed
    at motor.core.py:120 in get_io_loop()
```

### Root Causes

1. **Async Fixture Lifecycle Mismatch**
   - The `mongodb` fixture was being cleaned up (closing Motor client connection) while the test event loop was still active
   - Both pytest-asyncio and the fixture's cleanup were trying to close the same event loop
   - This created a race condition where cleanup happened in the wrong order

2. **Double Cleanup Pattern**
   - Fixture used `yield` pattern with explicit Motor client cleanup
   - pytest-asyncio also performed its own event loop cleanup
   - These conflicting cleanups caused the event loop to be closed prematurely

3. **Motor's Connection Pooling**
   - Motor maintains persistent connections via connection pools
   - These connections don't work well with pytest's default per-function event loop cleanup
   - Connection pool expects to manage its own lifecycle

### What Made Assignments Special

Assignment tests revealed this issue because they had unique characteristics:

1. **Transaction Usage**
   ```python
   async with await request.app.state.mongodb.client.start_session() as session:
       async with session.start_transaction():
           # Dual collection updates
   ```
   - Assignments modify both `assignments` and `matches` collections atomically
   - Transactions require proper session and event loop management
   - More complex async context management exposed fixture lifecycle issues

2. **Dual Database Updates**
   - Creating/deleting assignments updates both collections
   - Required consistent ObjectId usage across related documents
   - More integration points = more opportunities for async issues

3. **Complete Referee Object Structure**
   - Tests needed full referee objects with all fields:
   ```python
   "referee": {
       "userId": "ref-1",
       "firstName": "John",
       "lastName": "Referee",
       "clubId": None,
       "clubName": None,
       "logoUrl": None,
       "points": 0,
       "level": "S2"
   }
   ```
   - Incomplete objects caused validation errors
   - Required more careful test data setup

---

## The Solution

### Critical Changes in `tests/conftest.py`

#### 1. Changed Fixture Scope (Most Important)

**Before (Broken):**
```python
@pytest_asyncio.fixture(scope="function")
async def mongodb():
    settings = TestSettings()
    client = AsyncIOMotorClient(settings.DB_URL)
    db = client[settings.DB_NAME]
    
    yield db
    
    # ❌ PROBLEM: Cleanup happening while event loop still active
    client.close()
```

**After (Fixed):**
```python
@pytest_asyncio.fixture(scope="session")
async def mongodb():
    settings = TestSettings()
    client = AsyncIOMotorClient(settings.DB_URL)
    db = client[settings.DB_NAME]
    
    # ✅ SOLUTION: Session scope + no explicit cleanup
    yield db
    # Motor client closes automatically when process ends
```

**Why This Works:**
- `session` scope ensures one database connection for all tests
- Prevents repeated connection/disconnection cycles
- Lets pytest-asyncio handle event loop lifecycle
- Motor's connection pool manages its own cleanup when process terminates

#### 2. Proper Database Isolation

Instead of recreating the database connection for each test, we clean the data:

```python
@pytest_asyncio.fixture(scope="session", autouse=True)
async def clean_test_database():
    """Clean test database once at start of session"""
    settings = TestSettings()
    client = AsyncIOMotorClient(settings.DB_URL)
    db = client[settings.DB_NAME]
    
    # Safety check
    assert db.name == "bishl_test", f"Wrong database: {db.name}"
    
    # Drop all collections at session start
    collections = await db.list_collection_names()
    for collection_name in collections:
        await db[collection_name].drop()
    
    client.close()
    yield
```

#### 3. Per-Test Data Cleanup

```python
@pytest_asyncio.fixture
async def test_isolation(mongodb):
    """Provides test isolation by tracking and cleaning test data"""
    import uuid
    
    class TestIsolation:
        def __init__(self, db):
            self.db = db
            self.id = f"test_{uuid.uuid4().hex[:8]}"
            self.created_docs = []
        
        async def create(self, collection: str, document: dict):
            """Create a document and track it for cleanup"""
            document["test_id"] = self.id
            result = await self.db[collection].insert_one(document)
            self.created_docs.append((collection, {"_id": result.inserted_id}))
            return result.inserted_id
        
        async def cleanup(self):
            """Clean up all created documents"""
            for collection, filter_dict in reversed(self.created_docs):
                await self.db[collection].delete_many(filter_dict)
    
    isolation = TestIsolation(mongodb)
    yield isolation
    await isolation.cleanup()
```

### Router Implementation: Proper Transaction Handling

**Assignment Delete with Transaction:**

```python
@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_assignment(id: str, request: Request, current_user: User = Depends(auth.require_admin)):
    mongodb = request.app.state.mongodb
    assignment = await mongodb["assignments"].find_one({"_id": ObjectId(id)})
    
    if not assignment:
        raise ResourceNotFoundException(resource_type="Assignment", resource_id=id)
    
    # ✅ Use transaction for atomic updates
    async with await request.app.state.mongodb.client.start_session() as session:
        async with session.start_transaction():
            try:
                # Delete assignment
                result = await mongodb["assignments"].delete_one(
                    {"_id": id}, 
                    session=session
                )
                
                if result.deleted_count == 0:
                    raise ResourceNotFoundException(resource_type="Assignment", resource_id=id)
                
                # Remove referee from match if assignment had a position
                if assignment.get("position"):
                    await assignment_service.remove_referee_from_match(
                        assignment["matchId"], 
                        assignment["position"], 
                        session=session
                    )
                
                # Transaction commits automatically on success
            except ResourceNotFoundException:
                raise
            except Exception as e:
                # Transaction aborts automatically on exception
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to delete assignment: {str(e)}",
                ) from e
    
    return Response(status_code=status.HTTP_204_NO_CONTENT)
```

---

## Best Practices for Future Development

### For Routers

1. ✅ **Always use transactions when updating multiple collections**
   ```python
   async with await mongodb.client.start_session() as session:
       async with session.start_transaction():
           # Multiple collection updates here
   ```

2. ✅ **Pass session parameter through service layer**
   ```python
   await service.update_related_data(match_id, session=session)
   ```

3. ✅ **Let transactions auto-commit/abort**
   - Don't manually call `session.commit_transaction()`
   - Transaction commits on successful context exit
   - Transaction aborts automatically on exception

4. ✅ **Use proper error handling with custom exceptions**
   ```python
   try:
       # Transaction operations
   except ResourceNotFoundException:
       raise  # Re-raise specific exceptions
   except Exception as e:
       raise HTTPException(...) from e
   ```

### For Tests

1. ✅ **Use session-scoped database fixtures**
   ```python
   @pytest_asyncio.fixture(scope="session")
   async def mongodb():
       # Single connection for all tests
   ```

2. ✅ **Use ObjectId() for all _id fields**
   ```python
   # ❌ Wrong
   {"_id": "some-string-id"}
   
   # ✅ Correct
   {"_id": ObjectId()}
   ```

3. ✅ **Create complete object structures matching Pydantic models**
   ```python
   # ❌ Incomplete
   "referee": {"userId": "ref-1"}
   
   # ✅ Complete
   "referee": {
       "userId": "ref-1",
       "firstName": "John",
       "lastName": "Referee",
       "clubId": None,
       "clubName": None,
       "logoUrl": None,
       "points": 0,
       "level": "S2"
   }
   ```

4. ✅ **Don't mix string IDs and ObjectIds - be consistent**
   ```python
   # ❌ Inconsistent
   match_id = "test-match-id"  # String
   assignment = {"matchId": ObjectId()}  # ObjectId
   
   # ✅ Consistent
   match_id = ObjectId()
   assignment = {"matchId": match_id}
   ```

5. ✅ **Verify both primary collection AND related collections**
   ```python
   # After deleting assignment
   assert not await mongodb["assignments"].find_one({"_id": assignment_id})
   
   # Also verify match was updated
   match = await mongodb["matches"].find_one({"_id": match_id})
   assert match["referee1"] is None
   ```

6. ✅ **Clean up test data but don't close database connection**
   ```python
   # ✅ Good: Clean data
   await mongodb["assignments"].delete_many({"test_id": test_id})
   
   # ❌ Bad: Close connection
   client.close()  # Don't do this in function-scoped fixtures
   ```

7. ✅ **Use proper async/await patterns consistently**
   ```python
   # ✅ Correct
   result = await mongodb["collection"].find_one({"_id": id})
   
   # ❌ Wrong
   result = mongodb["collection"].find_one({"_id": id})  # Missing await
   ```

### For Service Layer

1. ✅ **Accept optional session parameter for transactions**
   ```python
   async def remove_referee_from_match(
       self, 
       match_id: str, 
       position: str, 
       session=None
   ):
       await self.db["matches"].update_one(
           {"_id": ObjectId(match_id)},
           {"$set": {position: None}},
           session=session  # Pass through
       )
   ```

2. ✅ **Use consistent error handling**
   ```python
   if not match:
       raise ResourceNotFoundException(
           resource_type="Match",
           resource_id=match_id
       )
   ```

---

## Common Pitfalls to Avoid

### 1. Event Loop Issues

❌ **Don't:**
- Use function-scoped fixtures for database connections
- Explicitly close Motor clients in fixtures
- Mix sync and async code without proper context

✅ **Do:**
- Use session-scoped database fixtures
- Let Motor manage its own cleanup
- Use `await` consistently for all async operations

### 2. Transaction Issues

❌ **Don't:**
- Forget to pass `session` parameter
- Manually commit/abort transactions
- Mix transactional and non-transactional operations

✅ **Do:**
- Pass session through all related operations
- Use context managers for automatic commit/abort
- Keep all related updates in same transaction

### 3. Test Data Issues

❌ **Don't:**
- Use string IDs when ObjectIds are expected
- Create incomplete objects
- Leave test data after tests

✅ **Do:**
- Use ObjectId() consistently
- Match Pydantic model structures exactly
- Clean up test data (but not connections)

---

## Debugging Async Issues

### Enable Debug Logging

```python
# tests/test_config.py
class TestSettings(Settings):
    DEBUG_LEVEL: int = 10  # Maximum verbosity
```

### Check Event Loop Status

```python
import asyncio

def check_loop():
    try:
        loop = asyncio.get_event_loop()
        print(f"Loop running: {loop.is_running()}")
        print(f"Loop closed: {loop.is_closed()}")
    except RuntimeError as e:
        print(f"No event loop: {e}")
```

### Verify Database Connection

```python
@pytest_asyncio.fixture
async def mongodb():
    client = AsyncIOMotorClient(settings.DB_URL)
    db = client[settings.DB_NAME]
    
    # Safety check
    assert db.name == "bishl_test", f"Wrong database: {db.name}"
    
    yield db
```

---

## Success Metrics

After implementing these practices:

✅ All tests pass consistently without event loop errors  
✅ No `RuntimeError: Event loop is closed` exceptions  
✅ Tests run in isolation without interfering with each other  
✅ Transaction-based operations work correctly  
✅ Test data cleanup works properly  
✅ No need to restart test runner between runs  

---

## References

- [pytest-asyncio documentation](https://pytest-asyncio.readthedocs.io/)
- [Motor (async MongoDB driver) documentation](https://motor.readthedocs.io/)
- [MongoDB Transactions documentation](https://www.mongodb.com/docs/manual/core/transactions/)
- [FastAPI Testing documentation](https://fastapi.tiangolo.com/tutorial/testing/)

---

## Conclusion

The "Event loop is closed" issue was a critical learning experience that revealed the importance of:

1. Proper fixture scoping for async database connections
2. Understanding Motor's connection pooling behavior
3. Correct transaction handling patterns
4. Comprehensive test data setup
5. Consistent async/await usage

By following these best practices, future router implementations and tests will avoid these pitfalls and maintain a robust, reliable test suite.

---

*Last Updated: 2025-01-22*  
*Related Specs: testing-infrastructure-guide.md, refactoring-roadmap.md*
