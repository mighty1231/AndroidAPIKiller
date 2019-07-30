import os, sys
import subprocess
import datetime, time
import multiprocessing as mp
import fcntl
import re
from .config import getConfig

_adb_mp_delay = False # multiprocessing delay

def set_multiprocessing_mode():
    global _adb_mp_delay
    _adb_mp_delay = True

class AdbLongProcessBreak(Exception):
    pass

class AdbOfflineErrorBreak(Exception):
    def __init__(self, out, err):
        super(AdbOfflineErrorBreak, self).__init__(
            'adb offline error - try '\
            'adb kill-server && adb start-server\n'
        )
        self.out = out
        self.err = err

class AdbMultiprocessingDelay:
    _last_called_time = None
    _lock = mp.Lock()

    def __init__(self, delay_in_seconds = 1):
        self.delay = delay_in_seconds
        self.status = None
        self.excval = None

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
        self.excval = value
        if etype == AdbOfflineErrorBreak:
            self.status = 'offline'
            return True
        elif etype == AdbLongProcessBreak:
            self.status = 'longproc'
            return True

class RunCmdError(Exception):
    def __init__(self, cmd, out, err):
        super(RunCmdError, self).__init__(err)

        self.cmd = cmd
        self.out = out
        self.err = err
        self._message = None

    @property
    def message(self):
        if self._message is not None:
            return self._message
        msg = "--- RunCmdError.command [{}] ---\n".format(self.cmd)
        if self.out is not None:
            msg += "--- RunCmdError.out ---\n"
            msg += self.out
        if self.err is not None:
            msg += "--- RunCmdError.err ---\n"
            msg += self.err
        msg += "-----------------------\n"
        self._message = msg
        return msg

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

