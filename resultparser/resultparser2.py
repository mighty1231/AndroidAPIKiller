import sys, os
import csv
import glob, re
from androidkit import run_cmd


class Counter:
    def __init__(self):
        self.content = {}

    def append(self, item):
        try:
            self.content[item] += 1
        except KeyError:
            self.content[item] = 1

    def pretty(self):
        maxcnt = -1
        for item in sorted(self.content.keys(), key=lambda k:-self.content[k]):
            value = self.content[item]
            if maxcnt == -1:
                maxcnt = len(str(value))
            print('%{}d : {}'.format(maxcnt, item) % value)

    def __getitem__(self, item):
        if item in self.content:
            return self.content[item]
        return 0

    def __iter__(self, *args, **kwargs):
        return self.content.__iter__(*args, **kwargs)

    def total(self):
        return sum(self.content.values())

class ExperimentUnit:
    def __init__(self, expname, exptype, directory):
        # init
        # necessary files
        pass

strategies = [
    'TRIVIAL_ACTIVITY',
    'SATURATED_STATE',
    'USE_BUFFER',
    'EARLY_STAGE',
    'MCMC',
    'EPSILON_GREEDY',
    'RANDOM',
    'NULL',
    'BUFFER_LOSS',
    'FILL_BUFFER',
    'BAD_STATE',
]

