# FastAPI Rules

Production rules for FastAPI services under the python-pro standard.

## Handlers
- Every path operation is `async def`; never run blocking I/O inside it (see `async`).
- Annotate all parameters and the return type; always set `response_model`.
- Raise `HTTPException(status_code=status.HTTP_*, detail=...)` — never return error dicts.

## I/O contracts
- Validate every request and response with Pydantic models; never accept or return bare `dict`.
- Return DTOs, not ORM objects — map explicitly so the schema is stable.

## Structure
- One `APIRouter(prefix="/x", tags=["x"])` per resource; mount routers on the app.
- Shared logic (db session, current user, pagination) goes through `Depends(...)`.
- Keep handlers thin: parse → call a service/use-case → return. Business logic lives elsewhere.

```python
# good
@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(payload: UserIn, db: AsyncSession = Depends(get_db)) -> UserOut:
    """Create a user."""
    return await UserService(db).create(payload)
```

## More Rules
- Put shared `prefix` / `tags` / `dependencies` on the `APIRouter(...)` constructor, not on every operation. No trailing slash in `prefix`.
- Import router modules by name (`from .routers import items; items.router`) — importing the `router` name from several modules shadows it.
- Inject deps with `Annotated[T, Depends(fn)]` (pass the callable, no `()`); factor a repeated one into a module-level type alias. App-wide deps go on `FastAPI(...)`.
- Shared deps live in one module (`app/dependencies.py`); every package dir has `__init__.py`.
