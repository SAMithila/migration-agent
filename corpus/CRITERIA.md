# Corpus acceptance criteria

Fixed before screening began, so thresholds couldn't be quietly relaxed to hit a target count. Where they *were* relaxed, the change and reason are recorded below.

## Static screen (metadata only, no clone)

| Criterion | Initial | Final | Reason for change |
|---|---|---|---|
| Stars | 50–3000 | 15–3000 | Initial floor left 23 candidates; too thin for expected Docker attrition |
| Last push | within 18 months | within 30 months | The target population (repos on an old pin) is old by construction |
| License | MIT, Apache-2.0, BSD-2/3 | + ISC, MPL-2.0, Unlicense, 0BSD, and unset | Many repos carry a permissive LICENSE file with no SPDX id set by GitHub |
| Repo size | < 50 MB | < 80 MB | Same reason as the star floor |
| Archived | reject | reject | — |
| Fork | reject | reject | — |

## Clone screen (requires clone)

- Has a test directory or test files
- Dependency pin confirmed by reading an actual dependency file, not by trusting the search hit
- Install command derivable from the main dependency file — never a dev/test-only file
- Service dependencies (Postgres, Redis, MySQL) flagged via `docker-compose.yml` or `conftest.py`; kept in the pool but tracked separately

## Docker baseline (ground truth)

A repo enters the manifest only if all of the following hold:

- The install command completes with a zero exit status (with `set -o pipefail` — see README)
- `pytest` collects and runs
- Zero failures and zero errors
- At least one test passes
- **Two consecutive runs produce identical pass / fail / error / skip counts**

The determinism requirement is the important one. A suite that passes 87 tests once and 86 the next time cannot serve as a before/after oracle — any migration result measured against it is noise.

Timeouts: 10 minutes per repo, covering install and both test runs. A repo needing longer is a poor corpus candidate regardless of whether it would eventually succeed.
