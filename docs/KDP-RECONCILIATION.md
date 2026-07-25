# KDP sales reconciliation contract

**Status:** Repository-side contract ready for real exports  
**Last reviewed:** 25 July 2026

The website can measure qualified sessions, book views and Amazon outbound clicks. Amazon/KDP sales remain an external commercial data source. This contract joins those two sides without scraping Amazon or inventing purchase conversion.

## Inputs

`data/funnel-events-export-template.csv`

```text
date,book_slug,qualified_sessions,book_views,amazon_clicks
```

`data/kdp-sales-template.csv`

```text
date,book_slug,sales
```

Use ISO dates (`YYYY-MM-DD`) and the canonical website book slug. Rows may be daily per title or repeated; the reconciliation tool aggregates repeated date/slug rows.

## Run

```bash
python3 scripts/reconcile_kdp.py --funnel path/to/funnel.csv --sales path/to/kdp.csv --output kdp-reconciliation.csv
```

The output calculates, only when denominators exist:

- book reach = book views / qualified sessions
- Amazon outbound click rate = Amazon clicks / book views
- observed outbound-to-sale conversion = KDP sales / Amazon clicks

A missing denominator is left blank rather than converted into a fictional zero-rate story. The 15-30 sales/day target should not be back-solved into required traffic until real observed conversion inputs exist.

The two repository CSV files are headers/templates only. Do not commit private KDP exports or customer-level data.
