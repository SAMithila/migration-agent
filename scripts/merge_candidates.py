import json

files = ["corpus/q1.json", "corpus/q2.json", "corpus/q3.json", "corpus/q4.json"]

all_hits = []
for fname in files:
    with open(fname) as f:
        data = json.load(f)
    print(f"{fname}: {len(data)} hits")
    all_hits.append(data)

flat = [hit for group in all_hits for hit in group]
print(f"\nTotal hits across all queries: {len(flat)}")

seen = {}
for hit in flat:
    repo = hit["repository"]["nameWithOwner"]
    if repo not in seen:
        seen[repo] = {
            "repo": repo,
            "url": hit["repository"]["url"],
            "matched_paths": [hit["path"]],
        }
    else:
        if hit["path"] not in seen[repo]["matched_paths"]:
            seen[repo]["matched_paths"].append(hit["path"])

candidates = list(seen.values())
print(f"Unique repos after dedup: {len(candidates)}")

with open("corpus/candidates.json", "w") as f:
    json.dump(candidates, f, indent=2)

print("\nWrote corpus/candidates.json")
