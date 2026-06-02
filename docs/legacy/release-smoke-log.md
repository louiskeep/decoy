# Release-smoke log (append-only)

Every green fresh-install smoke run gets one line here. This is the artifact that retires the OSS-CLI launch README §8 R2 risk: "canonical smoke run has zero recorded executions."

Format per entry: date (YYYY-MM-DD), SHA tested at, Python version(s), how it was run (CI workflow URL or "manual <OS>"), one-line note.

Until the first green run lands, this file is the documented gap. Do not delete or edit prior entries.

| Date | SHA | Python | Run | Notes |
|------|-----|--------|-----|-------|
| _no green runs yet_ | | | | OSS.1 commit 3 (2026-06-02) shipped the gate; first run will land on the next `workflow_dispatch` or tag push. |
