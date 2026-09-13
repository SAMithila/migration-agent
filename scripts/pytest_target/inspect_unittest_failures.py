import json
import os

with open("corpus/pytest_clone_screen.json") as f:
    results = json.load(f)

failures = [r for r in results if "no_confirmed_unittest_style" in r["flags"]][:5]

for r in failures:
    slug = r["repo"].replace("/", "__")
    dest = f"corpus/repos/{slug}"
    print(f"\n=== {r['repo']} ===")
    # show what test files actually exist
    for root, dirs, files in os.walk(dest):
        if ".git" in root:
            continue
        for f in files:
            if "test" in f.lower() and f.endswith(".py"):
                print(f"  found: {os.path.join(root, f)}")
