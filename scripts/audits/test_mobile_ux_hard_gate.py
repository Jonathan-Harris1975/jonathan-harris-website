import argparse
import json
import os
import tempfile
import unittest

from scripts.audits import mobile_ux_hard_gate as audit
from scripts.audits.common import resolve_r2_public_base_for_bucket


class MobileUxHardGateTests(unittest.TestCase):
  def test_runtime_callback_config_uses_app_url_fallback(self):
    old_app_url = os.environ.get("APP_URL")
    old_token = os.environ.get("AI_SUITE_AUDIT_CALLBACK_TOKEN")
    try:
      os.environ["APP_URL"] = "https://zeroth-kara-jonathanharris-3296ed37.koyeb.app"
      os.environ["AI_SUITE_AUDIT_CALLBACK_TOKEN"] = "token-from-env"
      args = argparse.Namespace(callback_url=None, callback_token=None)
      audit.resolve_runtime_callback_config(args)
      self.assertEqual(args.callback_url, "https://zeroth-kara-jonathanharris-3296ed37.koyeb.app/audits/mobile-ux/callback")
      self.assertEqual(args.callback_token, "token-from-env")
    finally:
      if old_app_url is None:
        os.environ.pop("APP_URL", None)
      else:
        os.environ["APP_URL"] = old_app_url
      if old_token is None:
        os.environ.pop("AI_SUITE_AUDIT_CALLBACK_TOKEN", None)
      else:
        os.environ["AI_SUITE_AUDIT_CALLBACK_TOKEN"] = old_token

  def test_missing_playwright_capability_hard_gates_browser_screenshots_and_emulation(self):
    capabilities = audit.build_capabilities("playwright import failed", "failure")
    self.assertFalse(capabilities["renderedBrowserAutomation"])
    self.assertFalse(capabilities["screenshotCapture"])
    self.assertFalse(capabilities["mobileViewportEmulation"])
    self.assertGreaterEqual(len(capabilities["blockedTests"]), 3)




  def test_browser_capability_hard_gate_takes_precedence_over_storage_gate(self):
    source = audit.Path("scripts/audits/mobile_ux_hard_gate.py").read_text(encoding="utf-8")
    hard_gate_index = source.index('if not capabilities["renderedBrowserAutomation"]')
    storage_gate_index = source.index("missing_r2 = missing_r2_upload_config()")
    self.assertLess(hard_gate_index, storage_gate_index)
    self.assertIn(audit.HARD_GATE_MESSAGE, audit.failure_report_html({"message": audit.HARD_GATE_MESSAGE}, {"blocks": []}))

  def test_runtime_probe_blocks_when_chromium_launch_fails(self):
    class FailingChromium:
      def launch(self, **_kwargs):
        raise RuntimeError("browser executable missing")

    class FailingPlaywright:
      chromium = FailingChromium()
      def __enter__(self):
        return self
      def __exit__(self, *_args):
        return False

    blocks = audit.probe_rendered_mobile_runtime(lambda: FailingPlaywright(), audit.Path(tempfile.mkdtemp()))
    capabilities = {item["capability"] for item in blocks}
    self.assertIn("renderedBrowserAutomation", capabilities)
    self.assertIn("screenshotCapture", capabilities)
    self.assertIn("mobileViewportEmulation", capabilities)

  def test_build_capabilities_preserves_runtime_probe_blocks(self):
    capabilities = audit.build_capabilities(None, "success", [{"capability": "screenshotCapture", "reason": "probe screenshot failed"}])
    self.assertTrue(capabilities["renderedBrowserAutomation"])
    self.assertFalse(capabilities["screenshotCapture"])
    self.assertTrue(capabilities["mobileViewportEmulation"])
    self.assertEqual(capabilities["blockedTests"][0]["capability"], "screenshotCapture")

  def test_missing_r2_upload_config_reports_required_audit_storage_envs(self):
    names = [
      "R2_ENDPOINT",
      "R2_ACCESS_KEY_ID",
      "R2_SECRET_ACCESS_KEY",
      "R2_BUCKET_AUDITS",
      "R2_PUBLIC_BASE_URL_AUDITS",
    ]
    old_env = {name: os.environ.get(name) for name in names}
    try:
      for name in names:
        os.environ.pop(name, None)
      self.assertEqual(audit.missing_r2_upload_config(), names)
      self.assertFalse(audit.r2_upload_configured())
      with self.assertRaisesRegex(RuntimeError, "R2 audit upload configuration is incomplete"):
        audit.upload_artifacts_if_configured("audits/mobile-ux/unit", audit.Path(tempfile.mkdtemp()), require=True)
    finally:
      for name, value in old_env.items():
        if value is None:
          os.environ.pop(name, None)
        else:
          os.environ[name] = value

  def test_audits_bucket_public_base_is_preferred_for_audits_bucket(self):
    old_bucket = os.environ.get("R2_BUCKET_AUDITS")
    old_base = os.environ.get("R2_PUBLIC_BASE_URL_AUDITS")
    try:
      os.environ["R2_BUCKET_AUDITS"] = "audits"
      os.environ["R2_PUBLIC_BASE_URL_AUDITS"] = "https://audits.example.test/"
      self.assertEqual(resolve_r2_public_base_for_bucket("audits"), "https://audits.example.test")
    finally:
      if old_bucket is None:
        os.environ.pop("R2_BUCKET_AUDITS", None)
      else:
        os.environ["R2_BUCKET_AUDITS"] = old_bucket
      if old_base is None:
        os.environ.pop("R2_PUBLIC_BASE_URL_AUDITS", None)
      else:
        os.environ["R2_PUBLIC_BASE_URL_AUDITS"] = old_base

  def test_live_404_route_is_not_treated_as_repo_static_404(self):
    self.assertEqual(audit.detect_template_family(audit.LIVE_404_ROUTE), "live-404")
    self.assertIn("__mobile-ux-404-probe__", audit.route_target("https://example.com", audit.LIVE_404_ROUTE, "session-one"))


  def test_workbook_exception_sweep_is_bounded_before_rendered_stage3(self):
    class Workbook:
      urls = [
        "https://example.com/catalogue/agriculture",
        "https://example.com/catalogue/finance",
        "https://example.com/catalogue/retail",
        "https://example.com/topics/ai-for-beginners",
        "https://example.com/topics/generative-ai",
        "https://example.com/topics/machine-learning",
        "https://example.com/contact",
        "https://example.com/newsletter",
      ]

    risk_routes = audit.workbook_mobile_risk_routes(Workbook(), [])
    selected = audit.select_workbook_focus_routes(risk_routes, {"/contact", "/newsletter"}, max_total=3, max_per_family=1)

    self.assertEqual(len(risk_routes), 8)
    self.assertLessEqual(len(selected), 3)
    self.assertEqual(len({audit.detect_template_family(route) for route in selected}), len(selected))
    self.assertNotIn("/contact", selected)
    self.assertNotIn("/newsletter", selected)

  def test_rendered_step_has_timeout_and_internal_runtime_budget(self):
    workflow = audit.Path(".github/workflows/mobile-ux-hard-gate.yml").read_text(encoding="utf-8")
    source = audit.Path("scripts/audits/mobile_ux_hard_gate.py").read_text(encoding="utf-8")

    self.assertIn("timeout-minutes: 45", workflow)
    self.assertIn("MOBILE_UX_MAX_RUNTIME_SECONDS", workflow)
    self.assertIn("Stage 3 runtime budget exceeded", source)
    self.assertIn("return records, executed, runtime_blocks", source)

  def test_parse_args_defines_max_runtime_seconds(self):
    old_argv = audit.sys.argv
    try:
      audit.sys.argv = [
        "mobile_ux_hard_gate.py",
        "--base-url", "https://example.com",
        "--session-id", "arg-test",
        "--report-prefix", "audits/mobile-ux/arg-test",
        "--max-runtime-seconds", "123",
      ]
      args = audit.parse_args()
      self.assertEqual(args.max_runtime_seconds, 123)
    finally:
      audit.sys.argv = old_argv

  def test_failure_payload_writes_complete_diagnostic_artifacts(self):
    old_env = {
      name: os.environ.get(name)
      for name in [
        "R2_ENDPOINT",
        "R2_ACCESS_KEY_ID",
        "R2_SECRET_ACCESS_KEY",
        "R2_BUCKET_AUDITS",
        "R2_PUBLIC_BASE_URL_AUDITS",
      ]
    }
    for name in old_env:
      os.environ.pop(name, None)

    try:
      with tempfile.TemporaryDirectory() as tmp:
        args = argparse.Namespace(
          session_id="failure-artifact-test",
          report_prefix="audits/mobile-ux/failure-artifact-test",
          callback_url=None,
          callback_token=None,
        )
        output_dir = audit.ensure_dir(audit.Path(tmp))
        payload = audit.write_failure_payload(
          args,
          output_dir,
          "rendered execution failed",
          {"capabilities": audit.build_capabilities()},
          {"error": "browser executable missing"},
        )

        expected = ["summary.json", "report.json", "coverage.json", "evidence.json", "halt.txt", "report.html"]
        for filename in expected:
          self.assertTrue((output_dir / filename).exists(), filename)

        coverage = json.loads((output_dir / "coverage.json").read_text(encoding="utf-8"))
        self.assertFalse(coverage["complete"])
        self.assertEqual(coverage["status"], "failed")
        self.assertIn("reportUrl", payload)
        report_json = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))
        self.assertIsNone(report_json["mobileQualityScore"])
        self.assertIsNone(report_json["releaseVerdict"])
        self.assertIn("Mobile UX audit failure report", (output_dir / "report.html").read_text(encoding="utf-8"))
    finally:
      for name, value in old_env.items():
        if value is None:
          os.environ.pop(name, None)
        else:
          os.environ[name] = value

  def test_callback_marker_is_written_after_structured_callback(self):
    calls = []
    original_post_callback = audit.post_callback
    try:
      audit.post_callback = lambda url, token, payload: calls.append((url, token, payload))
      with tempfile.TemporaryDirectory() as tmp:
        output_dir = audit.Path(tmp)
        args = argparse.Namespace(callback_url="https://suite.example.test/audits/mobile-ux/callback", callback_token="token")
        payload = {
          "auditType": "mobile-ux",
          "sessionId": "marker-test",
          "status": "failed",
          "message": "controlled",
          "reportPrefix": "audits/mobile-ux/marker-test",
        }
        audit.post_mobile_callback(args, output_dir, payload, workflow_failure=False)
        marker = json.loads((output_dir / audit.CALLBACK_MARKER_FILENAME).read_text(encoding="utf-8"))
        self.assertEqual(len(calls), 1)
        self.assertEqual(marker["sessionId"], "marker-test")
        self.assertFalse(marker["workflowFailure"])
    finally:
      audit.post_callback = original_post_callback

  def test_mobile_workflow_suppresses_generic_fallback_when_marker_exists(self):
    workflow = audit.Path(".github/workflows/mobile-ux-hard-gate.yml").read_text(encoding="utf-8")
    self.assertIn(audit.CALLBACK_MARKER_FILENAME, workflow)
    self.assertIn("suppressing generic fallback callback", workflow)
    self.assertIn("python -u scripts/audits/mobile_ux_hard_gate.py", workflow)

  def test_mobile_interaction_contract_preserves_conditional_header_and_real_viewport_checks(self):
    source = audit.Path("scripts/audits/mobile_ux_hard_gate.py").read_text(encoding="utf-8")
    self.assertIn("reveal_conditional_header(page)", source)
    self.assertIn('required_checks = ("revealed", "open", "escapeClose", "reopen", "outsideClose")', source)
    self.assertIn('box["x"] + box["width"] <= 0', source)
    self.assertIn('box["y"] >= viewport_height', source)
    self.assertIn('box["width"] < 44 or box["height"] < 44', source)
    self.assertIn('"openedBeforeResize": opened_before_resize', source)
    self.assertIn('"overlayVisibleOnDesktop"', source)
    self.assertIn('"scrollLockedOnDesktop"', source)
    self.assertIn('"resetAtOriginalWidth": reset_at_original', source)
    site_ui = audit.Path("assets/js/site-ui.min.js").read_text(encoding="utf-8")
    self.assertIn('qa(".jh-mobile-nav").forEach', site_ui)
    self.assertIn('set(menu,btn,false)', site_ui)

  def test_image_responsiveness_check_is_geometry_based_not_lazy_load_based(self):
    source = audit.Path("scripts/audits/mobile_ux_hard_gate.py").read_text(encoding="utf-8")
    inspect_images_source = source[source.index("def inspect_images"):source.index("def inspect_tables")]
    self.assertIn("rect.right > window.innerWidth + 2", inspect_images_source)
    self.assertNotIn("!img.complete", inspect_images_source)
    self.assertNotIn("img.naturalWidth === 0", inspect_images_source)


