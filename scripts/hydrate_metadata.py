import json
import subprocess
import time

with open("corpus/candidates.json") as f:
    candidates = json.load(f)

repos = [c["repo"] for c in candidates]
print(f"Hydrating metadata for {len(repos)} repos...")

results = []
failed = []

for i, repo in enumerate(repos):
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
    except Exception as e:
        failed.append(repo)

    if (i + 1) % 25 == 0:
        print(f"  {i+1}/{len(repos)} done...")
        time.sleep(1)  # be polite to rate limits

print(f"\nHydrated: {len(results)}")
print(f"Failed: {len(failed)}")

with open("corpus/metadata.json", "w") as f:
    json.dump(results, f, indent=2)

if failed:
    with open("corpus/failed_hydration.json", "w") as f:
        json.dump(failed, f, indent=2)

print("Wrote corpus/metadata.json")
