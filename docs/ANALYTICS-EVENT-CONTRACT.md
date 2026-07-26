# First-party funnel event contract

**Status:** Production contract  
**Last reviewed:** 25 July 2026

The website owns a small `window.JHAnalytics.track()` layer in `assets/js/funnel-events.min.js`. It pushes consent-compatible event objects into `window.dataLayer`; GTM/GA4 may map those events downstream without teaching templates about vendor-specific tags.

## Privacy boundary

Event payloads are allow-listed. They may contain only `book_slug`, `topic`, `page_type`, `placement`, `referrer_group`, `campaign`, `bundle_slug` and `episode_slug`. Email addresses, form field values, names, free text and other personal data must never be pushed. `utm_campaign` is trimmed and length-limited before use.

## Events

| Event | Trigger |
| --- | --- |
| `ebook_impression` | A catalogue ebook card first crosses the configured viewport threshold. Deduplicated per element. |
| `ebook_view` | A canonical ebook page initialises with a governed `data-book-slug`. |
| `ebook_amazon_click` | An intentional click on a governed buy route marked `data-ebook-amazon`. |
| `ebook_preview_open` | An intentional click on a governed preview route. |
| `ebook_preview_signup` | The governed Jotform confirms an AI Edge signup that originated from an ebook placement. The email field is never included. |
| `newsletter_view` | The governed AI Edge Jotform page is viewed. |
| `newsletter_cta_click` | A tracked AI Edge link is clicked from a book, topic, evidence, resource or other site placement. |
| `newsletter_submit` | The governed Jotform reports a completed submission. The email field is never included. |
| `newsletter_success` | The governed Jotform confirms completion. It does not fire on the CTA click alone. |
| `podcast_episode_view` | A podcast episode response/page initialises. |
| `podcast_play` | A governed native audio element emits a real `play` event. Deduplicated per episode. |
| `podcast_30_seconds` | A governed native audio element reaches at least 30 seconds of playback. Fires once per episode. |
| `bundle_view` | A reading-path page initialises. The public label is “Reading path”; the event name remains `bundle_view` for continuity. |
| `bundle_book_click` | A reading-path book action is intentionally clicked. |
| `book_finder_start` | The deterministic book-finder form is submitted. |
| `book_finder_complete` | The deterministic finder renders a non-empty ranked result set. |

## Placement examples

`catalogue_card`, `ebook_primary`, `reading_path`, `homepage:hero`, `homepage:inline`, `topic:healthcare`, `podcast:index`, `podcast_episode`, `compare:index`.

GTM should map event names and allow-listed dimensions as custom events/parameters. It should not scrape input values from the DOM and attach them to these events.
