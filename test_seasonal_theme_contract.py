from pathlib import Path

ROOT = Path(__file__).resolve().parent

def test_seasonal_theme_assets_and_wiring():
    js = (ROOT / "assets/js/site-ui.min.js").read_text()
    css = (ROOT / "assets/css/site.css").read_text()
    assert 'dataset.season' in js and 'dataset.event' in js
    events = (
        "new-year", "valentines", "easter", "halloween", "christmas",
        "safer-internet-day", "international-womens-day", "st-patricks-day",
        "mothering-sunday", "earth-day", "pride-month", "fathers-day",
        "bonfire-night", "remembrance",
    )
    for event in events:
        assert event in js
        assert f'data-event="{event}"' in css
    pages = [p for p in ROOT.rglob("*.html") if '/assets/css/site.css' in p.read_text(errors="ignore")]
    assert pages
    assert all('/assets/js/site-ui.min.js' in p.read_text(errors="ignore") for p in pages)


def test_seasonal_theme_preserves_button_and_accent_card_contrast():
    css = (ROOT / "assets/css/site.css").read_text()
    assert ':root.seasonal-theme-ready .hero .button.secondary:active' in css
    assert 'background:#fff!important;color:#111827!important' in css
    assert ':root.seasonal-theme-ready .main .ebook-section--accent' in css
    assert '.ebook-section--accent p' in css and 'color:var(--jh-text)!important' in css
    assert ':root.seasonal-theme-ready .btn-ghost:active' in css
    assert ':root.seasonal-theme-ready .jh-journey-actions a:first-child:active' in css