class MobileUxReportArtifactTests(unittest.TestCase):
  def test_production_report_appendix_documents_are_generated_from_rendered_records(self):
    record = {
      "route": "/",
      "url": "https://example.com/",
      "templateFamily": "homepage",
      "viewport": 390,
      "checks": {
        "viewportCorrectness": "PASS",
        "overflow": "FAIL",
        "hamburgerNavigation": "PASS",
        "touchTargetUsability": "PASS",
        "dynamicResizeReflow": "PASS",
        "ctaContinuity": "PASS",
        "typographyReadability": "PASS",
        "formUsability": "N/A",
        "imageResponsiveness": "PASS",
        "tableComparisonHandling": "N/A",
        "responsiveCoverage": "FAIL",
      },
      "screenshotRefs": [{"relativePath": "screenshots/home-390-fail.png", "publicUrl": "https://audits.example.test/audits/mobile-ux/run/screenshots/home-390-fail.png"}],
      "defectSummary": "Horizontal overflow detected.",
      "selectorComponentCodeAnchor": ".hero-grid",
    }
    summary = {
      "sessionId": "run-one",
      "reportPrefix": "audits/mobile-ux/run-one",
      "mobileQualityScore": 90.0,
      "mobileFailureCount": 1,
      "screenshotCount": 1,
      "focusedPagesAudited": 1,
    }
    issues = audit.build_issues([record])

    manifest = audit.screenshot_manifest_document([record], summary)
    scorecard = audit.mandatory_mobile_scorecard_document([record], summary)
    focused = audit.focused_page_appendix_document(summary, [record], issues)
    repository_issues = audit.repository_issue_appendix_document(summary, issues)
    fixes = audit.responsive_fix_appendix_document(summary, issues)

    self.assertEqual(manifest["totalScreenshots"], 1)
    self.assertEqual(scorecard["rows"][0]["responsiveCoverage"], "FAIL")
    self.assertEqual(focused["routes"][0]["route"], "/")
    self.assertEqual(repository_issues["issueCount"], len(issues))
    self.assertTrue(fixes["rows"])


  def test_required_completion_artefact_gate_requires_report_json_and_appendices(self):
    uploaded = {name: f"https://audits.example.test/{name}" for name in audit.MANDATORY_COMPLETION_ARTEFACTS}
    self.assertEqual(audit.missing_required_completion_artefacts(uploaded), [])

    uploaded.pop("report.json")
    uploaded.pop("responsive-fix-appendix.json")
    missing = audit.missing_required_completion_artefacts(uploaded)
    self.assertIn("report.json", missing)
    self.assertIn("responsive-fix-appendix.json", missing)
    self.assertIn("screenshot-manifest.json", audit.MANDATORY_COMPLETION_ARTEFACTS)

  def test_report_json_document_is_non_scoring_only_when_summary_is_non_scoring(self):
    summary = {
      "status": "failed",
      "message": audit.HARD_GATE_MESSAGE,
      "mobileQualityScore": None,
      "releaseVerdict": None,
      "screenshotCount": 0,
      "mobileFailureCount": 0,
    }
    report_json = audit.report_json_document(summary, [], [], {"complete": False}, {"crossSourceMismatches": []})
    self.assertIsNone(report_json["summary"]["mobileQualityScore"])
    self.assertIsNone(report_json["summary"]["releaseVerdict"])
    self.assertEqual(report_json["appendices"]["screenshotManifest"]["auditType"], "mobile-ux")

  def test_report_html_contains_required_production_appendices_and_screenshot_manifest(self):
    record = {
      "route": "/",
      "url": "https://example.com/",
      "templateFamily": "homepage",
      "viewport": 390,
      "checks": {
        "viewportCorrectness": "PASS",
        "overflow": "PASS",
        "hamburgerNavigation": "PASS",
        "touchTargetUsability": "PASS",
        "dynamicResizeReflow": "PASS",
        "ctaContinuity": "PASS",
        "typographyReadability": "PASS",
        "formUsability": "N/A",
        "imageResponsiveness": "PASS",
        "tableComparisonHandling": "N/A",
        "responsiveCoverage": "PASS",
      },
      "screenshotRefs": [{"relativePath": "screenshots/home-390-pass.png", "publicUrl": "https://audits.example.test/audits/mobile-ux/run/screenshots/home-390-pass.png"}],
      "defectSummary": "",
      "selectorComponentCodeAnchor": "",
    }
    preflight = {
      "workbook": {"filename": "workbook.xlsm", "primarySheet": "Pages", "headerRow": 1, "urlCount": 1},
      "liveHomepage": {"status": 200, "viewport": "width=device-width, initial-scale=1", "title": "Home"},
      "repository": {"totalFiles": 1, "mediaQueryCount": 0, "containerQueryCount": 0, "fixedWidthMinWidthRisks": [], "responsiveRuleInventory": []},
      "capabilities": {"staticFileInspection": True, "fetchSourceInspection": True, "renderedBrowserAutomation": True, "screenshotCapture": True, "mobileViewportEmulation": True, "blockedTests": []},
    }
    summary = {
      "sessionId": "run-one",
      "reportPrefix": "audits/mobile-ux/run-one",
      "releaseVerdict": "PASS",
      "renderedPages": 1,
      "viewportRuns": 1,
      "screenshotCount": 1,
      "mobileFailureCount": 0,
      "mobileQualityScore": 100,
      "confidenceModel": {"executionCoverageConfidence": {"status": "HIGH", "value": 100, "evidence": "fixture"}},
      "preflight": preflight,
      "focusedPagesAudited": 1,
      "exceptionsEscalated": 0,
      "verificationMatrix": {"release readiness": "PASS"},
      "weightedScorecard": [("UX", 14, 100, "Observed Live (mobile)")],
      "reportControlBlock": {"skipped required tasks count": 0},
    }
    html = audit.report_html(
      summary,
      [record],
      {"report.json": "https://audits.example.test/report.json", "screenshot-manifest.json": "https://audits.example.test/manifest.json"},
      [],
      {"complete": True, "skippedRequiredTasksCount": 0},
      {"crossSourceMismatches": [], "crossSourceMismatchCount": 0},
    )
    self.assertIn("Blocked-tests list", html)
    self.assertIn("Source inventory", html)
    self.assertIn("Evidence labels and claim control", html)
    self.assertIn("report.json", html)
    self.assertIn("Screenshot manifest", html)
    self.assertIn("Focused Page Appendix", html)
    self.assertIn("Mandatory Mobile UX Scorecard", html)
    self.assertIn("Responsive Fix Appendix", html)


