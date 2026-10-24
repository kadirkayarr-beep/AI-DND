"""A world/weather subject is not a question about the NPC's day."""
import unittest
import local_dialogue

class PersonalWeatherScopeTests(unittest.TestCase):
    def test_weather_not_npc_day(self):
        for text in ('Bugün hava nasıl?', 'Bugün havalar nasıl gidiyor?', 'Bugün kapı ne durumda?', 'Bugün nasıl bir hava var?', 'Bugün nasıl bir yol izleyeceğiz?'):
            with self.subTest(text=text):
                self.assertNotEqual(local_dialogue.personal_question_kind(text),'day')
    def test_direct_day_questions_preserved(self):
        for text in ('Günün nasıl geçiyor?', 'Nasılsın?', 'Keyfin nasıl?', 'Bugün nasıl gidiyor?'):
            with self.subTest(text=text):
                self.assertEqual(local_dialogue.personal_question_kind(text),'day')
