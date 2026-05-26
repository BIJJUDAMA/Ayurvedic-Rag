import unittest
import sys
import os

# Add src to path so we can import the module
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

class TestNoiseManifest(unittest.TestCase):
    def test_import(self):
        from chunking.shusrut_samhita_chunking.noise_manifest import clean_noise
        self.assertIsNotNone(clean_noise)

    def test_clean_noise_indological_truths(self):
        from chunking.shusrut_samhita_chunking.noise_manifest import clean_noise
        text = "Some text ## Indological Truths more text"
        self.assertEqual(clean_noise(text), "Some text  more text")

    def test_clean_noise_base64_image(self):
        from chunking.shusrut_samhita_chunking.noise_manifest import clean_noise
        text = "Image data: data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="
        self.assertEqual(clean_noise(text), "Image data:")

    def test_clean_noise_dashes(self):
        from chunking.shusrut_samhita_chunking.noise_manifest import clean_noise
        text = "Text --- more text -- end"
        self.assertEqual(clean_noise(text), "Text  more text  end")

    def test_clean_noise_ss_pattern(self):
        from chunking.shusrut_samhita_chunking.noise_manifest import clean_noise
        text = "Chapter 1 ## S.S. II. 123 text"
        self.assertEqual(clean_noise(text), "Chapter 1  text")
        
        text = "Chapter 2 ## S.S.  II.  456 more text"
        self.assertEqual(clean_noise(text), "Chapter 2  more text")

    def test_clean_noise_suggested_problems(self):
        from chunking.shusrut_samhita_chunking.noise_manifest import clean_noise
        text = "Some text SUGGESTED RESEARCH PROBLEMS and some more info\non next line"
        # Testing DOTALL - it should remove everything after SUGGESTED...
        self.assertEqual(clean_noise(text), "Some text")

    def test_clean_noise_send_suggestions(self):
        from chunking.shusrut_samhita_chunking.noise_manifest import clean_noise
        text = "Text SEND US YOUR SUGGESTIONS for this project\nmore lines"
        self.assertEqual(clean_noise(text), "Text")

    def test_clean_noise_case_insensitive(self):
        from chunking.shusrut_samhita_chunking.noise_manifest import clean_noise
        text = "## indological truths"
        self.assertEqual(clean_noise(text), "")

    def test_clean_noise_strip(self):
        from chunking.shusrut_samhita_chunking.noise_manifest import clean_noise
        text = "   Some text   "
        self.assertEqual(clean_noise(text), "Some text")

if __name__ == '__main__':
    unittest.main()
