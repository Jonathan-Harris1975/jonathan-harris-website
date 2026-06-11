# HIVE shared skills access for the website

The website has read-only access to the shared HIVE skill pool stored in Cloudflare R2.

## R2 details

```text
R2_PUBLIC_BASE_URL_HIVE_SKILLS=https://pub-da50a6512f164566955a3076a1c795ef.r2.dev
R2_BUCKET_HIVE_SKILLS=hive-skills
```

## Access model

The website can read approved skill metadata, manifests and indexes. It must not execute skills directly and must not hold LLM, GitHub, Cloudflare write, Koyeb, OpenRouter or Vectorize secrets.

The same-origin proxy is:

```text
/api/hive-skills/<object-key>
```

Useful examples:

```text
/api/hive-skills/manifests/website-skills-manifest.json
/api/hive-skills/index/search-documents.json
/api/hive-skills/index/capability-map.json
/api/hive-skills/skills/S201_web-perf.json
```

If no object key is supplied, the endpoint returns:

```text
manifests/website-skills-manifest.json
```

## Intended use

The website may use this data for public or internal read-only surfaces, including capability display, skill discovery, documentation, dashboards and lightweight status checks.

HIVE remains the execution and reasoning layer. Any AI search, model routing, repository write, deployment, audit generation or R2 write action should be handled by HIVE or another backend service with proper gates.

## Files added for this integration

```text
data/hive-skills-config.json
functions/api/hive-skills/[[path]].js
docs/hive-shared-skills.md
```


## Local `.agents` folder policy

The website no longer needs a local `.agents` folder for skill descriptors.

Shared skills are now controlled centrally through the HIVE R2 skill pool. The website should only keep lightweight read-only configuration and the same-origin proxy. This prevents duplicated skill definitions drifting away from the central registry.

Recommended deletion from the website repo after applying this patch:

```text
.agents/
scripts/setup-batch-1-skills.sh
api/hive-skills/
```

`functions/api/hive-skills/[[path]].js` should be kept because that is the Cloudflare Pages Function endpoint.

## Safety rule

The website can know what skills exist. HIVE decides what a skill is allowed to do.
