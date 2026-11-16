from datetime import datetime, timedelta
import tempfile
from pathlib import Path
from unittest.mock import patch
import unittest
import kingshot_bot as bot

NOW=datetime(2026,11,16,13,10,tzinfo=bot.shared.JST)
CFG={'max_posts_per_day':15,'daily_target':12,'min_interval_minutes':45,
     'morning_images':['https://example.test/morning.jpg']}

class KingshotTests(unittest.TestCase):
    def choose(self,state,news=None,at=NOW):
        with tempfile.TemporaryDirectory() as directory, patch.object(bot,'ROOT',Path(directory)):
            return bot.select(state,news or [],at,CFG)

    def test_first_baseline_is_not_replayed_as_news(self):
        state={'posts':{},'baseline':{'publisher':['https://official.test/a']}}
        news=[{'key':'new','source':'publisher','identity':'https://official.test/a'}]
        self.assertNotEqual(self.choose(state,news)['key'],'new')

    def test_unknown_send_blocks_all_further_mutations(self):
        self.assertIsNone(self.choose({'posts':{'a':{'status':'uncertain'}}}))

    def test_pacing_and_daily_cap(self):
        state={'posts':{'a':{'status':'accepted','attempted_at':NOW.isoformat(),'attempt_date':NOW.date().isoformat()}}}
        self.assertIsNone(self.choose(state))
        state={'posts':{str(i):{'status':'accepted','attempt_date':NOW.date().isoformat()} for i in range(15)}}
        self.assertIsNone(self.choose(state))

    def test_guide_cooldown_and_exhaustion(self):
        first=self.choose({'posts':{}})
        history={g[0]:{'status':'accepted','guide_id':g[0],'attempt_date':'2026-11-15'} for g in bot.GUIDES}
        self.assertIsNone(self.choose({'posts':history}))
        next_item=self.choose({'posts':{first['key']:dict(first,status='accepted',attempt_date='2026-11-15')}})
        self.assertNotEqual(first['guide_id'],next_item['guide_id'])

    def test_morning_image_only_used_in_morning(self):
        self.assertEqual(self.choose({'posts':{}},at=NOW.replace(hour=8))['kind'],'morning')
        self.assertNotEqual(self.choose({'posts':{}})['image_url'],CFG['morning_images'][0])

    def test_source_text_hashtags_and_image(self):
        for index in range(len(bot.GUIDES)):
            used={g[0]:{'status':'accepted','guide_id':g[0],'attempt_date':'2026-11-15'} for g in bot.GUIDES[:index]}
            item=self.choose({'posts':used})
            self.assertIn('#キングショット',item['text'])
            self.assertIn(bot.APP,item['text'])
            self.assertIn('/assets/kingshot/',item['image_url'])
            # URL gets 23 weighted units, ASCII 1, Japanese 2; emoji 2.
            rest=item['text'].replace(bot.APP,'')
            self.assertLessEqual(sum(1 if ord(c)<128 else 2 for c in rest)+23,280)

    def test_news_never_uses_morning_or_restricted_strategy_art(self):
        config={'media_pool':[
            {'id':'morning','url':'morning.jpg','allowed_kinds':['morning']},
            {'id':'rally','url':'rally.jpg','allowed_kinds':['guide'],'guide_ids':['formation']},
            {'id':'news','url':'news.jpg','allowed_kinds':['news','guide']}]}
        self.assertEqual(bot.select_image({'image_url':'old.jpg'},{'posts':{}},config),'news.jpg')
        self.assertEqual(bot.select_image({'kind':'guide','guide_id':'avatar','image_url':'old.jpg'},{'posts':{}},config),'news.jpg')

    def test_image_rotation_prefers_less_recently_used_picture(self):
        config={'media_pool':[{'id':str(i),'url':str(i)+'.jpg','allowed_kinds':['guide']} for i in range(2)]}
        state={'posts':{'old':{'image_url':'0.jpg','attempted_at':'2026-11-16T12:00:00+09:00'}}}
        self.assertEqual(bot.select_image({'kind':'guide','image_url':'old.jpg'},state,config),'1.jpg')

if __name__=='__main__':
    unittest.main()
