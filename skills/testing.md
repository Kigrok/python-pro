# Testing Rules

Test rules under the python-pro standard. Pairs with the `run_tests` tool and the `test-author` agent.

## Layout
- `pytest`; async via `pytest-asyncio` + `@mark.asyncio`.
- Files `tests/test_<module>.py`, functions `test_<behaviour>`.
- Arrange–Act–Assert; one behaviour per test.

## Coverage
- Cover the happy path, edge cases, and every raised exception (`pytest.raises`).
- Test through the public surface; do not assert on private helpers.

## Style
- `@mark.parametrize` for table cases; fixtures for shared setup.
- Test code obeys the standard too: exact-name imports, full annotations, no `Any`.
- Don't chase coverage numbers with trivial asserts; assert real behaviour.

```python
# good
from pytest import raises


def test_withdraw_rejects_overdraft() -> None:
    """Withdrawing more than the balance raises ValueError."""
    with raises(ValueError):
        Account(balance=10).withdraw(20)
```

## More Rules

- Tests in a top-level `tests/` dir (or a package `tests/` subdir) — never beside production modules.
- Set `addopts = ["--import-mode=importlib"]`; otherwise add `__init__.py` to every test dir and keep test filenames unique.
- Shared fixtures go in `conftest.py` (auto-discovered) — never import a fixture from another test module; register external fixtures via `pytest_plugins`.
- `yield` fixtures for teardown (cleanup after the `yield`); one state-changing action per fixture.
- Fixture scope matches resource cost — expensive resources (DB/network) at least `module` scope.
- `@pytest.mark.usefixtures(...)` for side-effect-only fixtures; `autouse=True` only for truly universal ones.
- Parametrize over duplicated test functions; give cases readable `ids=`.
- Factory-as-fixture when a test needs the object built several times.
- Test every public function against its standard failure modes: empty / None / wrong-type / boundary / overflow inputs, and assert each exception it can raise with `pytest.raises`. One behaviour (happy path or one failure mode) per test.
