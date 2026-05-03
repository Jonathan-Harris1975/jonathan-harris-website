import unittest
from scripts.audits import seo_aeo_geo_forensic as audit


class SeoAeoGeoAnalysisAsyncTests(unittest.TestCase):
  def test_derive_analysis_url_from_callback(self):
    self.assertEqual(
      audit.derive_analysis_url('https://app.example.com/audits/seo-aeo-geo/callback'),
      'https://app.example.com/audits/seo-aeo-geo/analysis',
    )

  def test_extract_analysis_from_top_level_response(self):
    payload = {'analysis': {'executiveSummary': {'overallVerdict': 'ok'}}}
    self.assertEqual(audit._extract_analysis_payload(payload), payload['analysis'])

  def test_extract_analysis_from_async_job_response(self):
    analysis = {'executiveSummary': {'overallVerdict': 'ok'}}
    payload = {'job': {'result': {'analysis': analysis}}}
    self.assertEqual(audit._extract_analysis_payload(payload), analysis)

  def test_relative_status_url_uses_analysis_endpoint_origin(self):
    self.assertEqual(
      audit._resolve_status_url(
        'https://app.example.com/audits/seo-aeo-geo/analysis',
        '/audits/seo-aeo-geo/analysis/abc123',
      ),
      'https://app.example.com/audits/seo-aeo-geo/analysis/abc123',
    )


if __name__ == '__main__':
  unittest.main()
