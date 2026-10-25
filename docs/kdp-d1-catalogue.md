# KDP D1 ebook catalogue

Cloudflare D1 database `KDP` is the source of truth for website ebook metadata. The Pages Functions binding is `KDP_DB`.

- `migrations/0001_create_ebooks.sql` defines the catalogue schema.
- The 40 initial ebook records were loaded from the approved workbook and reconciled against the R2 object list.
- `functions/api/v1/ebooks.json.js` provides the read-only website endpoint at `/api/v1/ebooks.json`.
- `scripts/import_ebook_catalogue.py` fetches that endpoint during the site build and imports the public fields into the generated build master. Production builds fail closed if the endpoint is unavailable.
- Local and preview builds may fall back to the workbook while the API is being bootstrapped. That fallback is never used for production.
- The workbook remains for its whole-site `Pages` route inventory checks; the ebook metadata source has moved to D1.
- Manuscript PDFs remain in the private `kdp` R2 bucket. D1 stores each exact object key in `manuscript_r2_key`; `manuscript_url` is NULL.
- The public endpoint and website build never emit R2 keys, manuscript filenames, or manuscript URLs.

Other systems can consume the same D1 catalogue through authenticated Cloudflare bindings or a purpose-built API contract. Do not expose the private R2 metadata when adding those consumers.
