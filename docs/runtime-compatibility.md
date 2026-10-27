# Runtime and dependency compatibility

Review date: 2026-10-27. Scope: the M1 report-intake branch. No application
feature or package version upgrade is part of this compatibility change.

## Decisions

| Item | Decision | Reason / verification |
| --- | --- | --- |
| Python for the Windows walkthrough | Continue with Anaconda Python 3.12.15 in `myenv` | User verified the interpreter path/version, installed requirements, and reported a clean `pip check`; application acceptance is still in progress |
| Python 3.11 | Retain the existing Linux CI check | The original CI validated 3.11; retaining it avoids accidentally dropping an already tested environment |
| CI coverage | Add Linux 3.12 and Windows 3.12; keep Linux 3.11 | The existing Linux-only 3.11 job did not cover the user's Python minor version or operating system; the matrix runs the existing 24 tests, two no-model scenarios and recorded replay |
| FastAPI 0.141.1, google-genai 2.25.0, httpx 0.28.1, Pydantic 2.13.5, typing_extensions 4.16.0, Uvicorn 0.54.0 | Keep the six direct pins in requirements.txt | Existing Linux 3.11 CI and Linux 3.12 local checks pass; the user's 3.12 dependency check passes. No demonstrated M1 failure requires changing these pins |
| Transitive packages | Record the actual resolved packages in each CI job | Direct pins do not lock every dependency. Each clean CI installation runs pip check and logs Python/OS plus pip list; this is evidence of the tested set, not a complete cross-platform lockfile |
| Other Python minors, macOS, production deployment | No support claim yet | No relevant acceptance evidence in this project; avoid expanding the matrix without a deployment or maintainer need |

Package metadata in the local environment declares Python >=3.10 for both
FastAPI 0.141.1 and google-genai 2.25.0. A package's declared floor does not prove
that this application's code works on every Python release above that floor;
only the project checks establish the tested combinations.

## Evidence and status

| Environment | Observed evidence | Boundary |
| --- | --- | --- |
| Linux / Python 3.12.14 / venv | 24 unit tests, both no-model scenarios, replay and process-restart HTTP check passed on M1 commit 37b15c4; pip check repeated successfully in this review | Offline checks and local HTTP; no live Gemini call |
| Linux / Python 3.11 / GitHub Actions | M1 [run 40314543790](https://github.com/yushi916/property-operations-triage-agent/actions/runs/40314543790) completed successfully | Before the new matrix; exact interpreter patch was not recorded here |
| Windows / Anaconda Python 3.12.15 / myenv | User confirmed executable/version, dependency installation and `No broken requirements found` | Database initialization, tests and API/restart acceptance are pending; this is not a Windows end-to-end pass |
| New matrix: Linux / CPython 3.11.17 | 24 tests, pip check, both scenarios and replay passed | Hosted Ubuntu; no live model |
| New matrix: Linux / CPython 3.12.15 | 24 tests, pip check, both scenarios and replay passed | Hosted Ubuntu; no live model |
| New matrix: Windows / CPython 3.12.10 | 24 tests, pip check, both scenarios and replay passed | Hosted Windows Server 2025; not the user's Anaconda 3.12.15 |

The three-job results were observed for commit `450fc9e` in
[run 40466419616](https://github.com/yushi916/property-operations-triage-agent/actions/runs/40466419616).
[compatibility-evidence.json](compatibility-evidence.json) records the exact
interpreter, platform and installed package versions from those job logs.
The `3.12` selector resolved differently on Linux and Windows in this run;
minor selectors do not imply identical patch versions or Anaconda builds.
Each row above was checked for success, not inferred from the configuration.

`pip check` verifies declared dependency compatibility. It does not execute
the report workflow, test model APIs, or prove the absence of security issues.

The local set includes Starlette 1.10.0. Importing FastAPI's TestClient emits an
httpx-related deprecation warning in that set, but existing tests pass. Keep
it as a tracked maintenance observation; do not replace httpx or introduce
httpx2 without checking FastAPI/Starlette integration and rerunning the suite.

Before deployment, resolve and preserve a clean environment/constraints set
for the selected deployment target, separate from a shared Anaconda course
environment. Do not commit a raw dump of an unrelated local environment or
private package URLs. A later dependency update needs a concrete motivation
(incompatibility, an applicable fix, or a required capability), a small diff,
and the same regression checks.

## Sources

- [pip check](https://pip.pypa.io/en/stable/cli/pip_check/): scope of dependency-declaration validation.
- [GitHub Python testing](https://docs.github.com/en/actions/tutorials/build-and-test-code/python): selecting Python versions and matrix-based checks.
- [setup-python advanced usage](https://github.com/actions/setup-python/blob/main/docs/advanced-usage.md): matrix and hosted-environment selection.
- Installed package metadata and the project's requirements/CI/source files.

This change updates evidence coverage and support documentation, not the
business behavior under test. Continue M1 Windows acceptance before M2 work.
