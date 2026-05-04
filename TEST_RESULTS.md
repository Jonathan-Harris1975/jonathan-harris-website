# TEST RESULTS

```bash
python3 -m py_compile scripts/audits/seo_aeo_geo_forensic.py scripts/audits/test_seo_aeo_geo_forensic.py
python3 -m unittest -v scripts.audits.test_seo_aeo_geo_forensic
```

Result: passed. 8 tests passed, 0 failed.

Covered:

- callback missing-field diagnostics
- analysis URL derivation from callback URL
- async job analysis payload extraction
- manual analysis URL override
- status URL resolution
- env fallback handling for callback config
- token masking in diagnostics
