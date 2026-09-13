import json
from datetime import datetime, timezone
from collections import Counter

with open("corpus/pytest_metadata.json") as f:
    repos = json.load(f)

cutoff = datetime.now(timezone.utc).timestamp() - (30 * 30 * 24 * 3600)
allowed_licenses = {"MIT", "Apache-2.0", "BSD-3-Clause", "BSD-2-Clause", "ISC", "MPL-2.0", "Unlicense", "0BSD", None}

passed = []
rejected = []

for r in repos:
    reasons = []

    if r.get("archived"):
        reasons.append("archived")
    if r.get("fork"):
        reasons.append("fork")

    stars = r.get("stargazers_count", 0)
    if stars < 15:
        reasons.append(f"stars_too_low({stars})")
    if stars > 3000:
        reasons.append(f"stars_too_high({stars})")

    pushed_at = r.get("pushed_at")
    if pushed_at:
        pushed_ts = datetime.strptime(pushed_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
        if pushed_ts < cutoff:
            reasons.append("stale_pushed_over_30mo")
    else:
        reasons.append("no_pushed_at")

    license_id = r.get("license")
    if license_id not in allowed_licenses:
        reasons.append(f"license_not_allowed({license_id})")

    size_kb = r.get("size", 0)
    if size_kb > 80000:
        reasons.append(f"too_large({size_kb}KB)")

    if reasons:
        rejected.append({"repo": r["full_name"], "reasons": reasons})
    else:
        passed.append(r)

print(f"Passed static screen: {len(passed)}")
print(f"Rejected: {len(rejected)}")

with open("corpus/pytest_passed_static.json", "w") as f:
    json.dump(passed, f, indent=2)
with open("corpus/pytest_rejected_static.json", "w") as f:
    json.dump(rejected, f, indent=2)

reason_counts = Counter()
for r in rejected:
    for reason in r["reasons"]:
        reason_counts[reason.split("(")[0]] += 1

print("\nRejection breakdown:")
for reason, count in reason_counts.most_common():
    print(f"  {reason}: {count}")
