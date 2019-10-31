import sys, os

from androidkit import (
    run_adb_cmd,
    get_package_name,
    set_multiprocessing_mode,
    unset_multiprocessing_mode,
    get_avd_list,
    list_snapshots,
    load_snapshot,
    save_snapshot,
    kill_emulator,
    emulator_run_and_wait,
    emulator_setup,
    emulator_wait_for_boot,
    install_package
)

import time
import threading
from multiprocessing.sharedctypes import Value
from mt_run import Connections, kill_mtserver, WrongConnectionState
from ape_runner import fetch_result

# compress files with thread
from consumer import collapse_per_message_binary
import threading
from logcat_catcher import generate_catcher_thread, kill_generated_logcat_processes

ART_APE_MT_READY_SS = "ART_APE_MT" # snapshot name
TMP_LOCATION = "/data/local/tmp"

def libart_check(libart_path, serial):
    # Check our target libart.so is installed
    # Since checking is done by its size, it may give wrong result.
    size1 = os.path.getsize(libart_path)
    output = run_adb_cmd("shell ls -l /system/lib/libart.so", serial=serial)
    size2 = int(output.split()[3])

    return size1 == size2

def install_art_ape_mt(avd_name, libart_path, ape_jar_path, mtserver_path, force_clear = False):
    avd_list = get_avd_list()
    avd = next(avd for avd in avd_list if avd.name == avd_name)

    serial = None
    if avd.running:
        if not force_clear and ART_APE_MT_READY_SS in list_snapshots(serial = avd.serial):
            load_snapshot(ART_APE_MT_READY_SS, serial = avd.serial)
            time.sleep(3)
            assert libart_check(libart_path, serial = avd.serial)
            return avd
        serial = avd.serial
    elif not force_clear:
        serial = emulator_run_and_wait(avd_name, snapshot = ART_APE_MT_READY_SS,
                writable_system = True, partition_size_in_mb=8192)

    if force_clear or ART_APE_MT_READY_SS not in list_snapshots(serial = serial):
        print("No saved snapshot on the device, rebooting and making snapshot...")
        if serial:
            kill_emulator(serial = serial)
        time.sleep(3)
        serial = emulator_run_and_wait(avd_name, wipe_data = True,
                writable_system = True, partition_size_in_mb=8192)

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
        run_adb_cmd("push {} {}".format(ape_jar_path, os.path.join(TMP_LOCATION, "ape.jar")), serial=serial)

        print("Installing minitrace")
        run_adb_cmd("push {} {}".format(mtserver_path, TMP_LOCATION), serial=serial)

        save_snapshot(ART_APE_MT_READY_SS, serial = serial)
        assert libart_check(libart_path, serial = avd.serial)
    avd.setRunning(serial)
    return avd

class ConnectionsWithValue(Connections):
    def __init__(self, *args):
        value = args[-1]
        self._value = args[-1]
        self._threads = []
        super(ConnectionsWithValue, self).__init__(*(args[:-1]))

    def stdout_callback(self, line):
        if line.startswith('Server with uid'):
            self._value.value += 1
        super(ConnectionsWithValue, self).stdout_callback(line)

    def close_connection(self, socketfd, prefix):
        prefix_local = super(ConnectionsWithValue, self).close_connection(socketfd, prefix)
        if prefix_local != '':
            thread = threading.Thread(target=collapse_per_message_binary,
                args=(prefix_local, ))
            thread.start()
            self._threads.append(thread)

    def clean_up(self, reason):
        print('Waiting for collapsing threads')
        if super(ConnectionsWithValue, self).clean_up(reason):
            for thread in self._threads:
                thread.join()

def mt_task(package_name, output_folder, serial, logging_flag, mt_is_running):
    connections = ConnectionsWithValue(package_name, serial, output_folder, mt_is_running)

    try:
        print('Start mtserver...')
        out = run_adb_cmd('shell /data/local/tmp/mtserver server {} {}'  \
                .format(package_name, logging_flag),
            stdout_callback = connections.stdout_callback,
            stderr_callback = connections.stderr_callback,
            serial=serial)
    except WrongConnectionState:
        print('CONNECTION: WrongConnectionState. Check follow log...')
        for line in connections.log:
            print(line)

        kill_mtserver(serial)
    except KeyboardInterrupt:
        connections.clean_up("KeyboardInterrupt")
        raise
    except Exception as e:
        connections.clean_up("Exception " + repr(e))
        raise
    connections.clean_up("Normal")


