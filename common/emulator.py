from utils import run_cmd, run_adb_cmd, RunCmdError, list_snapshots
from config import getConfig
import os, subprocess
import sys
import time
import re

class AVD:
    def __init__(self, name, device, path, target, base, tag, skin, sdcard):
        self.name = name
        self.device = device
        self.path = path
        self.target = target
        self.base = base
        self.tag = tag
        self.skin = skin
        self.sdcard = sdcard

        # Two cases:
        #    running (there is serial)
        #    not running
        self.running = False
        self.serial = None

    def setRunning(self, serial):
        self.running = True
        self.serial = serial

    def __repr__(self):
        if self.running:
            return '<AVD[{}] {}, {}, running with {}>'.format(self.name, self.device, self.tag, self.serial)
        else:
            return '<AVD[{}] {}, {}, available>'.format(self.name, self.device, self.tag)

    def getDetail(self):
        ret = []
        for attr in ['device', 'path', 'target', 'base', 'tag',
                'skin', 'sdcard', 'running', 'sdcard', 'running', 'serial']:
            ret.append('AVD<{}>.{} = {}'.format(self.name, attr, getattr(self, attr)))
        return '\n'.join(ret)

def get_avd_list():
    # get all available devices
    avdmanager = getConfig()['AVDMANAGER_PATH']
    output = run_cmd('{} list avd'.format(avdmanager))

    # parse result for avdmanager list avd
    avd_list = []
    try:
        lines = output.split('\n')
        assert lines[0].startswith('Parsing ')

        i = 1
        while i < len(lines) and lines[i] != '':
            name   = re.match(r'Name: (.*)', lines[i].lstrip()).groups()[0]
            device = re.match(r'Device: (.*)', lines[i+1].lstrip()).groups()[0]
            path   = re.match(r'Path: (.*)', lines[i+2].lstrip()).groups()[0]
            target = re.match(r'Target: (.*)', lines[i+3].lstrip()).groups()[0]
            base, tag = re.match(r'Based on: (.*) Tag/ABI: (.*)', lines[i+4].lstrip()).groups()
            skin   = re.match(r'Skin: (.*)', lines[i+5].lstrip()).groups()[0]
            sdcard = re.match(r'Sdcard: (.*)', lines[i+6].lstrip()).groups()[0]
            avd = AVD(name, device, path, target, base, tag, skin, sdcard)

            if avd.tag.startswith('google_apis_playstore'):
                print('Warning: AVD[{}] cannot be rooted'.format(name), file=sys.stderr)
            else:
                avd_list.append(avd)
            i += 8

    except Exception as e:
        print('Error: Unexpected form on avdmanager list avd', file=sys.stderr)
        print('Result of avdmanger list avd -->', file=sys.stderr)
        print('//---------------------------//')
        print(output, file=sys.stderr)
        print('//---------------------------//')
        raise

    # fetch currently running devices
    res = run_adb_cmd('devices')
    assert res.count('\n') >= 2, res
    for line in res.split('\n')[1:]:
        if line == '':
            continue
        serial = line.split()[0]

        # At now, assert all devices are based on emulator
        avd_name = run_adb_cmd('emu avd name', serial=serial).split()[0]

        # find with avd_name
        for avd in avd_list:
            if avd.name == avd_name:
                avd.setRunning(serial)
                break

    return avd_list


def print_avd_status():
    avd_list = get_avd_list()
    for avd in avd_list:
        print(avd)

def kill_emulator(serial = None):
    try:
        run_adb_cmd('emu kill', serial = serial)
    except RunCmdError as e:
        print('Exception on emu kill')
        print('RunCmdError: out', e.out)
        print('RunCmdError: err', e.err)

def _check_port_is_available(port):
    try:
        run_cmd('lsof -i :{}'.format(port))
        return False
    except RunCmdError as e:
        return True

