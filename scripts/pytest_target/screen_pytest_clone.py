import json
import subprocess
import os
import re
import glob

with open("corpus/pytest_passed_static.json") as f:
    repos = json.load(f)

os.makedirs("corpus/repos", exist_ok=True)

def run(cmd, cwd=None, timeout=60):
    try:
        return subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True,
                               text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None

DEP_GLOBS = [
    "setup.py", "pyproject.toml", "setup.cfg",
    "requirements.txt", "requirement.txt", "req.txt",
    "Pipfile", "Pipfile.lock", "poetry.lock",
    "constraints.txt",
]

UNITTEST_PATTERN = re.compile(
    r'unittest\.TestCase|self\.assert(Equal|True|False|Raises|In|IsNone|IsNotNone|ListEqual|DictEqual|AlmostEqual|NotEqual)\b'
)
PYTEST_DEP_PATTERN = re.compile(r'\bpytest\b', re.IGNORECASE)

results = []

for i, r in enumerate(repos):
    full_name = r["full_name"]
    slug = full_name.replace("/", "__")
    dest = f"corpus/repos/{slug}"

    print(f"[{i+1}/{len(repos)}] {full_name}")

    entry = {"repo": full_name, "flags": [], "install_cmd": None, "has_tests": False,
              "unittest_style_confirmed": False, "pytest_available": False, "needs_service": False}

    if not os.path.isdir(dest):
        clone = run(f"git clone --depth 1 https://github.com/{full_name}.git {dest}", timeout=90)
        if clone is None or clone.returncode != 0:
            entry["flags"].append("clone_failed")
            results.append(entry)
            continue

    # Broadened: find ANY .py file with "test" anywhere in the filename,
    # case-insensitive - naming conventions vary too much to guess narrowly.
    # Content check below does the real filtering.
    test_file_list = []
    for root, dirs, files in os.walk(dest):
        if "/.git" in root:
            continue
        depth = root[len(dest):].count(os.sep)
        if depth > 5:
            dirs[:] = []
            continue
        for fname in files:
            if fname.endswith(".py") and "test" in fname.lower():
                test_file_list.append(os.path.relpath(os.path.join(root, fname), dest))

    entry["has_tests"] = bool(test_file_list)
    if not entry["has_tests"]:
        entry["flags"].append("no_tests_found")

    # Confirm real unittest-style content in at least one candidate file
    # (scan up to 30 files - repos can have many test files, cap for speed)
    unittest_confirmed = False
    for tf in test_file_list[:30]:
        path = os.path.join(dest, tf)
        try:
            with open(path, errors="ignore") as f:
                content = f.read()
            if UNITTEST_PATTERN.search(content):
                unittest_confirmed = True
                break
        except (IOError, OSError):
            continue
    entry["unittest_style_confirmed"] = unittest_confirmed
    if not unittest_confirmed:
        entry["flags"].append("no_confirmed_unittest_style")

    dep_files_found = []
    seen_paths = set()
    for pattern in DEP_GLOBS:
        matches = sorted(glob.glob(os.path.join(dest, "**", pattern), recursive=True))
        for m in matches:
            if "/node_modules/" not in m and "/.git/" not in m and m not in seen_paths:
                dep_files_found.append(m)
                seen_paths.add(m)

    matched_file = dep_files_found[0] if dep_files_found else None
    pytest_found = False
    for path in dep_files_found:
        try:
            with open(path, errors="ignore") as f:
                content = f.read()
            if PYTEST_DEP_PATTERN.search(content):
                pytest_found = True
        except (IOError, OSError):
            continue
    entry["pytest_available"] = pytest_found

    if matched_file:
        base = os.path.basename(matched_file)
        rel = os.path.relpath(matched_file, dest)
        if base in ("setup.py", "pyproject.toml", "setup.cfg"):
            entry["install_cmd"] = "pip install -e ."
        elif "Pipfile" in base:
            entry["install_cmd"] = "pipenv install"
        elif "poetry.lock" in base:
            entry["install_cmd"] = "poetry install"
        elif "requirements" in base or base.startswith("req"):
            entry["install_cmd"] = f"pip install -r {rel}"
        else:
            entry["install_cmd"] = "pip install -e ."
    else:
        entry["flags"].append("no_dependency_file_found")

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

with open("corpus/pytest_clone_screen.json", "w") as f:
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
