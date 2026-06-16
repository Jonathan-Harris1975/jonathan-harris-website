> **Document status:** Production reference  
> **Last reviewed:** 16 June 2026  
> **Operational authority:** Current repository README, SECURITY policy and operations guide.

# Image publishing contract

The live site intentionally serves logo and ebook cover assets from `https://images.jonathan-harris.online`. The repository does not version those binaries locally, so the URL contract has to stay tight.

## Governed image classes

| Class | Governed source |
| --- | --- |
| Site logo | `https://images.jonathan-harris.online/site-logo` |
| Ebook covers | `cover art url` column in the workbook and the derived `cover` field in `data/ebooks-master.json` |
| Metadata images | The same governed cover URL used on each ebook page |
| Homepage featured cover | The `cover` field for the currently featured title |

## Rules

1. Cover URLs must be absolute HTTPS URLs on `images.jonathan-harris.online`.
2. Canonical ebook pages, catalogue cards, and the homepage featured slot must use the governed remote cover URL directly as `src`.
3. Do not emit generated `/cdn-cgi/image/...` `srcset` markup for remote cover URLs. Remote covers should stay on the governed source URL unless the delivery contract is changed deliberately.
4. Run `python3 scripts/check_image_assets.py` for repo-local contract validation.
5. Run `python3 scripts/check_image_assets.py --live` in a networked environment before or after release to confirm that the published logo and cover URLs still resolve.
