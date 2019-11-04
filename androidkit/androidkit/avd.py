import re, sys, os
from .config import getConfig
from .utils import (
    run_cmd,
    run_adb_cmd,
    RunCmdError,
    CacheDecorator
)

class AVD:
    def __init__(self, name, device, path, target, base, tag, optional_pairs):
        self.name = name
        self.device = device
        self.path = path
        self.target = target
        self.base = base
        self.tag = tag
        self.optional_pairs = optional_pairs

        # Two cases:
        #    running (there is serial)
        #    not running
        self.running = False
        self.serial = None

    def setRunning(self, serial):
        self.running = True
        self.serial = serial

    def __repr__(self):
        if self.running:
            return '<AVD[{}] {}, {}, running with {}>'.format(self.name, self.device, self.tag, self.serial)
        else:
            return '<AVD[{}] {}, {}, available>'.format(self.name, self.device, self.tag)

    def getDetail(self):
        ret = []
        for attr in ['device', 'path', 'target', 'base', 'tag',
                'optional_pairs', 'running', 'serial']:
            ret.append('AVD<{}>.{} = {}'.format(self.name, attr, getattr(self, attr)))
        return '\n'.join(ret)

def run_avdmanager(cmd):
    # wrapper for avdmanager
    avdmanager = getConfig('AVDMANAGER_PATH')
    try:
        output = run_cmd('{} {}'.format(avdmanager, cmd))
        return output
    except RunCmdError as e:
        if 'AvdManagerCli : Unsupported major.minor version' in e.err:
            TAG = "Androidkit.run_avdmanager: "
            print(TAG + "Problem on versions of java or javac", file=sys.stderr)
            print(TAG + "Following commands would be help for debugging", file=sys.stderr)
            print(TAG + " - which (java|javac)", file=sys.stderr)
            print(TAG + " - echo ($JAVA_HOME|$PATH)", file=sys.stderr)
            print(TAG + " - sudo update-alternatives --config (java|javac)", file=sys.stderr)
        raise

@CacheDecorator
def _run_avdmanager_list_avd():
    # get all available devices
    # this function seems not be changed, so use cache
    output = run_avdmanager('list avd')

    # parse result for avdmanager list avd
    avd_list = []
    try:
        lines = output.split('\n')
        assert lines[0].startswith('Parsing '),                             \
                "You should modify the logic in here, or"                   \
                "please report to developer to following output\n" + output

        i = 1
        while i < len(lines) and lines[i] != '':
            name      = re.match(r'Name: (.*)', lines[i].lstrip()).groups()[0]
            device    = re.match(r'Device: (.*)', lines[i+1].lstrip()).groups()[0]
            path      = re.match(r'Path: (.*)', lines[i+2].lstrip()).groups()[0]
            target    = re.match(r'Target: (.*)', lines[i+3].lstrip()).groups()[0]
            base, tag = re.match(r'Based on: (.*) Tag/ABI: (.*)', lines[i+4].lstrip()).groups()

            # now, optional arguments - Skin, Sdcard, Snapshot
            i += 5
            optional_pairs = []
            while i < len(lines) and lines[i] != '' and not lines[i].startswith('----'):
                sep = lines[i].index(':')
                key = lines[i][:sep].strip()
                value = lines[i][sep+1:].strip()
                optional_pairs.append((key, value))
                i += 1
            if lines[i].startswith('----'):
                i += 1

            avd = (name, device, path, target, base, tag, optional_pairs)

            if tag.startswith('google_apis_playstore'):
                print('Warning: AVD[{}] cannot be rooted'.format(name), file=sys.stderr)
            else:
                avd_list.append(avd)

    except Exception as e:
        print('Error: Unexpected form on avdmanager list avd', file=sys.stderr)
        print('Result of avdmanger list avd -->', file=sys.stderr)
        print('//---------------------------//')
        print(output, file=sys.stderr)
        print('//---------------------------//')
        raise
    return avd_list

def get_avd_list(warned = False):
    avd_list = list(map(lambda args:AVD(*args), _run_avdmanager_list_avd()))

    # fetch currently running devices
    res = run_adb_cmd('devices')
    assert res.count('\n') >= 2, res
    for line in res.split('\n')[1:]:
        if line == '':
            continue
        serial = line.split()[0]

        # At now, assert all devices are based on emulator
        avd_name = run_adb_cmd('emu avd name', serial=serial).split()[0]

        # find with avd_name
        for avd in avd_list:
            if avd.name == avd_name:
                avd.setRunning(serial)
                break

    return avd_list

def create_avd(name, sdkversion, tag, device, sdcard):
    assert tag in ['default', 'google_apis'], tag
    assert sdkversion.startswith('android-'), sdkversion

    package = "system-images;{};{};x86".format(sdkversion, tag)
    cmd = "create avd --force --name '{}' --package '{}' "\
          "--sdcard {} --device '{}'".format(
            name,
            package,
            sdcard,
            device
        )
    try:
        ret = run_avdmanager(cmd)
        print('create_avd success')
    except RunCmdError as e:
        print('create_avd failed')
        if 'Package path is not valid' in e.err:
            print(e.err)
            print('You would install the package {} with sdkmanager'.format(package))
            sdkmanager_path = os.path.join(os.path.split(package)[0], 'sdkmanager')
            print('Try {} {}'.format(sdkmanager_path, package))
        else:
            print(e.message)
