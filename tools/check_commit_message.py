from __future__ import annotations

import re
import sys
from pathlib import Path

PATTERN = re.compile(
    r"^(feat|fix|docs|refactor|perf|test|build|ci|chore)(\([a-z0-9_-]+\))?!?: .{1,72}$"
)


def main() -> int:
    message = Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()[0]
    if message.startswith(("Merge ", "Revert ")) or PATTERN.fullmatch(message):
        return 0
    print(
        "提交首行应为 <type>(<scope>): <summary>，摘要不超过 72 字符", file=sys.stderr
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
