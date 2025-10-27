
# API Response Standardization

*Created: 2025-01-22*  
*Status: Implemented*  
*Priority: Medium*

---

## Overview

All API endpoints now return standardized response formats for consistency and better client experience. This includes standard wrappers for single resources, paginated lists, and bulk operations.

---

## Response Formats

### Single Resource Response

Used for GET (single item), POST, PUT, PATCH operations.

```json
{
  "success": true,
  "data": {
    "_id": "67165e0190212e4ad16ca8dd",
    "name": "Example Match",
    "status": "COMPLETED"
  },
  "message": "Match retrieved successfully"
}
```

**Model:** `StandardResponse[T]`

### Paginated List Response

Used for GET operations that return multiple items.

```json
{
  "success": true,
  "data": [
    {"_id": "1", "name": "Item 1"},
    {"_id": "2", "name": "Item 2"}
  ],
  "pagination": {
    "page": 1,
    "page_size": 10,
    "total_items": 25,
    "total_pages": 3,
    "has_next": true,
    "has_prev": false
  },
  "message": "Retrieved 10 matches"
}
```

**Model:** `PaginatedResponse[T]`

### Delete Response

Used for DELETE operations.

```json
{
  "success": true,
  "deleted_count": 1,
  "message": "Match deleted successfully"
}
```

**Model:** `DeleteResponse`

### Bulk Operation Response

Used for bulk create/update/delete operations.

```json
{
  "success": true,
  "processed_count": 10,
  "success_count": 9,
  "error_count": 1,
  "errors": [
    {"item_id": "5", "error": "Validation failed"}
  ],
  "message": "Bulk operation completed with some errors"
}
```

**Model:** `BulkOperationResponse`

---

## Pagination

### Query Parameters

All list endpoints accept these pagination parameters:

- `page` (integer, default: 1): Page number (1-indexed)
- `page_size` (integer, default: 10-20): Items per page (max: 100)

### Example Request

```bash
GET /matches?page=2&page_size=20
```

### Pagination Metadata

The `pagination` object contains:
- `page`: Current page number
- `page_size`: Items per page
- `total_items`: Total matching items
- `total_pages`: Total number of pages
- `has_next`: Whether there's a next page
- `has_prev`: Whether there's a previous page

---

## Implementation Guide

### Using Standard Responses in Routers

```python
from models.responses import StandardResponse, PaginatedResponse
from utils.pagination import PaginationHelper

# Single resource
@router.get("/{id}", response_model=StandardResponse[Match])
async def get_match(id: str, request: Request):
    match = await request.app.state.mongodb["matches"].find_one({"_id": ObjectId(id)})
    
    if not match:
        raise ResourceNotFoundException("Match", id)
    
    return StandardResponse(
        success=True,
        data=match,
        message="Match retrieved successfully"
    )

# Paginated list
@router.get("", response_model=PaginatedResponse[Match])
async def get_matches(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100)
):
    items, total_count = await PaginationHelper.paginate_query(
        collection=request.app.state.mongodb["matches"],
        query={},
        page=page,
        page_size=page_size,
        sort=[("startDate", -1)]
    )
    
    return PaginationHelper.create_response(
        items=items,
        page=page,
        page_size=page_size,
        total_count=total_count,
        message=f"Retrieved {len(items)} matches"
    )
```

---

## Migration Checklist

### Phase 1: Infrastructure (✅ Complete)
- [x] Create `models/responses.py` with response models
- [x] Create `utils/pagination.py` with pagination helpers
- [x] Update `routers/matches.py` with pagination
- [x] Update `routers/players.py` with pagination

### Phase 2: Remaining Routers
- [ ] `routers/tournaments.py` - Add pagination to GET /tournaments
- [ ] `routers/clubs.py` - Add pagination to GET /clubs
- [ ] `routers/users.py` - Add pagination to GET /users
- [ ] `routers/assignments.py` - Add pagination to GET /assignments
- [ ] `routers/posts.py` - Add pagination to GET /posts
- [ ] `routers/documents.py` - Add pagination to GET /documents

### Phase 3: Testing & Documentation
- [ ] Test all paginated endpoints
- [ ] Update API documentation examples
- [ ] Add pagination examples to OpenAPI docs
- [ ] Update frontend integration guide

---

## Frontend Integration

### Example Client Code

```javascript
async function fetchMatches(page = 1, pageSize = 10) {
  const response = await fetch(`/matches?page=${page}&page_size=${pageSize}`);
  const result = await response.json();
  
  if (!result.success) {
    throw new Error('Failed to fetch matches');
  }
  
  return {
    items: result.data,
    pagination: result.pagination
  };
}

// Usage with pagination controls
function MatchList() {
  const [page, setPage] = useState(1);
  const { items, pagination } = await fetchMatches(page);
  
  return (
    <div>
      {items.map(match => <MatchCard key={match._id} match={match} />)}
      
      <Pagination
        page={pagination.page}
        totalPages={pagination.total_pages}
        hasNext={pagination.has_next}
        hasPrev={pagination.has_prev}
        onPageChange={setPage}
      />
    </div>
  );
}
```

---

## Benefits

1. **Consistency**: All endpoints return the same structure
2. **Pagination**: Built-in support for large datasets
3. **Client-friendly**: Easy to parse and handle in frontend
4. **Type-safe**: Full TypeScript/Pydantic support
5. **Searchability**: Easy to add search to paginated endpoints

---

*Next Steps: Complete Phase 2 migration of remaining routers*
