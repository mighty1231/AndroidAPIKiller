from __future__ import print_function
import os
import subprocess
from config import getConfig
import functools
import multiprocessing as mp
import datetime, time

class RunCmdError(Exception):
    def __init__(self, out, err):
        msg = "----------------------------------------------------\n"
        msg += "Out: %s\nError: %s" % (out, err)
        super(RunCmdError, self).__init__(msg)

        self.out = out
        self.err = err

class AdbOfflineError(Exception):
    def __init__(self):
        super(AdbOfflineError, self).__init__(
            'adb offline error - try '\
            'adb kill-server && adb start-server'
        )

def _put_serial(serial):
    if serial is None:
        return ''
    elif type(serial) == int:
        return ' -s emulator-{} '.format(serial)
    elif type(serial) == str:
        return ' -s "{}" '.format(serial)
    else:
        raise ValueError("Serial must be integer or string: {}".format(serial))

@MultiprocessingDelayDecorator
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

        offline_error = False
        output = []
        for line in iter(proc.stdout.readline, b''):
            line = line.rstrip().decode('utf-8')
            output.append(line)
            if 'error: device offline' in line:
                offline_error = True

        if proc.poll() > 0:
            if offline_error:
                raise AdbOfflineError()
            else:
                print('run_adb_cmd(): error with command', cmd)
                print('run_adb_cmd(): output:')
                print(output)
            raise RunCmdError('', output)

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
                raise AdbOfflineError()
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

class MultiprocessingDelayDecorator: # assume that it only used on run_adb_cmd (offline error things...)
    def __init__(self, f):
        self.func = f
        self.lock = mp.Lock()
        self.last_called_time = None

    def __call__(self, *args, **kwargs):
        if hasattr(self.func, '_mp'):
            self.lock.acquire()
            if self.last_called_time is not None and \
                    (datetime.datetime.now() - self.last_called_time).total_seconds() <= 1:
                time.sleep(1)
            try:
                return self.func(*args, **kwargs)
            except AdbOfflineError as e:
                run_adb_cmd('kill-server')
                run_adb_cmd('start-server')
                time.sleep(1)

                # try again!
                try:
                    return self.func(*args, **kwargs)
                except Exception as e2:
                    self.last_called_time = datetime.datetime.now()
                    self.lock.release()
                    raise e
            except Exception as e:
                self.last_called_time = datetime.datetime.now()
                self.lock.release()
                raise
        else:
            return self.func(*args, **kwargs)

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
