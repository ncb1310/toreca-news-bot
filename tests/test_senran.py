import unittest
from datetime import datetime
import news_bot as shared
from senran_bot import select, BANK

class SenranTests(unittest.TestCase):
    def at(self,hour,day=17):
        return datetime(2026,11,day,hour,0,tzinfo=shared.JST)
    def test_before_morning(self):
        self.assertIsNone(select({'posts':{}},self.at(7)))
    def test_slots(self):
        for h,k in [(8,'morning'),(12,'noon'),(18,'evening'),(22,'night')]:
            post=select({'posts':{}},self.at(h))
            self.assertEqual(post['kind'],k)
            self.assertIn('/'+k+'.jpg',post['image_url'])
            self.assertIn('#創作',post['text'])
    def test_no_stale_morning(self):
        self.assertEqual(select({'posts':{}},self.at(21))['kind'],'evening')
    def test_no_duplicate(self):
        self.assertIsNone(select({'posts':{'2026-11-17-evening':{}}},self.at(21)))
    def test_unknown_outcome_blocks(self):
        self.assertIsNone(select({'posts':{'x':{'status':'uncertain'}}},self.at(21)))
    def test_spacing(self):
        p={'attempted_at':self.at(22).isoformat(),'status':'accepted'}
        self.assertIsNone(select({'posts':{'previous':p}},self.at(22)))
    def test_existing_noon_not_duplicated(self):
        self.assertIsNone(select({'posts':{}},self.at(12,16)))
    def test_bank_length(self):
        for entries in BANK.values():
            self.assertEqual(len(entries),len(set(entries)))
            self.assertTrue(all(len(x)<200 for x in entries))
