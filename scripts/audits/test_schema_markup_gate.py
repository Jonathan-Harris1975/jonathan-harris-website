from pathlib import Path

from schema_markup_gate import run_schema_gate, validate_html_file


def test_schema_gate_allows_valid_blogposting(tmp_path: Path):
    html = tmp_path / "index.html"
    html.write_text(
        '<script type="application/ld+json">{"@context":"https://schema.org","@type":"BlogPosting","headline":"Title","description":"Desc","datePublished":"2026-05-17T08:00:00Z","author":{"@type":"Person","name":"Jonathan Harris"},"mainEntityOfPage":{"@type":"WebPage","@id":"https://example.com"}}</script>',
        encoding="utf-8",
    )
    assert validate_html_file(html, tmp_path) == []


def test_schema_gate_fails_invalid_jsonld(tmp_path: Path):
    html = tmp_path / "blog" / "bad" / "index.html"
    html.parent.mkdir(parents=True)
    html.write_text('<script type="application/ld+json">{"@context":</script>', encoding="utf-8")
    findings = validate_html_file(html, tmp_path)
    assert findings and findings[0].severity == "critical"


def test_schema_gate_reports_repo_summary(tmp_path: Path):
    html = tmp_path / "blog" / "post" / "index.html"
    html.parent.mkdir(parents=True)
    html.write_text("<html><head></head><body>No schema</body></html>", encoding="utf-8")
    report = run_schema_gate(tmp_path)
    assert report["skill"] == "schema-markup"
    assert report["advisoryCount"] == 1
    assert report["criticalCount"] == 0
