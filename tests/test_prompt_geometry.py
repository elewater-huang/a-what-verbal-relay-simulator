"""Tkinter regression test: incoming questions must not move the phrase buttons.

This test exercises the actual layout when a graphical display is available.
On headless machines without X11/Windows/macOS display, it skips cleanly.
To exercise it headlessly on Linux: xvfb-run -a python -m unittest discover -s tests
"""
import tkinter as tk
import unittest
from types import SimpleNamespace

from app import App


class PromptGeometryTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError:
            self.skipTest('Tkinter display not available')
        self.app = App(self.root)
        self.root.update()

    def tearDown(self):
        if hasattr(self, 'app'):
            self.app.close()

    def button_rectangles(self):
        return {(side, code): (button.winfo_rootx(),
                               button.winfo_rooty(),
                               button.winfo_width(),
                               button.winfo_height())
                for side in ('L', 'R')
                for code, button in self.app.phrase_btns[side].items()}

    def test_pending_prompts_and_language_switch_keep_all_buttons_fixed(self):
        original = self.button_rectangles()
        answer = SimpleNamespace(context='answer')
        ask_back = SimpleNamespace(context='ask-back')
        finish = SimpleNamespace(context='finish')
        cases = [
            {'L': [], 'R': []},
            {'L': [answer], 'R': []},
            {'L': [], 'R': [ask_back]},
            {'L': [answer, finish], 'R': [ask_back]},
            {'L': [answer] * 15, 'R': [finish] * 10},
            {'L': [], 'R': []},
        ]
        for case in cases:
            self.app.on_prompt(case)
            self.root.update()
            self.assertEqual(self.button_rectangles(), original)
        self.app.switch_lang(1)
        self.root.update()
        self.assertEqual(self.button_rectangles(), original)
        self.app.switch_lang(0)
        self.root.update()
        self.assertEqual(self.button_rectangles(), original)


if __name__ == '__main__':
    unittest.main()
