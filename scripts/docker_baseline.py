import json
import subprocess
import os
import re
import glob

with open("corpus/docker_pool.json") as f:
    pool = json.load(f)

os.makedirs("logs", exist_ok=True)
manifest = []

DEV_REQ_PATTERNS = [
    "dev_requirements.txt", "dev-requirements.txt", "requirements-dev.txt",
    "requirements_dev.txt", "test_requirements.txt", "test-requirements.txt",
    "requirements-test.txt", "requirements_test.txt",
]

def run(cmd, timeout):
    try:
        return subprocess.run(cmd, shell=True, capture_output=True,
                               text=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        class Fake:
            returncode = -1
            stdout = str(e.stdout or "")[-2000:]
            stderr = "TIMEOUT"
        return Fake()

def parse_pytest_summary(output):
    m = re.search(r'(\d+) passed', output)
    passed = int(m.group(1)) if m else 0
    m = re.search(r'(\d+) failed', output)
    failed = int(m.group(1)) if m else 0
    m = re.search(r'(\d+) error', output)
    errors = int(m.group(1)) if m else 0
    m = re.search(r'(\d+) skipped', output)
    skipped = int(m.group(1)) if m else 0
    return {"passed": passed, "failed": failed, "errors": errors, "skipped": skipped}

def find_dev_req_files(repo_path):
    found = []
    for pattern in DEV_REQ_PATTERNS:
        matches = glob.glob(os.path.join(repo_path, "**", pattern), recursive=True)
        found.extend(matches)
    return found

for i, r in enumerate(pool):
    full_name = r["repo"]
    slug = full_name.replace("/", "__")
    host_path = os.path.abspath(f"corpus/repos/{slug}")
    install_cmd = r.get("install_cmd") or "pip install -e ."
    install_cmd = re.sub(r'\s*\(.*?\)\s*$', '', install_cmd)

    print(f"[{i+1}/{len(pool)}] {full_name}")

    entry = {
        "repo": full_name,
        "install_cmd": install_cmd,
        "status": "unknown",
        "sha": None,
        "runs": [],
    }

    sha_result = run(f"git -C {host_path} rev-parse HEAD", timeout=10)
    entry["sha"] = sha_result.stdout.strip() if sha_result.returncode == 0 else None

    dev_reqs = find_dev_req_files(host_path)
    dev_install_parts = []
    for dr in dev_reqs:
        rel = os.path.relpath(dr, host_path)
        dev_install_parts.append(f"pip install -q -r {rel}")
    dev_install_cmd = " && ".join(dev_install_parts) if dev_install_parts else "true"
    entry["dev_req_files"] = [os.path.relpath(d, host_path) for d in dev_reqs]

    # pipefail only matters for the INSTALL chain - a real install failure
    # should abort. The two pytest runs use ';' so a nonzero pytest exit
    # (i.e. real test failures, which is expected/valid data) doesn't
    # prevent the DONE markers from printing.
    inner_cmd = (
        f"set -o pipefail && "
        f"pip install --quiet --upgrade pip && "
        f"{install_cmd} -q && "
        f"{dev_install_cmd} && "
        f"pip install --quiet pytest pytest-mock && "
        f"echo '---INSTALL_DONE---' ; "
        f"pytest -q --tb=short -p no:cacheprovider 2>&1 | tail -60 ; "
        f"echo '---RUN1_DONE---' ; "
        f"pytest -q --tb=short -p no:cacheprovider 2>&1 | tail -60 ; "
        f"echo '---RUN2_DONE---'"
    )

    docker_cmd = (
        f'docker run --rm -v "{host_path}:/w" -w /w '
        f'migagent-base:latest bash -c "{inner_cmd}" 2>&1 | tail -80'
    )

    result = run(docker_cmd, timeout=600)
    output = result.stdout + result.stderr

    with open(f"logs/{slug}.log", "w") as f:
        f.write(output)

    if "---INSTALL_DONE---" not in output:
        entry["status"] = "install_failed"
    else:
        runs_text = output.split("---INSTALL_DONE---")[1]
        run_chunks = runs_text.split("---RUN1_DONE---")
        if len(run_chunks) < 2:
            entry["status"] = "test_run_failed"
        else:
            run1_summary = parse_pytest_summary(run_chunks[0])
            entry["runs"].append(run1_summary)
            remainder = run_chunks[1]
            if "---RUN2_DONE---" in remainder:
                run2_text = remainder.split("---RUN2_DONE---")[0]
                run2_summary = parse_pytest_summary(run2_text)
                entry["runs"].append(run2_summary)

            if len(entry["runs"]) == 2:
                r1, r2 = entry["runs"]
                if r1["failed"] == 0 and r1["errors"] == 0 and r1["passed"] > 0 and r1 == r2:
                    entry["status"] = "green_deterministic"
                elif r1["failed"] == 0 and r1["errors"] == 0 and r1["passed"] > 0:
                    entry["status"] = "green_but_flaky"
                else:
                    entry["status"] = "red"
            else:
                entry["status"] = "partial_run"

    manifest.append(entry)
    print(f"    -> {entry['status']}")

with open("corpus/manifest.json", "w") as f:
    json.dump(manifest, f, indent=2)

from collections import Counter
statuses = Counter(e["status"] for e in manifest)
print("\n=== BASELINE SUMMARY ===")
for status, count in statuses.most_common():
    print(f"  {status}: {count}")
