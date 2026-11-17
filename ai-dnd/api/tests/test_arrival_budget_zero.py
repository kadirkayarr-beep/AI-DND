"""BM Task 10 (D-324): when the Python entry already fills the return cap, no model call is made and the source says python."""
import game
from api.tests.test_arrival_narration import NOTICE, Fixture


class ArrivalBudgetZero(Fixture):
    def full_python_return(self, answer="Rüzgâr esiyor. Otlar eğiliyor."):
        scene = self.return_after(3 * 3600)
        self.assertTrue(scene["wants_model"])
        lead = f"Kent kapısından geçip giriyorsun. {scene['name']} önüne geliyorsun. Kapı kapalı. Kapı kolunu çevirip açıyorsun. "
        text, info = self.narrate(scene=scene, answer=answer, lead=lead, tail=NOTICE)
        return scene, text, info

    def test_full_python_return_makes_no_call(self):
        scene, text, info = self.full_python_return()
        self.assertEqual(self.client.calls, [])
        self.assertEqual((info["source"], info["calls"]), ("python", 0))
        self.assertLessEqual(len(game._split_sentences_keep_speech(text)), 4, text)
        self.assertIn(NOTICE, text)
        self.assertIn(scene["name"], text)

    def test_room_left_still_calls_the_model(self):
        scene = self.return_after(3 * 3600)
        _, info = self.narrate(scene=scene, answer="Rüzgâr esiyor. Otlar eğiliyor.")
        self.assertEqual(info["source"], "model")
        self.assertEqual(len(self.client.calls), 1)
