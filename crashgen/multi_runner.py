import multiprocessing as mp
import sys
import glob
import os
import traceback
import time

sys.path.insert(0, '../common')
from emulator import get_avd_list
from utils import run_adb_cmd, RunCmdError
from ape_runner import run_ape, install_ape_and_make_snapshot

def run_ape_task(avd_name, apk_queue, error_queue):
    for apk_path in iter(apk_queue.get, 'STOP'):
        dirname, filename = os.path.split(apk_path)
        output_dir = os.path.join(dirname, 'ape_output')
        try:
            run_ape(apk_path, avd_name, output_dir, running_minutes=1)
        except RunCmdError as e:
            error_queue.put((avd_name, apk_path, e.out, e.err))
        except Exception as e:
            error_queue.put((avd_name, apk_path, sys.exc_info()[0], traceback.format_exc()))

if __name__ == "__main__":
    apk_files = sorted(glob.glob(sys.argv[1]))
    assert len(apk_files) >= 2
    print('Total {} apk files are found'.format(len(apk_files)))

    # Check apks
    apk_queue = mp.Queue()
    for apk_file in apk_files:
        apk_queue.put(apk_file)
    error_queue = mp.Queue()

    # Check AVDs
    avd_names = sys.argv[2:]
    avd_available_names = map(lambda t:t.name, get_avd_list())
    assert all(avd in avd_available_names for avd in avd_names)
    for avd_name in avd_names:
        install_ape_and_make_snapshot(avd_name)

    avd_cnt = len(avd_names)
    from utils import _set_multiprocessing
    _set_multiprocessing()

    for avd_name in avd_names:
        mp.Process(target=run_ape_task, args=(avd_name, apk_queue, error_queue)).start()
    apk_queue.close()
    apk_queue.join_thread()

    i = 0
    for error in iter(error_queue.get, 'STOP'):
        print('Error #{} - {} {}'.format(i, error[0], error[1]))
        for e in error[2:]:
            print(e)
        i += 1

