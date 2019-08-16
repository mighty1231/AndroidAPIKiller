import os, sys
import re
import time

from androidkit import (
    get_package_name,
    get_pids,
    run_adb_cmd,
    AdbOfflineError,
    unset_multiprocessing_mode
)

STATE_START_CONSTRUCTED = 0
STATE_START_PREFIX_GIVEN = 1
STATE_STOP_CONSTRUCTED = 2

class WrongConnectionState(Exception):
    pass

class Connections:
    def __init__(self, package_name, serial, output_folder):
        if not os.path.isdir(output_folder):
            os.makedirs(output_folder)

        self.package_name = package_name
        self.serial = serial
        self.output_folder = output_folder
        self.started_processes = []
        self.connections = {}
        self._clean_up = False
        self.log = []

    def _check_processes(self):
        # Check processes are alive or not
        # If the process is dead, pull related logs
        pids = get_pids(self.package_name,
                serial=self.serial)
        remaining_procs = []
        for running_pid, prefix in self.started_processes:
            if running_pid not in pids:
                print("Process with pid {} is terminated".format(running_pid))
                out = run_adb_cmd('shell ls {}*'.format(prefix),
                        serial=self.serial)
                if "No such file or directory" not in out:
                    for line in out.split():
                        if line == '':
                            break
                        fname = line.rstrip()
                        print(" - pulling and removing {}".format(fname))
                        run_adb_cmd("pull {} {}".format(fname, self.output_folder),
                                serial=self.serial)
                        run_adb_cmd("shell rm {}".format(fname),
                                serial=self.serial)
                    continue
            remaining_procs.append((running_pid, prefix))
        self.started_processes = remaining_procs

    def new_start_connection(self, socketfd, pid):
        if socketfd in self.connections:
            raise WrongConnectionState
        self.connections[socketfd] = (STATE_START_CONSTRUCTED, pid)
        self._check_processes()

    def give_prefix(self, socketfd, prefix):
        if socketfd not in self.connections:
            raise WrongConnectionState
        state, pid = self.connections[socketfd]

        if state != STATE_START_CONSTRUCTED:
            raise WrongConnectionState
        self.connections[socketfd] = (STATE_START_PREFIX_GIVEN, (pid, prefix))
        print('New Connection! pid', pid, 'prefix', prefix)

    def new_stop_connection(self, socketfd, pid):
        # This part could be called with gentle termination of the app (not SIGKILL)
        if socketfd in self.connections:
            raise WrongConnectionState
        self.connections[socketfd] = (STATE_STOP_CONSTRUCTED, pid)

    def release_file(self, socketfd, fname):
        # This part could be called with gentle termination of the app (not SIGKILL)
        if socketfd not in self.connections:
            raise WrongConnectionState
        state, pid = self.connections[socketfd]

        if state != STATE_STOP_CONSTRUCTED:
            raise WrongConnectionState

        print("Releasing file {}".format(fname))
        run_adb_cmd("pull {} {}".format(fname, self.output_folder),
                serial=self.serial)
        run_adb_cmd("shell rm {}".format(fname),
                serial=self.serial)

    def close_connection(self, socketfd):
        if socketfd not in self.connections:
            raise WrongConnectionState

        state, data = self.connections[socketfd]
        if state == STATE_START_PREFIX_GIVEN:
            pid, prefix = data
            self.started_processes.append((pid, prefix))
            del self.connections[socketfd]
        elif state == STATE_STOP_CONSTRUCTED:
            # This part could be called with gentle termination of the app (not SIGKILL)
            # Files from process with target pid are already pulled.
            targetpid = data
            self.started_processes = [(pid, prefix) for pid, prefix in self.started_processes if pid != targetpid]
            del self.connections[socketfd]
        else:
            raise WrongConnectionState

    def clean_up(self):
        if self._clean_up:
            return False
        unset_multiprocessing_mode()
        self._clean_up = True
        print('Deleting connections...')
        for running_pid, prefix in self.started_processes:
            run_adb_cmd("shell kill {}".format(running_pid), serial=self.serial)
        self._check_processes()

        if self.started_processes != []:
            print("Immediately killed processes without any traced data")
            for running_pid, prefix in self.started_processes:
                print(" - pid {} with prefix {}".format(running_pid, prefix))
        kill_mtserver(self.serial)
        print('----- Start of the log -----')
        for l in self.log:
            print(l)
        print('----- END of the log -----')
        return True

    def stdout_callback(self, line):
        self.log.append(line)
        if line.startswith('Server with uid'):
            print("mtserver: server is running")
            return
        if 'Connection attempt!' in line:
            print("mtserver: connection attempt!")
            return

        match = re.match(r'\[Socket ([0-9]+)\] Connection with pid ([0-9]+) from Start\(\)',
            line)
        if match is not None:
            socketfd, pid = match.groups()
            self.new_start_connection(int(socketfd), int(pid))
            return

        match = re.match(r'\[Socket ([0-9]+)\] Selected prefix: (.*)', line)
        if match is not None:
            socketfd, prefix = match.groups()
            self.give_prefix(int(socketfd), prefix)
            return

        match = re.match(r'\[Socket ([0-9]+)\] Connection with pid ([0-9]+) from Stop\(\)',
            line)
        if match is not None:
            socketfd, pid = match.groups()
            self.new_stop_connection(int(socketfd), int(pid))
            return

        match = re.match(r'\[Socket ([0-9]+)\] File released: (.*)',
            line)
        if match is not None:
            socketfd, fname = match.groups()
            self.release_file(int(socketfd), fname)
            return

        match = re.match(r'\[Socket ([0-9]+)\] Connection closed', line)
        if match is not None:
            socketfd = match.group(1)
            self.close_connection(int(socketfd))
            return

        print("Warning: Unexpected line", line)

def kill_mtserver(serial = None):
    pids = get_pids('/data/local/tmp/mtserver', serial=serial)
    for pid in pids:
        run_adb_cmd('shell kill {}'.format(pid), serial=serial)

def run_mtserver(package_name, output_folder, serial=None):
    connections = Connections(package_name, serial, output_folder)

    while True:
        kill_mtserver(serial)
        try:
            print('Running mtserver...')
            out = run_adb_cmd('shell /data/local/tmp/mtserver server {}'  \
                    .format(package_name),
                stdout_callback = connections.stdout_callback,
                serial=serial)
            break
        except WrongConnectionState:
            print('Wrong state on connection! Check follow log...')
            for line in connections.log:
                print(line)

            kill_mtserver(serial)
            break
        except KeyboardInterrupt:
            connections.clean_up()
            raise
        except Exception:
            connections.clean_up()
            raise

    connections.clean_up()

if __name__ == "__main__":
    run_mtserver('com.hoi.simpleapp22', 'temp')
