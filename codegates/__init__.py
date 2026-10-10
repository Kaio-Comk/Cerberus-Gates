"""codegates: AST regression gates for Python projects (no code is imported or executed)."""
from .checks import CHECKS, Finding, scan

__all__ = ["CHECKS", "Finding", "scan"]
__version__ = "0.1.0"
