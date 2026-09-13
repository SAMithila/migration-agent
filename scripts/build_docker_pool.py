import json

with open("corpus/clone_screen.json") as f:
    results = json.load(f)

clean = [r for r in results if not r["flags"]]

service_flags = {"has_docker_compose", "conftest_needs_service"}
service_only = [r for r in results
                 if r["flags"]  # must have at least one flag
                 and set(r["flags"]).issubset(service_flags)
                 and r["sqlalchemy_pin"]]

pool = clean + service_only
print(f"Clean: {len(clean)}")
print(f"Service-dependent (pin confirmed, otherwise clean): {len(service_only)}")
print(f"Total Docker baseline pool: {len(pool)}")

with open("corpus/docker_pool.json", "w") as f:
    json.dump(pool, f, indent=2)
