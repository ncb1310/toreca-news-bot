from copy import deepcopy
from datetime import datetime
import unittest
from unittest.mock import patch
import json
from pathlib import Path
import tempfile
import news_bot as bot

POKEMON = '''<li id="newsTab_all"><a class="List_item_inner" href="/info/new.html">
<img alt="拡張パックの予約販売を開始！"><div class="List_body">
<div class="Calendar_Label">商品</div><span class="Date">2026.11.14</span></div></a></li>
<li id="newsTab_product"><a class="List_item_inner" href="/info/duplicate.html">
<img alt="別タブ"><span class="Date">2026.11.14</span></a></li>'''
ONEPIECE = '''<ul class="topicsBox"><li class="topicDetail row-4"><a href="/products/new.php">
<dt class="topicTit"><span class="js_topicTit">カードセット再販決定！</span></dt>
<dd class="topicCategory"><object><a href="?tags=products">PRODUCTS</a></object></dd>
<dd class="topicDate">2026.11.14</dd></a></li></ul>'''
NOW = datetime(2026, 11, 14, 12, tzinfo=bot.JST)


class NewsTests(unittest.TestCase):
    def item(self):
        return bot.parse('pokemon', POKEMON)[0]

    def test_pokemon_uses_only_all_tab(self):
        items = bot.parse('pokemon', POKEMON)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['title'], '拡張パックの予約販売を開始！')
        self.assertEqual(items[0]['url'], 'https://www.pokemon-card.com/info/new.html')

    def test_onepiece_nested_anchor_preserves_product_url(self):
        item = bot.parse('onepiece', ONEPIECE)[0]
        self.assertEqual(item['url'], 'https://www.onepiece-cardgame.com/products/new.php')
        self.assertEqual(item['category'], 'PRODUCTS')

    def test_changed_layout_fails_instead_of_emptying_baseline(self):
        with self.assertRaises(ValueError):
            bot.parse('pokemon', '<html>blocked or changed</html>')

    def test_external_and_non_https_links_rejected(self):
        for href in ['https://evil.test/', 'http://www.pokemon-card.com/a', 'javascript:alert(1)']:
            self.assertIsNone(bot.canonical_url(bot.SOURCES['pokemon'][1], href))

    def test_first_run_is_baseline_not_post(self):
        state = {}
        bot.update_state(state, {'pokemon': [self.item()]}, NOW)
        self.assertIsNone(bot.select_candidate(state, NOW, 3))

    def test_new_item_after_baseline_is_candidate(self):
        state = {'sources': {'pokemon': {}}, 'items': {}}
        bot.update_state(state, {'pokemon': [self.item()]}, NOW)
        self.assertIsNotNone(bot.select_candidate(state, NOW, 3))
        count = len(state['items'])
        bot.update_state(state, {'pokemon': [self.item()]}, NOW)
        self.assertEqual(len(state['items']), count)

    def test_same_url_updated_title_gets_distinct_identity(self):
        a = self.item()
        b = bot.parse('pokemon', POKEMON.replace('予約販売を開始', '再販が決定'))[0]
        self.assertEqual(a['url'], b['url'])
        self.assertNotEqual(a['key'], b['key'])

    def test_old_future_event_and_relative_day_rejected(self):
        for updates in [{'published': '2026-01-01'}, {'published': '2026-12-31'},
                        {'title': '大会の抽選エントリー開始'},
                        {'title': '本日発売', 'published': '2026-11-13'}]:
            self.assertFalse(bot.eligible(dict(self.item(), **updates), NOW))

    def test_daily_limit_and_quiet_hours(self):
        item = dict(self.item(), status='ready')
        state = {'items': {'new': item}}
        self.assertIsNone(bot.select_candidate(state, NOW.replace(hour=4), 3))
        state['items']['previous'] = dict(item, status='accepted', attempt_date='2026-11-14')
        self.assertIsNone(bot.select_candidate(state, NOW, 1))

    def test_uncertain_or_in_progress_stops_all_new_posts(self):
        for status in ['sending', 'uncertain']:
            state = {'items': {'new': dict(self.item(), status='ready'),
                               'old': dict(self.item(), status=status)}}
            self.assertIsNone(bot.select_candidate(state, NOW, 3))

    def test_post_budget(self):
        item = dict(self.item(), title='あ' * 500)
        post = bot.format_post(item)
        self.assertLessEqual(2 * len(post.removesuffix(item['url'])) + 23, 270)

    def test_expired_ready_item_never_publishes(self):
        state = {'sources': {'pokemon': {}}, 'items': {}}
        bot.update_state(state, {'pokemon': [self.item()]}, NOW)
        bot.update_state(state, {}, NOW.replace(day=20))
        self.assertEqual(next(iter(state['items'].values()))['status'], 'expired')

    def test_mutation_contains_exact_verified_target(self):
        with patch('news_bot.buffer_query', return_value={'createPost': {'post': {'id': 'post'}}}) as api:
            self.assertEqual(bot.send(self.item(), 'selected-channel'), 'post')
            query = api.call_args.args[0]
            self.assertIn('"selected-channel"', query)
            self.assertIn('mode: shareNow', query)

    def test_api_rejection_not_success(self):
        with patch('news_bot.buffer_query', return_value={'createPost': {'message': 'rejected'}}):
            with self.assertRaises(ValueError):
                bot.send(self.item(), 'selected-channel')

    def test_wrong_platform_rejected(self):
        with patch('news_bot.buffer_query', return_value={'channel': {'id': 'channel', 'service': 'instagram'}}):
            with self.assertRaises(ValueError):
                bot.check_channel('channel')

    def test_retailer_shop_name_is_preserved(self):
        html = '''<div class="claboCard"><strong class="claboCard_title"><a href="/shop/himeji/blog/1/">ONE PIECEカード再販抽選販売</a></strong><p class="claboCard_shop">姫路店</p><p class="claboCard_date">2026.11.14</p></div>'''
        item = bot.parse('labo', html)[0]
        self.assertEqual(item['store'], '姫路店')
        self.assertIn('姫路店', bot.format_post(item))
        self.assertTrue(bot.eligible(item, NOW))

    def test_aeon_ended_lottery_is_never_candidate(self):
        html = '''<a href="/campaign/campaign_detail/test"><img alt="ポケモンカードゲーム 抽選販売"><p>2026.11.14</p><span>終了しました</span></a>'''
        item = bot.parse('kids', html)[0]
        self.assertTrue(item['closed'])
        self.assertFalse(bot.eligible(item, NOW))

    def test_retailer_non_card_campaign_ignored(self):
        items = {}
        bot.record_retail(items, 'furu', 'ゲームソフト予約販売', '2026/11/14', '/news/game', '', '')
        self.assertFalse(bot.eligible(next(iter(items.values())), NOW))

    def test_pokemon_center_date_and_title(self):
        html = '''<a href="/news/?id=20261114"><span class="time">2026年11月14日</span><span class="ttl">ポケモンカードゲーム 抽選販売</span></a>'''
        item = bot.parse('pcstore', html)[0]
        self.assertEqual(item['published'], '2026-11-14')
        self.assertTrue(bot.eligible(item, NOW))

    def test_hobby_disallowed_ended_notice(self):
        html = '''<section id="news"><a href="https://www.hbst.net/?p=1"><h4>【2026.11.14】※応募は終了しました ポケモンカード抽選販売</h4></a></section>'''
        self.assertFalse(bot.eligible(bot.parse('hobby', html)[0], NOW))

    def test_start_date_is_japan_date(self):
        config = {'start_date_jst': '2026-11-15'}
        self.assertFalse(bot.publishing_started(config, NOW))
        self.assertTrue(bot.publishing_started(config, NOW.replace(day=15)))

    def test_failed_source_candidate_withheld_but_other_sources_work(self):
        item = dict(self.item(), status='ready')
        state = {'items': {'new': item}}
        self.assertIsNone(bot.select_candidate(state, NOW, 10, ['kids']))
        self.assertIsNotNone(bot.select_candidate(state, NOW, 10, ['pokemon']))

    def test_ended_update_cancels_pending_announcement(self):
        item = dict(self.item(), status='ready')
        state = {'sources': {'pokemon': {}}, 'items': {item['key']: item}}
        bot.update_state(state, {'pokemon': [dict(item, closed=True)]}, NOW)
        self.assertEqual(item['status'], 'expired')

    def test_no_send_if_durable_checkpoint_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'config.json').write_text(json.dumps({'channel_id': 'channel', 'posting_enabled': True, 'max_posts_per_day': 3}))
            state_path = root / 'data' / 'state.json'
            state_path.parent.mkdir()
            state_path.write_text(json.dumps({'sources': {'pokemon': {}, 'onepiece': {}}, 'items': {}}))
            with patch.object(bot, 'ROOT', root), patch.object(bot, 'STATE', state_path), \
                 patch('sys.argv', ['news_bot.py', '--live']), \
                 patch.dict('os.environ', {'GITHUB_ACTIONS': 'true'}), \
                 patch.object(bot, 'official_page', side_effect=[POKEMON, ONEPIECE]), \
                 patch.object(bot, 'checkpoint', side_effect=RuntimeError('push failed')), \
                 patch.object(bot, 'send') as send:
                with self.assertRaises(RuntimeError):
                    bot.main()
                send.assert_not_called()


if __name__ == '__main__':
    unittest.main()
