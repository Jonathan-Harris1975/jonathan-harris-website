# CogniPal / AIMS Website Chat Deployment

The website chat is first-party. BotSailor is not part of the public runtime.

## Runtime path

1. The governed site script loads `/assets/css/cognipal-webchat.min.css` and `/assets/js/cognipal-webchat.min.js`.
2. The browser sends same-origin requests to `/api/cognipal/message` and `/api/cognipal/sync`. Requests without a valid same-origin `Origin` header are rejected.
3. The Pages Function consumes strongly consistent per-global, per-IP, per-visitor and per-session limits from the `COGNIPAL_RATE_LIMITER` Durable Object before any request reaches AIMS.
4. Cloudflare Pages Functions sign accepted requests with HMAC-SHA256 and forward them to AIMS.
5. AIMS stores the visitor, conversation, messages and takeover state in Comms Hub D1.
6. Operator replies are stored in the same conversation and returned to the browser during transcript sync.

## Rate-limiter Worker

The Pages project cannot define a Durable Object itself. Deploy the external Worker in `workers/cognipal-rate-limit` first, then deploy/redeploy the Pages project so its `COGNIPAL_RATE_LIMITER` binding resolves to that Worker.

From `workers/cognipal-rate-limit`, deploy with the repository's normal authenticated Wrangler environment. The Worker declares `CogniPalRateLimiter` as a SQLite-backed Durable Object through the `exports` configuration. The root `wrangler.toml` binds that external class to Pages using `script_name = "cognipal-rate-limit"`.

Production limits are enforced over 60-second windows:

| Route | Global | Client IP | Visitor | Session |
|---|---:|---:|---:|---:|
| `/api/cognipal/message` | 600 | 20 | 15 | 12 |
| `/api/cognipal/sync` | 2400 | 180 | 90 | 60 |

The gateway fails closed with `503 rate_limiter_unavailable` if the Durable Object binding or service is unavailable in production. A rejected limit returns `429 rate_limited` with `Retry-After`. Session rotation does not bypass the client-IP or global ceilings.

## Cloudflare Pages settings

Set these in the Pages project, not in the repository:

- `AIMS_COMMS_HUB_BASE_URL` — current public AIMS origin. The gateway accepts either the bare origin (`https://…`) or an origin ending in `/comms-hub` without duplicating the route prefix.
- `COMMS_HUB_COGINPAL_WEBHOOK_SECRET` — secret; must exactly match the AIMS/Koyeb value.
- `AIMS_COMMS_HUB_CHAT_TIMEOUT_MS` — optional, default 12000 ms.
- `COGNIPAL_RATE_LIMITER` — Durable Object binding to class `CogniPalRateLimiter` in Worker `cognipal-rate-limit` (declared in root `wrangler.toml`).

## AIMS / Koyeb settings

- `COMMS_HUB_CHAT_ENABLED=true`
- `COMMS_HUB_COGINPAL_WEBHOOK_SECRET` — same shared secret used by Pages.
- `COMMS_HUB_CHAT_AI_WORKFLOW_ENABLED=true` when automated CogniPal replies are intended in production.
- `COMMS_HUB_CHAT_MAX_MESSAGE_CHARS=4000`
- `COMMS_HUB_CHAT_MAX_MESSAGES_PER_MINUTE=12`
- `COMMS_HUB_CHAT_HISTORY_LIMIT=100`

The optional `COMMS_HUB_COGINPAL_API_BASE_URL` and `COMMS_HUB_COGINPAL_API_KEY` may remain blank for the first-party transport.

## Launcher behaviour

- The launcher uses `https://assets.jonathan-harris.online/CogniPal.jpg` for both the floating button and chat header avatar.
- First-time visitors see the launcher after 30 seconds or after scrolling 35% of the page, whichever happens first. The widget never auto-opens.
- Visitors who have previously opened or used CogniPal see the launcher immediately on later visits.
- The launcher is vertically offset from the site's back-to-top control so the two floating controls do not overlap.
- Public copy speaks directly about Jonathan rather than referring to a team.

## Route resilience

The Pages gateway accepts `AIMS_COMMS_HUB_BASE_URL` as either the bare AIMS origin or an origin ending in `/comms-hub`; it normalises the upstream path to prevent a duplicated `/comms-hub/comms-hub/...` route. AIMS captures the exact raw body for both `/intake/chat` and `/intake/chat/sync` so HMAC verification uses the same bytes that Cloudflare signed.

## Launch gates

`python3 scripts/check_webchat_contract.py` checks that the first-party gateway, rate-limit binding and Worker are present. `node --test --experimental-default-type=module scripts/cognipal-rate-limit.test.mjs` verifies that rotating visitor/session IDs cannot bypass the per-IP ceiling on either message or sync routes, that missing Origin is rejected, and that production fails closed if the limiter is unavailable.

The post-deployment ecosystem smoke in MAST sends one production CogniPal message and sync request using the website origin. This verifies the Pages rate limiter, HMAC gateway and AIMS transport together.

## Live canary

1. Open a private/incognito browser session on the production site.
2. Open CogniPal and send one owned test message.
3. Confirm one new `chat` conversation appears in AIMS with the correct starting page and no duplicate message.
4. Request a person and confirm the session changes to `takeover_requested`.
5. From AIMS, switch to `human` and send one reply. Confirm it appears in the open website widget within one polling cycle.
6. Close the session and confirm further operator sends are rejected.
7. Re-send the same signed message only in a controlled test; AIMS must reject the replay.

## BotSailor removal gate

`python3 scripts/check_webchat_contract.py` fails if BotSailor is present in public HTML or CSP. `scripts/govern_page_scripts.py --validate` also rejects public BotSailor runtime references. Legacy BotSailor strings may remain only in removal/validation regexes so future page generation cannot reintroduce the old widget.
