import io
import unittest
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import patch
from urllib.error import HTTPError, URLError
import check_buffer


class ConnectionTests(unittest.TestCase):
    def run_check(self, token='', payload=None, failure=None):
        output = io.StringIO()
        with patch.dict('os.environ', {'BUFFER_API_KEY': token}, clear=True), \
             patch('check_buffer.urlopen') as fetch, \
             redirect_stdout(output), redirect_stderr(output):
            if failure:
                fetch.side_effect = failure
            else:
                fetch.return_value.__enter__.return_value = io.StringIO(__import__('json').dumps(payload))
            result = check_buffer.main()
        self.assertNotIn('example-private-token', output.getvalue())
        return result, fetch, output.getvalue()

    def test_missing_secret_does_not_request(self):
        result, fetch, _ = self.run_check()
        self.assertEqual(result, 1)
        fetch.assert_not_called()

    def test_success_is_read_only(self):
        result, fetch, output = self.run_check('example-private-token', {'data': {'account': {'organizations': [{'id': 'org'}]}}})
        self.assertEqual(result, 0)
        request = fetch.call_args.args[0]
        self.assertEqual(request.full_url, 'https://api.buffer.com')
        self.assertNotIn('mutation', request.data.decode())
        self.assertIn('接続成功', output)

    def test_graphql_error_is_failure_and_not_logged(self):
        self.assertEqual(self.run_check('example-private-token', {'errors': [{'message': 'example-private-token'}]})[0], 1)

    def test_null_account_is_failure(self):
        self.assertEqual(self.run_check('example-private-token', {'data': {'account': None}})[0], 1)

    def test_unauthorized_is_failure(self):
        self.assertEqual(self.run_check('example-private-token', failure=HTTPError('https://api.buffer.com', 401, 'example-private-token', {}, None))[0], 1)

    def test_network_error_is_failure(self):
        self.assertEqual(self.run_check('example-private-token', failure=URLError('example-private-token'))[0], 1)


if __name__ == '__main__':
    unittest.main()
