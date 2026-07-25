# Search Console stale `/book/*` remediation

**Last reviewed:** 25 July 2026

The repository preserves historical equity by permanently redirecting legacy `/book/<slug>/` and `/book/<slug>/buy-now` routes to the exact `/ebooks/<slug>/` equivalents. Build regression tests verify the route family and reject redirect chains in repository rules.

After a production release:

1. Test representative old book and buy-now URLs against the live hostname and confirm one permanent redirect to the exact canonical destination.
2. Inspect affected legacy URLs in Google Search Console and request recrawl of the canonical replacements where useful.
3. Submit the current authoritative `/sitemap.xml`.
4. Monitor legacy URL impressions/index status. Do not report them as removed until the live index actually changes.

Compatibility redirects are intentional. Do not delete them merely to make the redirect file smaller.

## Other stale locale aliases

Historical locale-prefixed variants such as `/en-gb/` and `/en-au/` should be treated the same way: verify their current permanent redirect/canonical destination before asking Google to refresh them. Where an obsolete URL still appears, use **URL Inspection → Request indexing** on the canonical replacement after the redirect is live. Search Console **Removals** can temporarily hide a harmful/stale result when genuinely needed, but it does not replace the redirect/canonical fix and should not be presented as permanent de-indexing.
