import unittest
from pathlib import Path

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


if __name__ == "__main__":
  unittest.main()
