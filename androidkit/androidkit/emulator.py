import os, subprocess
import sys
import time
import re
from .utils import run_cmd, run_adb_cmd, RunCmdError
from .config import getConfig
from .avd import get_avd_list

def emulator_wait_for_boot(avd_name, r_fd=None, serial=None):
    bootanim = ''
    not_found_cnt = 0
    wait_anim_count = 0
    while not bootanim.startswith('stopped'):
        try:
            print('RunEmulator[{}, {}]: shell getprop init.svc.bootanim'.format(avd_name, serial))
            bootanim = run_adb_cmd('shell getprop init.svc.bootanim', serial=serial)
        except RunCmdError as e:
            if 'not found' in e.err and not_found_cnt < 5:
                not_found_cnt += 1
            else:
                print('RunEmulator[{}, {}]: Failed, check following message'.format(avd_name, serial))
                print(e.message)
                if r_fd is not None:
                    print('RunEmulator[{}, {}]: Message from emulator'.format(avd_name, serial))
                    handle = os.fdopen(r_fd, 'r')
                    while True:
                        line = handle.readline()
                        if not line:
                            break
                        print(line, end='')
                    handle.close()
                raise RuntimeError
        print('RunEmulator[{}, {}]: Waiting for booting emulator'.format(avd_name, serial))
        wait_anim_count += 1
        if wait_anim_count > 6: # waited for 30 seconds
            print('RunEmulator[{}, {}]: Failed'.format(avd_name, serial))
            if r_fd is not None:
                print('RunEmulator[{}, {}]: Check message from emulator'.format(avd_name, serial))
                kill_emulator(serial)
                handle = os.fdopen(r_fd, 'r')
                while True:
                    line = handle.readline()
                    if not line:
                        break
                    print(line, end='')
                handle.close()
            raise RuntimeError
        time.sleep(5)
    return True

def emulator_run_and_wait(avd_name, serial=None, snapshot=None, wipe_data=False, writable_system=False, ram_size_in_mb=None, partition_size_in_mb=None):
    # check avd
    avd_list = get_avd_list()
    if any(a.running and a.name == avd_name for a in avd_list):
        raise RuntimeError('AVD<{}> is already running'.format(avd_name))

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
        print('RunEmulator[{}]: Port set to {}, {}'.format(avd_name, serial, serial+1))
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
        print("RunEmulator[{}, {}]: Warning, wipe_data would remove all of snapshots".format(avd_name, serial))
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

    if ram_size_in_mb is not None:
        assert type(ram_size_in_mb) == int or \
                (type(ram_size_in_mb) == str and all(ord('0') <= ord(ch) <= ord('9') for ch in ram_size_in_mb)), \
                'ram_size_in_mb should be integer, given {}'.format(ram_size_in_mb)
        emulator_cmd.append('-memory {}'.format(ram_size_in_mb))

    if partition_size_in_mb:
        assert type(partition_size_in_mb) == int or \
                (type(partition_size_in_mb) == str and all(ord('0') <= ord(ch) <= ord('9') for ch in partition_size_in_mb)), \
                'partition_size_in_mb should be integer, given {}'.format(partition_size_in_mb)
        emulator_cmd.append('-partition-size {}'.format(partition_size_in_mb))

    proc = subprocess.Popen(' '.join(emulator_cmd), stdout=w_fd, stderr=w_fd, shell=True,
        cwd = os.path.join(getConfig('SDK_PATH'), 'tools'))
    os.close(w_fd)

    emulator_wait_for_boot(avd_name, r_fd, serial=serial)

    # turn off keyboard
    run_adb_cmd("shell settings put secure show_ime_with_hard_keyboard 0", serial=serial)
    run_adb_cmd("root", serial=serial)

    os.close(r_fd)

    return serial

def emulator_setup(serial = None):
    # Install various files to sdcard
    # These files are from Stoat

    folder, filename = os.path.split(__file__)

    run_adb_cmd("push {} /mnt/sdcard/tmp".format(os.path.join(folder, 'sdcard')),
        serial=serial)
    run_adb_cmd("shell mv /mnt/sdcard/tmp/* /mnt/sdcard/", serial=serial)
    run_adb_cmd("shell rm -rf /mnt/sdcard/tmp", serial=serial)
    print("emulator_setup() complete")

def kill_emulator(serial = None):
    run_adb_cmd('emu kill', serial = serial)

def _check_port_is_available(port):
    try:
        run_cmd('lsof -i :{}'.format(port))
        return False
    except RunCmdError as e:
        return True
