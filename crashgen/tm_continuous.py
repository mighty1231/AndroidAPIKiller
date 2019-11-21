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
    install_package,
    RunCmdError
)

import time
import threading
import re
import traceback
from multiprocessing.sharedctypes import Value
from mt_run import kill_mtserver
from logcat_catcher import generate_catcher_thread, kill_generated_logcat_processes
from ape_mt_runner import install_art_ape_mt
import datetime

ART_APE_MT_READY_SS = "ART_APE_MT" # snapshot name
TMP_LOCATION = "/data/local/tmp"

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


def ape_task(avd_name, serial, package_name, output_dir, running_minutes, mt_is_running, mtdtarget_fname, target_all_thread, no_guide):
    sleep_cnt = 0
    while mt_is_running.value == 0 and sleep_cnt < 30:
        time.sleep(1)
        sleep_cnt += 1
    # Something wrong on mtserver, wait 30 seconds
    if sleep_cnt == 30:
        kill_mtserver(serial=serial)
        return

    mt_data_dir = os.path.join(output_dir, 'mt_data')
    if not os.path.isdir(mt_data_dir):
        os.makedirs(mt_data_dir)

    def ape_stdout_callback(line):
        f.write(line + '\n')
        if line.startswith("[APE_MT] mt data "):
            directory = line[len("[APE_MT] mt data "):]
            run_adb_cmd("pull {} {}".format(directory, mt_data_dir), serial=serial)
            run_adb_cmd("shell rm -rf {}".format(directory), serial=serial)

    print('ape_task(): Emulator[{}, {}] Running APE with package {}'.format(avd_name, serial, package_name))
    args = '-p {} --running-minutes {} --mt --mtdtarget {} {}{}--ape sata'.format(package_name, running_minutes, mtdtarget_fname,
        "--no-mtdguide " if no_guide else "",
        "--target-all-thread " if target_all_thread else "")
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
    try:
        run_adb_cmd('shell rmdir /data/ape/mt_data', serial=serial)
    except RunCmdError as e:
        print(e.message, file=sys.stderr)
    ret = run_adb_cmd('pull /data/ape {}'.format(output_dir), serial=serial)

