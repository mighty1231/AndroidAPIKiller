from __future__ import print_function
import os, sys
import subprocess
from config import getConfig
import functools
import datetime, time
import multiprocessing as mp
import fcntl

_adb_mp_delay = False # multiprocessing delay

def _set_multiprocessing():
    global _adb_mp_delay
    _adb_mp_delay = True

class AdbLongProcessBreak(Exception):
    pass

class AdbOfflineErrorBreak(Exception):
    def __init__(self, msg):
        super(AdbOfflineErrorBreak, self).__init__(
            'adb offline error - try '\
            'adb kill-server && adb start-server\n' + msg
        )

class AdbMultiprocessingDelay:
    _last_called_time = None
    _lock = mp.Lock()

    def __init__(self, delay_in_seconds = 1):
        self.delay = delay_in_seconds
        self.status = None

    def __enter__(self):
        AdbMultiprocessingDelay._lock.acquire()
        if AdbMultiprocessingDelay._last_called_time is not None:
            timediff = (datetime.datetime.now() - AdbMultiprocessingDelay._last_called_time).total_seconds()
            if timediff <= self.delay:
                time.sleep(self.delay - timediff)
        return self

    def __exit__(self, etype, value, traceback):
        AdbMultiprocessingDelay._last_called_time = datetime.datetime.now()
        AdbMultiprocessingDelay._lock.release()
        if etype == AdbOfflineErrorBreak:
            self.status = 'offline'
            return True
        elif etype == AdbLongProcessBreak:
            self.status = 'longproc'
            return True

class RunCmdError(Exception):
    def __init__(self, out, err, cmd=''):
        msg = "----------------------------------------------------\n"
        if cmd:
            msg += "Command: {}\n".format(cmd)
        msg += "Out: %s\nError: %s" % (out, err)
        super(RunCmdError, self).__init__(msg)

        self.out = out
        self.err = err
        self.cmd = cmd


class CacheDecorator:
    '''
    Cache some results for function call with some inputs.
    Useful for functions with
       - high load
       - few values for inputs
       - returned values are same from same inputs, whenever be called
    '''
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

def _put_serial(serial):

    if serial is None:
        return ''
    elif type(serial) == int:
        return ' -s emulator-{} '.format(serial)
    elif type(serial) == str:
        return ' -s "{}" '.format(serial)
    else:
        raise ValueError("Serial must be integer or string: {}".format(serial))

