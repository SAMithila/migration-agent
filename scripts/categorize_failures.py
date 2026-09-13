import json
import os
import re

with open("corpus/manifest.json") as f:
    manifest = json.load(f)

failed = [e for e in manifest if e["status"] == "install_failed"]

categories = {
    "numpy/pandas build": r"numpy|pandas.*build|distutils",
    "python version incompatible": r"requires-python|python_requires|Requires-Python",
    "missing system lib": r"fatal error.*\.h|command '.*' failed|No such file or directory.*\.(so|h)",
    "dependency resolution conflict": r"ResolutionImpossible|version solving failed|conflicting",
    "package not found": r"Could not find a version|No matching distribution",
    "timeout": r"TIMEOUT",
    "syntax/import error at setup": r"SyntaxError|ModuleNotFoundError.*setup",
}

results = {}
for e in failed:
    slug = e["repo"].replace("/", "__")
    log_path = f"logs/{slug}.log"
    if not os.path.isfile(log_path):
        results[e["repo"]] = "no_log"
        continue
    with open(log_path, errors="ignore") as f:
        content = f.read()
    matched = "uncategorized"
    for cat, pattern in categories.items():
        if re.search(pattern, content, re.IGNORECASE):
            matched = cat
            break
    results[e["repo"]] = matched

from collections import Counter
counts = Counter(results.values())
print("=== FAILURE CATEGORIES ===")
for cat, count in counts.most_common():
    print(f"  {cat}: {count}")

print("\n=== DETAIL ===")
for repo, cat in results.items():
    print(f"  [{cat}] {repo}")