def run_ape_with_mt(apk_path, avd_name, libart_path, ape_path, mtserver_path,
        output_dir, running_minutes, force_clear, methods, target_all_thread, no_guide=False):
    package_name = get_package_name(apk_path)
    print('run_ape_with_mt(): given apk_path {} avd_name {}'.format(apk_path, avd_name))

    assert os.path.split(libart_path)[1] == 'libart.so'
    assert os.path.split(mtserver_path)[1] == 'mtserver'
    assert os.path.split(ape_path)[1] == 'ape.jar'

    avd = install_art_ape_mt(avd_name, libart_path, ape_path, mtserver_path, force_clear)

    try:
        install_package(apk_path, serial=avd.serial)
    except RuntimeError as e:
        print(e)
        return "install"

    mtdtarget_fname = 'mtdtarget.txt'
    mtdtarget_emulpath = '/data/local/tmp/mtdtarget.txt'
    with open(mtdtarget_fname, 'wt') as f:
        for clsname, mtdname, signature in methods:
           f.write("%s\t%s\t%s\t1\n" % (clsname, mtdname, signature)) # 1: method enter
    run_adb_cmd("push {} {}".format(mtdtarget_fname, mtdtarget_emulpath), serial=avd.serial)

    kill_mtserver(serial = avd.serial)
    mt_is_running = Value('i', 0)
    mtserver_thread = threading.Thread(target=mt_task,
        args=(package_name, avd.serial, "00010180", mt_is_running))
    apetask_thread = threading.Thread(target=ape_task,
        args=(avd_name, avd.serial, package_name, output_dir, running_minutes,
              mt_is_running, mtdtarget_emulpath, target_all_thread, no_guide))

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
        return "rerun"

    # feedback
    # 1. method is not found, then stop experiment this (apk, targeting methods)
    # 2. method is not called
    methods_registered_over_exp = [] # list of registered methods for each run
    logs = []
    try:
        with open(os.path.join(output_dir, "logcat.txt"), 'rt') as f:
            cur_methods_registered = None
            lazy_methods = []
            for line in f:
                '''
                MiniTrace: TargetMethod %s:%s[%s] lazy
                MiniTrace: TargetMethod %s:%s[%s] registered
                MiniTrace: TargetMethod %s:%s[%s] registered lazily
                '''
                if 'MiniTrace' not in line:
                    continue

                line = line.rstrip()
                line = line[line.index('MiniTrace'):]
                if line.startswith("MiniTrace: connection success, received"):
                    lazy_methods = []
                    if cur_methods_registered is not None:
                        methods_registered_over_exp.append(cur_methods_registered)
                    cur_methods_registered = []
                    logs.append(line)
                    continue
                gp = re.match(r'MiniTrace: TargetMethod (.*):(.*)\[(.*)\] ([a-z ]+)', line)
                if gp:
                    logs.append(line)
                    clsname, mtdname, signature, status = gp.groups()
                    if status == 'lazy':
                        assert (clsname, mtdname, signature) in methods, (clsname, mtdname, signature, methods)
                        lazy_methods.append((clsname, mtdname, signature))
                    elif status == 'registered':
                        assert (clsname, mtdname, signature) in methods, (clsname, mtdname, signature, methods)
                        cur_methods_registered.append(methods.index((clsname, mtdname, signature)))
                    else:
                        assert status == 'registered lazily', status
                        assert clsname[0] == 'L' and clsname[-1] == ';', clsname
                        clsname = clsname[1:-1]
                        assert (clsname, mtdname, signature) in lazy_methods, (clsname, mtdname, signature, lazy_methods)
                        cur_methods_registered.append(methods.index((clsname, mtdname, signature)))
            if cur_methods_registered is not None:
                methods_registered_over_exp.append(cur_methods_registered)
    except AssertionError as e:
        print("run_ape_with_mt(): Feedback - failed to register methods")
        print(methods_registered_over_exp)
        print('\n'.join(logs))
        print(e)
        traceback.print_exc()
        return "unregistered"
    if all(executed == [] for executed in methods_registered_over_exp):
        print("run_ape_with_mt(): Feedback - failed to register any methods")
        return "unregistered"
    print('run_ape_with_mt(): methods registered...')
    print(methods_registered_over_exp)

    if no_guide:
        return "success"

    # 2. method is not called
    with open(os.path.join(output_dir, 'ape_stdout_stderr.txt'), 'rt') as logf:
        for line in logf:
            line = line.rstrip()
            if "met target" in line:
                return "success"

    return "notsearched"

def run(apk_path, avd_name, total_count, methods, libart_path, ape_path, mtserver_path, running_minutes, target_all_thread, output_dir, force_clear):
    expidx = 0
    notsearched_count = 0
    unregistered_count = 0
    while expidx < total_count:
        outf = os.path.join(output_dir, "t_{}".format(expidx))
        if not os.path.isdir(outf):
            print("Creating folder ", outf)
            os.makedirs(outf)
        status = run_ape_with_mt(apk_path, avd_name, libart_path, ape_path, mtserver_path,
                outf, running_minutes, force_clear, methods, target_all_thread, no_guide=False)
        if status == "install":
            return
        elif status == "rerun":
            print("{} exp status {} on {}".format(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), status, outf), flush=True)
            continue
        elif status == "unregistered":
            # try 2 times
            if unregistered_count == 1 == expidx:
                return
            unregistered_count += 1
        elif status == "notsearched":
            notsearched_count += 1
        else:
            assert status == "success", status
        expidx += 1
        force_clear = False
        print("{} exp status {} on {}".format(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), status, outf), flush=True)

    if notsearched_count == total_count:
        print("Failed to search target methods during {} experiments".format(total_count))
        return

    expidx = 0
    while expidx < total_count:
        outf = os.path.join(output_dir, "nt_{}".format(expidx))
        if not os.path.isdir(outf):
            print("Creating folder ", outf)
            os.makedirs(outf)
        status = run_ape_with_mt(apk_path, avd_name, libart_path, ape_path, mtserver_path,
                outf, running_minutes, force_clear, methods, target_all_thread, no_guide=True)
        if status == "rerun":
            print("{} exp status {} on {}".format(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), status, outf), flush=True)
            continue
        assert status in ["unregistered", "success"], status
        expidx += 1
        print("{} exp status {} on {}".format(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), status, outf), flush=True)

