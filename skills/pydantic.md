# Pydantic Rules (v2)

Production rules for Pydantic models under the python-pro standard.

## Models
- Subclass `BaseModel`; annotate every field; never `Any`.
- Use `X | None = None` for optional fields, never `Optional[X]`.
- Constrain fields with `Field(...)` (`min_length`, `max_length`, `ge`, `le`, `pattern`).
- Config via `model_config = ConfigDict(...)`, not an inner `class Config`.

## Validation
- Custom checks with `@field_validator(...)` / `@model_validator(...)`; typed, returning the value.
- Validate at the boundary; pass validated models inward, not raw dicts.

## Serialisation
- Use `model_validate` / `model_dump` / `model_dump_json`; avoid deprecated `parse_obj` / `dict()`.

```python
# good
class UserIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=320)
    age: int | None = Field(default=None, ge=0)
```

## v2 Rules (no v1 patterns)

- `model_config = ConfigDict(...)` — not inner `class Config`. `frozen=True`, not
  `allow_mutation=False`.
- `@field_validator` (with `@classmethod` below it) — not `@validator`.
  `@model_validator(mode="after"|"before")` — not `@root_validator`.
- `before` / `plain` / `wrap` validator inputs are typed `Any` (they run before coercion).
- Every validator MUST `return` the value. Raise `ValueError` inside it — never `assert`.
- `model_rebuild()` (not `update_forward_refs()`); `model_validate(obj,
  from_attributes=True)` (not `from_orm`); `model_validate_json(raw)` over
  `model_validate(json.loads(raw))`.
- `model_post_init(self, ctx)` over a custom `__init__`.
- `model_construct()` only on already-trusted data (it skips validation).
- Cross-field checks go in `@model_validator(mode="after")` — `info.data` lacks
  not-yet-validated fields.
- `extra="forbid"` on request/boundary models to reject undeclared fields.
