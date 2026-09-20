from __future__ import annotations

import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from pypdf import PdfReader
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from scripts import generate_ai_glossary_pdf
from scripts.sync_manuscript_samples import extract_chapter


def _write_manuscript_fixture(path: Path) -> None:
    pdf = canvas.Canvas(str(path), pagesize=A4, pageCompression=1, invariant=1)
    width, height = A4

    def page(heading: str | None, prefix: str, start: int) -> None:
        text = pdf.beginText(42, height - 48)
        text.setFont("Helvetica", 9)
        if heading:
            text.textLine(heading)
            text.textLine("")
        counter = start
        for _ in range(28):
            words = [f"{prefix}{counter + offset}" for offset in range(8)]
            text.textLine(" ".join(words))
            counter += 8
        pdf.drawText(text)
        pdf.showPage()

    page("Chapter 1: Foundations of Responsible AI", "body", 0)
    page(None, "continued", 0)
    page("Chapter 2: Applying the Framework", "next", 0)
    pdf.save()


class PdfPipelineRegressionTests(unittest.TestCase):
    def test_glossary_generation_is_deterministic_and_readable(self) -> None:
        original_out = generate_ai_glossary_pdf.OUT
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                first = Path(temp_dir) / "glossary-first.pdf"
                second = Path(temp_dir) / "glossary-second.pdf"

                with redirect_stdout(StringIO()):
                    generate_ai_glossary_pdf.OUT = first
                    generate_ai_glossary_pdf.main()
                    generate_ai_glossary_pdf.OUT = second
                    generate_ai_glossary_pdf.main()

                self.assertEqual(first.read_bytes(), second.read_bytes())

                reader = PdfReader(str(first))
                self.assertFalse(reader.is_encrypted)
                self.assertEqual(len(reader.pages), 1)
                text = "\n".join((page.extract_text() or "") for page in reader.pages)
                self.assertIn("AI Edge: AI Glossary Cheat Sheet", text)
                self.assertIn("Artificial intelligence (AI)", text)
        finally:
            generate_ai_glossary_pdf.OUT = original_out

    def test_reportlab_fixture_can_be_extracted_by_manuscript_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = Path(temp_dir) / "manuscript.pdf"
            _write_manuscript_fixture(fixture)
            result = extract_chapter(fixture)

        self.assertEqual(result["chapter_title"], "Chapter 1: Foundations of Responsible AI")
        self.assertEqual(result["page_start"], 1)
        self.assertEqual(result["page_end"], 2)
        self.assertGreaterEqual(result["word_count"], 350)
        self.assertTrue(result["paragraphs"])


if __name__ == "__main__":
    unittest.main()