def ape_task(avd_name, serial, package_name, output_dir, running_minutes, mt_is_running):
    sleep_cnt = 0
    while mt_is_running.value == 0 and sleep_cnt < 30:
        time.sleep(1)
        sleep_cnt += 1
    # Something wrong on mtserver, wait 30 seconds
    if sleep_cnt == 30:
        kill_mtserver(serial=serial)
        return

    print('ape_task(): Emulator[{}, {}] Running APE with package {}'.format(avd_name, serial, package_name))
    args = '-p {} --running-minutes {} --mt --ape sata'.format(package_name, running_minutes)
    with open(os.path.join(output_dir, 'ape_stdout_stderr.txt'), 'wt') as f:
        ret = run_adb_cmd('shell CLASSPATH={} {} {} {} {}'.format(
                os.path.join(TMP_LOCATION, 'ape.jar'),
                '/system/bin/app_process',
                TMP_LOCATION,
                'com.android.commands.monkey.Monkey',
                args),
            stdout_callback = lambda t:f.write(t + '\n'),
            stderr_callback = lambda t:f.write(t + '\n'),
            serial = serial,
        )

    fetch_result(output_dir, serial)

def run_ape_with_mt(apk_path, avd_name, libart_path, ape_jar_path, mtserver_path,
        ape_output_folder, mt_output_folder, running_minutes, force_clear):
    package_name = get_package_name(apk_path)
    print('run_ape_with_mt(): given apk_path {} avd_name {}'.format(apk_path, avd_name))

    assert os.path.split(libart_path)[1] == 'libart.so'
    assert os.path.split(mtserver_path)[1] == 'mtserver'
    assert os.path.split(ape_jar_path)[1] == 'ape.jar'

    avd = install_art_ape_mt(avd_name, libart_path, ape_jar_path, mtserver_path, force_clear)

    try:
        install_package(apk_path, serial=avd.serial)
    except RuntimeError as e:
        print(e)
        return True

    kill_mtserver(serial = avd.serial)
    mt_is_running = Value('i', 0)
    mtserver_thread = threading.Thread(target=mt_task,
        args=(package_name, mt_output_folder, avd.serial, "20010107", mt_is_running))
    apetask_thread = threading.Thread(target=ape_task,
        args=(avd_name, avd.serial, package_name, ape_output_folder, running_minutes, mt_is_running))

    set_multiprocessing_mode()
    generate_catcher_thread(os.path.join(mt_output_folder, "logcat.txt"),
        serial = avd.serial)
    mtserver_thread.start()
    apetask_thread.start()
    apetask_thread.join()

    kill_mtserver(serial = avd.serial)
    mtserver_thread.join()
    kill_generated_logcat_processes()
    unset_multiprocessing_mode()

    if mt_is_running.value == 0: # It failed to run ape/mt
        print('run_ape_with_mt(): failed to run')
        return False
    return True

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Runner of APE with MiniTracing')
    parser.add_argument('apk_list_file')
    parser.add_argument('avd_name')
    parser.add_argument('--force_clear', default=False, action='store_true')
    parser.add_argument('--libart_path', default='../bin/libart.so')
    parser.add_argument('--ape_jar_path', default='../bin/ape.jar')
    parser.add_argument('--mtserver_path', default='../bin/mtserver')
    parser.add_argument('--running_minutes', default='20')
    parser.add_argument('--ape_output_folder', default='{dirname}/ape_output')
    parser.add_argument('--mt_output_folder', default='{dirname}/mt_output')

    apk_files = []
    args = parser.parse_args()
    with open(args.apk_list_file, 'rt') as f:
        for line in f:
            if line == '' or line.startswith('//'):
                continue
            line = line.rstrip()
            assert os.path.isfile(line), 'Parsing apk list: {} is not a file'.format(line)
            apk_files.append(line)

    i = 0
    force_clear = args.force_clear
    while i < len(apk_files):
        apk_path = apk_files[i]
        dirname, filename = os.path.split(apk_path)
        ape_output_folder = args.ape_output_folder.format(dirname=dirname, filename=filename)
        mt_output_folder = args.mt_output_folder.format(dirname=dirname, filename=filename)
        if not os.path.isdir(ape_output_folder):
            print("Creating folder ", ape_output_folder)
            os.makedirs(ape_output_folder)
        if not os.path.isdir(mt_output_folder):
            print("Creating folder ", mt_output_folder)
            os.makedirs(mt_output_folder)
        if run_ape_with_mt(apk_path, args.avd_name, args.libart_path, args.ape_jar_path, args.mtserver_path,
                ape_output_folder, mt_output_folder, args.running_minutes, force_clear):
            i += 1
            force_clear = False
