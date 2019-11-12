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


def ape_task(avd_name, serial, package_name, output_dir, running_minutes, mt_is_running, mtdtarget_fname, no_guide):
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
    args = '-p {} --running-minutes {} --mt --mtdtarget {} {}--ape sata'.format(package_name, running_minutes, mtdtarget_fname,
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
    try:
        run_adb_cmd('shell rmdir /data/ape/mt_data', serial=serial)
    except RunCmdError as e:
        print(e.message, file=sys.stderr)
    ret = run_adb_cmd('pull /data/ape {}'.format(output_dir), serial=serial)

def run_ape_with_mt(apk_path, avd_name, libart_path, ape_path, mtserver_path,
        output_dir, running_minutes, force_clear, methods, no_guide=False):
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
        args=(package_name, avd.serial, "20010100", mt_is_running))
    apetask_thread = threading.Thread(target=ape_task,
        args=(avd_name, avd.serial, package_name, output_dir, running_minutes,
              mt_is_running, mtdtarget_emulpath, no_guide))

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
    remaining_methods = list(methods)
    logs = []
    try:
        with open(os.path.join(output_dir, "logcat.txt"), 'rt') as f:
            observe_count = 25 + 5 * len(methods)
            lazy_methods = []
            for line in f:
                '''
                MiniTrace: TargetMethod %s:%s[%s] registered lazy
                MiniTrace: TargetMethod %s:%s[%s] not found
                MiniTrace: TargetMethod %s:%s[%s] registered
                '''
                if 'MiniTrace' not in line:
                    continue

                line = line.rstrip()
                line = line[line.index('MiniTrace'):]
                gp = re.match(r'MiniTrace: TargetMethod (.*):(.*)\[(.*)\] ([a-z ]+)', line)
                if gp:
                    logs.append(line)
                    clsname, mtdname, signature, status = gp.groups()
                    if status == 'registered lazy':
                        assert (clsname, mtdname, signature) in remaining_methods, (remaining_methods, clsname, mtdname, signature)
                        remaining_methods.remove((clsname, mtdname, signature))
                        lazy_methods.append(('L' + clsname + ';', mtdname, signature))
                    else:
                        assert status =='registered', status
                        if (clsname, mtdname, signature) in remaining_methods:
                            remaining_methods.remove((clsname, mtdname, signature))
                        else:
                            assert (clsname, mtdname, signature) in lazy_methods, (clsname, mtdname, signature, remaining_methods, lazy_methods)
                            lazy_methods.remove((clsname, mtdname, signature))
                if len(remaining_methods) == 0 == len(lazy_methods):
                    break
                observe_count -= 1
                if observe_count == 0:
                    break
            remaining_methods += lazy_methods
    except AssertionError as e:
        print("run_ape_with_mt(): Feedback - failed to register methods")
        print('\n'.join(logs))
        print(e)
        traceback.print_exc()
        return "method_register"

    if len(methods) != 0 and len(methods) == len(remaining_methods):
        print("run_ape_with_mt(): Feedback - failed to register any methods")
        return "method_register"

    # 2. method is not called
    if no_guide:
        return "success"

    with open(os.path.join(output_dir, 'ape_stdout_stderr.txt'), 'wt') as logf:
        for line in logf:
            line = line.rstrip()
            if "[APE_MT] MET_TARGET" in line:
                return "success"

    return "notmet"

def run(apk_path, avd_name, total_count, methods, libart_path, ape_path, mtserver_path, running_minutes, output_dir, force_clear):
    i = 0
    notmet_count = 0
    while i < total_count:
        outf = os.path.join(output_dir, "t_{}".format(i))
        if not os.path.isdir(outf):
            print("Creating folder ", outf)
            os.makedirs(outf)
        status = run_ape_with_mt(apk_path, avd_name, libart_path, ape_path, mtserver_path,
                outf, running_minutes, force_clear, methods, no_guide=False)
        if status == "install":
            return
        elif status == "rerun":
            print("rerun")
            continue
        elif status == "method_register":
            return
        if status == "notmet":
            notmet_count += 1
        else:
            assert status == "success", status
        i += 1
        force_clear = False

    if notmet_count == total_count:
        print("Failed to search target methods during {} experiments".format(total_count))
        return

    i = 0
    while i < total_count:
        outf = os.path.join(output_dir, "nt_{}".format(i))
        if not os.path.isdir(outf):
            print("Creating folder ", outf)
            os.makedirs(outf)
        status = run_ape_with_mt(apk_path, avd_name, libart_path, ape_path, mtserver_path,
                outf, running_minutes, force_clear, methods, no_guide=True)
        assert status in ["rerun", "success"]
        if status == "success":
            i += 1

class ExperimentUnit:
    def __init__(self, apk_path, methods):
        assert os.path.isfile(apk_path), apk_path
        assert isinstance(methods, list), methods
        for method in methods:
            clsname, mtdname, signature = method
        self.apk_path = apk_path
        self.methods = methods

    def __eq__(self, other):
        if self.apk_path != other.apk_path:
            return False
        return self.methods == other.methods

    @staticmethod
    def fromlines(lines):
        apk_path = lines[0]
        methods = []
        for line in lines[1:]:
            clsname, mtdname, signature = line.split("\t")
            methods.append((clsname, mtdname, signature))
        return ExperimentUnit(apk_path, methods)

def make_output_dir(output_dir):
    if not os.path.isdir(output_dir):
        if os.path.isfile(output_dir):
            raise RuntimeError("Output directory {} is file".format(output_dir))
        os.makedirs(output_dir)

    idx = 0
    while idx < 500:
        new_output_dir = os.path.join(output_dir, 'exp_{}'.format(idx))
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
    args = parser.parse_args()

    repeat_count = int(args.repeat_count)
    assert repeat_count > 0, repeat_count
    done_experiments = []
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
                for i in range(mtdcnt+1):
                    lines.append(next(iter(it)).rstrip())
                tmp = ExperimentUnit.fromlines(lines)
                if tmp in done_experiments:
                    continue
                expunit = tmp
                break
        if expunit is None:
            break

        print("[Experiment]")
        print(expunit.apk_path)
        for clsname, mtdname, signature in expunit.methods:
            print('\t'.join([clsname, mtdname, signature]))
        output_dir = make_output_dir(args.output_dir)
        print('Output directory', output_dir, flush=True)
        run(expunit.apk_path, args.avd_name, repeat_count, expunit.methods, args.libart_path, args.ape_path, args.mtserver_path, args.running_minutes, output_dir, args.force_clear)
        done_experiments.append(expunit)
