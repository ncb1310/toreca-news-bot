import unittest
import news_bot as bot
from editorial import GUIDES

class HashtagTests(unittest.TestCase):
    def test_every_guide_has_relevant_hashtags_within_budget(self):
        for _, title, _, body, url in GUIDES:
            post = bot.format_post(dict(kind='guide',title=title,body=body,url=url))
            self.assertIn('#トレカ', post)
            self.assertIn('#トレカ初心者', post)
            self.assertLessEqual(len(post.removesuffix(url))*2+23,270)

    def test_news_game_and_event_tags_are_kept_even_for_long_titles(self):
        for source,title,expected in [('pokemon','ポケカ抽選販売'+'あ'*500,['#ポケカ','#抽選情報']),('onepiece','予約販売'+'あ'*500,['#ワンピースカード','#予約情報']),('labo','ポケカ再入荷'+'あ'*500,['#ポケカ','#再販情報'])]:
            item=dict(source=source,title=title,url='https://example.com/news',published='2026-11-15')
            post=bot.format_post(item)
            for tag in expected:
                self.assertIn(tag,post)
            self.assertLessEqual(len(post.removesuffix(item['url']))*2+23,270)

    def test_generic_retailer_posts_still_have_tags(self):
        item=dict(source='hobby',title='カード販売の公式案内',url='https://www.hbst.net/?p=1',published='2026-11-15')
        self.assertIn('#トレカ',bot.format_post(item))