class ExperimentUnit:
    def __init__(self, name, apk_path, methods):
        assert os.path.isfile(apk_path), apk_path
        assert isinstance(methods, list), methods
        for method in methods:
            clsname, mtdname, signature = method
        self.name = name
        self.apk_path = apk_path
        self.methods = methods

    def __eq__(self, other):
        if self.name != other.name:
            return False
        if self.apk_path != other.apk_path:
            return False
        return self.methods == other.methods

    @staticmethod
    def fromlines(name, apk_path, lines):
        methods = []
        for line in lines:
            clsname, mtdname, signature = line.split()
            methods.append((clsname, mtdname, signature))
        return ExperimentUnit(name, apk_path, methods)

def make_output_dir(output_dir):
    idx = 0
    while idx < 500:
        new_output_dir = output_dir + "_{}".format(idx)
        if os.path.isdir(new_output_dir):
           idx += 1
           continue
        os.makedirs(new_output_dir)
        return new_output_dir
    raise RuntimeError

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Runner of APE, MiniTracing with method target')
    parser.add_argument('avd_name')
    parser.add_argument('exp_file')
    parser.add_argument('--force_clear', default=False, action='store_true')
    parser.add_argument('--libart_path', default='../bin/libart.so')
    parser.add_argument('--ape_path', default='../bin/ape.jar')
    parser.add_argument('--mtserver_path', default='../bin/mtserver')
    parser.add_argument('--repeat_count', default='10')
    parser.add_argument('--running_minutes', default='20')
    parser.add_argument('--output_dir', default='../results/continuous')
    parser.add_argument('--target_all_thread', default=False, action='store_true')
    parser.add_argument('--names', default=None) # do experiment with given expnames
    args = parser.parse_args()

    repeat_count = int(args.repeat_count)
    assert repeat_count > 0, repeat_count
    done_experiments = []
    force_clear = args.force_clear
    names = None
    if args.names:
        names = args.names.split(',')
        print('Do experiments with name {}'.format(', '.join(names)))
    while True:
        expunit = None
        with open(args.exp_file, 'rt') as f:
            it = iter(f)
            for line in it:
                line = line.rstrip()
                if line == '':
                    continue
                mtdcnt = int(line)
                lines = []
                expname, apk_path = next(iter(it)).rstrip().split()
                for i in range(mtdcnt):
                    lines.append(next(iter(it)).rstrip())
                tmp = ExperimentUnit.fromlines(expname, apk_path, lines)
                if tmp in done_experiments:
                    continue
                if names is not None and tmp.name not in names:
                    continue
                expunit = tmp
                break
        if expunit is None:
            break

        print("[Experiment - {}] {}".format(expunit.name, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        print(expunit.apk_path)
        for clsname, mtdname, signature in expunit.methods:
            print('\t'.join([clsname, mtdname, signature]))
        output_dir = os.path.join(args.output_dir, expunit.name)
        if os.path.isdir(output_dir):
            print(" - Warning: there is folder {} already".format(output_dir))
            output_dir = make_output_dir(output_dir)
            print(' - New output directory', output_dir, flush=True)
        else:
            os.makedirs(output_dir)
            print(' - Output directory', output_dir, flush=True)
        run(expunit.apk_path, args.avd_name, repeat_count, expunit.methods,
                args.libart_path, args.ape_path, args.mtserver_path,
                args.running_minutes, args.target_all_thread,
                output_dir, force_clear)
        done_experiments.append(expunit)
        force_clear = False
