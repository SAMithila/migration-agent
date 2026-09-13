# migration-agent

A reproducible pipeline for building **verified corpora** of real-world Python repositories — repos whose test suites are confirmed green in a clean container, pinned to an exact commit — for use as ground truth when evaluating automated code migration.

Built as the foundation for an LLM-assisted SQLAlchemy 1.4 → 2.0 migration tool. The corpus-building stage turned out to be the substantive part, and is what this repo documents.

---

## The finding

Automated GitHub code search is a poor way to find repositories with currently-passing test suites.

Across two unrelated migration targets, **~7% of candidates that reached containerized testing had a green, deterministic baseline**:

| Target | Candidates harvested | Passed static screen | Reached Docker | Green + deterministic |
|---|---|---|---|---|
| SQLAlchemy 1.4 → 2.0 | 522 | 80 | 29 | 2 |
| unittest → pytest | 364 | 42 | 15 | 1 |

The failure modes at the Docker stage:

| Reason | SQLAlchemy | pytest |
|---|---|---|
| Install failed | 17 | 10 |
| Tests ran but failed | 10 | 4 |
| Green + deterministic | 2 | 1 |

**Why this happens:** searching for "code that still uses an old API" selects for unmaintained projects by construction. A repo that pinned SQLAlchemy 1.4 and never upgraded is, on average, a repo nobody is maintaining — which is also why its dependency tree no longer resolves. The same holds for `unittest.TestCase`-style tests: the pattern correlates with age, and age correlates with rot.

Dominant install failures were unresolvable dependency conflicts and build failures on pinned transitive dependencies (`numpy` wheels that no longer build on Python 3.11/ARM64, `poetry-core` version constraints, undeclared runtime dependencies like `msgpack`).

**Implication:** for corpus construction, a visible passing CI badge is a far stronger signal than any keyword query. Hand-curation of 20 repos would likely outperform the 886 candidates screened here.

---

## Verified corpus

`corpus/final_manifest.json` — three repositories, pinned to commit, install command recorded, test suite confirmed green across two consecutive runs in a clean container.

| Repo | SHA | Target | Baseline |
|---|---|---|---|
| `linkedin/iris-relay` | `609ee35e` | SQLAlchemy 1.4 → 2.0 | 11 passed, 0 failed |
| `farahats9/sqlalchemy-celery-beat` | `6791fd0f` | SQLAlchemy 1.4 → 2.0 | 87 passed, 0 failed |
| `py2many/py2many` | `a3c39224` | unittest → pytest | 98 passed, 1594 skipped¹ |

¹ All skips are missing target-language toolchains (`rustfmt`, `gofmt`, `dart`, `zig`, `clang-format` …). Expected for a transpiler test suite in a bare Python container; verified via `pytest -rs`.

Every entry ran twice with identical pass/fail/skip counts. Non-deterministic suites were rejected — a flaky baseline can't tell you whether a migration broke something.

---

## Pipeline

```
harvest → hydrate → static screen → clone screen → docker baseline → manifest
```

| Stage | Script | What it does |
|---|---|---|
| 1. Harvest | `gh search code` (see below) | Find candidate repos by code pattern |
| 2. Merge | `scripts/merge_candidates.py` | Flatten and dedupe by repo name |
| 3. Hydrate | `scripts/hydrate_metadata.py` | Pull stars, license, last-push, size via API |
| 4. Static screen | `scripts/screen_static.py` | Filter on metadata alone — no cloning |
| 5. Clone screen | `scripts/screen_clone.py` | Clone; confirm tests exist, pin is real, detect install command and service deps |
| 6. Pool | `scripts/build_docker_pool.py` | Combine clean + service-dependent candidates |
| 7. Baseline | `scripts/docker_baseline.py` | Install and run the suite twice in a container |
| 8. Finalize | `scripts/finalize_manifest.py` | Emit the verified manifest |

`scripts/categorize_failures.py` buckets install failures by cause.

### Harvest queries

GitHub's code search grammar is stricter than it looks. Notes that cost time:

- `filename:` works; `path:` silently returns nothing for the same query.
- Wildcards are not supported — `filename:test_*.py` matches files literally named `test_*.py`.
- `gh search code` has no `--sort` flag; results cannot be biased toward recency.
- Bare multi-term queries (`unittest.TestCase flask`) return zero results without a `language:` qualifier.

```bash
gh search code 'SQLAlchemy==1.4 filename:requirements.txt' --limit 100 --json repository,path,url > corpus/q1.json
gh search code 'SQLAlchemy>=1.4 filename:setup.py'         --limit 100 --json repository,path,url > corpus/q2.json
gh search code 'sqlalchemy filename:pyproject.toml'        --limit 100 --json repository,path,url > corpus/q3.json
gh search code 'SQLAlchemy~=1.4 filename:requirements.txt' --limit 100 --json repository,path,url > corpus/q4.json
```

