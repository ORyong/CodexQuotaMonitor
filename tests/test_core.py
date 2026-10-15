import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import Mock

from quota_monitor.client import AUTH_MESSAGE, NoRedirect, QuotaError, fetch_usage, parse_usage
from quota_monitor.settings import Settings
from quota_monitor.state import QuotaState, reset_text, window_name


def usage(used=13, secondary=2):
    return {'rate_limit': {
        'primary_window': {'used_percent': used, 'limit_window_seconds': 18000, 'reset_at': 1792063446},
        'secondary_window': None if secondary is None else {'used_percent': secondary, 'limit_window_seconds': 604800, 'reset_at': 1792650246}}}


class QuotaTests(unittest.TestCase):
    def test_actual_shape_and_remaining(self):
        result = parse_usage(usage())
        self.assertEqual((result.primary.display, result.secondary.display), ('87%', '98%'))
        self.assertEqual(window_name(result.primary, ''), '5 小时额度')
        self.assertEqual(window_name(result.secondary, ''), '周额度')

    def test_zero_missing_and_overage_are_distinct(self):
        state = QuotaState(parse_usage(usage(100, None)))
        self.assertEqual(state.values, ('0%', '--'))
        self.assertEqual(parse_usage(usage(110)).primary.remaining, 0)

    def test_fractional_remaining_not_rounded_up(self):
        self.assertEqual(parse_usage(usage(99.9)).primary.display, '0%')
        self.assertEqual(parse_usage(usage(.1)).primary.display, '99%')

    def test_null_windows_are_unknown(self):
        self.assertIsNone(parse_usage({'rate_limit': {'primary_window': None}}).primary)

    def test_invalid_shapes_fail_instead_of_assuming_full_quota(self):
        for data in [None, {}, {'rate_limit': {}}, {'rate_limit': {'primary_window': []}}]:
            with self.subTest(data=data), self.assertRaises(QuotaError):
                parse_usage(data)

    def test_missing_fields_boolean_nan_and_negative_rejected(self):
        for key, values in [('used_percent', [None, True, float('nan'), -1, '13']),
                            ('limit_window_seconds', [None, False, 0, 3.2]),
                            ('reset_at', [False, -10, 10**40, '1792063446'])]:
            for value in values:
                data = usage()
                data['rate_limit']['primary_window'][key] = value
                with self.subTest(key=key, value=value), self.assertRaises(QuotaError):
                    parse_usage(data)

    def test_absent_reset_is_not_inferred(self):
        data = usage()
        del data['rate_limit']['primary_window']['reset_at']
        self.assertEqual(reset_text(parse_usage(data).primary), '重置时间暂不可用')

    def test_error_keeps_last_success_until_new_success(self):
        state = QuotaState()
        state.failure(AUTH_MESSAGE)
        self.assertEqual(state.values, ('--', '--'))
        self.assertNotIn('数据已过期', state.status())
        state.success(parse_usage(usage()))
        state.failure('断网')
        self.assertEqual(state.values, ('87%', '98%'))
        self.assertIn('数据已过期', state.tooltip())
        state.success(parse_usage(usage(20)))
        self.assertIsNone(state.error)
        self.assertEqual(state.values[0], '80%')

    def test_get_headers_and_credentials_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            auth = Path(tmp) / 'auth.json'
            content = json.dumps({'tokens': {'access_token': 'SYNTHETIC-ACCESS', 'account_id': 'SYNTHETIC-ID', 'refresh_token': 'NEVER-USED'}})
            auth.write_text(content, encoding='utf-8')
            opener = Mock()
            opener.open.return_value = io.BytesIO(json.dumps(usage()).encode())
            result = fetch_usage(auth, opener)
            req = opener.open.call_args.args[0]
            self.assertEqual(req.get_method(), 'GET')
            self.assertEqual(req.full_url, 'https://chatgpt.com/backend-api/wham/usage')
            self.assertEqual(req.get_header('Authorization'), 'Bearer SYNTHETIC-ACCESS')
            self.assertIsNone(req.data)
            self.assertEqual(auth.read_text(encoding='utf-8'), content)
            self.assertEqual(result.primary.display, '87%')

    def test_no_redirects(self):
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, '', {}, 'https://other.invalid'))

    def test_safe_errors_do_not_include_server_body_or_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            auth = Path(tmp) / 'auth.json'
            auth.write_text(json.dumps({'tokens': {'access_token': 'SECRET', 'account_id': 'ID'}}))
            for code, expected in [(401, AUTH_MESSAGE), (403, AUTH_MESSAGE), (429, '查询过于频繁'), (500, 'HTTP 500')]:
                opener = Mock()
                opener.open.side_effect = urllib.error.HTTPError('private-url', code, 'SECRET', {}, io.BytesIO(b'SECRET'))
                with self.subTest(code=code), self.assertRaises(QuotaError) as ctx:
                    fetch_usage(auth, opener)
                self.assertIn(expected, str(ctx.exception))
                self.assertNotIn('SECRET', str(ctx.exception))
            opener.open.side_effect = urllib.error.URLError('SECRET')
            with self.assertRaises(QuotaError) as ctx:
                fetch_usage(auth, opener)
            self.assertNotIn('SECRET', str(ctx.exception))

    def test_missing_and_malformed_credentials_do_not_contact_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            auth = Path(tmp) / 'auth.json'
            for content in ['{}', 'null', 'bad json', '{"tokens":{"access_token":"x\\ny","account_id":"id"}}']:
                auth.write_text(content)
                opener = Mock()
                with self.assertRaises(QuotaError):
                    fetch_usage(auth, opener)
                opener.open.assert_not_called()

    def test_malformed_response(self):
        with tempfile.TemporaryDirectory() as tmp:
            auth = Path(tmp) / 'auth.json'
            auth.write_text(json.dumps({'tokens': {'access_token': 'SYNTHETIC', 'account_id': 'ID'}}))
            opener = Mock()
            opener.open.return_value = io.BytesIO(b'<html>not quota</html>')
            with self.assertRaises(QuotaError) as ctx:
                fetch_usage(auth, opener)
            self.assertEqual(ctx.exception.kind, 'schema')


class SettingsTests(unittest.TestCase):
    def test_roundtrip_colors_modes_position(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'settings.json'
            settings = Settings(mode='float', scale=150, background='#24594E', x=-1500, y=30)
            settings.save(path)
            self.assertEqual(Settings.load(path), settings)
            self.assertEqual(set(json.loads(path.read_text())), set(settings.__dict__))

    def test_broken_preferences_use_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'settings.json'
            for content in ['not json', 'null', '[]', '{"mode":"bad","scale":999,"background":"bad"}']:
                path.write_text(content)
                self.assertEqual(Settings.load(path), Settings())


if __name__ == '__main__':
    unittest.main()
