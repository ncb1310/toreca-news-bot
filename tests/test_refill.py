import unittest
from datetime import datetime
from unittest.mock import patch
import news_bot as shared
import refill_queue as refill
import tempfile
from pathlib import Path
from urllib.error import HTTPError

class RefillTests(unittest.TestCase):
    def test_rate_limit_is_persisted_and_prevents_further_requests(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'data').mkdir()
            error=HTTPError('https://api.buffer.com',429,'rate limited',{'Retry-After':'7200'},None)
            with patch.object(shared,'ROOT',root),patch.dict('os.environ',{'BUFFER_API_KEY':'test-only'}),patch.object(shared,'urlopen',side_effect=error) as request,patch.object(shared,'checkpoint'):
                with self.assertRaises(shared.BufferRateLimit):shared.buffer_query('query { account { id } }')
                with self.assertRaises(shared.BufferRateLimit):shared.buffer_query('query { account { id } }')
                self.assertEqual(request.call_count,1)
                self.assertTrue((root/'data/buffer-api-budget.json').exists())
    def test_senran_slots_have_correct_hours_and_are_future_only(self):
        now=datetime(2026,11,17,0,30,tzinfo=shared.JST)
        slots=list(refill.slots('senran1515',now))
        self.assertEqual([d.hour for d in slots[:8]],[8,12,18,22]*2)
        self.assertTrue(all(d>now for d in slots))
    def test_kingshot_has_eight_spaced_daily_slots(self):
        now=datetime(2026,11,17,0,30,tzinfo=shared.JST)
        slots=list(refill.slots('kingshot5555',now))
        self.assertEqual(len(slots[:8]),8)
        self.assertTrue(all((b-a).total_seconds()>=7200 for a,b in zip(slots,slots[1:])))
    def test_close_slots_are_not_scheduled_in_past(self):
        now=datetime(2026,11,17,7,50,tzinfo=shared.JST)
        self.assertEqual(next(refill.slots('senran1515',now)).hour,12)
    def test_queue_pagination_does_not_allow_unchecked_send(self):
        with patch.object(shared,'buffer_query',return_value={'posts':{'pageInfo':{'hasNextPage':True},'edges':[]}}):
            with self.assertRaises(RuntimeError):refill.queued('org','channel')
