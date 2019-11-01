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
from ape_runner import fetch_result
from logcat_catcher import generate_catcher_thread, kill_generated_logcat_processes

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

from ape_mt_runner import install_art_ape_mt, ConnectionsWithValue, mt_task

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
    run_adb_cmd("push {} {}".format(mtdtarget_fname, mtdtarget_destname))
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
            stdout_callback = lambda t:f.write(t + '\n'),
            stderr_callback = lambda t:f.write(t + '\n'),
            serial = serial,
        )

    fetch_result(output_dir, serial)

def run_ape_with_mt(apk_path, avd_name, libart_path, ape_jar_path, mtserver_path,
        ape_output_folder, mt_output_folder, running_minutes, force_clear, mtdtarget, no_guide=False):
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
        args=(package_name, mt_output_folder, avd.serial, "20010100", mt_is_running))
    apetask_thread = threading.Thread(target=ape_task,
        args=(avd_name, avd.serial, package_name, ape_output_folder, running_minutes,
              mt_is_running, mtdtarget, no_guide))

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
    parser.add_argument('apk_path')
    parser.add_argument('avd_name')
    parser.add_argument('--force_clear', default=False, action='store_true')
    parser.add_argument('--libart_path', default='../bin/libart.so')
    parser.add_argument('--ape_jar_path', default='../bin/ape.jar')
    parser.add_argument('--mtserver_path', default='../bin/mtserver')
    parser.add_argument('--running_minutes', default='20')
    parser.add_argument('--ape_output_folder', default='{dirname}/ape_output_tm')
    parser.add_argument('--mt_output_folder', default='{dirname}/mt_output_tm')

    apk_files = []
    args = parser.parse_args()
    assert os.path.isfile(args.apk_path)
    dirname, filename = os.path.split(args.apk_path)

    ape_output_folder = args.ape_output_folder.format(dirname=dirname, filename=filename)
    mt_output_folder = args.mt_output_folder.format(dirname=dirname, filename=filename)

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
        aof = ape_output_folder + "_t_{}".format(i)
        mof = mt_output_folder + "_t_{}".format(i)
        if not os.path.isdir(aof):
            print("Creating folder ", aof)
            os.makedirs(aof)
        if not os.path.isdir(mof):
            print("Creating folder ", mof)
            os.makedirs(mof)
        if run_ape_with_mt(args.apk_path, args.avd_name, args.libart_path, args.ape_jar_path, args.mtserver_path,
                aof, mof, args.running_minutes, force_clear, mtdtarget_destname, no_guide=False):
            i += 1
            force_clear = False

    i = 0
    while i < 10:
        aof = ape_output_folder + "_nt_{}".format(i)
        mof = mt_output_folder + "_nt_{}".format(i)
        if not os.path.isdir(aof):
            print("Creating folder ", aof)
            os.makedirs(aof)
        if not os.path.isdir(mof):
            print("Creating folder ", mof)
            os.makedirs(mof)
        if run_ape_with_mt(args.apk_path, args.avd_name, args.libart_path, args.ape_jar_path, args.mtserver_path,
                aof, mof, args.running_minutes, force_clear, mtdtarget_destname, no_guide=True):
            force_clear = False
            i += 1
