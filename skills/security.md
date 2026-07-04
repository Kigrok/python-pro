# Security Rules

Secure-coding rules under the python-pro standard. Pairs with the `security_scan` tool.

## Code execution
- Never `eval` / `exec` / `compile` on dynamic input.
- `subprocess` without `shell=True`; pass arguments as a list, not a string.
- No `os.system`.

## Deserialisation
- No `pickle.loads` on untrusted data; no bare `yaml.load` — use `yaml.safe_load`.

## Secrets & crypto
- No secrets in source; read from env or a secret store.
- Hash with `sha256`+; never `md5` / `sha1` for security. Passwords via `bcrypt` / `argon2`.

## Data & queries
- Parameterised SQL only; never build queries with f-strings or `%`.
- Validate and bound all external input (sizes, ranges, types).

```python
# good
from subprocess import run

run(["git", "status"], check=True)  # no shell=True, args as a list
```

## More Rules
- `hashlib.md5` / `sha1` not for security; use `sha256`+ (pass `usedforsecurity=False` only for non-security checksums).
- `secrets`, never `random`, for tokens / nonces / passwords / IDs.
- `tempfile.mkstemp()` / `NamedTemporaryFile` — never `mktemp()` (TOCTOU race); never a hardcoded `/tmp/...` path.
- Never `verify=False` on TLS in production — supply a CA bundle instead.
- `assert` is NOT validation — `-O` strips it; raise an explicit exception.
- RSA/DSA keys ≥ 2048 bits, EC curves ≥ 224 bits.
- `ast.literal_eval` for data parsing — never `eval`. Deserialize untrusted data with `json`, never `pickle` / `shelve` / `yaml.load`.
