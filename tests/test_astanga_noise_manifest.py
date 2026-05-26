import unittest
import sys
import os

# Add src to path so we can import the module
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

class TestAstangaNoiseManifest(unittest.TestCase):
    def test_import(self):
        from chunking.astanga_hridya_chunking.noise_manifest import clean_noise
        self.assertIsNotNone(clean_noise)

    def test_clean_noise_header(self):
        from chunking.astanga_hridya_chunking.noise_manifest import clean_noise
        text = "## Astanga Hridaya Sutrasthan Chapter 1"
        self.assertEqual(clean_noise(text), "Chapter 1")

    def test_clean_noise_dashes(self):
        from chunking.astanga_hridya_chunking.noise_manifest import clean_noise
        text = "Text --- more text -- end"
        self.assertEqual(clean_noise(text), "Text  more text  end")

    def test_clean_noise_code_fences(self):
        from chunking.astanga_hridya_chunking.noise_manifest import clean_noise
        text = "```text\ncontent\n```"
        self.assertEqual(clean_noise(text), "text\ncontent")

    def test_clean_noise_case_insensitive(self):
        from chunking.astanga_hridya_chunking.noise_manifest import clean_noise
        text = "## ASTANGA HRIDAYA SUTRASTHAN Title"
        self.assertEqual(clean_noise(text), "Title")

    def test_clean_noise_strip(self):
        from chunking.astanga_hridya_chunking.noise_manifest import clean_noise
        text = "   Some text   "
        self.assertEqual(clean_noise(text), "Some text")

if __name__ == '__main__':
    unittest.main()
