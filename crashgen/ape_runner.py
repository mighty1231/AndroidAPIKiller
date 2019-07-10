import sys, os
sys.path.insert(0, '../common')

from utils import (
    run_adb_cmd,
    RunCmdError,
    get_package_name,
    list_snapshots,
    save_snapshot,
    load_snapshot
)
from emulator import get_avd_list, kill_emulator, emulator_run_and_wait, emulator_setup
import time

APE_READY_SS = 'APE_READY' # snapshot name
APE_ROOT = '/data/local/tmp/'

def install_ape_and_make_snapshot(avd_name, force_snapshot=False):
    avd_list = get_avd_list()
    avd = next(avd for avd in avd_list if avd.name == avd_name)

    if avd.running:
        if not force_snapshot and APE_READY_SS in list_snapshots(serial = avd.serial):
            load_snapshot(APE_READY_SS, serial = avd.serial)
            return avd
        kill_emulator(serial = avd.serial)
        time.sleep(3)

    serial = emulator_run_and_wait(avd_name, snapshot = APE_READY_SS)
    if APE_READY_SS not in list_snapshots(serial = serial):
        print('No saved snapshot on the device, rebooting and making snapshot...')
        kill_emulator(serial = serial)
        time.sleep(3)
        serial = emulator_run_and_wait(avd_name, wipe_data = True)
        print('Setup emulator...')
        emulator_setup(serial = serial)
        run_adb_cmd('push ape.jar {}'.format(APE_ROOT), serial = serial, realtime=True)
        save_snapshot(APE_READY_SS, serial = serial)
    avd.setRunning(serial)
    return avd

def run_ape(apk_path, avd_name, output_dir, running_minutes=20):
    package_name = get_package_name(apk_path)
    print('Installing APE...')

    avd = install_ape_and_make_snapshot(avd_name)
    run_adb_cmd('install {}'.format(apk_path), serial=avd.serial, realtime=True)

    # run ape
    print('Running APE...')
    args = '-p {} --running-minutes {} --ape sata --bugreport'.format(package_name, running_minutes)
    ret = run_adb_cmd('shell CLASSPATH={} {} {} {} {}'.format(
        os.path.join(APE_ROOT, 'ape.jar'),
        '/system/bin/app_process',
        APE_ROOT,
        'com.android.commands.monkey.Monkey',
        args
    ), serial=avd.serial, realtime=True)

    fetch_result(output_dir, avd.serial)

def fetch_result(output_dir, serial):
    ret = run_adb_cmd('shell ls /sdcard/', serial=serial)
    folder = None
    for line in ret.split('\n'):
        if line.startswith('sata-'):
            assert folder is None, "Error: Multiple folder for outputs..."
            folder = '/sdcard/{}'.format(line.rstrip())
    run_adb_cmd('pull {} {}'.format(folder, output_dir), serial=serial, realtime=True)

if __name__ == "__main__":
    apk_path = sys.argv[1]
    avd_name = sys.argv[2]
    output_dir = sys.argv[3]

    run_ape(apk_path, avd_name, output_dir)
