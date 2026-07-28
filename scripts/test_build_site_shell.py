import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_site_shell import build_site_shell
from scripts import inject_partials, ebook_pipeline


class BuildSiteShellTests(unittest.TestCase):
    def test_builds_versioned_external_shell_and_latest_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "assets" / "partials").mkdir(parents=True)
            (root / "assets" / "partials" / "header.html").write_text(
                '<a class="skip-link" href="#main">Skip</a><header id="site-primary-nav"><a href="/blog/">Blog</a></header>',
                encoding="utf-8",
            )
            (root / "assets" / "partials" / "footer.html").write_text(
                '<footer class="site-footer"><a href="/newsletter/">AI Edge</a></footer>',
                encoding="utf-8",
            )

            manifest = build_site_shell(root=root, base_url="https://example.test", version="abc1234567")

            self.assertEqual(manifest["releaseSha"], "abc1234567")
            self.assertEqual(manifest["headerUrl"], "https://example.test/assets/site-shell/abc1234567/header.html")
            header = (root / "assets" / "site-shell" / "abc1234567" / "header.html").read_text(encoding="utf-8")
            footer = (root / "assets" / "site-shell" / "abc1234567" / "footer.html").read_text(encoding="utf-8")
            latest = json.loads((root / "assets" / "site-shell" / "manifest.json").read_text(encoding="utf-8"))

            self.assertIn("JH_SITE_SHELL_HEADER_START", header)
            self.assertIn('href="https://example.test/blog/"', header)
            self.assertIn('href="https://example.test/newsletter/"', footer)
            self.assertEqual(latest["releaseSha"], "abc1234567")
            self.assertEqual(len(manifest["headerSha256"]), 64)
            self.assertEqual(len(manifest["footerSha256"]), 64)

    def test_site_shell_artifacts_are_excluded_from_public_route_discovery(self):
        self.assertTrue(ebook_pipeline.is_site_shell_artifact_path(Path("assets/site-shell/abc1234567/header.html")))
        self.assertTrue(ebook_pipeline.is_site_shell_artifact_path(Path("assets/site-shell/abc1234567/footer.html")))
        self.assertTrue(ebook_pipeline.is_site_shell_artifact_path(Path("assets/site-shell/manifest.json")))
        self.assertFalse(ebook_pipeline.is_site_shell_artifact_path(Path("assets/partials/header.html")))
        self.assertFalse(ebook_pipeline.is_site_shell_artifact_path(Path("podcast/index.html")))

    def test_site_shell_fragments_are_not_treated_as_standalone_pages(self):
        version_dir = inject_partials.ROOT / "assets" / "site-shell" / "abc1234567"
        self.assertTrue(inject_partials.should_skip_page(version_dir / "header.html"))
        self.assertTrue(inject_partials.should_skip_page(version_dir / "footer.html"))


if __name__ == "__main__":
    unittest.main()
