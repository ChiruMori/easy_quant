from pathlib import Path


def example_sources() -> dict[str, str]:
    root = Path(__file__).parents[4] / "resources" / "examples"
    return {path.stem: path.read_text(encoding="utf-8") for path in sorted(root.glob("*.py"))}
