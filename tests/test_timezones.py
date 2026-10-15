import unittest
from datetime import datetime,timezone
from quota_monitor.timezones import localize,offset_label,valid_timezone
from quota_monitor.settings import Settings
from quota_monitor.client import parse_usage
from quota_monitor.state import QuotaState,reset_text
from pathlib import Path
import tempfile,json

class TimezoneTests(unittest.TestCase):
 def test_shanghai_is_separate_from_system(self):
  utc=datetime(2026,10,15,0,0,tzinfo=timezone.utc)
  self.assertEqual(localize(utc,'Asia/Shanghai').hour,8)
  self.assertEqual(offset_label(localize(utc,'Asia/Shanghai')),'UTC+08:00')
  self.assertEqual(utc.hour,0)
 def test_los_angeles_dst_transition(self):
  before=localize(datetime(2026,3,8,9,30,tzinfo=timezone.utc),'America/Los_Angeles')
  after=localize(datetime(2026,3,8,10,30,tzinfo=timezone.utc),'America/Los_Angeles')
  self.assertEqual((before.hour,offset_label(before)),(1,'UTC-08:00'))
  self.assertEqual((after.hour,offset_label(after)),(3,'UTC-07:00'))
 def test_display_changes_without_modifying_quota_timestamps(self):
  snapshot=parse_usage({'rate_limit':{'primary_window':{'used_percent':50,'limit_window_seconds':18000,'reset_at':1792022400}}})
  state=QuotaState(snapshot,timezone='UTC')
  utc=state.tooltip();state.timezone='Asia/Shanghai'
  self.assertNotEqual(state.tooltip(),utc)
  self.assertEqual(snapshot.primary.reset_at,1792022400)
  self.assertEqual(state.values[0],'50%')
 def test_unknown_timezone_defaults_to_system(self):
  self.assertFalse(valid_timezone('Not/AZone'))
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'s.json';p.write_text(json.dumps({'timezone':'Not/AZone'}))
   self.assertEqual(Settings.load(p).timezone,'system')
 def test_timezone_roundtrip(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'s.json';s=Settings(timezone='America/Los_Angeles');s.save(p)
   self.assertEqual(Settings.load(p).timezone,s.timezone)

if __name__=='__main__':unittest.main()
