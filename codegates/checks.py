"""AST checks. Each check returns a list of `Finding` and never imports the code it scans."""
from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Iterator

DEFAULT_SKIP = {".venv", "venv", "node_modules", ".git", "__pycache__", "build", "dist", ".tox"}

# Calls that block the event loop when made directly inside `async def`.
BLOCKING_CALLS = {
    "time.sleep",
    "subprocess.run", "subprocess.call", "subprocess.check_call", "subprocess.check_output",
    "requests.get", "requests.post", "requests.put", "requests.delete", "requests.patch",
    "requests.head", "requests.request",
    "urllib.request.urlopen",
    "os.system",
    "shutil.copy", "shutil.copyfile", "shutil.copytree", "shutil.move", "shutil.rmtree",
}
# Method names that perform file I/O synchronously.
BLOCKING_METHODS = {"read_text", "write_text", "read_bytes", "write_bytes"}

LOG_HINTS = ("log", "warning", "error", "info", "debug", "exception", "print", "fail", "critical")
SWALLOWED_BY_NO_ONE = {"CancelledError", "KeyboardInterrupt", "SystemExit"}


@dataclass(frozen=True)
class Finding:
    check: str
    path: str
    line: int
    message: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: [{self.check}] {self.message}"


def iter_py_files(root: Path, skip: Iterable[str] = DEFAULT_SKIP) -> Iterator[Path]:
    skip = set(skip)
    root = Path(root)
    if root.is_file():
        yield root
        return
    for p in sorted(root.rglob("*.py")):
        if any(part in skip for part in p.parts):
            continue
        yield p


def _parse(path: Path):
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError, OSError):
        return None


def _dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Attribute):
        base = _dotted(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    if isinstance(node, ast.Name):
        return node.id
    return ""


def _caught_names(h: ast.ExceptHandler) -> list[str]:
    if h.type is None:
        return ["<bare>"]
    elems = h.type.elts if isinstance(h.type, ast.Tuple) else [h.type]
    return [_dotted(e).split(".")[-1] for e in elems]


def _handled(h: ast.ExceptHandler) -> bool:
    """True when the handler re-raises or calls something that looks like logging."""
    for sub in ast.walk(h):
        if isinstance(sub, ast.Raise):
            return True
        if isinstance(sub, ast.Call):
            name = _dotted(sub.func).split(".")[-1].lower()
            if any(k in name for k in LOG_HINTS):
                return True
    return False


def silent_except(path: Path, tree: ast.AST) -> list[Finding]:
    """`except Exception:` / bare `except:` that neither logs nor re-raises."""
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            names = _caught_names(node)
            if any(n in ("Exception", "BaseException", "<bare>") for n in names) and not _handled(node):
                out.append(Finding("silent-except", str(path), node.lineno,
                                   f"catches {names} without logging or re-raising"))
    return out


def swallowed_cancellation(path: Path, tree: ast.AST) -> list[Finding]:
    """Handlers that catch CancelledError / KeyboardInterrupt / SystemExit without re-raising."""
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            hit = [n for n in _caught_names(node) if n in SWALLOWED_BY_NO_ONE]
            if hit and not any(isinstance(s, ast.Raise) for s in ast.walk(node)):
                out.append(Finding("swallowed-cancellation", str(path), node.lineno,
                                   f"catches {hit} and does not re-raise"))
    return out


def blocking_in_async(path: Path, tree: ast.AST) -> list[Finding]:
    """Blocking calls made directly in an `async def` body (nested sync defs are skipped:
    those are usually the target of `asyncio.to_thread`)."""
    out = []
    for fn in ast.walk(tree):
        if not isinstance(fn, ast.AsyncFunctionDef):
            continue
        stack = list(fn.body)
        while stack:
            n = stack.pop()
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                continue
            if isinstance(n, ast.Call):
                name = _dotted(n.func)
                kind = None
                if name in BLOCKING_CALLS:
                    kind = name
                elif name == "open":
                    kind = "open() (sync file I/O)"
                elif name.split(".")[-1] in BLOCKING_METHODS:
                    kind = f"{name.split('.')[-1]}() (sync file I/O)"
                if kind:
                    out.append(Finding("blocking-in-async", str(path), n.lineno,
                                       f"{kind} inside async def {fn.name}(); use asyncio.to_thread "
                                       f"or an async API"))
            stack.extend(ast.iter_child_nodes(n))
    return out


CHECKS: dict[str, Callable[[Path, ast.AST], list[Finding]]] = {
    "silent-except": silent_except,
    "swallowed-cancellation": swallowed_cancellation,
    "blocking-in-async": blocking_in_async,
}


def scan(root: Path, checks: Iterable[str] | None = None,
         skip: Iterable[str] = DEFAULT_SKIP) -> list[Finding]:
    names = list(checks or CHECKS)
    unknown = [n for n in names if n not in CHECKS]
    if unknown:
        raise ValueError(f"unknown checks: {unknown}; available: {sorted(CHECKS)}")
    findings: list[Finding] = []
    for p in iter_py_files(Path(root), skip):
        tree = _parse(p)
        if tree is None:
            continue
        for n in names:
            findings.extend(CHECKS[n](p, tree))
    return sorted(findings, key=lambda f: (f.path, f.line, f.check))
