import argparse
from .avd import get_avd_list, create_avd
from .emulator import emulator_run_and_wait, emulator_setup
from .utils import extract_apk, get_activity_stack, get_uid, get_pids

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
        writable_system=args.writable_system
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
else:
    raise