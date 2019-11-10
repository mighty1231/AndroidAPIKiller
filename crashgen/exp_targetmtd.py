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
from mt_run import kill_mtserver
from logcat_catcher import generate_catcher_thread, kill_generated_logcat_processes
from ape_mt_runner import install_art_ape_mt

ART_APE_MT_READY_SS = "ART_APE_MT" # snapshot name
TMP_LOCATION = "/data/local/tmp"
mtdtarget_fname = 'mtdtarget.txt'
mtdtarget_destname = '/data/local/tmp/mtdtarget.txt'

def libart_check(libart_path, serial):
    # Check our target libart.so is installed
    # Since checking is done by its size, it may give wrong result.
    size1 = os.path.getsize(libart_path)
    output = run_adb_cmd("shell ls -l /system/lib/libart.so", serial=serial)
    size2 = int(output.split()[3])

    return size1 == size2


def mt_task(package_name, serial, logging_flag, mt_is_running):
    def stdout_callback(line):
        if line.startswith('Server with uid'):
            mt_is_running.value += 1

    print('Start mtserver...')
    run_adb_cmd('shell /data/local/tmp/mtserver server {} {}'  \
            .format(package_name, logging_flag),
                stdout_callback = stdout_callback,
                stderr_callback = stdout_callback,
                serial=serial)
    kill_mtserver(serial)


def ape_task(avd_name, serial, package_name, output_dir, running_minutes, mt_is_running, mtdtarget, no_guide):
    sleep_cnt = 0
    while mt_is_running.value == 0 and sleep_cnt < 30:
        time.sleep(1)
        sleep_cnt += 1
    # Something wrong on mtserver, wait 30 seconds
    if sleep_cnt == 30:
        kill_mtserver(serial=serial)
        return
    assert mtdtarget

    mt_data_dir = os.path.join(output_dir, 'mt_data')
    if not os.path.isdir(mt_data_dir):
        os.makedirs(mt_data_dir)

    if not os.path.isdir(output_dir):
        os.makedirs(output_dir)
    def ape_stdout_callback(line):
        f.write(line + '\n')
        if line.startswith("[APE_MT] mt data "):
            directory = line[len("[APE_MT] mt data "):]
            run_adb_cmd("pull {} {}".format(directory, mt_data_dir), serial=serial)
            print("callback: {} pulled into {}".format(directory, mt_data_dir))
            run_adb_cmd("shell rm -rf {}".format(directory), serial=serial)

    run_adb_cmd("push {} {}".format(mtdtarget_fname, mtdtarget_destname), serial=serial)
    print('ape_task(): Emulator[{}, {}] Running APE with package {}'.format(avd_name, serial, package_name))
    args = '-p {} --running-minutes {} --mt --mtdtarget {} {}--ape sata'.format(package_name, running_minutes, mtdtarget_destname,
        "--no-mtdguide " if no_guide else "")
    with open(os.path.join(output_dir, 'ape_stdout_stderr.txt'), 'wt') as f:
        ret = run_adb_cmd('shell CLASSPATH={} {} {} {} {}'.format(
                os.path.join(TMP_LOCATION, 'ape.jar'),
                '/system/bin/app_process',
                TMP_LOCATION,
                'com.android.commands.monkey.Monkey',
                args),
            stdout_callback = ape_stdout_callback,
            stderr_callback = lambda t:f.write(t + '\n'),
            serial = serial,
        )
    # pull ape results
    run_adb_cmd('rmdir /data/ape/mt_data', serial=serial)
    ret = run_adb_cmd('pull /data/ape {}'.format(output_dir), serial=serial)

def run_ape_with_mt(apk_path, avd_name, libart_path, ape_jar_path, mtserver_path,
        output_dir, running_minutes, force_clear, mtdtarget, no_guide=False):
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
        return

    kill_mtserver(serial = avd.serial)
    mt_is_running = Value('i', 0)
    mtserver_thread = threading.Thread(target=mt_task,
        args=(package_name, avd.serial, "20010100", mt_is_running))
    apetask_thread = threading.Thread(target=ape_task,
        args=(avd_name, avd.serial, package_name, output_dir, running_minutes,
              mt_is_running, mtdtarget, no_guide))

    set_multiprocessing_mode()
    generate_catcher_thread(os.path.join(output_dir, "logcat.txt"),
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
    parser.add_argument('apk_path')
    parser.add_argument('avd_name')
    parser.add_argument('--force_clear', default=False, action='store_true')
    parser.add_argument('--libart_path', default='../bin/libart.so')
    parser.add_argument('--ape_jar_path', default='../bin/ape.jar')
    parser.add_argument('--mtserver_path', default='../bin/mtserver')
    parser.add_argument('--running_minutes', default='20')
    parser.add_argument('--output_dir', default='{dirname}/output')

    apk_files = []
    args = parser.parse_args()
    assert os.path.isfile(args.apk_path)
    dirname, filename = os.path.split(args.apk_path)

    output_dir = args.output_dir.format(dirname=dirname, filename=filename)

    # mtdtarget
    methods = [
        # 0061
        # ("android/app/IntentService", "onStart", "(Landroid/content/Intent;I)V"),
        # ("com/android/org/conscrypt/OpenSSLECGroupContext", "getContext", "()J"),

        # toy
        # ("com/fsck/k9/activity/setup/WelcomeMessage", "hiddenFunc", "()V"),

        # 0039
        # ("android/app/ActivityThread", "requestRelaunchActivity", "(Landroid/os/IBinder;Ljava/util/List;Ljava/util/List;IZLandroid/content/res/Configuration;Z)V"),

        # 0061
        # ("org/gnucash/android/ui/util/widget/CalculatorEditText$3", "onClick", "(Landroid/view/View;)V"),
        
        # 0061
        ("org/gnucash/android/ui/account/AccountsActivity$2", "onClick", "(Landroid/view/View;)V")
    ]
    with open(mtdtarget_fname, 'wt') as f:
        for clsname, mtdname, signature in methods:
           f.write("%s\t%s\t%s\t1\n" % (clsname, mtdname, signature)) # 1: method enter

    force_clear = args.force_clear
    i = 0
    while i < 10:
        outf = os.path.join(output_dir, "t_{}".format(i))
        if not os.path.isdir(outf):
            print("Creating folder ", outf)
            os.makedirs(outf)
        if run_ape_with_mt(args.apk_path, args.avd_name, args.libart_path, args.ape_jar_path, args.mtserver_path,
                outf, args.running_minutes, force_clear, mtdtarget_destname, no_guide=False):
            i += 1
            force_clear = False

    i = 0
    while i < 10:
        outf = os.path.join(output_dir, "nt_{}".format(i))
        if not os.path.isdir(outf):
            print("Creating folder ", outf)
            os.makedirs(outf)
        if run_ape_with_mt(args.apk_path, args.avd_name, args.libart_path, args.ape_jar_path, args.mtserver_path,
                outf, args.running_minutes, force_clear, mtdtarget_destname, no_guide=True):
            i += 1
            force_clear = False