---

## Reproducing

```bash
# prerequisites: Docker Desktop running, gh authenticated, Python 3.11
conda create -n migagent python=3.11 -y && conda activate migagent
pip install -r requirements.txt
gh auth login

docker build -t migagent-base:latest -f docker/Dockerfile.base .

# run the four harvest queries above, then:
python3 scripts/merge_candidates.py
python3 scripts/hydrate_metadata.py
python3 scripts/screen_static.py
python3 scripts/screen_clone.py
python3 scripts/build_docker_pool.py
python3 scripts/docker_baseline.py
python3 scripts/finalize_manifest.py
```

Budget ~20GB free disk. Cloned repos land in `corpus/repos/` (gitignored) and each container run pulls its own dependency set.

---

## Engineering notes

Bugs found the hard way, kept here because each one silently corrupted results before it was caught:

**`set -o pipefail` is mandatory, and only for the install chain.** Piping `pip install` to `tail` makes bash report `tail`'s exit code. Installs failed, the `&&` chain continued anyway, and doomed test runs were recorded as legitimate failures. But pytest exits non-zero on any test failure — which is normal data, not an error — so the test runs must be chained with `;`, not `&&`, or every repo with a failing test is misreported as a broken pipeline.

**Python set iteration is not deterministic across processes.** `PYTHONHASHSEED` is randomized per run, so iterating a `set` of file paths returned different orderings on identical inputs. Whichever dependency file happened to be checked first won, so `install_cmd` for the same repo differed between runs — a repo verified green one day installed only its dev-requirements the next and went red. Fixed by using a priority-ordered list and `sorted()` glob results.

**`--network=none` blocks pip.** Isolation during the test run is desirable; during install it means nothing installs and `pytest: command not found`.

**Docker Desktop's VM goes read-only when the host disk fills.** Errors surface as `write /var/lib/desktop-containerd/...: read-only file system` and every container run fails identically, which reads like a code bug. Also: `df -h /` reports the macOS **System** volume, not the Data volume where everything actually lives — check `diskutil apfs list` instead.

**Test-file naming conventions vary more than three globs can cover.** `test_*.py`, `*_test.py`, `tests.py` missed `ActionTests.py`, `runtests.py`, `unittests.py`, `BuilderTests.py`. Better approach: match any `.py` with `test` in the name, then filter on file *content*.

**Dependency pins are rarely where you expect.** Confirmed pins turned up in `setup.cfg`, `Pipfile.lock`, `cnpj_requirements.txt`, `prefect-requirements.txt`. Root-level exact-filename matching missed most of them.

**Repos need their dev/test requirements installed too.** A suite failing on `fixture 'mocker' not found` isn't a broken repo — it's `pytest-mock` sitting in an uninstalled `dev_requirements.txt`.

---

## Status

Phase 0 (corpus construction) is complete. The migration engine itself — LibCST codemods, residue detection, the LLM patch loop, and anti-cheating verification — was not built.

Design, for anyone picking this up:

1. **Deterministic pass.** LibCST codemods for mechanical rewrites (`session.query(M).filter_by(**k).first()` → `session.scalars(select(M).filter_by(**k)).first()`, `declarative_base(cls=Base)` → a `DeclarativeBase` subclass). Record the pass rate — it is the baseline the LLM must beat.
2. **Residue detection.** After the codemod pass, collect failing tests with tracebacks and remaining deprecation warnings. This is the LLM's work queue; it never touches files the codemod handled.
3. **Patch loop.** Per failing file: send the failing function, its traceback, and the relevant migration-guide section. Request aider-style `SEARCH`/`REPLACE` blocks — more reliable from an LLM than unified diffs, and they fail loudly on mismatch. Apply on a branch, run the affected tests, then the full suite. Three attempts, then mark unresolved and move on.
4. **Anti-cheating verification.** The part that matters. LLMs pass tests by weakening tests. Reject any diff touching `test_*` / `tests/`; require assertion count (AST `Assert` nodes + `pytest.raises` blocks) not to decrease; reject new `skip`/`xfail` marks; require the collected test count to match baseline exactly.
5. **Report.** Per repo: baseline, codemod-only result, post-LLM result, tokens, cost, retries. Plus a failure taxonomy — bucketing what the tool *couldn't* fix is more interesting than the headline percentage.

Corpus size is the binding constraint on any claim this tool could make. With three repos, it can demonstrate a working method but not a success rate. Anyone continuing should hand-curate 15–20 repos with visible passing CI first — the finding above is that automated search will not get you there.

---

## Layout

```
migration-agent/
├── corpus/
│   ├── final_manifest.json     # the verified corpus
│   ├── CRITERIA.md             # acceptance criteria, fixed before screening
│   └── repos/                  # clones (gitignored)
├── docker/
│   └── Dockerfile.base
├── scripts/
└── logs/                       # per-repo container output (gitignored)
```

## License

MIT
