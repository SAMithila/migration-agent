import json
import subprocess
import os
import re
import glob

with open("corpus/passed_static.json") as f:
    repos = json.load(f)

os.makedirs("corpus/repos", exist_ok=True)

DEP_GLOBS = [
    "setup.py", "pyproject.toml", "setup.cfg",
    "requirements.txt", "requirement.txt", "req.txt",
    "Pipfile", "Pipfile.lock", "poetry.lock",
    "constraints.txt",
]

PIN_PATTERNS = [
    r'sqlalchemy\s*[><=~!]+\s*["\']?1\.4',
    r'sqlalchemy["\']?\s*=\s*["\']?\^?1\.4',
    r'sqlalchemy\[[a-z]*\]\s*[><=~!]+\s*1\.4',
    r'name\s*=\s*"sqlalchemy".{0,80}?version\s*=\s*"1\.4',
    r'sqlalchemy\s*<\s*2\.0',
]

def run(cmd, cwd=None, timeout=60):
    try:
        return subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True,
                               text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None

results = []

for i, r in enumerate(repos):
    full_name = r["full_name"]
    slug = full_name.replace("/", "__")
    dest = f"corpus/repos/{slug}"

    print(f"[{i+1}/{len(repos)}] {full_name}")

    entry = {"repo": full_name, "flags": [], "install_cmd": None, "has_tests": False,
              "sqlalchemy_pin": None, "pin_confidence": None, "needs_service": False}

    if not os.path.isdir(dest):
        clone = run(f"git clone --depth 1 https://github.com/{full_name}.git {dest}", timeout=90)
        if clone is None or clone.returncode != 0:
            entry["flags"].append("clone_failed")
            results.append(entry)
            continue

    has_test_dir = os.path.isdir(os.path.join(dest, "tests")) or \
                    os.path.isdir(os.path.join(dest, "test"))
    has_test_files = run("find . -maxdepth 4 -iname 'test_*.py' -o -iname '*_test.py'", cwd=dest, timeout=15)
    entry["has_tests"] = has_test_dir or bool(has_test_files and has_test_files.stdout.strip())
    if not entry["has_tests"]:
        entry["flags"].append("no_tests_found")

    # Deterministic, priority-ordered search: main package files first,
    # never dev/test-only files (those are handled separately at install time)
    dep_files_found = []
    seen_paths = set()
    for pattern in DEP_GLOBS:
        matches = sorted(glob.glob(os.path.join(dest, "**", pattern), recursive=True))
        for m in matches:
            if "/node_modules/" not in m and "/.git/" not in m and m not in seen_paths:
                dep_files_found.append(m)
                seen_paths.add(m)

    pin_found = None
    pin_confidence = None
    matched_file = None
    for path in dep_files_found:
        try:
            if os.path.getsize(path) > 2_000_000:
                continue
            with open(path, errors="ignore") as f:
                content = f.read()
        except (IOError, OSError):
            continue
        for pattern in PIN_PATTERNS:
            m = re.search(pattern, content, re.IGNORECASE | re.DOTALL)
            if m:
                pin_found = m.group(0)[:60]
                matched_file = os.path.relpath(path, dest)
                pin_confidence = "weak" if pattern == PIN_PATTERNS[-1] else "strong"
                break
        if pin_found:
            break

    entry["sqlalchemy_pin"] = pin_found
    entry["pin_confidence"] = pin_confidence
    entry["pin_file"] = matched_file
    if not pin_found:
        entry["flags"].append("no_confirmed_1.4_pin")
    elif pin_confidence == "weak":
        entry["flags"].append("weak_pin_confidence")

    if matched_file:
        base = os.path.basename(matched_file)
        if base in ("setup.py", "pyproject.toml", "setup.cfg"):
            entry["install_cmd"] = "pip install -e ."
        elif "Pipfile" in base:
            entry["install_cmd"] = "pipenv install"
        elif "poetry.lock" in base:
            entry["install_cmd"] = "poetry install"
        elif "requirements" in base or base.startswith("req"):
            entry["install_cmd"] = f"pip install -r {matched_file}"
        else:
            entry["install_cmd"] = f"pip install -e ."

    for svc_file in ["docker-compose.yml", "docker-compose.yaml"]:
        if os.path.isfile(os.path.join(dest, svc_file)):
            entry["needs_service"] = True
            entry["flags"].append("has_docker_compose")
            break
    conftest_matches = glob.glob(os.path.join(dest, "**", "conftest.py"), recursive=True)
    for cpath in conftest_matches:
        try:
            with open(cpath, errors="ignore") as f:
                c = f.read()
            if re.search(r'postgres|psycopg|redis|mysql', c, re.IGNORECASE):
                entry["needs_service"] = True
                if "has_docker_compose" not in entry["flags"]:
                    entry["flags"].append("conftest_needs_service")
                break
        except (IOError, OSError):
            continue

    loc = run("find . -name '*.py' | xargs wc -l 2>/dev/null | tail -1", cwd=dest, timeout=15)
    if loc and loc.stdout.strip():
        try:
            entry["loc"] = int(loc.stdout.strip().split()[0])
        except (ValueError, IndexError):
            entry["loc"] = None

    results.append(entry)

with open("corpus/clone_screen.json", "w") as f:
    json.dump(results, f, indent=2)

clean = [r for r in results if not r["flags"]]
print(f"\n=== SUMMARY ===")
print(f"Total screened: {len(results)}")
print(f"Clean (no flags): {len(clean)}")

from collections import Counter
flag_counts = Counter()
for r in results:
    for f in r["flags"]:
        flag_counts[f] += 1
print("\nFlag breakdown:")
for flag, count in flag_counts.most_common():
    print(f"  {flag}: {count}")
