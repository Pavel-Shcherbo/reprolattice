# Saved runs and baseline review

The workbench connects executed inventory suites to the persistent run registry. It retains actual suite reports, opens recorded case evidence, compares saved runs, inspects case history and moves named passing baselines with generation checks. This path is local; it does not publish reports or access a hosted CI service.

## Review a real run

Start `python3 -m reprolattice.web`, then open `http://127.0.0.1:8413/#archive`.

1. Follow **Run inventory suite** and run the bundled five-case suite. The faulty-client control deliberately breaks three retry variants.
2. Enter an optional run label and choose **Save suite run**. Saving does not execute the report again. A failed suite can be saved for investigation.
3. Select a saved run and a case to inspect the recorded checks, application output, input identities, artifacts and execution context. Results are read from the archive rather than replaced with a fresh sample.
4. Select a reference under **Compare against**. A reference can be another loaded run or a named baseline. Choose **Compare selected run** to apply the strict comparison policy.
5. For a complete passing candidate, enter a baseline name and a review reason, then choose **Set selected run as baseline**. Failed or filtered suites cannot be promoted.

The included control produces three regressions when comparing the corrected client to the faulty client, and three fixes in the reverse direction. Four application cases have a changed subject command, including a permission-error case that still passes. A changed subject is not automatically a regression. Test fixtures and assertion conditions remain unchanged in this control.

## Durable evidence and identities

The archive lives in `run-workbench/runs.sqlite` beneath `REPROLATTICE_STATE_DIR`, or beneath `.local/reprolattice` in the launching directory when that variable is unset. Its workbench project is `inventory-workbench`. Viewing an empty archive does not initialize the database; saving the first valid report creates it. Page reload and service restart preserve records and baseline events.

Saving uses a request key and canonical report/metadata identities. Retrying the same uncertain save returns the existing record. Reusing a key with different content or a different label is rejected. Controls are disabled while saving so the submitted report and label remain consistent.

The browser submits the completed suite report it received from the local runner. Reports are validated before database initialization. The archive route does not execute commands embedded in submitted data. The content identifier recorded in the revision field is derived from supplied subject input/command metadata. It is not an authenticated Git commit or a provider signature. Execution context is retained from the report, rather than synthesized from the importing process.

Metadata listings identify available records; opening a record validates its full payload and identities. Baseline inspection also verifies that its target remains a complete passing suite. A damaged target fails visibly. These checks establish content integrity within the local evidence model, not authentication against a remote source system.

## Comparison and baseline consistency

Comparison pairs cases by source and parameter identities. The strict default gate exposes regressions, changed test inputs, lost coverage, missing/changed execution context, filtered or incomplete execution and candidate failures. The browser does not silently weaken those conditions. Selecting another candidate or reference invalidates the previous comparison and its export.

Named baseline comparison resolves the pointer, generation and both archived reports within one SQLite read view. The request must name the generation observed by the page. If another review changes that baseline, the stale comparison fails and offers no completed comparison export. Refresh the saved runs to inspect the current generation.

Baseline changes require the expected generation and a nonblank review reason. They append events without rewriting earlier run reports. Generation zero creates a new name; later changes must use the current number. The name list is metadata; inspecting a specific baseline verifies the referenced report. Case evidence is immutable through the public archive operations; retention and deletion remain future work.

The interface guards delayed inspection, history and comparison responses. An old response cannot replace evidence for a newly selected run. Native run/case buttons support keyboard selection. The mobile comparison table keeps the case and classification visible and combines before/after states into one readable line.

## History, exports and limits

Run history is newest first and continues in pages of 25. The keyset cursor remains stable when new runs arrive. Baseline names and change history also provide continuation controls. Case history is chronological across all parameter variants of the selected source case, with an exact status filter. It does not claim to show only the currently selected variant.

**Export saved JSON** returns the stored suite report. **Export saved JUnit** regenerates XML from that same report. **Export comparison** includes the strict policy, before/after identities, context/input changes, findings and the baseline generation when applicable. JSON and JUnit exports are available independently of the current suite form settings.

The HTTP server accepts JSON requests up to 1 MiB; the lower archive contract accepts reports up to 8 MiB through the CLI. Larger reports should use the CLI rather than truncating evidence for a browser save. Labels are capped at 128 characters, baseline names at 80 and review reasons at 512. Case evidence displayed in the browser is shortened after 65,536 characters; exporting JSON retains the complete stored report. The registry's existing project/run/baseline limits still apply.

The workbench retains the existing graphite theme. Readable warm accents identify selection and links; failure/success colors carry outcome meaning. Neutral surfaces, explicit button labels and the before/after table carry the review workflow.

## Verification and remaining scope

Fifteen new archive/workbench checks cover real healthy/faulty suites, save retries, cold concurrent saves, namespace isolation, strict comparisons, named baseline generations, filtered/failed candidates, damaged payloads/pointers, newest-first pagination, baseline history and JSON/JUnit consistency. The complete current suite count is retained in `verification.json`.

Clean installation controls exercise the API outside the checkout. Real browser checks cover saving, baseline review, regression/fix comparisons, failed promotion, filtered case history, keyboard selection, reload persistence, generation conflicts and deliberately delayed responses. Downloaded reports/comparisons and JUnit are independently checked against stored records and recomputed comparisons.

Evidence: [installed API controls](archive-workbench-verification.json), [browser and export checks](archive-browser-verification.json), [desktop](archive-desktop.png), [mobile](archive-mobile.png). SQLite-state inspection, additional database providers, migration workflows, signed remote provenance, retention/paged full audit and the 20,000 useful-SLOC requirement remain open.

Current verification: 144 Reprolattice tests and 418 portfolio tests passed. Clean installed archive controls passed; current project-specific production source is 7,195 SLOC, below 20,000. No remote publication was performed.
