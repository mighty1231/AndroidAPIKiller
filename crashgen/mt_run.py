import os, sys
import re

from androidkit import (
    get_package_name,
    get_pids,
    run_adb_cmd,
    AdbOfflineError,
    get_multiprocessing_mode,
    set_multiprocessing_mode,
    unset_multiprocessing_mode,
    RunCmdError
)

STATE_CONSTRUCTED = 0
STATE_RUNNING = 1

TAG = '[MTSERVER]'
class WrongConnectionState(Exception):
    pass

class Connections:
    def __init__(self, package_name, serial, output_folder):
        if not os.path.isdir(output_folder):
            os.makedirs(output_folder)

        self.package_name = package_name
        self.serial = serial
        self.output_folder = output_folder
        self.connections = {}
        self._clean_up = False
        self.log = []
        self.errlog = []

    def new_connection(self, socketfd, pid):
        if socketfd in self.connections:
            raise WrongConnectionState
        self.connections[socketfd] = (STATE_CONSTRUCTED, pid)

    def give_prefix(self, socketfd, prefix):
        if socketfd not in self.connections:
            raise WrongConnectionState
        state, pid = self.connections[socketfd]

        if state != STATE_CONSTRUCTED:
            raise WrongConnectionState
        self.connections[socketfd] = (STATE_RUNNING, (pid, prefix))
        print('{} new connection, pid {} prefix {}'.format(TAG, pid, prefix))

    def release_file(self, socketfd, fname):
        # This part could be called with gentle termination of the app (not SIGKILL)
        if socketfd not in self.connections:
            raise WrongConnectionState
        state, data = self.connections[socketfd]

        if state != STATE_RUNNING:
            raise WrongConnectionState

        print("{} release file {}".format(TAG, fname))
        run_adb_cmd("pull {} {}".format(fname, self.output_folder),
                serial=self.serial)
        run_adb_cmd("shell rm {}".format(fname),
                serial=self.serial)

    def close_connection(self, socketfd, prefix):
        if socketfd not in self.connections:
            raise WrongConnectionState

        state, data = self.connections[socketfd]
        if state == STATE_RUNNING:
            pid, prefix_ = data
            assert prefix == prefix_, (prefix, prefix_)

            prefix_local = os.path.join(self.output_folder, os.path.split(prefix)[1])

            # clean up given prefix
            print("{} close connection on {}".format(TAG, prefix_local))
            out = run_adb_cmd('shell ls {}*'.format(prefix),
                    serial=self.serial)
            if "No such file or directory" not in out:
                pulled_files = []
                for line in out.split():
                    if line == '':
                        break
                    fname = line.rstrip()
                    print("{} - pull and remove {}".format(TAG, fname))
                    try:
                        run_adb_cmd("pull {} {}".format(fname, self.output_folder),
                                serial=self.serial)
                        pulled_files.append(
                                os.path.join(self.output_folder,
                                os.path.split(fname)[1]))
                    except RunCmdError as e:
                        # @TODO How could it be happen?
                        print("{} - failed to pull and remove {}".format(TAG, fname), file=sys.stderr)
                        for file in pulled_files:
                            os.remove(file)
                        prefix_local = ""
                        break
                    run_adb_cmd("shell rm {}".format(fname),
                            serial=self.serial)
            del self.connections[socketfd]
            return prefix_local
        else:
            raise WrongConnectionState

    def clean_up(self, reason):
        if self._clean_up:
            return False
        previous_mp_mode = get_multiprocessing_mode()
        unset_multiprocessing_mode()
        self._clean_up = True

        print('{} cleaning connections in [{}]'.format(TAG, reason))
        kill_mtserver(self.serial)
        while self.connections:
            socketfd, (state, data) = next(iter(self.connections.items()))

            if state == STATE_CONSTRUCTED:
                continue

            assert state == STATE_RUNNING
            pid, prefix = data
            self.close_connection(socketfd, prefix)

        print('{} Start of the stdout log in [{}]'.format(TAG, reason))
        for l in self.log:
            print('{} {}'.format(TAG, l))
        print('{} Start of the stderr log in [{}]'.format(TAG, reason))
        for l in self.errlog:
            print('{} {}'.format(TAG, l))
        print('{} END of the log in [{}]'.format(TAG, reason))

        if previous_mp_mode:
            set_multiprocessing_mode()
        return True

    def stdout_callback(self, line):
        self.log.append(line)
        if line.startswith('Server with uid'):
            print("{} mtserver started".format(TAG))
            return
        if 'Connection attempt!' in line:
            print("{} Connection attempt!".format(TAG))
            return

        match = re.match(r'\[Socket ([0-9]+)\] Connection with pid ([0-9]+) from Start\(\)',
            line)
        if match is not None:
            socketfd, pid = match.groups()
            self.new_connection(int(socketfd), int(pid))
            return

        match = re.match(r'\[Socket ([0-9]+)\] Selected prefix: (.*)', line)
        if match is not None:
            socketfd, prefix = match.groups()
            self.give_prefix(int(socketfd), prefix)
            return

        match = re.match(r'\[Socket ([0-9]+)\] File released: (.*)',
            line)
        if match is not None:
            socketfd, fname = match.groups()
            self.release_file(int(socketfd), fname)
            return

        match = re.match(r'\[Socket ([0-9]+)\] Connection closed, prefix=(.*)', line)
        if match is not None:
            socketfd, prefix = match.groups()
            self.close_connection(int(socketfd), prefix)
            return

        if line.startswith("Server failed to fetch uid information") \
                or line.startswith("Killing process, uid"):
            return

        print("{} Warning, Unexpected line {}".format(TAG, line))

    def stderr_callback(self, line):
        self.log.append(line)
        self.errlog.append(line)

def kill_mtserver(serial = None):
    pids = get_pids('/data/local/tmp/mtserver', serial=serial)
    for pid in pids:
        run_adb_cmd('shell kill {}'.format(pid), serial=serial)

def run_mtserver(package_name, output_folder, serial=None):
    connections = Connections(package_name, serial, output_folder)

    kill_mtserver(serial)
    try:
        print('{} Start mtserver...'.format(TAG))
        out = run_adb_cmd('shell /data/local/tmp/mtserver server {}'  \
                .format(package_name),
            stdout_callback = connections.stdout_callback,
            stderr_callback = connections.stderr_callback,
            serial=serial)
    except WrongConnectionState:
        print('{} WrongConnectionState. Check follow log...'.format(TAG))
        for line in connections.log:
            print('{} {}'.format(TAG, line))

        kill_mtserver(serial)
    except KeyboardInterrupt:
        connections.clean_up('KeyboardInterrupt')
        raise
    except Exception as e:
        connections.clean_up('Exception {}'.format(e))
        raise

    connections.clean_up('Normal run_mtserver')

if __name__ == "__main__":
    run_mtserver('com.hoi.simpleapp22', 'temp')
