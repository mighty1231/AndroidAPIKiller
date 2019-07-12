import multiprocessing as mp
import sys
import glob
import os
import traceback
import time
import queue

from androidkit import get_avd_list, run_adb_cmd, RunCmdError

from ape_runner import run_ape, install_ape_and_make_snapshot

def print_error(error, file=None):
    avd_name, apk_path, *etc = error
    if file is None:
        file = sys.stdout
    print('[{}] Error with apk={}'.format(avd_name, apk_path), file=file)
    for info in etc:
        print('[{}] {}'.format(avd_name, info), file=file)

def run_ape_task(avd_name, apk_queue, error_queue, output_dir_format, running_minutes):
    for apk_path in iter(apk_queue.get, 'STOP'):
        dirname, filename = os.path.split(apk_path)
        output_dir = output_dir_format.format(dirname=dirname, filename=filename)
        try:
            run_ape(apk_path, avd_name, output_dir, running_minutes=running_minutes)
        except RunCmdError as e:
            error = (avd_name, apk_path, e.out, e.err)
            error_queue.put(error)
            print_error(error, file=sys.stderr)
            break
        except Exception as e:
            error = (avd_name, apk_path, sys.exc_info()[0], traceback.format_exc())
            error_queue.put(error)
            print_error(error, file=sys.stderr)
            break

if __name__ == "__main__":
    '''
    python3 multi_runner.py apklist.txt N5_22_1 N5_22_2 N5_22 --running_minutes 1 --output_dir_format "{dirname}/{filename}/ape/result/"
    '''
    import argparse

    parser = argparse.ArgumentParser(description='Multiprocessing runner for APE')
    parser.add_argument('apk_list_file')
    parser.add_argument('avd_names', nargs='*')
    parser.add_argument('--output_dir_format', default='{dirname}/ape_output')
    parser.add_argument('--running_minutes', default=60)

    apk_files = []
    args = parser.parse_args()
    with open(args.apk_list_file, 'rt') as f:
        for line in f:
            if line == '' or line.startswith('//'):
                continue
            line = line.rstrip()
            assert os.path.isfile(line), 'Parsing apk list: {} is not a file'.format(line)
            apk_files.append(line)

    assert len(apk_files) >= 2
    print('Total {} apk files are found'.format(len(apk_files)))

    # Check apks
    apk_queue = mp.Queue()
    for apk_file in apk_files:
        apk_queue.put(apk_file)
    error_queue = mp.Queue()

    # Check AVDs
    avd_names = args.avd_names
    avd_available_names = list(map(lambda t:t.name, get_avd_list()))
    assert all(avd in avd_available_names for avd in avd_names), (avd_names, avd_available_names)
    avd_cnt = len(avd_names)
    assert avd_cnt > 1
    print('Total {} avds are found'.format(avd_cnt))
    if avd_cnt > 3:
        print('Warning: More than 3 emulator can generate error on some emulator')

    for avd_name in avd_names:
        install_ape_and_make_snapshot(avd_name)

    for i in range(avd_cnt):
        apk_queue.put('STOP')

    from utils import _set_multiprocessing
    _set_multiprocessing()

    jobs = []
    for avd_name in avd_names:
        proc = mp.Process(target=run_ape_task,
            args=(avd_name,
                apk_queue,
                error_queue,
                args.output_dir_format,
                args.running_minutes))
        jobs.append(proc)
        proc.start()

    apk_queue.close()

    for job in jobs:
        job.join()

    i = 0
    try:
        while True:
            error = error_queue.get_nowait()
            print('Error #{} - {} {}'.format(i, error[0], error[1]), file=sys.stderr)
            for e in error[2:]:
                print(e, file=sys.stderr)
            i += 1
    except queue.Empty:
        pass