if __name__ == "__main__":
  unittest.main()

class MobileUxExecutiveGroupingTests(unittest.TestCase):
  def _record(self, route, viewport, check="overflow", anchor=".shared-card-grid"):
    checks = {
      "viewportCorrectness": "PASS",
      "overflow": "PASS",
      "hamburgerNavigation": "PASS" if viewport <= audit.MOBILE_NAV_BREAKPOINT else "N/A",
      "touchTargetUsability": "PASS",
      "dynamicResizeReflow": "PASS",
      "ctaContinuity": "PASS",
      "typographyReadability": "PASS",
      "formUsability": "N/A",
      "imageResponsiveness": "PASS",
      "tableComparisonHandling": "N/A",
      "responsiveCoverage": "PASS",
    }
    checks[check] = "FAIL"
    if check in {"overflow", "dynamicResizeReflow"}:
      checks["responsiveCoverage"] = "FAIL"
    return {
      "route": route,
      "url": f"https://example.com{route if route != '/' else '/'}",
      "templateFamily": audit.detect_template_family(route),
      "viewport": viewport,
      "checks": checks,
      "details": {check: {"selector": anchor}},
      "screenshotRefs": [{"relativePath": f"screenshots/{route.strip('/') or 'home'}-{viewport}-fail.png", "publicUrl": f"https://audits.example.test/{route.strip('/') or 'home'}-{viewport}-fail.png"}],
      "defectSummary": check,
      "selectorComponentCodeAnchor": anchor,
    }

  def test_root_cause_grouping_collapses_repeated_viewport_noise(self):
    records = [
      self._record("/ebooks", 320),
      self._record("/ebooks", 390),
      self._record("/newsletter", 320),
      self._record("/newsletter", 390),
    ]
    issues = audit.build_issues(records)
    groups = audit.root_cause_groups_document(issues, records, {"sessionId": "group-test", "reportPrefix": "audits/mobile-ux/group-test"})

    self.assertGreater(len(issues), groups["groupCount"])
    self.assertTrue(all(issue.get("groupId") for issue in issues))
    self.assertEqual(groups["groups"][0]["bestAvailableCodeAnchor"], ".shared-card-grid")
    self.assertIn("repository-issue-appendix.json", groups["groups"][0]["detailedAppendixReference"])

  def test_blocked_release_is_declared_in_completed_summary(self):
    records = [self._record("/", 390, "overflow")]
    issues = audit.build_issues(records)
    summary = audit.build_summary(
      argparse.Namespace(session_id="blocked-test", report_prefix="audits/mobile-ux/blocked-test"),
      {
        "workbook": {"filename": "inventory.xlsx", "primarySheet": "Pages", "headerRow": 1, "urlCount": 1},
        "capabilities": audit.build_capabilities(),
        "repository": {"totalFiles": 1, "mediaQueryCount": 1, "containerQueryCount": 0},
        "exceptionSweep": {"urlCount": 1},
      },
      ["/"],
      records,
      issues,
      {"complete": True, "skippedRequiredTasksCount": 0},
      {"crossSourceMismatchCount": 0},
      "2026-08-03T00:00:00Z",
    )

    self.assertEqual(summary["status"], "completed")
    self.assertEqual(summary["releaseVerdict"], "BLOCKED")
    self.assertTrue(summary["hardGateBlocked"])

  def test_mobile_navigation_audit_reveals_intentionally_deferred_header(self):
    source = audit.Path("scripts/audits/mobile_ux_hard_gate.py").read_text(encoding="utf-8")
    self.assertIn("def reveal_conditional_header", source)
    self.assertIn("[data-jh-header-reveal-anchor]", source)
    self.assertIn("intentional header reveal point", source)
    self.assertIn('if box["width"] < 44 or box["height"] < 44', source)

  def test_mobile_navigation_checks_match_the_1100px_site_breakpoint(self):
    self.assertEqual(audit.MOBILE_NAV_BREAKPOINT, 1100)
    source = audit.Path("scripts/audits/mobile_ux_hard_gate.py").read_text(encoding="utf-8")
    self.assertIn("intentionalScroller", source)
    self.assertIn("el.getAttribute('aria-hidden') === 'true'", source)
    self.assertIn('page.locator("#jh-nav-overlay")', source)

  def test_responsive_fix_appendix_uses_group_contracts_and_retest_steps(self):
    records = [self._record("/ebooks", 320), self._record("/ebooks", 390)]
    issues = audit.build_issues(records)
    fixes = audit.responsive_fix_appendix_document({"sessionId": "fix-test", "reportPrefix": "audits/mobile-ux/fix-test"}, issues, records)

    self.assertTrue(fixes["rows"])
    first = fixes["rows"][0]
    self.assertTrue(first["fixId"].startswith("FIX-MUX-G"))
    self.assertIn("linkedGroupId", first)
    self.assertIn("bestAvailableCodeAnchor", first)
    self.assertIn("viewportRetestSteps", first)
    self.assertTrue(first["screenshotReferences"])

  def test_confidence_model_is_split_and_release_confidence_blocks_blocked_reports(self):
    records = [self._record("/", 390)]
    issues = audit.build_issues(records)
    confidence = audit.confidence_model(records, issues, {"complete": True, "skippedRequiredTasksCount": 0}, 1, "BLOCKED")

    self.assertIn("executionCoverageConfidence", confidence)
    self.assertIn("findingConfidence", confidence)
    self.assertIn("scoringConfidence", confidence)
    self.assertEqual(confidence["releaseConfidence"]["status"], "BLOCKED")

  def test_verification_matrix_does_not_invent_visual_brand_failure(self):
    records = [self._record("/", 390, "overflow")]
    issues = audit.build_issues(records)
    matrix = audit.build_verification_matrix(records, issues)

    self.assertEqual(matrix["horizontal overflow status"]["status"], "FAIL")
    self.assertEqual(matrix["visual design consistency"]["status"], audit.EVIDENCE_CAPTURED_STATUS)
    self.assertIn("does not issue subjective brand/design PASS or FAIL", matrix["visual design consistency"]["evidence"])
    self.assertEqual(matrix["cover art quality"]["status"], audit.NOT_ASSESSED_STATUS)

  def test_report_json_exposes_root_groups_and_raw_records_for_appendices(self):
    records = [self._record("/ebooks", 320), self._record("/ebooks", 390)]
    issues = audit.build_issues(records)
    summary = {
      "status": "completed",
      "sessionId": "json-test",
      "reportPrefix": "audits/mobile-ux/json-test",
      "releaseVerdict": "CONDITIONAL PASS",
      "mobileQualityScore": 90,
      "confidenceModel": audit.confidence_model(records, issues, {"complete": True, "skippedRequiredTasksCount": 0}, 2, "CONDITIONAL PASS"),
      "focusedPagesAudited": 1,
      "mobileFailureCount": 2,
      "screenshotCount": 2,
    }
    document = audit.report_json_document(summary, records, issues, {"complete": True, "skippedRequiredTasksCount": 0}, {"crossSourceMismatches": [], "crossSourceMismatchCount": 0}, {"report.json": "https://audits.example.test/report.json"})

    self.assertIn("executiveThemes", document)
    self.assertIn("rootCauseGroups", document)
    self.assertGreaterEqual(document["executiveThemes"]["themeCount"], 1)
    self.assertLess(document["rootCauseGroups"]["groupCount"], len(document["issues"]))
    self.assertEqual(len(document["execution"]["records"]), len(records))
    self.assertIn("report.json", document["appendixLinks"])
