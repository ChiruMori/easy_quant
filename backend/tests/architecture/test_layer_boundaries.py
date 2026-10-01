from __future__ import annotations

import ast
from pathlib import Path

FORBIDDEN_ROOTS = {"akshare", "flask", "httpx", "sqlalchemy"}


def test_domain_does_not_import_frameworks_or_adapters() -> None:
    domain_root = Path(__file__).parents[3] / "src" / "easy_quant" / "domain"
    violations: list[str] = []
    for path in domain_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                if name.split(".", maxsplit=1)[0] in FORBIDDEN_ROOTS:
                    violations.append(
                        f"{path.relative_to(domain_root)}:{getattr(node, 'lineno', 0)} {name}"
                    )
    assert not violations, "领域层存在禁止依赖：\n" + "\n".join(violations)