def emulator_run_and_wait(avd_name, serial=None, snapshot=None, wipe_data=False, writable_system=False):
    r_fd, w_fd = os.pipe()

    if serial is None:
        # Pairs for port would be one of
        #   (5554,5555) (5556,5557) ... (5584,5585)
        serial = 5554
        while True:
            if _check_port_is_available(serial):
                break
            else:
                serial += 2

                if serial > 5584:
                    raise RuntimeError
        assert _check_port_is_available(serial+1) == True
        print('RunEmulator: Port set to {}, {}'.format(serial, serial+1))
    elif type(serial) == str:
        serial = re.match(r'emulator-(\w+)', serial).groups()[0]
    else:
        assert type(serial) == int

    # parent process
    emulator_cmd = ['./emulator',
        '-netdelay', 'none',
        '-netspeed', 'full',
        '-ports', '{},{}'.format(serial, serial+1),
        '-avd', avd_name
    ]
    if snapshot is not None and wipe_data:
        print("RunEmulator: Warning, wipe_data would remove all of snapshots")
    if snapshot is not None:
        # This option would not raise any exception,
        #   even if there is no snapshot with specified name.
        # You should check it with list_snapshots()
        emulator_cmd.append('-snapshot')
        emulator_cmd.append(snapshot)

    if wipe_data:
        # It would wipe all data on device, even snapshots.
        emulator_cmd.append('-wipe-data')

    if writable_system:
        # This option is used when modification on /system is needed.
        # It could be used for modifying /system/lib/libart.so, as MiniTracing does
        emulator_cmd.append('-writable-system')

    proc = subprocess.Popen(' '.join(emulator_cmd), stdout=w_fd, stderr=w_fd, shell=True,
        cwd = os.path.join(getConfig()['SDK_PATH'], 'tools'))
    os.close(w_fd)

    bootanim = ''
    not_found_cnt = 0
    while not bootanim.startswith('stopped'):
        try:
            print('RunEmulator: shell getprop init.svc.bootanim')
            bootanim = run_adb_cmd('shell getprop init.svc.bootanim', serial=serial)
        except RunCmdError as e:
            print('RunCmdError: out', e.out)
            print('RunCmdError: err', e.err)
            if 'not found' in e.err and not_found_cnt < 2:
                not_found_cnt += 1
            else:
                print('RunEmulator: Failed, check following log from emulator')
                handle = os.fdopen(r_fd, 'r')
                while True:
                    line = handle.readline()
                    if not line:
                        break
                    print(line, end='')
                handle.close()
                raise RuntimeError
        print('RunEmulator: Waiting for booting emulator')
        time.sleep(5)

    # turn off keyboard
    run_adb_cmd("shell settings put secure show_ime_with_hard_keyboard 0", serial=serial)
    run_adb_cmd("root", serial=serial)

    if writable_system:
        run_adb_cmd("remount", serial=serial)
        run_adb_cmd("shell su root mount -o remount,rw /system", serial=serial)
    os.close(r_fd)
    # proc.communicate()

    return serial

def emulator_setup(serial = None):
    ''' File setup borrowed from Stoat '''
    files = [
        "./sdcard/1.vcf",
        "./sdcard/2.vcf",
        "./sdcard/3.vcf",
        "./sdcard/4.vcf",
        "./sdcard/5.vcf",
        "./sdcard/6.vcf",
        "./sdcard/7.vcf",
        "./sdcard/8.vcf",
        "./sdcard/9.vcf",
        "./sdcard/10.vcf",
        "./sdcard/Troy_Wolf.vcf",
        "./sdcard/pic1.jpg",
        "./sdcard/pic2.jpg",
        "./sdcard/pic3.jpg",
        "./sdcard/pic4.jpg",
        "./sdcard/example1.txt",
        "./sdcard/example2.txt",
        "./sdcard/license.txt",
        "./sdcard/first.img",
        "./sdcard/sec.img",
        "./sdcard/hackers.pdf",
        "./sdcard/Hacking_Secrets_Revealed.pdf",
        "./sdcard/Heartbeat.mp3",
        "./sdcard/intermission.mp3",
        "./sdcard/mpthreetest.mp3",
        "./sdcard/sample.3gp",
        "./sdcard/sample_iPod.m4v",
        "./sdcard/sample_mpeg4.mp4",
        "./sdcard/sample_sorenson.mov",
        "./sdcard/wordnet-3.0-1.html.aar",
        "./sdcard/sample_3GPP.3gp.zip",
        "./sdcard/sample_iPod.m4v.zip",
        "./sdcard/sample_mpeg4.mp4.zip",
        "./sdcard/sample_sorenson.mov.zip",
    ]
    for file in files:
        res = run_adb_cmd("push {} /mnt/sdcard/".format(file), serial=serial)
        print(res)

if __name__ == "__main__":
    '''
    Run emulator
    python emulator.py status
    python emulator.py run DEVICE_NAME [SERIAL]
    '''
    import argparse

    parser = argparse.ArgumentParser(description='Manages android emulator')


    subparsers = parser.add_subparsers(dest='func')

    list_parser = subparsers.add_parser('status')

    run_parser = subparsers.add_parser('run')
    run_parser.add_argument('device_name', action='store', type=str)
    run_parser.add_argument('--port', action='store', default=None)
    run_parser.add_argument('--snapshot', action='store', default=None)
    run_parser.add_argument('--wipe_data', action='store_true')
    run_parser.add_argument('--writable_system', action='store_true')

    arbi_parser = subparsers.add_parser('exec')
    arbi_parser.add_argument('expression', action='store', type=str)

    args = parser.parse_args()
    if args.func == 'status':
        print_avd_status()
    elif args.func == 'run':
        try:
            port = int(args.port)
        except (TypeError, ValueError):
            port = args.port
        emulator_run_and_wait(args.device_name,
            serial=port,
            snapshot=args.snapshot,
            wipe_data=args.wipe_data,
            writable_system=args.writable_system
        )
    elif args.func == 'exec':
        print('Executing {}...'.format(args.expression))
        retval = exec(args.expression)
        print('Return value for {}: {}'.format(args.expression, retval))
    else:
        raise
