# Test results

## Passed

```bash
python3 -m py_compile scripts/audits/seo_aeo_geo_forensic.py scripts/audits/test_seo_aeo_geo_forensic.py
python3 -m unittest -v scripts.audits.test_seo_aeo_geo_forensic
```

Result: passed. 8 tests passed, 0 failed.

Coverage included:
- Callback URL derivation.
- Async analysis response extraction.
- Relative status URL handling.
- Runtime env fallback for callback URL/token.
- Safe masking of token-like response details.

## Not run

The live GitHub Actions workflow and R2 upload path were not run because production GitHub/R2 runtime access is unavailable here.
