> **Document status:** Production reference  
> **Last reviewed:** 25 July 2026  
> **Operational authority:** Current repository README, SECURITY policy and operations guide.

# Image publishing contract

The live site intentionally serves logo and ebook cover assets from `https://images.jonathan-harris.online`. The repository does not version those binaries locally, so the URL and responsive-delivery contract has to stay tight.

## Governed image classes

| Class | Governed source |
| --- | --- |
| Site logo | `https://images.jonathan-harris.online/site-logo` |
| Ebook covers | `cover art url` column in the workbook and the derived `cover` field in `data/ebooks-master.json` |
| Metadata images | The same governed cover URL used on each ebook page |
| Homepage featured cover | The `cover` field for the currently featured title |

## Rules

1. Cover URLs must be absolute HTTPS URLs on `images.jonathan-harris.online`.
2. Canonical ebook pages, catalogue cards and the homepage featured slot keep the governed remote cover URL as the fallback `src` and metadata image.
3. Responsive delivery uses Cloudflare Pages' same-origin image resizing contract only: `/cdn-cgi/image/width=<width>,quality=85,fit=scale-down,format=auto/<governed absolute image URL>`.
4. Ebook covers emit 400w, 800w and 1200w candidates where the intrinsic source width permits them, plus a context-appropriate `sizes` value. Do not invent a second transform host or route arbitrary third-party images through this contract.
5. Preserve intrinsic `width` and `height` on cover markup to protect layout stability.
6. Run `python3 scripts/check_image_assets.py` for repo-local contract validation.
7. Run `python3 scripts/check_image_assets.py --live` in a networked environment before or after release to confirm that the published logo, originals and responsive variants still resolve.
