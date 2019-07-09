from utils import run_adb_cmd, RunCmdError, list_snapshots
from config import getConfig
import os, subprocess
import sys
import time
import re

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
        print("RunEmulator: Warning, wipe_data would remove all of snapshot data")
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
    emulator_run_and_wait('N5X22_511r3', 5554)
