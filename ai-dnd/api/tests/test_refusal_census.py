"""Every refusal code a fight or an action can raise has a Turkish text, and every product function that shows that
text also tells the narrator (Dilim 2, Task 13; J-014 #6, tasarım karar 59)."""
import ast
import unittest
from pathlib import Path

import refusals

ROOT = Path(__file__).resolve().parents[2]          # ai-dnd/
SCANNED = ("action_economy.py", "combat_lifecycle.py", "weapon_attack.py", "game.py")   # + spell modules below


def _spell_modules():
    return sorted(p.relative_to(ROOT).as_posix() for p in ROOT.glob("*.py") if "spell" in p.name and not p.name.startswith("test_"))


def codes_found():
    codes = set()
    for rel in (*SCANNED, *_spell_modules()):
        for node in ast.walk(ast.parse((ROOT / rel).read_text(encoding="utf-8-sig"))):
            if (isinstance(node, ast.Call) and (getattr(node.func, "id", None) or getattr(node.func, "attr", None))
                    in {"fail", "CombatRequestError"} and node.args and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)):
                codes.add(node.args[0].value)
    return codes


class RefusalCensus(unittest.TestCase):
    def test_every_fail_code_has_turkish_text(self):
        found = codes_found()
        self.assertIn("invalid_ready_trigger", found)                     # the scan really sees action_economy
        self.assertEqual(sorted(found - set(refusals.REFUSAL_TEXT)), [])
        self.assertEqual([code for code in found if not refusals.REFUSAL_TEXT[code].strip()], [])

    def test_every_text_for_caller_also_notes(self):
        # J-014 #6 (tasarım karar 59): a refusal the player sees is also a note the narrator reads; HTTP panel text is the one exception
        missing = []
        for path in sorted(ROOT.rglob("*.py")):
            rel = path.relative_to(ROOT).as_posix()
            if ("/tests/" in f"/{rel}" or rel.startswith(("legacy_debug/", "docs/", "reports/")) or "__pycache__" in rel
                    or ("/" not in rel and rel.startswith("test_")) or rel in {"refusals.py", "api/main.py"}):
                continue
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                called = {sub.func.attr for sub in ast.walk(node) if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute)
                          and isinstance(sub.func.value, ast.Name) and sub.func.value.id == "refusals"}
                if "text_for" in called and "note" not in called:
                    missing.append(f"{rel}:{node.name}")
        self.assertEqual(missing, [])
        self.assertIn("combat_refusal_turn", {n.name for n in ast.walk(ast.parse((ROOT / "game.py").read_text(encoding="utf-8-sig")))
                                              if isinstance(n, ast.FunctionDef)
                                              and "note" in {s.func.attr for s in ast.walk(n) if isinstance(s, ast.Call)
                                                             and isinstance(s.func, ast.Attribute)}})

    def test_the_named_texts_are_word_for_word(self):
        self.assertEqual(refusals.REFUSAL_TEXT["invalid_ready_trigger"],
                         "Hazırlanmak için neyi bekleyeceğini ve o olunca ne yapacağını söyle (ör. 'Haydut yaklaşırsa vururum').")
        self.assertEqual(refusals.text_for("weapon_not_owned", weapon="Kılıç"), "Kılıç yok; yumrukla vuruyorsun.")
        self.assertEqual(refusals.text_for("which_enemy", names="Haydut mu, Okçu mu"), "Hangisine yaklaşıyorsun: Haydut mu, Okçu mu?")


if __name__ == "__main__":
    unittest.main()
