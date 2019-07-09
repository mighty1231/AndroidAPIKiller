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

def install_ape_and_make_snapshot():
    APE_ROOT = '/data/local/tmp/'
    run_adb_cmd('push ape.jar {}'.format(APE_ROOT))
    save_snapshot('APE_INSTALLED')

def run_ape(apk_path, running_minutes=20):
    package_name = get_package_name(apk_path)

    # install ape.jar
    if 'APE_INSTALLED' not in list_snapshots():
        raise RuntimeError('APE must be installed as default environment')
    load_snapshot('APE_INSTALLED')

    # install apk
    run_adb_cmd('install {}'.format(apk_path))

    # run ape
    args = '-p {} --running-minutes {} -vvv --ape sata --bugreport'.format(package_name, running_minutes)
    ret = run_adb_cmd('shell CLASSPATH={} {} {} {} {}'.format(
        os.path.join(APE_ROOT, 'ape.jar'),
        '/system/bin/app_process',
        APE_ROOT,
        'com.android.commands.monkey.Monkey',
        args
    ))

    print(ret)

if __name__ == "__main__":
    apk_path = sys.argv[1]
    run_ape(apk_path)
