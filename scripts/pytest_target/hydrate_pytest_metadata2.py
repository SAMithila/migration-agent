import json
import subprocess
import time

with open("corpus/pytest_candidates.json") as f:
    candidates = json.load(f)

with open("corpus/pytest_metadata.json") as f:
    existing = json.load(f)
existing_names = {r["full_name"] for r in existing}

new_repos = [c["repo"] for c in candidates if c["repo"] not in existing_names]
print(f"Already hydrated: {len(existing_names)}")
print(f"New repos to hydrate: {len(new_repos)}")

results = list(existing)
failed = []

for i, repo in enumerate(new_repos):
    try:
        out = subprocess.run(
            ["gh", "api", f"repos/{repo}",
             "--jq", '{full_name, stargazers_count, pushed_at, license: .license.spdx_id, size, archived, fork, default_branch}'],
            capture_output=True, text=True, timeout=15
        )
        if out.returncode != 0:
            failed.append(repo)
            continue
        meta = json.loads(out.stdout)
        results.append(meta)
    except Exception:
        failed.append(repo)

    if (i + 1) % 25 == 0:
        print(f"  {i+1}/{len(new_repos)} done...")
        time.sleep(1)

print(f"\nTotal hydrated: {len(results)}")
print(f"Failed: {len(failed)}")

with open("corpus/pytest_metadata.json", "w") as f:
    json.dump(results, f, indent=2)

print("Updated corpus/pytest_metadata.json")
