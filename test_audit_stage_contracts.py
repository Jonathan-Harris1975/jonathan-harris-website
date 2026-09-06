import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import io

from scripts.audits.common import resolve_r2_public_base_for_bucket, validate_public_json_artifacts
from scripts.audits.validate_workflow_inputs import validate_audit_reference
from scripts.audits.digital_growth_audit import analysis_is_complete
from scripts.audits.seo_aeo_geo_forensic import seo_analysis_is_complete


class AuditStageContractTests(unittest.TestCase):
  def test_digital_growth_requires_complete_substantive_analysis(self):
    self.assertFalse(analysis_is_complete({}))
    self.assertFalse(analysis_is_complete({"auditCompletionState": "Complete", "scorecard": {}}))
    self.assertTrue(analysis_is_complete({
      "auditCompletionState": "Complete",
      "scorecard": {"trafficGrowth": {"score": 7}},
      "overallVerdict": "Evidence-led verdict",
    }))

  def test_seo_requires_score_table_and_substantive_analysis(self):
    self.assertFalse(seo_analysis_is_complete({"auditCompletionState": "Complete"}))
    self.assertFalse(seo_analysis_is_complete({
      "auditCompletionState": "Complete",
      "scoreTable": {"technicalSeo": 8},
    }))
    self.assertTrue(seo_analysis_is_complete({
      "auditCompletionState": "Complete",
      "scoreTable": {"technicalSeo": 8},
      "rankedIssueLedger": [{"issueId": "SEO-1"}],
    }))

  def test_seo_callback_failure_is_fatal_for_pipeline_runs(self):
    root = Path(__file__).resolve().parent
    source = (root / "scripts" / "audits" / "seo_aeo_geo_forensic.py").read_text(encoding="utf-8")
    self.assertIn('if args.callback_url:\n      raise', source)

  def test_completed_source_callbacks_wait_for_public_machine_readable_json(self):
    root = Path(__file__).resolve().parent
    digital = (root / "scripts" / "audits" / "digital_growth_audit.py").read_text(encoding="utf-8")
    seo = (root / "scripts" / "audits" / "seo_aeo_geo_forensic.py").read_text(encoding="utf-8")
    self.assertIn('validate_public_json_artifacts(', digital)
    self.assertIn('["report.json", "summary.json", "evidence.json"]', digital)
    self.assertIn('validate_public_json_artifacts(', seo)
    self.assertIn('["report.json", "summary.json", "coverage.json"]', seo)

  def test_private_audit_bucket_resolves_to_r2_reference_when_no_public_base_exists(self):
    with patch.dict("os.environ", {"R2_BUCKET_AUDITS": "private-audits"}, clear=False):
      with patch.dict("os.environ", {"R2_PUBLIC_BASE_URL_AUDITS": ""}, clear=False):
        self.assertEqual(resolve_r2_public_base_for_bucket("private-audits"), "r2://private-audits")

  def test_private_r2_json_validation_uses_authenticated_r2_client(self):
    client = Mock()
    client.get_object.return_value = {"Body": io.BytesIO(b'{"auditCompletionState":"Complete"}')}
    with patch("scripts.audits.common.build_r2_client", return_value=client):
      result = validate_public_json_artifacts(
        {"report.json": "r2://private-audits/audits/run/report.json"},
        ["report.json"],
        attempts=1,
      )
    client.get_object.assert_called_once_with(Bucket="private-audits", Key="audits/run/report.json")
    self.assertEqual(result["status"], "PASS")

  def test_workflow_input_validator_accepts_private_r2_bucket_reference(self):
    validate_audit_reference("audit_public_base_url", "r2://private-audits", optional=True)
    with self.assertRaises(SystemExit):
      validate_audit_reference("audit_public_base_url", "r2://private-audits/object.json", optional=True)

  def test_public_json_validation_retries_then_returns_parseable_object_metadata(self):
    failed = Mock()
    failed.raise_for_status.side_effect = RuntimeError("not visible yet")
    passed = Mock()
    passed.raise_for_status.return_value = None
    passed.json.return_value = {"auditCompletionState": "Complete"}
    passed.content = b'{"auditCompletionState":"Complete"}'

    with patch("scripts.audits.common.requests.get", side_effect=[failed, passed]) as get:
      result = validate_public_json_artifacts(
        {"report.json": "https://example.test/report.json"},
        ["report.json"],
        attempts=2,
        delay_seconds=0,
      )

    self.assertEqual(get.call_count, 2)
    self.assertEqual(result["status"], "PASS")
    self.assertEqual(result["checked"]["report.json"]["attempt"], 2)


if __name__ == "__main__":
  unittest.main()
