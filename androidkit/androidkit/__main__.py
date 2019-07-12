import argparse
from .avd import get_avd_list, create_avd
from .emulator import emulator_run_and_wait, emulator_setup

parser = argparse.ArgumentParser(description='Manages android emulator')

subparsers = parser.add_subparsers(dest='func')

list_parser = subparsers.add_parser('status')
list_parser.add_argument('--detail', action='store_true')

run_parser = subparsers.add_parser('run')
run_parser.add_argument('avd_name', type=str)
run_parser.add_argument('--port', default=None)
run_parser.add_argument('--snapshot', default=None)
run_parser.add_argument('--wipe_data', action='store_true')
run_parser.add_argument('--writable_system', action='store_true')

arbi_parser = subparsers.add_parser('exec')
arbi_parser.add_argument('expression', type=str)

setup_parser = subparsers.add_parser('setup')
setup_parser.add_argument('serial', type=str)

create_parser = subparsers.add_parser('create')
create_parser.add_argument('name')
create_parser.add_argument('--sdkversion', default='android-22')
create_parser.add_argument('--tag', default='default')
create_parser.add_argument('--device', default='Nexus 5')
create_parser.add_argument('--sdcard', default='512M')

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
    try:
        serial = int(args.serial)
    except (TypeError, ValueError):
        serial = args.serial
    emulator_setup(serial = serial)
elif args.func == 'create':
    create_avd(args.name, args.sdkversion, args.tag, args.device, args.sdcard)
else:
    raise
