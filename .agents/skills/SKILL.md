# Phase 4A Schema Gate

This repo uses the local Phase 4A gate for `schema-markup`.

Rules:
- Template-bounded schema patches may be applied automatically.
- Generated content pages must keep valid JSON-LD.
- Invalid JSON-LD is a release blocker.
- Podcast episode data is not collected in this static repo; the podcast hub is embed-led and the R2 podcast estate is authoritative.

Command:

```bash
python3 scripts/audits/schema_markup_gate.py --root . --json
```
