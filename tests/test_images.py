import unittest
from unittest.mock import patch
import news_bot as bot

class ImageTests(unittest.TestCase):
    def test_every_news_mutation_includes_stable_image(self):
        with patch.object(bot, 'format_post', return_value='news'), patch.object(bot, 'buffer_query', return_value={'createPost': {'post': {'id': 'ok'}}}) as api:
            self.assertEqual(bot.send({}, 'channel'), 'ok')
            query = api.call_args.args[0]
            self.assertIn('assets: [{ image: { url:', query)
            self.assertIn(bot.NEWS_IMAGE_URL, query)
            self.assertNotIn('assets: []', query)
