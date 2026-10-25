# KDP D1 ebook catalogue

The Cloudflare D1 database named `KDP` stores the website's ebook catalogue. Its production binding is `KDP_DB`.

- `migrations/0001_create_ebooks.sql` defines the catalogue schema.
- The initial 40 records were loaded from the approved website workbook and reconciled against the R2 object list.
- `functions/api/v1/ebooks.json.js` exposes the read-only website endpoint at `/api/v1/ebooks.json`.
- Manuscript PDFs remain in the private `kdp` R2 bucket. D1 stores their exact object keys in `manuscript_r2_key`; `manuscript_url` is NULL.
- The endpoint selects public catalogue fields only. It never returns R2 object keys, manuscript filenames, or manuscript URLs.

The existing static build still uses the workbook while this read path is introduced. Switch page generation to D1 after the endpoint is deployed and its output has been checked against the current pages.
