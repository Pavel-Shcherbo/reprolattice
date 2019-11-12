# Tasks

Updated: 2026-11-04. Actual status only; historical roadmap rows remain proposed.

| Task | Status | Evidence | Remaining work |
|---|---|---|---|
| Core domain path | Implemented; 54 current tests passed | `reprolattice/`, `tests/` | Expand adversarial coverage as the model grows |
| Local CLI | Implemented; CLI end-to-end checks passed | `reprolattice/__main__.py`, `examples/` | Retained in the local verification evidence |
| Local workbench | Implemented; local HTTP and reviewed browser flows passed | `reprolattice/web.py`, `reprolattice/static/` | Retain checks as new screens and flows are added |
| Broad product scope | Planned | `docs/PRODUCT_SCOPE.md` | Most platform subsystems require implementation |
| Weekly reconstruction plan | Written | `docs/proposed-weekly-roadmap.csv` | Proposed commit counts are not actual commits |
| Publication | Waiting on Pavel | Current request: do not upload without Pavel | No push or hosted deployment |
| Production implementation ≥20,000 useful SLOC | Not achieved | 2350 project-specific SLOC measured; not achieved | Implement and verify the broad subsystem scope without padding |
| Explicit HTTP capture | Implemented; capture and CLI checks passed | `reprolattice/capture.py`, `tests/test_capture.py` | Request matchers and assertions implemented and verified; expand capture protocol coverage |
| Installable local package | Verified from a clean environment outside the source tree | `docs/installed-verification.json`, `_build.py`, `MANIFEST.in` | Cross-version/platform qualification remains open |


Next executable increment: scenario collections, parameterized runs and portable report export, followed by application-state adapters.

Local reconstruction: five initial substantive stage commits created, plus verification, capture and matcher/assertion increments. No remote is configured; no upload was performed. The full dated roadmap remains proposed.

Current implementation verification: 54 tests passed, CLI checked, clean wheel installation and installed workbench HTTP checked. Broad scope and the 20,000-SLOC requirement remain open.

Verified increment: typed JSON-pointer application assertions, dynamic request matchers, shared CLI/workbench protocol verification and bounded process-output collection. 54 unit/integration tests passed; clean installed CLI and HTTP dynamic-scenario success/failure checks passed. Evidence: `docs/verification.json`, `docs/installed-verification.json`. The 20,000-SLOC and broad product requirements remain open.