def makeUnit(expname, exptype, directory):
    apelog_fname = os.path.join(directory, 'ape_stdout_stderr.txt')
    logcat_fname = os.path.join(directory, 'logcat.txt')
    mtdata_directories = glob.glob(os.path.join(directory, 'mt_data', '*'))

    assert os.path.isfile(apelog_fname)
    assert os.path.isfile(logcat_fname)

    modelobjects = glob.glob(os.path.join(directory, 'ape', 'sata-*', 'sataModel.obj'))
    if len(modelobjects) < 1:
        print("There is no model object in {}".format(directory))
        with open(apelog_fname, 'rt') as f:
            num_lines = int(run_cmd('wc -l {}'.format(apelog_fname)).split()[0])

            for i, line in enumerate(f):
                if i >= num_lines - 10:
                    print(' {}: {}'.format(i, line.rstrip()))

        return None

    assert len(modelobjects) == 1, modelobjects
    modelobject_fname = modelobjects[0]

    warningCounter = Counter()
    waitCounter = Counter()
    crashLongMessagesCounter = Counter()
    time_elapsed = -1
    with open(apelog_fname, 'rt') as f:
        for line in f:
            line = line.rstrip()
            if line.startswith('[APE_MT_WARNING]'):
                warningCounter.append(line)

            elif line.startswith('## Network stats: elapsed time='):
                gp = re.match(r'## Network stats: elapsed time=([0-9]+)ms \(([0-9]+)ms mobile, ([0-9]+)ms wifi, ([0-9]+)ms not connected\)', line)
                assert gp, line
                total, mob, wifi, total2 = gp.groups()
                assert total == total2 and mob == wifi, line
                time_elapsed = int(total)

            if line == "[APE] *** INFO *** We are still waiting for activity loading. Let's wait for another 100ms...":
                waitCounter.append(line)

            elif 'Long Message' in line:
                crashLongMessagesCounter.append(line)

    if time_elapsed == -1:
        print("Time elapsed not found")
        with open(apelog_fname, 'rt') as f:
            num_lines = int(run_cmd('wc -l {}'.format(apelog_fname)).split()[0])

            for i, line in enumerate(f):
                if i >= num_lines - 10:
                    print(' {}: {}'.format(i, line.rstrip()))
        return None

    targetMethods = []
    lazy_counter = Counter()
    registered_counter = Counter()
    registered_lazily_counter = Counter()
    with open(logcat_fname, 'rt') as f:
        for line in f:
            if 'MiniTrace' not in line:
                continue

            line = line.rstrip()
            line = line[line.index('MiniTrace'):]

            gp = re.match(r'MiniTrace: TargetMethod (.*):(.*)\[(.*)\] ([a-z ]+)', line)
            if gp:
                clsname, mtdname, signature, status = gp.groups()
                if status == 'lazy':
                    clsname = 'L{};'.format(clsname)
                    if (clsname, mtdname, signature) not in targetMethods:
                        targetMethods.append((clsname, mtdname, signature))
                    lazy_counter.append((clsname, mtdname, signature))
                elif status == 'registered':
                    clsname = 'L{};'.format(clsname)
                    if (clsname, mtdname, signature) not in targetMethods:
                        targetMethods.append((clsname, mtdname, signature))
                    lazy_counter.append((clsname, mtdname, signature))
                else:
                    assert status == 'registered lazily', status
                    assert clsname[0] == 'L' and clsname[-1] == ';', clsname
                    registered_lazily_counter.append((clsname, mtdname, signature))
    method_register_status = {method: "r{} lr{}/{}".format(registered_counter[method],
            registered_lazily_counter[method], lazy_counter[method]) for method in targetMethods}

    # self.exptype = exptype
    # self.expname = expname
    # self.directory = directory

    # marked call
    class MtdCounter(object):
        def __init__(self):
            self.cnt = 0
            self.main_tid = -1
            self.main_cnt = 0
        def setTid(self, main_tid):
            self.main_tid = main_tid
        def inc(self, value):
            self.main_cnt += 1
        def tidInc(self, tid, value):
            assert self.main_tid != -1
            if tid == self.main_tid:
                self.main_cnt += 1
            self.cnt += 1

    class ExecutionData:
        def __init__(self, string):
            assert all(c in ['0', '1'] for c in string), string
            self.string = string

        def union(self, new_string):
            assert len(self.string) == len(new_string)
            new_string = ''.join(['1' if a == '1' or b == '1' else '0' \
                for a, b in zip(self.string, new_string)])
            self.string = new_string

        def __or__(self, other):
            assert len(self.string) == len(other.string)
            new_string = ''.join(['1' if a == '1' or b == '1' else '0' \
                for a, b in zip(self.string, other.string)])
            return ExecutionData(new_string)

        def __repr__(self):
            return '<ExecutionData string={}>'.format(self.string)

        def ratio(self):
            return self.string.count('1') / len(self.string)

    sys.path.append('../crashgen')
    from consumer import parse_data, Threads, Methods

    execution_data = {}
    mtdCounter = MtdCounter()
    for mtdata_directory in mtdata_directories:
        binary = os.path.join(mtdata_directory, 'data_0.bin')
        threadf = os.path.join(mtdata_directory, 'info_t.log')
        mtdCounter.setTid(Threads(threadf).get_main_tid())
        parse_data(binary, {10: mtdCounter.inc, 11: mtdCounter.inc, 12: mtdCounter.inc,
            13: mtdCounter.tidInc, 14: mtdCounter.tidInc, 15: mtdCounter.tidInc}, verbose=False)

        methods = Methods(os.path.join(mtdata_directory, 'info_m.log'))
        execf = os.path.join(mtdata_directory, 'exec.txt')
        with open(execf, 'rt') as f:
            for line in f:
                line = line.rstrip()
                if line == '':
                    break
                if not line.startswith('Timestamp'):
                    mtdptr, execdata = line.split()
                    mtdptr = int(mtdptr, 16)
                    clsname, mtdname, signature, defclass = methods[mtdptr]
                    try:
                        execution_data[(clsname, mtdname, signature)].union(execdata)
                    except KeyError:
                        execution_data[(clsname, mtdname, signature)] = ExecutionData(execdata)

    warningCounter.pretty()
    crashLongMessagesCounter.pretty()

    string = '{},{}'.format(expname, exptype)
    string += ',{},{},{},{},'.format(time_elapsed, warningCounter.total(), waitCounter.total(), crashLongMessagesCounter.total())

    assert all(method in targetMethods for method in execution_data)
    method_data = []
    for method in targetMethods:
        if method not in execution_data:
            data = 0.0
        else:
            data = execution_data[method].ratio()
        method_data.append('%s:%.3f' % (method_register_status[method], data))
    string += '/'.join(method_data)
    string += ',{},{}'.format(mtdCounter.main_cnt, mtdCounter.cnt)

    return string

if __name__ == "__main__":
    results = []
    for exp in sys.argv[1:]:
        while exp.endswith('/'):
            exp = exp[:-1]
        expname, exptype = exp.split('/')[-2:]
        print('Experiment {}/{}'.format(expname, exptype))
        result = makeUnit(expname, exptype, exp)
        if result is not None:
            results.append(result)
        print()

    print('----------- csv ---------')
    with open('result.csv', 'wt') as f:
        string = 'expname,exptype,time_elapsed,#warnings,#wait,#crashes,#targetmethod reg:cov,#invoc in main,#invoc in all'
        f.write(string)
        f.write('\n')
        print(string)
        for result in results:
            f.write(result)
            f.write('\n')
            print(result)
