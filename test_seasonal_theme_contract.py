from pathlib import Path

ROOT = Path(__file__).resolve().parent

def test_seasonal_theme_assets_and_wiring():
    js = (ROOT / "assets/js/site-ui.min.js").read_text()
    css = (ROOT / "assets/css/site.css").read_text()
    assert 'dataset.season' in js and 'dataset.event' in js
    for event in ("new-year", "valentines", "easter", "halloween", "christmas", "safer-internet-day", "international-womens-day", "st-patricks-day", "mothering-sunday", "earth-day", "pride-month", "fathers-day", "bonfire-night", "remembrance"):
        assert event in js
        assert f'data-event="{event}"' in css
    pages = [p for p in ROOT.rglob("*.html") if '/assets/css/site.css' in p.read_text(errors="ignore")]
    assert pages
    assert all('/assets/js/site-ui.min.js' in p.read_text(errors="ignore") for p in pages)
