import os, sys
import re
import signal
import time

from androidkit import (
    get_package_name,
    get_uid,
    get_pids,
    run_adb_cmd,
    AdbOfflineError
)

STATE_CONSTRUCTED = 0
STATE_PREFIX_GIVEN = 1
states = [STATE_CONSTRUCTED, STATE_PREFIX_GIVEN]

class WrongConnectionState(Exception):
    pass

class Connections:
    def __init__(self, package_name, serial, output_folder):
        self.package_name = package_name
        self.serial = serial
        self.output_folder = output_folder
        self.started_processes = []
        self.connections = {}
        self._clean_up = False

    def _check_processes(self):
        # Check processes are alive or not
        # If the process is dead, pull related logs
        pids = get_pids(self.package_name,
                serial=self.serial)
        remaining_procs = []
        for running_pid, prefix in self.started_processes:
            if running_pid not in pids:
                print("Process Termination, pid", running_pid)
                out = run_adb_cmd('shell ls {}*'.format(prefix),
                        serial=self.serial)
                for line in out.split():
                    if line == '':
                        break
                    fname = line.rstrip()
                    print(" - pulling and removing {}".format(fname))
                    run_adb_cmd("pull {} {}".format(fname, self.output_folder),
                            serial=self.serial)
                    run_adb_cmd("shell rm {}".format(fname),
                            serial=self.serial)
            else:
                remaining_procs.append((running_pid, prefix))
        self.started_processes = remaining_procs


    def new_connection(self, socketfd, pid):
        if socketfd in self.connections:
            raise WrongConnectionState
        self.connections[socketfd] = (STATE_CONSTRUCTED, pid)
        self._check_processes()

    def give_prefix(self, socketfd, prefix):
        if socketfd not in self.connections:
            raise WrongConnectionState
        state, pid = self.connections[socketfd]

        if state != STATE_CONSTRUCTED:
            raise WrongConnectionState
        self.connections[socketfd] = (STATE_PREFIX_GIVEN, (pid, prefix))
        print('New Connection! pid', pid, 'prefix', prefix)

    def close_connection(self, socketfd):
        if socketfd not in self.connections:
            raise WrongConnectionState

        state, (pid, prefix) = self.connections[socketfd]
        if state != STATE_PREFIX_GIVEN:
            raise WrongConnectionState
        self.started_processes.append((pid, prefix))
        del self.connections[socketfd]

        print('Running processes: ', self.started_processes)
        print('Connection State: ', self.connections)

    def clean_up(self):
        if self._clean_up:
            return False
        self._clean_up = True
        print('Deleting connections...')
        for running_pid, prefix in self.started_processes:
            run_adb_cmd("shell kill {}".format(running_pid), serial=self.serial)
        self._check_processes()
        kill_mtserver(self.serial)
        return True

connections = None
log = []
def _stdout_callback(line):
    global log
    log.append(line)
    if line.startswith('Server with'):
        return
    if 'Connection attempt!' in line:
        return

    global connections

    match = re.match(r'\[Socket ([0-9]+)\] Connection with pid ([0-9]+) from Start\(\)',
        line)
    if match is not None:
        socketfd, pid = match.groups()
        connections.new_connection(int(socketfd), int(pid))
        return

    match = re.match(r'\[Socket ([0-9]+)\] Selected prefix: (.*)', line)
    if match is not None:
        socketfd, prefix = match.groups()
        connections.give_prefix(int(socketfd), prefix)
        return

    match = re.match(r'\[Socket ([0-9]+)\] Connection closed', line)
    if match is not None:
        socketfd = match.group(1)
        connections.close_connection(int(socketfd))
        return

    print("Warning: Unexpected line", line)

def kill_mtserver(serial = None):
    pids = get_pids('/data/local/tmp/mtserver', serial=serial)
    for pid in pids:
        run_adb_cmd('shell kill {}'.format(pid), serial=serial)

def sigterm_handler(signal, frame):
    print('MTSERVER SIGTERM received')
    global connections, log
    if connections is not None and connections.clean_up():
        print('----- Start of the log -----')
        for l in log:
            print(l)
        print('----- END of the log -----')
    sys.exit(0)

def run_mtserver(package_name, output_folder, serial=None):
    if not os.path.isdir(output_folder):
        os.makedirs(output_folder)
    signal.signal(signal.SIGTERM, sigterm_handler)

    global connections, log
    connections = Connections(package_name, serial, output_folder)
    uid = get_uid(package_name, serial=serial)

    while True:
        kill_mtserver(serial)
        try:
            print('Running mtserver...')
            out = run_adb_cmd('shell /data/local/tmp/mtserver server {} {}'  \
                    .format(uid, package_name),
                stdout_callback = _stdout_callback,
                serial=serial,
                retry_cnt=-1)
            break

        except WrongConnectionState:
            print('Wrong state on connection! Check follow log...')
            for line in log:
                print(line)

            kill_mtserver(serial)
            break

        except AdbOfflineError as e:
            # retry due to offline error
            print("run_mtserver: retry due to offline error...")

            run_adb_cmd('kill-server', retry_cnt = -1)
            run_adb_cmd('start-server', retry_cnt = -1)

            time.sleep(1)
            continue

        except Exception:
            if connections.clean_up():
                print('----- Start of the log -----')
                for l in log:
                    print(l)
                print('----- END of the log -----')
            raise


if __name__ == "__main__":
    run_mtserver('com.hoi.simpleapp22', 'temp')
