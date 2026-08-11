import cv2, time, os
#import send_email
import queue
import threading
import numpy as np

import sys
sys.path.append(os.getcwd()+'/common/')
sys.path.append(os.getcwd()+'/human_detection/')

from config import * #h264_folder, mp4_folder, motion_threshold,log_dir,log_file,countfile
from file_managernano import FileManagerThread, FileCleanerThread, counter
import send_telegram as notifier

file_q = queue.Queue()
command_q = queue.Queue()
liveness_file = os.path.join(log_dir, 'liveness_enabled')
started_at = time.time()

os.environ['TZ']= location
time.tzset()

print(('Time: {}. Starting...'.format(time.strftime("%a, %d %b %Y %H:%M:%S",time.localtime()))))
print('Finished importing modules')
print(('Sleeping for {} seconds'.format(initial_sleep)))
time.sleep(initial_sleep)

def gstreamer_pipeline (capture_width=320, capture_height=240, display_width=320, display_height=240, framerate=60, flip_method=0) :   
    return ('nvarguscamerasrc ! ' 
    'video/x-raw(memory:NVMM), '
    'width=(int)%d, height=(int)%d, '
    'format=(string)NV12, framerate=(fraction)%d/1 ! '
    'nvvidconv flip-method=%d ! '
    'video/x-raw, width=(int)%d, height=(int)%d, format=(string)BGRx ! '
    'videoconvert ! '
    'video/x-raw, format=(string)BGR ! appsink'  % (capture_width,capture_height,framerate,flip_method,display_width,display_height))

time_since_last_sent=200 #in minutes
time_last_sent=time.time()
file_counter=counter(countfile)

video_num=file_counter.count
if usbcam: #defined in config.py
	camera=cv2.VideoCapture(0)
else:
	camera=cv2.VideoCapture(gstreamer_pipeline(flip_method=0),cv2.CAP_GSTREAMER)

if not camera.isOpened():
    raise RuntimeError('Camera could not be opened')

fct=FileCleanerThread()
fct.daemon = True
fct.start()

fmt= FileManagerThread(h264_q=file_q)
fmt.daemon = True
fmt.start()


class TelegramCommandThread(threading.Thread):
    def __init__(self):
        super(TelegramCommandThread, self).__init__()
        self.daemon = True

    def run(self):
        offset = None
        while True:
            try:
                commands, updates = notifier.get_commands(offset=offset)
                for update in updates:
                    offset = max(offset or 0, update['update_id'] + 1)
                for _, command in commands:
                    command_q.put(command)
            except Exception as error:
                print('Telegram command polling failed: {}'.format(error))
                time.sleep(10)


TelegramCommandThread().start()


def send_photo(frame, caption):
    filename = os.path.join('/tmp', 'homesecurity-live.jpg')
    cv2.imwrite(filename, frame)
    try:
        notifier.send_alert([filename], caption)
    finally:
        if os.path.exists(filename):
            os.remove(filename)

def record_for(rec_time):
    video_num=file_counter.get_current_count()
    this_file='video{}.mp4'.format(video_num)
    if this_file in os.listdir(h264_folder):
        os.remove(h264_folder+this_file)
    #remove this file, if it already exists
    fps=24.0
    size=(320,240)
    writer=cv2.VideoWriter(h264_folder+this_file,cv2.VideoWriter_fourcc(*'MP4V'),fps,size)
    print('Video recording started')
    starttime=time.time()
    while (time.time()-starttime)<rec_time:
        ret,frame=camera.read()
        writer.write(frame)
    writer.release()
    file_counter.update_count()
    file_q.put(this_file)
    #handle_file(filename)

if __name__ == '__main__':
    start=time.time()
    not_beginning=False
    count=0
    fgbg=cv2.createBackgroundSubtractorMOG2(history=20, varThreshold=8, detectShadows=False)
    kernel=cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(3,3))
    time.sleep(1)
    while True:
        ret,frame=camera.read()
        if not ret or frame is None:
            raise RuntimeError('Camera stopped returning frames')
        #cv2.imwrite('capture.jpg',image)
        fgmask=fgbg.apply(frame,learningRate=0.1)
        fgmask=cv2.erode(fgmask,kernel,iterations=1)
        motion_magnitude=np.mean(fgmask)
        #print(motion_magnitude)
        count+=1
        time_since_last_sent=(time.time()-time_last_sent)/60

        liveness_enabled = os.path.exists(liveness_file)
        while not command_q.empty():
            command = command_q.get_nowait()
            if command == '/status':
                notifier.send_alert(text='Camera online. Uptime: {} minutes. Liveness: {}.'.format(
                    int((time.time() - started_at) / 60),
                    'on' if liveness_enabled else 'off'))
            elif command == '/photo':
                send_photo(frame, 'Live photo from the home security camera.')
            elif command == '/liveness_on':
                open(liveness_file, 'a').close()
                liveness_enabled = True
                time_last_sent = 0
                notifier.send_alert(text='Hourly liveness photos enabled.')
            elif command == '/liveness_off':
                if os.path.exists(liveness_file):
                    os.remove(liveness_file)
                liveness_enabled = False
                notifier.send_alert(text='Hourly liveness photos disabled.')
            else:
                notifier.send_alert(text='Commands: /status, /photo, /liveness_on, /liveness_off')

        if liveness_enabled and (time.time() - time_last_sent) >= 3600:
            send_photo(frame, 'Hourly liveness photo. Camera is online.')
            time_last_sent = time.time()

        if count%50==0:
            not_beginning=True
            print(('frame rate={}'.format(count/(time.time()-start))))

        if not_beginning and motion_magnitude>=motion_threshold:
            print('Motion detected!!')
            record_for(20)
            not_beginning=False
            count=0
            fgbg=cv2.createBackgroundSubtractorMOG2(history=20, varThreshold=8, detectShadows=False)
            start=time.time()
        elif count>1000000:
            print('count is 1 million. Setting count to zero')
            count=0

        # if time.localtime().tm_min<2 and time_since_last_sent>58:
