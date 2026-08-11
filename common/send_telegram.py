import ast
import json
import mimetypes
import os
import uuid
import urllib.error
import urllib.request


CONFIG_FILE = os.environ.get('HOMESECURITY_CONFIG', 'confidential.txt')


def _credentials():
    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')

    if (not token or not chat_id) and os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as config_file:
            config = ast.literal_eval(config_file.read())
        token = token or config.get('telegram_bot_token')
        chat_id = chat_id or config.get('telegram_chat_id')

    if not token or not chat_id:
        raise RuntimeError(
            'Telegram credentials are missing. Set TELEGRAM_BOT_TOKEN and '
            'TELEGRAM_CHAT_ID or add them to confidential.txt.'
        )
    return str(token), str(chat_id)


def _multipart(fields, file_field=None, filename=None):
    boundary = '----homesecurity{}'.format(uuid.uuid4().hex)
    body = bytearray()

    for name, value in fields.items():
        body.extend('--{}\r\n'.format(boundary).encode())
        body.extend(
            'Content-Disposition: form-data; name="{}"\r\n\r\n'.format(name).encode()
        )
        body.extend(str(value).encode('utf-8'))
        body.extend(b'\r\n')

    if file_field and filename:
        content_type = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
        body.extend('--{}\r\n'.format(boundary).encode())
        body.extend(
            'Content-Disposition: form-data; name="{}"; filename="{}"\r\n'.format(
                file_field, os.path.basename(filename)
            ).encode()
        )
        body.extend('Content-Type: {}\r\n\r\n'.format(content_type).encode())
        with open(filename, 'rb') as attachment:
            body.extend(attachment.read())
        body.extend(b'\r\n')

    body.extend('--{}--\r\n'.format(boundary).encode())
    return bytes(body), 'multipart/form-data; boundary={}'.format(boundary)


def _call(method, fields, file_field=None, filename=None):
    token, _ = _credentials()
    body, content_type = _multipart(fields, file_field, filename)
    request = urllib.request.Request(
        'https://api.telegram.org/bot{}/{}'.format(token, method),
        data=body,
        headers={'Content-Type': content_type},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            result = json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as error:
        raise RuntimeError('Telegram API returned HTTP {}'.format(error.code))
    except urllib.error.URLError as error:
        raise RuntimeError('Could not connect to Telegram: {}'.format(error.reason))

    if not result.get('ok'):
        raise RuntimeError('Telegram rejected the alert: {}'.format(result.get('description')))


def send_alert(files=None, text=''):
    _, chat_id = _credentials()
    files = files or []

    if not files:
        _call('sendMessage', {'chat_id': chat_id, 'text': text})
        return

    caption = text[:1024]
    for index, filename in enumerate(files):
        extension = os.path.splitext(filename)[1].lower()
        if extension in ('.jpg', '.jpeg', '.png'):
            method, field = 'sendPhoto', 'photo'
        elif extension in ('.mp4', '.mov', '.m4v'):
            method, field = 'sendVideo', 'video'
        else:
            method, field = 'sendDocument', 'document'

        fields = {'chat_id': chat_id}
        if index == 0 and caption:
            fields['caption'] = caption
        _call(method, fields, field, filename)
