import os
import time

import send_telegram as telegram


LOG_DIR = 'logs'
HEARTBEAT_FILE = os.path.join(LOG_DIR, 'camera_heartbeat')
PHOTO_REQUEST_FILE = os.path.join(LOG_DIR, 'photo_requested')
LIVENESS_FILE = os.path.join(LOG_DIR, 'liveness_enabled')


def camera_online():
    return (os.path.exists(HEARTBEAT_FILE) and
            time.time() - os.path.getmtime(HEARTBEAT_FILE) < 30)


def handle(command):
    if command == '/status':
        telegram.send_alert(text='Camera is {}. Hourly liveness photos are {}.'.format(
            'online' if camera_online() else 'starting or recovering',
            'enabled' if os.path.exists(LIVENESS_FILE) else 'disabled'))
    elif command == '/photo':
        open(PHOTO_REQUEST_FILE, 'a').close()
        telegram.send_alert(text='Live photo requested. It will arrive when the camera is ready.')
    elif command == '/liveness_on':
        open(LIVENESS_FILE, 'a').close()
        open(PHOTO_REQUEST_FILE, 'a').close()
        telegram.send_alert(text='Hourly liveness photos enabled.')
    elif command == '/liveness_off':
        if os.path.exists(LIVENESS_FILE):
            os.remove(LIVENESS_FILE)
        telegram.send_alert(text='Hourly liveness photos disabled.')
    else:
        telegram.send_alert(text='Commands: /status, /photo, /liveness_on, /liveness_off')


def main():
    offset = None
    while True:
        try:
            commands, updates = telegram.get_commands(offset=offset)
            for update in updates:
                offset = max(offset or 0, update['update_id'] + 1)
            for _, command in commands:
                handle(command)
        except Exception as error:
            print('Telegram command polling failed: {}'.format(error), flush=True)
            time.sleep(10)


if __name__ == '__main__':
    main()
