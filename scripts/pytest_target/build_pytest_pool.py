import json

with open("corpus/pytest_clone_screen.json") as f:
    results = json.load(f)

clean = [r for r in results if not r["flags"]]

service_flags = {"has_docker_compose", "conftest_needs_service"}
service_only = [r for r in results
                 if r["flags"]
                 and set(r["flags"]).issubset(service_flags)
                 and r["has_tests"] and r["unittest_style_confirmed"]]

pool = clean + service_only
print(f"Clean: {len(clean)}")
print(f"Service-dependent (usable): {len(service_only)}")
print(f"Total pool: {len(pool)}")

with open("corpus/pytest_docker_pool.json", "w") as f:
    json.dump(pool, f, indent=2)
