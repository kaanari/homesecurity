import json
import os
import tempfile
import unittest
from unittest import mock

from common import send_telegram


class FakeResponse(object):
    def __init__(self, result=None):
        self.result = {'ok': True} if result is None else result

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self):
        return json.dumps(self.result).encode('utf-8')


class TelegramNotifierTest(unittest.TestCase):
    @mock.patch.dict(os.environ, {
        'TELEGRAM_BOT_TOKEN': 'test-token',
        'TELEGRAM_CHAT_ID': '678221504',
    })
    @mock.patch('common.send_telegram.urllib.request.urlopen')
    def test_sends_video_and_photo_to_configured_chat(self, urlopen):
        urlopen.return_value = FakeResponse()
        with tempfile.TemporaryDirectory() as directory:
            video = os.path.join(directory, 'alert.mp4')
            photo = os.path.join(directory, 'alert.jpg')
            for filename in (video, photo):
                with open(filename, 'wb') as output:
                    output.write(b'attachment')

            send_telegram.send_alert([video, photo], 'Person detected')

        self.assertEqual(urlopen.call_count, 2)
        requests = [call[0][0] for call in urlopen.call_args_list]
        self.assertTrue(requests[0].full_url.endswith('/sendVideo'))
        self.assertTrue(requests[1].full_url.endswith('/sendPhoto'))
        self.assertIn(b'678221504', requests[0].data)
        self.assertIn(b'Person detected', requests[0].data)
        self.assertNotIn(b'Person detected', requests[1].data)

    @mock.patch.dict(os.environ, {
        'TELEGRAM_BOT_TOKEN': 'test-token',
        'TELEGRAM_CHAT_ID': '678221504',
    })
    @mock.patch('common.send_telegram.urllib.request.urlopen')
    def test_sends_text_when_there_are_no_attachments(self, urlopen):
        urlopen.return_value = FakeResponse()
        send_telegram.send_alert(text='Camera online')

        request = urlopen.call_args[0][0]
        self.assertTrue(request.full_url.endswith('/sendMessage'))
        self.assertIn(b'Camera online', request.data)

    @mock.patch.dict(os.environ, {
        'TELEGRAM_BOT_TOKEN': 'test-token',
        'TELEGRAM_CHAT_ID': '678221504',
    })
    @mock.patch('common.send_telegram.urllib.request.urlopen')
    def test_accepts_commands_only_from_configured_user(self, urlopen):
        urlopen.return_value = FakeResponse({'ok': True, 'result': [
            {'update_id': 10, 'message': {
                'from': {'id': 678221504}, 'text': '/status'}},
            {'update_id': 11, 'message': {
                'from': {'id': 999}, 'text': '/photo'}},
        ]})

        commands, updates = send_telegram.get_commands(timeout=0)

        self.assertEqual(commands, [(10, '/status')])
        self.assertEqual(len(updates), 2)


if __name__ == '__main__':
    unittest.main()
