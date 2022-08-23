#!/usr/bin/python3
from datetime import datetime
import evdev
import os
import logging
import zmq
import psutil
import subprocess

logger = logging.getLogger("main")
logging.basicConfig(format='%(levelname)s-%(message)s')
logger.addHandler(logging.StreamHandler())
logger.setLevel(logging.INFO)

PORT = "8998"
context = zmq.Context()
socket = context.socket(zmq.PUB)
socket.bind(f"tcp://*:{PORT}")


QC71_DIR = '/sys/devices/platform/qc71_laptop'
QC71_mod_loaded = True if os.path.isdir(QC71_DIR) else False


def checkIfProcessRunning(processName):
    '''
    Check if there is any running process that contains the given name processName.
    '''
    # Iterate over the all the running process
    for proc in psutil.process_iter():
        try:
            # Check if process name contains the given name string.
            if processName.lower() in proc.name().lower():
                return proc.name()
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return False


def notify_send(msg):
    dt = datetime.now()
    ts = datetime.timestamp(dt)
    data = {"msg": msg, "timestamp": ts}
    print(data)
    socket.send_json(data)
    #socket.send_string(f"10001 {msg}")


def detect_touchpad():
    touchpad_device = None
    for file in os.listdir('/dev'):
        if file.startswith('hidraw'):
            logger.debug(file)
            data_file = '/sys/class/hidraw/{file}/device/uevent'.format(
                file=file)
            logger.debug(data_file)
            for line in open(data_file).readlines():
                if line.startswith('HID_NAME=') and \
                        line.find('UNIW0001:00 093A:') != -1:
                    try:
                        logger.debug('Found keyboard at: ' +
                                     '/dev/{}'.format(file))
                        touchpad_device = open('/dev/{}'.format(file), 'r')
                    except Exception as e:
                        logger.error(e)
    return touchpad_device


def detect_keyboard():
    keyboard_device_path = None
    for file in os.listdir('/dev/input/by-path'):
        if file.endswith('event-kbd') and file.find('i8042') != -1:
            print(file)
            file_path = os.path.join('/dev/input/by-path', file)
            keyboard_device_path = os.path.realpath(
                os.path.join(file_path, os.readlink(file_path)))
            logger.debug('Found keyboard at: ' + keyboard_device_path)
    return keyboard_device_path


keyboard_device_path = detect_keyboard()
print(keyboard_device_path)
device = evdev.InputDevice(keyboard_device_path)
DEV = detect_touchpad()
EVENTS = {
    104: {
        "key": "F2",
        "msg": {0: "Super Key Lock disabled",
                1: "Super Key Lock enabled",
                'default': "Super Key Lock state changed"},
        "type": "",
    },
    105: {
        "key": "F5",
        "msg": {0: "Silent Mode disabled",
                1: "Silent Mode enabled",
                'default': "Silent Mode state changed"},
        "type": "",
    },
    118: {
        "key": "Touchpad button",
        "msg": {0: "Touchpad disabled",
                1: "Touchpad enabled",
                'default': "Touchpad state changed"},
        "type": "",
    },
}

last_event = 0
send_notification = None

# Check if any client process was running or not.
res = checkIfProcessRunning('client.py')
if res:
    print(res)
else:
    print('Client process not running; launching')
    subprocess.Popen(["/usr/bin/python3", "/usr/share/slimbook/client.py"],
                     stdout=subprocess.PIPE,
                     stderr=subprocess.PIPE)

for event in device.read_loop():
    if event.type == evdev.ecodes.EV_MSC:
        print(event)
        if event.value != last_event:
            state_int = None
            if event.value == 104:
                send_notification = True
                if QC71_mod_loaded:
                    qc71_filename = f"{QC71_DIR}/silent_mode"
                    file = open(qc71_filename, mode='r')
                    content = file.read()
                    # line = file.readline()
                    file.close()
                    try:
                        state_int = int(content)
                    except:
                        logger.error("Silent mode state read error")
                else:
                    logger.info('qc71_laptop not loaded')

            elif event.value == 105:
                send_notification = True

                if QC71_mod_loaded:
                    qc71_filename = f"{QC71_DIR}/silent_mode"
                    file = open(qc71_filename, mode='r')
                    content = file.read()
                    # line = file.readline()
                    file.close()
                    try:
                        state_int = int(content)
                    except:
                        logger.error("Silent mode state read error")

                else:
                    logger.info('qc71_laptop not loaded')

            elif event.value == 458811:
                print("aqui")
                msg = "En un lugar"
                notify_send(msg)
            elif event.value == 118:
                from fcntl import ioctl
                HIDIOCSFEATURE = 0xC0024806  # 2bytes
                HIDIOCGFEATURE = 0xC0024807  # 2bytes
                STATES = {
                    0: {
                        "bytes": bytes([0x07, 0x00]),
                        "action": 1,
                        "msg": "Disabled",
                    },
                    1: {
                        "bytes": bytes([0x07, 0x03]),
                        "action": 0,
                        "msg": "Enabled",
                    },
                }
                try:
                    status = ioctl(DEV, HIDIOCGFEATURE, bytes([0x07, 0]))
                    current_status = str(status)
                    # Setting state_int value != NONE we choose the notification according to the device state.
                    state_int = 1 if current_status.find("x00") != -1 else 0
                    logger.debug(str(state_int) + " " + str(current_status))
                except Exception as e:
                    logger.error(e)

                try:
                    ioctl(DEV, HIDIOCSFEATURE, STATES.get(
                        int(state_int)).get("bytes"))
                except Exception as e:
                    logger.error(e)

                send_notification = True

            last_event = event.value
            if EVENTS.get(event.value):
                msg = (
                    ((EVENTS.get(event.value)).get("msg")).get(state_int)
                    if state_int != None
                    else EVENTS.get(event.value).get("msg").get('default')
                )
                if send_notification:
                    logger.info("Should notify " + str(msg))
                    notify_send(msg)
                else:
                    logger.debug(send_notification)
