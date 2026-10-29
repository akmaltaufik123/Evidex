"""Mechanical checks for the user-provided Hallmark contract."""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class DesignContractTests(unittest.TestCase):
    def test_all_colors_and_fonts_use_tokens_after_root(self):
        css = (ROOT / 'evidex_next.css').read_text()
        root = css.index(':root {')
        rest = css[:root] + css[css.index('}', root) + 1:]
        self.assertNotRegex(rest, r'#[0-9a-fA-F]{3,8}\b|\b(?:oklch|rgba?|hsla?)\(')
        for value in re.findall(r'font-family:\s*([^;]+)', rest):
            self.assertRegex(value, r'^var\(--font-[\w-]+\)$')
        self.assertTrue(css.startswith('/* Hallmark'))
        self.assertIn('pre-emit critique:', css)

    def test_responsive_floor_is_declared(self):
        css = (ROOT / 'evidex_next.css').read_text()
        self.assertIn('html, body', css)
        self.assertIn('overflow-x: clip', css)
        self.assertNotIn('overflow-x: hidden', css)
        self.assertNotIn('100vw', css)
        self.assertNotIn('transition: all', css)
        self.assertNotRegex(css, r'grid-template-columns:[^;]*\s\d+(?:\.\d+)?fr\s*[;}]')
        self.assertIn('overflow-wrap: anywhere', css)
        self.assertIn('prefers-reduced-motion', css)
        self.assertIn('focus-visible', css)

    def test_active_images_do_not_use_the_legacy_device_mockups(self):
        catalog = json.loads((ROOT / 'evidex_next_content.json').read_text())
        for page in catalog['guide']:
            self.assertTrue(page['image'].endswith('-paper.webp'))
            self.assertTrue((ROOT / 'guide_assets' / page['image']).is_file())
        html = (ROOT / 'evidex_next.html').read_text()
        self.assertNotRegex(html, r'style="[^"]*(?:color|font-family)\s*:')
        self.assertIn('<figure class="guide-figure">', html)
        self.assertIn('<figcaption', html)
