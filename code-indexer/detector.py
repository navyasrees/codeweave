try:
    import tomllib          # python 3.11+
except ImportError:
    import tomli as tomllib # python 3.9 fallback
from pathlib import Path


def detect_structure(repo_path: Path) -> dict:
    repo_path = Path(repo_path)
    
    result = {
        "repo_name": repo_path.name,
        "source_dir": None,
        "docs_dir": None,
        "tests_dir": None,
    }

    # Step 1 — try pyproject.toml first
    pyproject = repo_path / "pyproject.toml"
    if pyproject.exists():
        with open(pyproject, "rb") as f:
            data = tomllib.load(f)
        
        # poetry
        name = data.get("tool", {}).get("poetry", {}).get("name")
        # pep 517
        if not name:
            name = data.get("project", {}).get("name")
        
        if name:
            result["repo_name"] = name
            candidate = repo_path / name.replace("-", "_")
            if candidate.exists():
                result["source_dir"] = candidate

    # Step 2 — try setup.py as fallback
    if not result["source_dir"]:
        setup_py = repo_path / "setup.py"
        if setup_py.exists():
            content = setup_py.read_text()
            import re
            match = re.search(r'name\s*=\s*["\']([^"\']+)["\']', content)
            if match:
                name = match.group(1)
                result["repo_name"] = name
                candidate = repo_path / name.replace("-", "_")
                if candidate.exists():
                    result["source_dir"] = candidate

    # Step 3 — fallback: largest python folder 
    # that isn't tests/docs/scripts
    if not result["source_dir"]:
        skip = {"tests", "test", "docs", "doc", "scripts", "examples", "example"}
        candidates = [
            d for d in repo_path.iterdir()
            if d.is_dir()
            and d.name not in skip
            and not d.name.startswith(".")
            and any(d.rglob("*.py"))
        ]
        if candidates:
            best = max(candidates, key=lambda d: len(list(d.rglob("*.py"))))
            # handle src layout — look one level deeper
            if best.name == "src":
                inner = [d for d in best.iterdir() if d.is_dir() and any(d.rglob("*.py"))]
                if inner:
                    best = max(inner, key=lambda d: len(list(d.rglob("*.py"))))
            result["source_dir"] = best


    # Step 4 — detect docs
    docs_candidates = [
        "docs/en/docs", "docs/en", "docs", "doc", "documentation"
    ]
    for candidate in docs_candidates:
        path = repo_path / candidate
        if path.exists() and any(path.rglob("*.md")):
            result["docs_dir"] = path
            break
    
    # fallback — README only
    if not result["docs_dir"] and (repo_path / "README.md").exists():
        result["docs_dir"] = repo_path

    # Step 5 — detect tests
    tests_candidates = ["tests", "test", "spec"]
    for candidate in tests_candidates:
        path = repo_path / candidate
        if path.exists() and any(path.rglob("*.py")):
            result["tests_dir"] = path
            break

    return result
