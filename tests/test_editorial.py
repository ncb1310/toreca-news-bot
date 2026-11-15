from copy import deepcopy
from datetime import datetime, timedelta
from unittest.mock import patch
import unittest
import news_bot as bot
from editorial import GUIDES, select_fallback

NOW = datetime(2026, 11, 15, 17, 10, tzinfo=bot.JST)
CONFIG = dict(max_posts_per_day=15, daily_target=10, editorial_max_per_day=4, min_post_interval_minutes=55, catchup_days=30)

def product(**updates):
    return dict(dict(key='p', source='pokemon', title='拡張パック「テスト」が11月27日発売！', published='2026-11-13', category='商品', url='https://www.pokemon-card.com/ex/test/'), **updates)

class EditorialTests(unittest.TestCase):
    def test_old_baseline_can_become_a_labeled_product_spotlight(self):
        item = select_fallback({'items': {}}, {'pokemon': [product()]}, NOW, CONFIG)
        self.assertEqual(item['kind'], 'spotlight')
        self.assertIn('新着速報ではありません', bot.format_post(item))

    def test_old_sales_closed_future_relative_and_stale_items_are_not_recycled(self):
        for update in [dict(title='抽選予約受付中'), dict(closed=True), dict(published='2026-11-16'), dict(title='本日発売'), dict(published='2026-03-01')]:
            result = select_fallback({}, {'pokemon': [product(**update)]}, NOW, CONFIG)
            self.assertEqual(result['kind'], 'guide')

    def test_existing_url_sends_prevent_spotlight_duplicate(self):
        state = {'items': {'old': dict(product(), status='accepted', attempt_date='2026-11-14')}}
        self.assertEqual(select_fallback(state, {'pokemon': [product()]}, NOW, CONFIG)['kind'], 'guide')

    def test_guide_not_repeated_for_14_days(self):
        state = {}
        first = select_fallback(state, {}, NOW, CONFIG)
        state['editorial_posts'] = {first['key']: dict(first, status='accepted', attempt_date='2026-11-14')}
        second = select_fallback(state, {}, NOW, CONFIG)
        self.assertNotEqual(first['guide_id'], second['guide_id'])

    def test_exhausted_pool_does_not_repeat_just_to_hit_target(self):
        state = {'editorial_posts': {g[0]: dict(status='accepted', guide_id=g[0], attempt_date='2026-11-14') for g in GUIDES}}
        self.assertIsNone(select_fallback(state, {}, NOW, CONFIG))

    def test_uncertain_sends_quiet_hours_pacing_and_daily_target(self):
        for state, at in [({'items': {'a': dict(status='uncertain')}}, NOW), ({}, NOW.replace(hour=7)),
                          ({'items': {'a': dict(status='accepted', attempt_date='2026-11-15', attempted_at=NOW.isoformat())}}, NOW),
                          ({'items': {str(i): dict(status='accepted', attempt_date='2026-11-15') for i in range(10)}}, NOW)]:
            self.assertIsNone(select_fallback(state, {}, at, CONFIG))

    def test_guide_posts_fit_x_budget(self):
        for guide_id, title, bullets, body, url in GUIDES:
            post = bot.format_post(dict(kind='guide', title=title, body=body, url=url))
            self.assertLessEqual(len(post.removesuffix(url))*2+23, 270)

    def test_publication_read_failure_never_retries_send(self):
        state = {'items': {'a': dict(status='accepted', buffer_post_id='p')}}
        with patch.object(bot, 'buffer_query', side_effect=RuntimeError), patch.object(bot, 'send') as send:
            bot.reconcile_publications(state, NOW)
            send.assert_not_called()
            self.assertEqual(state['items']['a']['status'], 'accepted')

    def test_sent_url_is_recorded(self):
        state = {'items': {'a': dict(status='accepted', buffer_post_id='p')}}
        response = dict(id='p', status='sent', sentAt='2026-11-15T08:10:00Z', externalLink='https://x.com/toreca_joshi/status/1', assets=[{'mimeType':'image/png'}])
        with patch.object(bot, 'buffer_query', return_value={'post': response}):
            bot.reconcile_publications(state, NOW)
        self.assertEqual(state['items']['a']['publication_result']['status'], 'sent')

class VerificationTests(unittest.TestCase):
    def test_unreachable_guide_is_skipped_for_day_instead_of_blocking_pool(self):
        first = select_fallback({}, {}, NOW, CONFIG)
        first.update(status='verification_failed', verification_failed_date=NOW.date().isoformat())
        next_item = select_fallback({'editorial_posts': {first['key']: first}}, {}, NOW, CONFIG)
        self.assertNotEqual(first['guide_id'], next_item['guide_id'])

class LivePipelineTests(unittest.TestCase):
    def run_live(self, card_failure=None):
        import json
        import tempfile
        from pathlib import Path
        from contextlib import ExitStack, redirect_stdout
        import io
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            root = Path(directory)
            (root/'data').mkdir()
            (root/'config.json').write_text(json.dumps(dict(CONFIG, posting_enabled=True, editorial_enabled=True, channel_id='channel')))
            state = dict(sources={'pokemon': {}}, items={'p':dict(product(),status='baseline')},channel_check=dict(date=NOW.date().isoformat(),channel=dict(id='channel',service='twitter')))
            (root/'data/state.json').write_text(json.dumps(state))
            stack.enter_context(patch.object(bot,'ROOT',root))
            stack.enter_context(patch.object(bot,'STATE',root/'data/state.json'))
            stack.enter_context(patch.object(bot,'SOURCES',{'pokemon':('ポケカ','https://www.pokemon-card.com/info/')}))
            stack.enter_context(patch('sys.argv',['news_bot.py','--live']))
            stack.enter_context(patch.dict('os.environ',{'GITHUB_ACTIONS':'true'}))
            clock=stack.enter_context(patch.object(bot,'datetime'))
            clock.now.return_value=NOW
            clock.fromisoformat.side_effect=datetime.fromisoformat
            stack.enter_context(patch.object(bot,'official_page',return_value='verified'))
            stack.enter_context(patch.object(bot,'parse',return_value=[product()]))
            stack.enter_context(patch.object(bot,'checkpoint'))
            stack.enter_context(patch.object(bot,'check_channel',return_value=dict(id='channel',service='twitter')))
            stack.enter_context(patch.object(bot,'reconcile_publications'))
            def card(item, now):
                if card_failure:
                    raise card_failure
                item['image_url']='https://raw.githubusercontent.com/ncb1310/toreca-news-bot/revision/assets/generated/test.png'
            stack.enter_context(patch.object(bot,'publish_card',side_effect=card))
            send=stack.enter_context(patch.object(bot,'send',return_value='newpost'))
            with redirect_stdout(io.StringIO()):
                if card_failure:
                    with self.assertRaises(RuntimeError):
                        bot.main()
                else:
                    self.assertEqual(bot.main(),0)
            return send.call_count,json.loads((root/'data/state.json').read_text())

    def test_live_fallback_records_a_real_editorial_attempt(self):
        calls,state=self.run_live()
        self.assertEqual(calls,1)
        item=next(iter(state['editorial_posts'].values()))
        self.assertEqual(item['status'],'accepted')
        self.assertEqual(item['buffer_post_id'],'newpost')
        self.assertIn('/assets/generated/',item['image_url'])

    def test_live_renderer_failure_never_sends_text_only(self):
        calls,state=self.run_live(RuntimeError('font unavailable'))
        self.assertEqual(calls,0)
        self.assertFalse(any(i.get('attempt_date') for i in state['editorial_posts'].values()))
