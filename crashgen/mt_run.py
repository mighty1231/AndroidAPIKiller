from androidkit import get_package_name, get_uid, get_pids, run_adb_cmd
import re

STATE_CONSTRUCTED = 0
STATE_PREFIX_GIVEN = 1
states = [STATE_CONSTRUCTED, STATE_PREFIX_GIVEN]

class WrongConnectionState(Exception):
    pass

class Connections:
    def __init__(self):
        self.started_processes = []
        self.connections = {}

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
        self.connections[socketfd] = (STATE_PREFIX_GIVEN, (pid, prefix))
        print('new connection with pid', pid, 'prefix', prefix)

    def close_connection(self, socketfd):
        if socketfd not in self.connections:
            raise WrongConnectionState

        self.started_processes.append(self.connections[socketfd])
        del self.connections[socketfd]

        print('Connection closed')
        print('closed connections', self.started_processes)
        print('connections', self.connections)


connections = Connections()
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

    raise WrongConnectionState

def kill_server(serial = None):
    pids = get_pids('/data/local/tmp/mtserver', serial=serial)
    for pid in pids:
        run_adb_cmd('shell kill {}'.format(pid), serial=serial)

def run_server(package_name, serial=None):
    uid = get_uid(package_name, serial=serial)
    kill_server(serial)
    try:
        out = run_adb_cmd('shell /data/local/tmp/mtserver server {} {}'  \
            .format(uid, package_name),
            stdout_callback = _stdout_callback,
            serial=serial)
        print(out)
    except WrongConnectionState:
        print('Wrong state on connection! Check follow log...')
        global log
        for line in log:
            print(line)

        kill_server(serial)

if __name__ == "__main__":
    run_server('com.hoi.simpleapp22')