def run_adb_cmd(orig_cmd, serial=None, timeout=None, restart_cnt=0,
        stdout_callback = None, stderr_callback = None):
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
            time.sleep(0.8)
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
                    if 'error: device offline' in err or ( \
                            'error: device' in err and 'not found' in err):
                        print("Restarting server...", file=sys.stderr)
                        subprocess.run([adb_binary, 'kill-server'])
                        subprocess.run([adb_binary, 'start-server'])
                        time.sleep(0.2)
                        raise AdbOfflineErrorBreak(out, err)
                    raise RunCmdError(cmd, out, err)
                return out

        if mpdelay.status == 'longproc':
            stdout_f = os.fdopen(stdout_r_fd, 'rt')
            fcntl.fcntl(stdout_f, fcntl.F_SETFL, os.O_NONBLOCK)
            stderr_f = os.fdopen(stderr_r_fd, 'rt')
            fcntl.fcntl(stderr_f, fcntl.F_SETFL, os.O_NONBLOCK)
            out_is_long = False
            total_out = ''
            out = ''
            err = ''
            while pollval is None:
                cur_out = stdout_f.read(64)
                if not out_is_long:
                    total_out += cur_out
                    if len(total_out) >= 10000:
                        out_is_long = True
                out += cur_out
                err += stderr_f.read(64)

                # flush
                if '\n' in out:
                    idx = out.rindex('\n')
                    if idx > 0:
                        for o in out[:idx].split('\n'):
                            if stdout_callback is None:
                                print('O: ' + o.rstrip())
                            else:
                                stdout_callback(o.rstrip())
                    out = out[idx+1:]
                if '\n' in err:
                    idx = err.rindex('\n')
                    if idx > 0:
                        for o in err[:idx].split('\n'):
                            if stderr_callback is None:
                                print('E: ' + o.rstrip(), file=sys.stderr)
                            else:
                                stderr_callback(o.rstrip())
                    err = err[idx+1:]
                pollval = proc.poll()
            cur_out = stdout_f.read()
            if not out_is_long:
                total_out += cur_out
            out += cur_out
            err += stderr_f.read()
            if out:
                for o in out.split('\n'):
                    if stdout_callback is None:
                        print('O: ' + o.rstrip())
                    else:
                        stdout_callback(o.rstrip())
            if err:
                for e in err.split('\n'):
                    if stderr_callback is None:
                        print('E: ' + e.rstrip(), file=sys.stderr)
                    else:
                        stderr_callback(o.rstrip())

            stdout_f.close()
            stderr_f.close()
            if pollval > 0:
                raise RunCmdError(cmd, total_out, None)
            return total_out
        elif mpdelay.status == 'offline':
            if restart_cnt < 2:
                print('E: device offline error', file=sys.stderr)
                return run_adb_cmd(orig_cmd, serial=serial, timeout=timeout, restart_cnt=restart_cnt+1)
            else:
                print('E: device offline error more than 2 times', file=sys.stderr)
                raise mpdelay.excval
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
        time.sleep(0.8)
        pollval = proc.poll()
        if pollval is None:
            # long process
            # stdout and stderr would be long
            stdout_f = os.fdopen(stdout_r_fd, 'rt')
            fcntl.fcntl(stdout_f, fcntl.F_SETFL, os.O_NONBLOCK)
            stderr_f = os.fdopen(stderr_r_fd, 'rt')
            fcntl.fcntl(stderr_f, fcntl.F_SETFL, os.O_NONBLOCK)
            out_is_long = False
            total_out = ''
            out = ''
            err = ''
            while pollval is None:
                cur_out = stdout_f.read(64)
                if not out_is_long:
                    total_out += cur_out
                    if len(total_out) >= 10000:
                        out_is_long = True
                out += cur_out
                err += stderr_f.read(64)

                # flush
                if '\n' in out:
                    idx = out.rindex('\n')
                    if idx > 0:
                        for o in out[:idx].split('\n'):
                            if stdout_callback is None:
                                print('O: ' + o.rstrip())
                            else:
                                stdout_callback(o.rstrip())
                    out = out[idx+1:]
                if '\n' in err:
                    idx = err.rindex('\n')
                    if idx > 0:
                        for o in err[:idx].split('\n'):
                            if stderr_callback is None:
                                print('E: ' + o.rstrip(), file=sys.stderr)
                            else:
                                stderr_callback(o.rstrip())
                    err = err[idx+1:]
                pollval = proc.poll()
            cur_out = stdout_f.read()
            if not out_is_long:
                total_out += cur_out
            out += cur_out
            err += stderr_f.read()
            if out:
                for o in out.split('\n'):
                    if stdout_callback is None:
                        print('O: ' + o.rstrip())
                    else:
                        stdout_callback(o.rstrip())
            if err:
                for o in err[:idx].split('\n'):
                    if stderr_callback is None:
                        print('E: ' + o.rstrip(), file=sys.stderr)
                    else:
                        stderr_callback(o.rstrip())

            stdout_f.close()
            stderr_f.close()
            if pollval > 0:
                raise RunCmdError(cmd, total_out, None)
            return total_out
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
                    subprocess.run([adb_binary, 'kill-server'])
                    subprocess.run([adb_binary, 'start-server'])
                    time.sleep(0.2)
                    if restart_cnt < 2:
                        print('E: device offline error', file=sys.stderr)
                        return run_adb_cmd(orig_cmd, serial=serial, timeout=timeout, restart_cnt=restart_cnt+1)
                    else:
                        print('E: device offline error more than 2 times', file=sys.stderr)
                        raise RunCmdError(cmd, out, err)
                raise RunCmdError(cmd, out, err)
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
        raise RunCmdError(cmd, out, err)

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

def extract_apk(package_name, ofname, serial = None):
    cmd = 'shell pm path {}'.format(package_name)
    out = run_adb_cmd(cmd, serial=serial)
    lines = out.split()
    if len(lines) == 0:
        print('Package {} is not found'.format(package_name))
        raise RuntimeError
    if len(lines) >= 2:
        print('Package {} seems to be sliced apk.'.format(package_name),
              'Is the app debugging purpose?')
        for i, line in enumerate(lines):
            print('out[{}] = {}'.format(i, line))
        print('Current version does not support for sliced apks')
        raise RuntimeError
    if not lines[0].startswith('package:'):
        print('Not expected output for cmd: {}'.format(cmd))
        for i, line in enumerate(lines):
            print('out[{}] = {}'.format(i, line))
        raise RuntimeError

    apk_path = lines[0][8:]
    run_adb_cmd('pull {} {}'.format(apk_path, ofname), serial=serial)
    print('Package {} is pulled into {}'.format(package_name, ofname))

