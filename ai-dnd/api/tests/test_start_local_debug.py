"""start_local.ps1 -LocalPlay turns on the speech trail so the model's raw speech can be read after play."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[3] / "start_local.ps1"


def local_play_block(text: str) -> str:
    start = text.index("if ($LocalPlay) {")
    depth = 0
    for index in range(start, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[start:index]
    raise AssertionError("LocalPlay block not closed")


class LocalPlaySpeechTrail(unittest.TestCase):
    def test_local_play_turns_on_the_speech_trail(self):
        block = local_play_block(SCRIPT.read_text(encoding="utf-8"))
        self.assertRegex(block, r"if \(-not \$env:AI_DND_SPEECH_DEBUG\)\s*\{[^}]*\$env:AI_DND_SPEECH_DEBUG\s*=\s*Join-Path \$saveDir \"speech-debug\.jsonl\"")

    def test_save_dir_is_made_before_the_trail_uses_it(self):
        block = local_play_block(SCRIPT.read_text(encoding="utf-8"))
        made = block.index("New-Item -ItemType Directory -Force -Path $saveDir")
        self.assertLess(block.index("$saveDir = "), made)
        self.assertLess(made, block.index("AI_DND_SPEECH_DEBUG ="))
        # the directory creation is not inside the campaign-db guard
        guard = re.search(r"if \(-not \$env:AI_DND_CAMPAIGN_DB\) \{[^}]*\}", block).group(0)
        self.assertNotIn("New-Item", guard)


if __name__ == "__main__":
    unittest.main()
