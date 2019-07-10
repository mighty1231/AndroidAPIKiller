from __future__ import print_function
import os
import subprocess
from config import getConfig
import functools

class RunCmdError(Exception):
    def __init__(self, out, err):
        msg = "----------------------------------------------------\n"
        msg += "Out: %s\nError: %s" % (out, err)
        super(RunCmdError, self).__init__(msg)

        self.out = out
        self.err = err

def _put_serial(serial):
    if serial is None:
        return ''
    elif type(serial) == int:
        return ' -s emulator-{} '.format(serial)
    elif type(serial) == str:
        return ' -s "{}" '.format(serial)
    else:
        raise ValueError("Serial must be integer or string: {}".format(serial))

def run_adb_cmd(orig_cmd, serial=None, timeout=None, realtime=False):
    # timeout should be string, for example '2s'
    # adb_binary = os.path.join(getConfig()['SDK_PATH'], 'platform-tools/adb')
    adb_binary = 'adb'
    cmd = '{} {} {}'.format(adb_binary, _put_serial(serial), orig_cmd)
    if timeout is not None:
        cmd = 'timeout {} {}'.format(timeout, cmd)

    if realtime:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True)

        for line in iter(proc.stdout.readline, b''):
            print(line.rstrip().decode('utf-8'))

        if proc.poll() > 0:
            if 'error: device offline' in err:
                run_cmd('{} kill-server'.format(adb_binary))
                return run_adb_cmd(orig_cmd, serial, timeout, realtime)
            print("Executing %s" % cmd)
            raise RunCmdError(out, err)

        return ''
    else:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        out, err = proc.communicate()
        if isinstance(out, bytes):
            out = out.decode('utf-8')
            err = err.decode('utf-8')

        res = out
        if not out:
            res = err

        if proc.returncode > 0:
            if 'error: device offline' in err:
                run_cmd('{} kill-server'.format(adb_binary))
                return run_adb_cmd(orig_cmd, serial, timeout, realtime)
            print("Executing %s" % cmd)
            raise RunCmdError(out, err)

        return res

def run_cmd(cmd, cwd=None, env=None):
    pipe = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, cwd=cwd, env=env)
    out, err = pipe.communicate()
    if isinstance(out, bytes):
        out = out.decode('utf-8')
        err = err.decode('utf-8')

    res = out
    if not out:
        res = err

    if pipe.returncode > 0:
        print("Executing %s" % cmd)
        raise RunCmdError(out, err)

    return res

class CacheDecorator:
    _size = 8
    def __init__(self, f):
        self.func = f
        self.recent_keys = []
        self.recent_values = []

    def __call__(self, *args):
        args_hashable = tuple(args)
        if args_hashable in self.recent_keys:
            # cache hit
            target = self.recent_keys.index(args_hashable)
            value = self.recent_values[target]

            # update 
            del self.recent_keys[target]
            del self.recent_values[target]

            self.recent_keys.insert(0, args_hashable)
            self.recent_values.insert(0, value)

            return value

        else:
            value = self.func(*args)

            self.recent_keys.insert(0, args_hashable)
            self.recent_values.insert(0, value)

            if len(self.recent_keys) >= CacheDecorator._size:
                del self.recent_keys[-1]
                del self.recent_values[-1]

            return value

def get_package_name(apk_path):
    res = run_cmd("{} dump badging {} | grep package | awk '{{print $2}}' | sed s/name=//g | sed s/\\'//g".format(
        getConfig()['AAPT_PATH'], apk_path
    ))
    return res.strip()

def save_snapshot(name, serial = None):
    return run_adb_cmd("emu avd snapshot save \"{}\"".format(name), serial=serial)

def load_snapshot(name, serial = None):
    return run_adb_cmd("emu avd snapshot load \"{}\"".format(name), serial=serial)

def list_snapshots(serial = None):
    res = run_adb_cmd("emu avd snapshot list", serial=serial)

    if res.startswith("There is no snapshot available"):
        return []
    else:
        lines = res.split("\n")
        ret = []
        for line in lines[2:]:
            if line.startswith("OK"):
                break
            tokens = line.split()
            name = ' '.join(tokens[1:-4])
            ret.append(name)

        return ret