def get_activity_stack(serial = None):
    # get_activity_stack returns list of list of activities
    # adb shell dumpsys activity activities | grep -i run
    #  ->
    #    Running activities (most recent first):
    #        Run #1: ActivityRecord{de9e636 u0 com.android.systemui/.recents.RecentsActivity t68} // <- foreground activity
    #        Run #0: ActivityRecord{508c61b u0 com.android.launcher3/.Launcher t4}
    #    Running activities (most recent first):
    #        Run #4: ActivityRecord{4bf664e u0 org.y20k.transistor/.MainActivity t93}
    #        Run #3: ActivityRecord{ab339e1 u0 com.android.dialer/.settings.DialerSettingsActivity t90}
    #        Run #2: ActivityRecord{31283e2 u0 com.android.dialer/.DialtactsActivity t90}
    #        Run #1: ActivityRecord{15fdbee u0 com.android.chrome/org.chromium.chrome.browser.ChromeTabbedActivity t94}
    #        Run #0: ActivityRecord{b69107c u0 com.google.android.youtube/com.google.android.apps.youtube.app.WatchWhileActivity t91}

    # In this situation, get_activity_stack() should return
    #  [['com.android.systemui/.recents.RecentsActivity',
    #    'com.android.launcher3/.Launcher'],
    #   ['org.y20k.transistor/.MainActivity',
    #    'com.android.dialer/.settings.DialerSettingsActivity',
    #    'com.android.dialer/.DialtactsActivity',
    #    'com.android.chrome/org.chromium.chrome.browser.ChromeTabbedActivity',
    #    'com.google.android.youtube/com.google.android.apps.youtube.app.WatchWhileActivity']]

    dumped = run_adb_cmd('shell dumpsys activity activities')
    stack_pattern = re.compile(r'\n    Running activities \(most recent first\):')

    # https://github.com/aosp-mirror/platform_frameworks_base/blob/master/services/core/java/com/android/server/am/ActivityRecord.java#L3007
    activity_pattern = re.compile(
        r'\n        Run #([0-9]*): ActivityRecord\{[^ ]* [^ ]* ([^ ]*) [^ ]*( f)?\}'
    )
    divisions = list(map(lambda t: t.end(), stack_pattern.finditer(dumped)))

    stacks = []
    N = len(divisions)
    for i in range(N):
        if i == N - 1:
            activities = activity_pattern.findall(dumped, divisions[i])
        else:
            activities = activity_pattern.findall(dumped, divisions[i],
                                                  divisions[i + 1])
        stacks.append(activities)  # [('1', '(Activity#1)'), ('0', '(Activity#0)')]

    # check validity
    ret = []
    for stack in stacks:
        length = len(stack)
        cur_stack = []
        for i, (idx, act, _finished) in enumerate(stack):
            if str(length - i - 1) != idx:
                ERROR_LOG_FILE = 'err.txt'
                with open(ERROR_LOG_FILE, 'wt') as f:
                    f.write(dumped)
                    f.write('\n')
                    f.write('{}'.format(stack))

                raise RuntimeError(
                    "data seems not valid, dumped in file:{}".format(
                        ERROR_LOG_FILE))

            cur_stack.append(act)

        ret.append(cur_stack)

    return ret

def get_uid(package_name, serial=None):
    res = run_adb_cmd('shell dumpsys package {} | grep userId'.format(
                package_name), serial = serial)
    uid = int(re.findall(r"userId=([0-9]+)", res)[0])
    return uid

def get_pids(package_name, serial=None):
    try:
        res = run_adb_cmd('shell ps'.format(package_name),
                serial=serial)
    except RunCmdError as e:
        # maybe the app is not running
        return []

    pids = []
    lines = res.split('\n')
    for line in lines:
        line = line.rstrip()
        if line == '':
            break
        tokens = line.split()
        if tokens[-1] == package_name:
            pids.append(int(tokens[1]))

    return pids
