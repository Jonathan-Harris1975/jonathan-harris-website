# CogniPal / AIMS Website Chat Deployment

The website chat is first-party. BotSailor is not part of the public runtime.

## Runtime path

1. The governed site script loads `/assets/css/cognipal-webchat.min.css` and `/assets/js/cognipal-webchat.min.js`.
2. The browser sends only same-origin requests to `/api/cognipal/message` and `/api/cognipal/sync`.
3. Cloudflare Pages Functions sign the request with HMAC-SHA256 and forward it to AIMS.
4. AIMS stores the visitor, conversation, messages and takeover state in Comms Hub D1.
5. Operator replies are stored in the same conversation and returned to the browser during transcript sync.

## Cloudflare Pages settings

Set these in the Pages project, not in the repository:

- `AIMS_COMMS_HUB_BASE_URL` — current public AIMS origin, without a trailing slash.
- `COMMS_HUB_COGINPAL_WEBHOOK_SECRET` — secret; must exactly match the AIMS/Koyeb value.
- `AIMS_COMMS_HUB_CHAT_TIMEOUT_MS` — optional, default 12000 ms.

## AIMS / Koyeb settings

- `COMMS_HUB_CHAT_ENABLED=true`
- `COMMS_HUB_COGINPAL_WEBHOOK_SECRET` — same shared secret used by Pages.
- `COMMS_HUB_CHAT_AI_WORKFLOW_ENABLED=false` for the first live phase.
- `COMMS_HUB_CHAT_MAX_MESSAGE_CHARS=4000`
- `COMMS_HUB_CHAT_MAX_MESSAGES_PER_MINUTE=12`
- `COMMS_HUB_CHAT_HISTORY_LIMIT=100`

The optional `COMMS_HUB_COGINPAL_API_BASE_URL` and `COMMS_HUB_COGINPAL_API_KEY` may both remain blank for the first-party transport.

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