def run_adb_cmd(orig_cmd, serial=None, timeout=None):
    # timeout should be string, for example '2s'
    # adb_binary = os.path.join(getConfig()['SDK_PATH'], 'platform-tools/adb')
    adb_binary = 'adb'
    cmd = '{} {} {}'.format(adb_binary, _put_serial(serial), orig_cmd)
    if timeout is not None:
        cmd = 'timeout {} {}'.format(timeout, cmd)

    if _adb_mp_delay:
        # multiprocessing
        stdout_r_fd, stdout_w_fd = os.pipe()
        stderr_r_fd, stderr_w_fd = os.pipe()
        with AdbMultiprocessingDelay() as mpdelay:
            proc = subprocess.Popen(
                cmd, stdout=stdout_w_fd, stderr=stderr_w_fd, shell=True)
            os.close(stdout_w_fd)
            os.close(stderr_w_fd)
            time.sleep(1)
            pollval = proc.poll()
            if pollval is None:
                # long process
                # stdout and stderr would be long
                # Long process -> release the lock and wait for process
                raise AdbLongProcessBreak
            else:
                # process is terminated
                # pollval is return value
                # handle error: device offline
                stdout_f = os.fdopen(stdout_r_fd, 'rb')
                out = stdout_f.read().decode('utf-8')
                stdout_f.close()
                stderr_f = os.fdopen(stderr_r_fd, 'rb')
                err = stderr_f.read().decode('utf-8')
                stderr_f.close()

                if pollval > 0:
                    if 'error: device offline' in err:
                        print('Device offline!')
                        subprocess.run([adb_binary, 'kill-server'])
                        subprocess.run([adb_binary, 'start-server'])
                        time.sleep(0.2)
                        raise AdbOfflineErrorBreak(out)
                    raise RunCmdError(out, err, cmd=cmd)
                return out

        if mpdelay.status == 'longproc':
            stdout_f = os.fdopen(stdout_r_fd, 'rt')
            fcntl.fcntl(stdout_f, fcntl.F_SETFL, os.O_NONBLOCK)
            stderr_f = os.fdopen(stderr_r_fd, 'rt')
            fcntl.fcntl(stderr_f, fcntl.F_SETFL, os.O_NONBLOCK)
            out = ''
            err = ''
            while pollval is None:
                out += stdout_f.read(64)
                err += stderr_f.read(64)

                # flush
                if '\n' in out:
                    idx = out.rindex('\n')
                    if idx > 0:
                        for o in out[:idx].split('\n'):
                            print('O: ' + o.rstrip())
                    out = out[idx+1:]
                if '\n' in err:
                    idx = err.rindex('\n')
                    if idx > 0:
                        for o in err[:idx].split('\n'):
                            print('E: ' + o.rstrip(), file=sys.stderr)
                    err = err[idx+1:]
                pollval = proc.poll()
            out += stdout_f.read()
            err += stderr_f.read()
            if out:
                for o in out.split('\n'):
                    print('O: ' + o.rstrip())
            if err:
                for e in err.split('\n'):
                    print('E: ' + e.rstrip(), file=sys.stderr)

            stdout_f.close()
            stderr_f.close()
            if pollval > 0:
                raise RunCmdError('', '', cmd=cmd)
            return ''
        elif mpdelay.status == 'offline':
            return run_adb_cmd(orig_cmd, serial=serial, timeout=timeout)
        else:
            raise RuntimeError('AdbMultiprocessingDelay.status =', mpdelay.status)
    else:
        # run as single process
        stdout_r_fd, stdout_w_fd = os.pipe()
        stderr_r_fd, stderr_w_fd = os.pipe()
        proc = subprocess.Popen(
            cmd, stdout=stdout_w_fd, stderr=stderr_w_fd, shell=True)
        os.close(stdout_w_fd)
        os.close(stderr_w_fd)
        time.sleep(1)
        pollval = proc.poll()
        if pollval is None:
            # long process
            # stdout and stderr would be long
            stdout_f = os.fdopen(stdout_r_fd, 'rt')
            fcntl.fcntl(stdout_f, fcntl.F_SETFL, os.O_NONBLOCK)
            stderr_f = os.fdopen(stderr_r_fd, 'rt')
            fcntl.fcntl(stderr_f, fcntl.F_SETFL, os.O_NONBLOCK)
            out = ''
            err = ''
            while pollval is None:
                out += stdout_f.read(64)
                err += stderr_f.read(64)

                # flush
                if '\n' in out:
                    idx = out.rindex('\n')
                    if idx > 0:
                        for o in out[:idx].split('\n'):
                            print('O: ' + o.rstrip())
                    out = out[idx+1:]
                if '\n' in err:
                    idx = err.rindex('\n')
                    if idx > 0:
                        for o in err[:idx].split('\n'):
                            print('E: ' + o.rstrip(), file=sys.stderr)
                    err = err[idx+1:]
                pollval = proc.poll()
            out += stdout_f.read()
            err += stderr_f.read()
            if out:
                for o in out.split('\n'):
                    print('O: ' + o.rstrip())
            if err:
                for e in err.split('\n'):
                    print('E: ' + e.rstrip(), file=sys.stderr)

            stdout_f.close()
            stderr_f.close()
            if pollval > 0:
                raise RunCmdError('', '', cmd=cmd)
            return ''
        else:
            # process is terminated
            # pollval is return value
            # handle error: device offline
            stdout_f = os.fdopen(stdout_r_fd, 'rb')
            out = stdout_f.read().decode('utf-8')
            stdout_f.close()
            stderr_f = os.fdopen(stderr_r_fd, 'rb')
            err = stderr_f.read().decode('utf-8')
            stderr_f.close()

            if pollval > 0:
                if 'error: device offline' in err:
                    print('Device offline!')
                    subprocess.run([adb_binary, 'kill-server'])
                    subprocess.run([adb_binary, 'start-server'])
                    time.sleep(0.2)
                    return run_adb_cmd(orig_cmd, serial=serial, timeout=timeout)
                raise RunCmdError(out, err, cmd=cmd)
            return out

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
        raise RunCmdError(out, err, cmd=cmd)

    return res


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
