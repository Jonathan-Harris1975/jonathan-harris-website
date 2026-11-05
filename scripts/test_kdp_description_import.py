"""D1 description changes survive import, subsequent loads and public rendering."""
import copy
import html
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import ebook_pipeline as pipeline
from scripts.import_ebook_catalogue import build_import_workbook


class KdpDescriptionImportTests(unittest.TestCase):
    def test_canonical_description_survives_old_overrides_and_is_visible(self):
        book = copy.deepcopy(pipeline.read_json(pipeline.MASTER_PATH)[0])
        approved = 'Explore race strategy and real-time analytics. A grounded guide to the decisions behind every lap, with practical questions for curious readers.'
        book['description'] = approved
        self.assertIn(book['slug'], pipeline.BOOK_SPECIFIC_DESCRIPTION_OVERRIDES)
        with tempfile.TemporaryDirectory() as directory:
            workbook = Path(directory) / 'd1.xlsx'
            master = Path(directory) / 'master.json'
            build_import_workbook([book], workbook)
            records = pipeline.build_master_from_workbook(workbook, preserve_description=True)
            self.assertEqual(records[0]['description'], approved)
            with patch.object(pipeline, 'MASTER_PATH', master):
                pipeline.save_master(records)
                loaded = pipeline.load_master()
            self.assertEqual(loaded[0]['description'], approved)
            with patch.object(pipeline, 'render_header', return_value=''), patch.object(pipeline, 'render_footer', return_value=''):
                page = pipeline.render_book_page(loaded[0], loaded)
            overview = page.split('id="deeper-overview"', 1)[1].split('</section>', 1)[0]
            self.assertIn(html.escape(approved), overview)
            self.assertEqual(pipeline.build_book_schema(loaded[0])['description'], approved)

    def test_workbook_bootstrap_retains_existing_editorial_overrides(self):
        book = copy.deepcopy(pipeline.read_json(pipeline.MASTER_PATH)[0])
        book['description'] = 'This workbook description is retained only when importing the D1 catalogue.'
        with tempfile.TemporaryDirectory() as directory:
            workbook = Path(directory) / 'bootstrap.xlsx'
            build_import_workbook([book], workbook)
            records = pipeline.build_master_from_workbook(workbook)
        self.assertEqual(records[0]['description'], pipeline.BOOK_SPECIFIC_DESCRIPTION_OVERRIDES[book['slug']])
        self.assertNotIn('description_source', records[0])

    def test_d1_description_is_not_rewritten_by_legacy_phrase_replacements(self):
        record = {'slug': 'test', 'title': 'Test', 'topic': 'Artificial Intelligence',
                  'description_source': 'kdp-d1', 'description': 'A comprehensive guide to AI, with practical details.'}
        expected = record['description']
        pipeline.sanitise_record_copy(record)
        self.assertEqual(record['description'], expected)


if __name__ == '__main__':
    unittest.main()
