import unittest
from quota_monitor.client import parse_usage
from quota_monitor.rings import ring_data
from quota_monitor.state import QuotaState

class RingsTests(unittest.TestCase):
    def test_unknown_is_not_full_or_exhausted(self):
        rows=ring_data(QuotaState())
        self.assertEqual([r['remaining'] for r in rows],[None,None])
        self.assertEqual([r['value'] for r in rows],['--','--'])
        self.assertEqual([r['label'] for r in rows],['5小时','一周'])

    def test_zero_missing_and_service_window_labels(self):
        state=QuotaState()
        state.success(parse_usage({'rate_limit':{'primary_window':{'used_percent':100,'limit_window_seconds':21600},'secondary_window':None}}))
        rows=ring_data(state)
        self.assertEqual(rows[0],{'remaining':0.0,'value':'0%','label':'6小时','short_label':'6h'})
        self.assertIsNone(rows[1]['remaining'])
        self.assertEqual(rows[1]['value'],'--')

    def test_ring_fraction_uses_remaining_not_used(self):
        state=QuotaState()
        state.success(parse_usage({'rate_limit':{'primary_window':{'used_percent':87.5,'limit_window_seconds':18000},'secondary_window':{'used_percent':0,'limit_window_seconds':604800}}}))
        rows=ring_data(state)
        self.assertEqual([r['remaining'] for r in rows],[12.5,100])
        self.assertEqual([r['value'] for r in rows],['12%','100%'])
        self.assertEqual(rows[1]['label'],'一周')

if __name__=='__main__':unittest.main()
