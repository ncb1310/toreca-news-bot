import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from PIL import Image
import news_bot as bot
from post_cards import render_card

class ImageTests(unittest.TestCase):
    def test_missing_or_generic_image_never_calls_mutation(self):
        for item in ({}, {'image_url': bot.NEWS_IMAGE_URL}):
            with patch.object(bot, 'buffer_query') as api:
                with self.assertRaises(ValueError):
                    bot.send(item, 'channel')
                api.assert_not_called()

    def test_post_specific_image_is_the_attached_asset(self):
        url = 'https://raw.githubusercontent.com/ncb1310/toreca-news-bot/revision/assets/generated/unique.png'
        with patch.object(bot, 'format_post', return_value='news'), patch.object(bot, 'buffer_query', return_value={'createPost': {'post': {'id': 'ok'}}}) as api:
            self.assertEqual(bot.send({'image_url': url}, 'channel'), 'ok')
            self.assertIn(url, api.call_args.args[0])
            self.assertNotIn(bot.NEWS_IMAGE_URL, api.call_args.args[0])

    def test_rendered_cards_change_with_content_and_preserve_size(self):
        item = dict(key='a', title='抽選の締切、3つを分けよう', kind='guide', bullets=['応募締切', '当選発表日', '当選後の購入期限'], url='https://www.pokemon-card.com/')
        with tempfile.TemporaryDirectory() as directory:
            a = render_card(item, '確認ガイド', datetime(2026,11,15,17,0), Path(directory)/'a.png')
            b = render_card(dict(item, title='ポケカの60枚デッキ入門'), '確認ガイド', datetime(2026,11,15,17,0), Path(directory)/'b.png')
            with Image.open(a) as rendered:
                self.assertEqual(rendered.size, (1200, 1200))
            self.assertNotEqual(a.read_bytes(), b.read_bytes())
