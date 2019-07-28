# Tasks

Updated: 2026-11-04. Actual status only; historical roadmap rows remain proposed.

| Task | Status | Evidence | Remaining work |
|---|---|---|---|
| Core domain path | Implemented; 18 current tests passed | `reprolattice/`, `tests/` | Expand adversarial coverage as the model grows |
| Local CLI | Implemented; CLI end-to-end checks passed | `reprolattice/__main__.py`, `examples/` | Retained in the local verification evidence |
| Local workbench | Implemented; local HTTP and reviewed browser flows passed | `reprolattice/web.py`, `reprolattice/static/` | Retain checks as new screens and flows are added |
| Broad product scope | Planned | `docs/PRODUCT_SCOPE.md` | Most platform subsystems require implementation |
| Weekly reconstruction plan | Written | `docs/proposed-weekly-roadmap.csv` | Proposed commit counts are not actual commits |
| Publication | Waiting on Pavel | Current request: do not upload without Pavel | No push or hosted deployment |
| Production implementation ≥20,000 useful SLOC | Not achieved | 1704 project-specific SLOC measured; not achieved | Implement and verify the broad subsystem scope without padding |
| Explicit HTTP capture | Implemented; capture and CLI checks passed | `reprolattice/capture.py`, `tests/test_capture.py` | Expand request matchers and assertions; retain final evidence |
| Installable local package | Verified from a clean environment outside the source tree | `docs/installed-verification.json`, `_build.py`, `MANIFEST.in` | Cross-version/platform qualification remains open |


Next executable increment: Add portable application-state assertions and process-tree cleanup, then introduce explicit local capture with reviewed redaction policies.

Local reconstruction: five initial substantive stage commits created, plus the current verification record. No remote is configured; no upload was performed. The full dated roadmap remains proposed.

Current implementation verification: 18 tests passed, CLI checked, clean wheel installation and installed workbench HTTP checked. Broad scope and the 20,000-SLOC requirement remain open.
