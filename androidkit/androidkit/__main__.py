import argparse
import re, os
from .avd import get_avd_list, create_avd
from .emulator import emulator_run_and_wait, emulator_setup
from .utils import (
    extract_apk,
    list_packages,
    clear_package,
    get_activity_stack,
    get_uid,
    get_pids,
    list_snapshots,
    load_snapshot,
    save_snapshot,
    run_adb_cmd,
    screen_capture
)

parser = argparse.ArgumentParser(description='Tools to manage android devices')

subparsers = parser.add_subparsers(dest='func')

list_parser = subparsers.add_parser('status')
list_parser.add_argument('--detail', action='store_true')

run_parser = subparsers.add_parser('run',
    help='Run Android emulator')
run_parser.add_argument('avd_name', type=str)
run_parser.add_argument('--port', default=None)
run_parser.add_argument('--snapshot', default=None)
run_parser.add_argument('--wipe_data', action='store_true')
run_parser.add_argument('--writable_system', action='store_true')
run_parser.add_argument('--partition_size', help='Disk size for emulator in MB', default=None)

arbi_parser = subparsers.add_parser('exec')
arbi_parser.add_argument('expression', type=str)

setup_parser = subparsers.add_parser('setup')
setup_parser.add_argument('serial', type=str)

create_parser = subparsers.add_parser('create',
    help='Create Android Virtual Device')
create_parser.add_argument('name')
create_parser.add_argument('--sdkversion', default='android-22')
create_parser.add_argument('--tag', default='default')
create_parser.add_argument('--device', default='Nexus 5')
create_parser.add_argument('--sdcard', default='512M')

extract_parser = subparsers.add_parser('extractapk',
    help='Extract installed apk file from device')
extract_parser.add_argument('package')
extract_parser.add_argument('output_dir_or_file',
    help="Interpreted as file with '*.apk', otherwise interpreted as directory. " \
         "For latter case, file name is set to (package_name).apk")
extract_parser.add_argument('--serial', default=None)

listpackages_parser = subparsers.add_parser('listpackages',
    help='List installed packages from device')
listpackages_parser.add_argument('--all',
    help='If checked, android packages are also shown.', action='store_true')
listpackages_parser.add_argument('--serial', default=None)

clearpackage_parser = subparsers.add_parser('clearpackage',
    help='Clear application data of specific package from device')
clearpackage_parser.add_argument('package')
clearpackage_parser.add_argument('--serial', default=None)

activity_stack_parser = subparsers.add_parser('activitystack',
    help='Print current activity stack on device')
activity_stack_parser.add_argument('--serial', default=None)

get_uid_parser = subparsers.add_parser('getuid',
    help='Get UID of installed package')
get_uid_parser.add_argument('package')
get_uid_parser.add_argument('--serial', default=None)

get_pid_parser = subparsers.add_parser('getpid',
    help='Get PID of running process with specified package')
get_pid_parser.add_argument('package')
get_pid_parser.add_argument('--serial', default=None)

pull_parser = subparsers.add_parser('pull',
    help='Pull files whose name starts with prefix')
pull_parser.add_argument('prefix',
    help='Examples: /sdcard/mt_0_ or /data/data/some.app/mt_3_')
pull_parser.add_argument('--destination', default='.')
pull_parser.add_argument('--serial', default=None)

cap_parser = subparsers.add_parser('capture',
    help='capture screen to png file')
cap_parser.add_argument('outf')
cap_parser.add_argument('--serial', default=None)

def parse_serial(serial):
    try:
        serial = int(serial)
    except (TypeError, ValueError):
        pass
    return serial

args = parser.parse_args()
if args.func == 'status':
    avd_list = get_avd_list()
    if args.detail:
        for avd in avd_list:
            print(avd.getDetail())
    else:
        for avd in avd_list:
            print(avd)
elif args.func == 'run':
    try:
        port = int(args.port)
    except (TypeError, ValueError):
        port = args.port
    emulator_run_and_wait(args.avd_name,
        serial=port,
        snapshot=args.snapshot,
        wipe_data=args.wipe_data,
        writable_system=args.writable_system,
        partition_size_in_mb=args.partition_size
    )
elif args.func == 'exec':
    print('Executing {}...'.format(args.expression))
    retval = exec(args.expression)
    print('Return value for {}: {}'.format(args.expression, retval))
elif args.func == 'setup':
    emulator_setup(serial = parse_serial(args.serial))
elif args.func == 'create':
    create_avd(args.name, args.sdkversion, args.tag, args.device, args.sdcard)
elif args.func == 'extractapk':
    import os
    basename, extension = os.path.splitext(args.output_dir_or_file)
    if extension == '.apk':
        target = args.output_dir_or_file
    if not os.path.isdir(args.output_dir_or_file):
        os.makedirs(args.output_dir_or_file)
    target = os.path.join(args.output_dir_or_file, '{}.apk'.format(args.package))

    extract_apk(args.package, target, serial = parse_serial(args.serial))
elif args.func == 'listpackages':
    packages = list_packages(serial = parse_serial(args.serial))
    if args.all:
        print('\n'.join(sorted(packages)))
    else:
        for p in sorted(packages):
            if p.startswith('com.android.') or p.startswith('com.example.android') or \
                    p == 'android':
                continue
            print(p)
elif args.func == 'clearpackage':
    clear_package(args.package, serial = parse_serial(args.serial))
elif args.func == 'activitystack':
    stacks = get_activity_stack(serial = parse_serial(args.serial))
    for i, stack in enumerate(stacks):
        print('Stack #{}'.format(i))

        for j, activity in enumerate(stack):
            print('  Activity #{} {}'.format(len(stack)-j, activity))
elif args.func == 'getuid':
    uid = get_uid(args.package, serial=parse_serial(args.serial))
    print(uid)
elif args.func == 'getpid':
    pids = get_pids(args.package, serial=parse_serial(args.serial))
    print(' '.join(map(str, pids)))
elif args.func == 'pull':
    serial = parse_serial(args.serial)

    # list files
    folder, prefix = os.path.split(args.prefix)
    out = run_adb_cmd('shell ls {}*'.format(args.prefix),
            serial=serial)
    if "No such file or directory" not in out:
        fnames = []
        for line in out.split():
            if line == '':
                break
            fnames.append(line.rstrip())

        print("List of files")
        for fname in fnames:
            print(' - ' + fname)
        ret = input("Are you sure to pull these files? [Y/N] ")
        if ret in ['Y', 'y']:
            for fname in fnames:
                run_adb_cmd("pull {} {}".format(fname, args.destination),
                        serial=serial)
                print(fname, 'pulled into',
                      os.path.join(args.destination,
                                   os.path.split(fname)[1]))
    else:
        print("No such file or directory")
elif args.func == 'capture':
    serial = parse_serial(args.serial)
    screen_capture(args.outf, serial=serial)
else:
    raise
