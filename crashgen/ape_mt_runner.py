import sys, os

from androidkit import (
    run_adb_cmd,
    get_package_name,
    set_multiprocessing_mode
)
from ape_runner import install_ape_and_make_snapshot

import time
import multiprocessing as mp
from mt_run import run_mtserver
from ape_runner import run_ape

def run_ape_with_mt(apk_path, avd_name, mt_binary):
    package_name = get_package_name(apk_path)
    print('run_ape_with_mt(): given apk_path {} avd_name {}'.format(apk_path, avd_name))
    avd = install_ape_and_make_snapshot(avd_name)
    run_adb_cmd('install {}'.format(apk_path), serial=avd.serial)
    run_adb_cmd('push {} /data/local/tmp/'.format(mt_binary), serial=avd.serial)

    set_multiprocessing_mode()

    mtserver_proc = mp.Process(target=run_mtserver,
        args=(package_name, "mt_output", avd.serial))
    apetask_proc = mp.Process(target=run_ape,
        args=(apk_path, avd_name, "ape_output", 20))

    mtserver_proc.start()
    apetask_proc.start()

    apetask_proc.join()

    mtserver_proc.kill()
    mtserver_proc.join()

if __name__ == "__main__":
    apk_path, avd_name, mt_binary = sys.argv[1:4]
    run_ape_with_mt(apk_path, avd_name, mt_binary)
