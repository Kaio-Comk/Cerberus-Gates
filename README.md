# codegates

AST regression gates for Python projects. They read your source with `ast`
(nothing is imported or executed) and fail your CI when a known-bad pattern
comes back. Extracted from a production Telegram bot, where each of these
patterns caused a real incident.

| Check | Catches | Why it hurts |
|---|---|---|
| `silent-except` | `except Exception:` / bare `except:` that neither logs nor re-raises | features silently stop working and nobody notices |
| `swallowed-cancellation` | handlers that catch `CancelledError`, `KeyboardInterrupt` or `SystemExit` without re-raising | tasks that cannot be cancelled, processes that cannot stop |
| `blocking-in-async` | `time.sleep`, `subprocess.run`, `requests.*`, `open()`, `Path.read_text()`... directly inside `async def` | one blocking call freezes the whole event loop (we lost a 700 MB upload to a 10-minute `subprocess.run(ffmpeg)`) |

## Use

```bash
pip install git+https://github.com/Kaio-Comk/pycode-gates.git
python -m codegates src/                       # all checks, exit code 1 on findings
python -m codegates src/ --check blocking-in-async --skip migrations
```

As a pytest gate:

```python
from codegates import scan

def test_no_silent_except():
    assert scan("src", ["silent-except"]) == []
```

Nested sync functions inside an `async def` are skipped on purpose: they are
usually the callable you hand to `asyncio.to_thread`.

## Limits

These are heuristics on the syntax tree: they do not follow calls into other
functions, and a handler counts as "handled" when it calls anything whose name
looks like logging. Use them as tripwires, not as proof.

## Tests

```bash
pip install -e ".[dev]" && pytest
```

## License

MIT
