import sys, os

from androidkit import (
    run_adb_cmd,
    get_package_name,
    set_multiprocessing_mode,
    get_avd_list,
    list_snapshots,
    load_snapshot,
    save_snapshot,
    kill_emulator,
    emulator_run_and_wait,
    emulator_setup,
    emulator_wait_for_boot
)

import time
import multiprocessing as mp
from mt_run import run_mtserver, kill_mtserver
from ape_runner import fetch_result

ART_APE_MT_READY_SS = "ART_APE_MT" # snapshot name
TMP_LOCATION = "/data/local/tmp"

def libart_check(libart_path, serial):
    # Check our target libart.so is installed
    # Since checking is done by its size, it may give wrong result.
    size1 = os.path.getsize(libart_path)
    output = run_adb_cmd("shell ls -l /system/lib/libart.so", serial=serial)
    size2 = int(output.split()[3])

    return size1 == size2

def install_art_ape_mt(avd_name, libart_path, mtserver_path, force_clear = False):
    avd_list = get_avd_list()
    avd = next(avd for avd in avd_list if avd.name == avd_name)

    if avd.running:
        if not force_clear and ART_APE_MT_READY_SS in list_snapshots(serial = avd.serial):
            load_snapshot(ART_APE_MT_READY_SS, serial = avd.serial)
            assert libart_check(libart_path, serial = avd.serial)
            return avd
        serial = avd.serial
    else:
        serial = emulator_run_and_wait(avd_name, snapshot = ART_APE_MT_READY_SS, writable_system = True)

    if force_clear or ART_APE_MT_READY_SS not in list_snapshots(serial = serial):
        print("No saved snapshot on the device, rebooting and making snapshot...")
        kill_emulator(serial = serial)
        time.sleep(3)
        serial = emulator_run_and_wait(avd_name, wipe_data = True, writable_system = True)

        print("Installing libart.so")
        run_adb_cmd("remount", serial=serial)
        run_adb_cmd("shell su root mount -o remount,rw /system", serial=serial)
        run_adb_cmd("push {} /sdcard/libart.so".format(libart_path), serial=serial)
        run_adb_cmd("shell su root mv /sdcard/libart.so /system/lib/libart.so", serial=serial)
        run_adb_cmd("shell su root chmod 644 /system/lib/libart.so", serial=serial)
        run_adb_cmd("shell su root chown root:root /system/lib/libart.so", serial=serial)
        run_adb_cmd("shell su root reboot")

        print("Wait for emulator")
        emulator_wait_for_boot(avd_name, r_fd=None, serial=serial)

        print("Setup emulator...")
        emulator_setup(serial = serial)

        print("Installing ape.jar")
        run_adb_cmd("push ape.jar {}".format(TMP_LOCATION), serial=serial)

        print("Installing minitrace")
        run_adb_cmd("push {} {}".format(mtserver_path, TMP_LOCATION), serial=serial)

        save_snapshot(ART_APE_MT_READY_SS, serial = serial)
        assert libart_check(libart_path, serial = avd.serial)
    avd.setRunning(serial)
    return avd

def ape_task(avd_name, serial, package_name, output_dir, running_minutes):
    print('ape_task(): Emulator[{}, {}] Running APE with package {}'.format(avd_name, serial, package_name))
    args = '-p {} --running-minutes {} --ape sata --bugreport'.format(package_name, running_minutes)
    ret = run_adb_cmd('shell CLASSPATH={} {} {} {} {}'.format(
        os.path.join(TMP_LOCATION, 'ape.jar'),
        '/system/bin/app_process',
        TMP_LOCATION,
        'com.android.commands.monkey.Monkey',
        args
    ), serial=serial)

    fetch_result(output_dir, serial)

def run_ape_with_mt(apk_path, avd_name, libart_path, mtserver_path):
    package_name = get_package_name(apk_path)
    print('run_ape_with_mt(): given apk_path {} avd_name {}'.format(apk_path, avd_name))

    assert os.path.split(libart_path)[1] == 'libart.so'
    assert os.path.split(mtserver_path)[1] == 'mtserver'

    avd = install_art_ape_mt(avd_name, libart_path, mtserver_path)

    run_adb_cmd('install {}'.format(apk_path))
    set_multiprocessing_mode()

    mtserver_proc = mp.Process(target=run_mtserver,
        args=(package_name, "mt_output", avd.serial))
    apetask_proc = mp.Process(target=ape_task,
        args=(avd_name, avd.serial, package_name, "ape_output", 1))

    mtserver_proc.start()
    apetask_proc.start()
    apetask_proc.join()

    kill_mtserver(serial = avd.serial)
    mtserver_proc.join()

if __name__ == "__main__":
    assert len(sys.argv) == 5
    apk_path, avd_name, libart_path, mtserver_path = sys.argv[1:5]
    run_ape_with_mt(apk_path, avd_name, libart_path, mtserver_path)
