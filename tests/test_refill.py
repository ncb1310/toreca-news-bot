import unittest
from datetime import datetime
from unittest.mock import patch
import news_bot as shared
import refill_queue as refill

class RefillTests(unittest.TestCase):
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
