import sys, os
import csv
import glob, re
from androidkit import run_cmd
import argparse
import numpy as np


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
            print('%{}d'.format(maxcnt) % value + ': {}'.format(item))

    def __getitem__(self, item):
        if item in self.content:
            return self.content[item]
        return 0

    def __iter__(self, *args, **kwargs):
        return self.content.__iter__(*args, **kwargs)

    def total(self):
        return sum(self.content.values())

    def keys(self):
        return self.content.keys()

    def values(self):
        return self.content.values()

    def __len__(self):
        return self.content.__len__()

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

def makeUnit(expname, exptype, directory, detail=False):
    apelog_fname = os.path.join(directory, 'ape_stdout_stderr.txt')
    logcat_fname = os.path.join(directory, 'logcat.txt')
    mtdata_directories = glob.glob(os.path.join(directory, 'mt_data', '*'))

    assert os.path.isfile(apelog_fname), apelog_fname
    assert os.path.isfile(logcat_fname), logcat_fname

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
    strategy_cnt = [0 for strategy in strategies]
    first_timestamp = -1
    strategy_changed_timestamp = -1
    first_met_timestamp = -1
    timestamp = -1
    with open(apelog_fname, 'rt') as f:
        it = iter(f)
        for line in it:
            line = line.rstrip()
            if line.startswith('[APE_MT_WARNING]'):
                warningCounter.append(line)

            gp = re.match(r'\[APE\] Sata Strategy: buffer size \(([0-9]+)\)', line)
            if gp:
                nums = [re.match(r'\[APE\] *([0-9]+)  ' + strategy, next(it).rstrip()) for strategy in strategies]
                strategy_cnt = list(map(lambda gp:int(gp.group(1)), nums))
                continue

            elif line.startswith('## Network stats: elapsed time='):
                gp = re.match(r'## Network stats: elapsed time=([0-9]+)ms \(([0-9]+)ms mobile, ([0-9]+)ms wifi, ([0-9]+)ms not connected\)', line)
                assert gp, line
                total, mob, wifi, total2 = gp.groups()
                assert total == total2 and mob == wifi, line
                time_elapsed = int(total)

            elif line == "[APE] *** INFO *** We are still waiting for activity loading. Let's wait for another 100ms...":
                waitCounter.append(line)

            elif line.startswith("[APE] // Long Msg: "):
                crashLongMessagesCounter.append(line[len("[APE] // Long Msg: "):])

            elif line == "[APE] *** INFO *** Half time/counter consumed":
                strategy_changed_timestamp = timestamp

            elif line.startswith("[MonkeyServer] idle fetch"):
                gp = re.match(r'\[MonkeyServer\] idle fetch ([-]{0,1}[0-9]+)', line)
                assert gp, line
                timestamp = int(gp.group(1))
                if first_timestamp == -1 and timestamp not in [0, -1]:
                    first_timestamp = timestamp
            elif line == '[APE_MT] Lastlast transition met target':
                if first_met_timestamp == -1:
                    first_met_timestamp = timestamp

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
    method_register_status = {}
    for method in targetMethods:
        if registered_counter[method] == 0:
            data =  '{}/{}'.format(registered_lazily_counter[method], lazy_counter[method])
        else:
            assert registered_lazily_counter[method] == 0, registered_lazily_counter[method]
            assert lazy_counter[method] == 0, lazy_counter[method]
            data = '{}/{}'.format(registered_counter[method], registered_counter[method])
        method_register_status[method] = data

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

    sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '../crashgen'))
    from consumer import parse_data, Threads, Methods

    execution_data = {}
    mtdCounter = MtdCounter()
    for mtdata_directory in mtdata_directories:
        binary_fname = os.path.join(mtdata_directory, 'data_0.bin')
        thread_fname = os.path.join(mtdata_directory, 'info_t.log')
        method_fname = os.path.join(mtdata_directory, 'info_m.log')

        if any(not os.path.isfile(fname) for fname in [binary_fname, thread_fname, method_fname]):
            continue
        mtdCounter.setTid(Threads(thread_fname).get_main_tid())
        parse_data(binary_fname, {10: mtdCounter.inc, 11: mtdCounter.inc, 12: mtdCounter.inc,
            13: mtdCounter.tidInc, 14: mtdCounter.tidInc, 15: mtdCounter.tidInc}, verbose=False)

        methods = Methods(method_fname)
        execf = os.path.join(mtdata_directory, 'exec.txt')
        with open(execf, 'rt') as f:
            for line in f:
                line = line.rstrip()
                if line.startswith('\0'):
                    line = line[1:]
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


    string = '{},{}'.format(expname, exptype)
    string += ',{},{},{},'.format(time_elapsed, warningCounter.total(), waitCounter.total())

    assert all(method in targetMethods for method in execution_data)
    method_data = []
    for method in targetMethods:
        if method not in execution_data:
            data = 0.0
        else:
            data = execution_data[method].ratio()
        method_data.append('%s:%.3f' % (method_register_status[method], data))
    string += '/'.join(method_data)
    string += ',{},{}'.format(strategy_cnt[strategies.index('MCMC')], sum(strategy_cnt))
    string += ',{},{}'.format(mtdCounter.main_cnt, mtdCounter.cnt)

    # strategy changed timestamp
    if strategy_changed_timestamp == -1:
        string += ',NaN'
    else:
        string += ',{}'.format(strategy_changed_timestamp - first_timestamp)
    # first met transition timestmap
    if first_met_timestamp == -1:
        string += ',NaN'
    else:
        string += ',{}'.format(first_met_timestamp - first_timestamp)

    warningCounter.pretty()
    if not detail:
        string += ',{}'.format(crashLongMessagesCounter.total())
        string += ',{}'.format('/'.join(map(lambda tup:'{} {} [{}]'.format(*tup), targetMethods)))
        return string

    # analysis for sataModel.obj
    # crashes with targets
    # GUITreeTransition marked/total
    # State marked/total
    # StateTransition marked/total
    # unique subsequences (>=3 times / at least once)
    # @TODO State score
    # @TODO StateTransition score
    data = []
    import javaobj
    from common import classReadJavaList, readJavaList
    from tree import GUITree
    from model import Model, Graph, StateTransition
    try:
        with open(modelobject_fname, 'rb') as f:
            model = Model(javaobj.loads(f.read()))
    except Exception:
        return string + ',javaobjError'

    graph = Graph.init(model.graph)

    # crashes
    crashWithTargetMethodsCounter = Counter()
    firstMoment = -1
    firstMomentTargetMethods = -1
    records = model.actionHistory
    for record in readJavaList(records):
        if firstMoment == -1:
            firstMoment = record.clockTimestamp
        if not record.guiAction:
            action = record.modelAction
            constant = action.type.constant
            if constant == 'PHANTOM_CRASH':
                # check stackTrace
                stackTrace = action.crash.stackTrace
                append = False
                for line in stackTrace.split('\n'):
                    if append:
                        break
                    for (clsname, mtdname, signature) in targetMethods:
                        if mtdname in line and clsname[1:-1].split('/')[-1] in line:
                            append = True
                            break
                if append:
                    crashWithTargetMethodsCounter.append(action.crash.stackTrace)
                    if firstMomentTargetMethods == -1:
                        firstMomentTargetMethods = record.clockTimestamp

    crashWithTargetMethodsCounter.pretty()
    if firstMomentTargetMethods == -1:
        data.append('NaN')
    else:
        data.append(firstMomentTargetMethods - firstMoment)
    data.append(crashWithTargetMethodsCounter.total())
    data.append(crashLongMessagesCounter.total())

    treeHistory = graph.treeTransitionHistory
    marked_gtransitions = []
    marked_transitions = set()
    for gtransition in treeHistory:
        if gtransition.hasMetTargetMethod:
            marked_gtransitions.append(gtransition)
            marked_transitions.add(gtransition.stateTransition)

    data.append(len(marked_gtransitions))
    data.append(len(treeHistory))

    targetGUITrees = classReadJavaList(graph.metTargetMethodGUITrees, GUITree)
    targetStates = set(map(lambda t:t.getCurrentState(), targetGUITrees))
    targetStateIds = set(map(lambda t:id(t.currentState), targetGUITrees))
    assert len(targetStates) == len(targetStateIds), (len(targetStates), len(targetStateIds))

    data.append(len(targetStates))
    data.append(graph.size())

    # Split with marked State (old) -> Split with marked StateTransition
    from parseobj import getSubsequences, TargetSubsequence
    subsequences = getSubsequences(model, graph)
    subseqCounter = Counter()
    for seq in subsequences:
        targetSubsequence = TargetSubsequence(seq[0])
        for tr in seq[1:]:
            if tr.hasMetTargetMethod == True:
            # if id(tr.source.currentState) in targetStateIds:
                subseqCounter.append(targetSubsequence)
                targetSubsequence = TargetSubsequence(tr)
            else:
                targetSubsequence.append(tr)
        # subseqCounter.append(targetSubsequence)

    data.append(len([s for s in subseqCounter.values() if s >= 3]))
    data.append(len(subseqCounter))

    string += ',' + ','.join(map(str, data))
    if len(subseqCounter) == 0:
        string += ',NaN,NaN,NaN,NaN,NaN,NaN'
    else:
        # #subseq with len <=1, <=2, <=3, <=4, <=5
        keys = subseqCounter.keys()
        cnts = []
        for sz in [1, 2, 3, 4, 5]:
            cnts.append(len([s for s in keys if len(s) <= sz]))
        cnts = tuple(cnts)
        string += ',%.2f,%d,%d,%d,%d,%d' % ((subseqCounter.total() / len(subseqCounter),) + cnts)

    # statistics for state / transition
    state_scores = []
    for state in targetStates:
        state_scores.append(graph.metTargetScore(state))
    if state_scores != []:
        state_scores = np.array(state_scores)
        string += ',%d,%.3f,%.3f,%.3f,%.3f' % (
            len(state_scores),
            np.min(state_scores),
            np.max(state_scores),
            np.average(state_scores),
            np.std(state_scores))
    else:
        string += ',0,NaN,NaN,NaN,NaN'

    transition_scores = []
    for transition in marked_transitions:
        transition_scores.append(StateTransition.init(transition).metTargetRatio())
    if transition_scores != []:
        transition_scores = np.array(transition_scores)
        string += ',%d,%.3f,%.3f,%.3f,%.3f' % (
            len(transition_scores),
            np.min(transition_scores),
            np.max(transition_scores),
            np.average(transition_scores),
            np.std(transition_scores))
    else:
        string += ',0,NaN,NaN,NaN,NaN'
    string += ',{}'.format('/'.join(map(lambda tup:'{} {} [{}]'.format(*tup), targetMethods)))

    return string


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Result parser')
    parser.add_argument('--detail', default=False, action='store_true')
    parser.add_argument('--output', default='result.csv')
    parser.add_argument('directories', nargs='+')

    args = parser.parse_args()

    if args.detail:
        results = []
        for exp in args.directories:
            while exp.endswith('/'):
                exp = exp[:-1]
            expname, exptype = exp.split('/')[-2:]
            print('Experiment {}/{}'.format(expname, exptype))
            result = makeUnit(expname, exptype, exp, True)
            if result is not None:
                results.append(result)
            print()

        print('----------- csv ---------')
        with open(args.output, 'wt') as f:
            string = 'expname,exptype,time_elapsed,#warnings,#wait,#targetmethod reg:cov'
            string += ',#strategy MH,#strategy all,#invoc in main,#invoc in all'
            string += ',ts strategy changed,ts first met'
            string += ',firstTimeMetCrash,#related crashes,#crashes'
            string += ',#gtransition marked,#gtransition total,#state marked,#state total'
            string += ',#subsequence (>=3),#subsequence total,#subseq avg per unique'
            string += ',#len<=1,2,3,4,5'
            string += ',state score:len,min,max,avg,std'
            string += ',transition score:len,min,max,avg,std'
            string += ',methods'
            f.write(string)
            f.write('\n')
            print(string)
            for result in results:
                f.write(result)
                f.write('\n')
                print(result)
    else:
        results = []
        for exp in args.directories:
            while exp.endswith('/'):
                exp = exp[:-1]
            expname, exptype = exp.split('/')[-2:]
            print('Experiment {}/{}'.format(expname, exptype))
            result = makeUnit(expname, exptype, exp)
            if result is not None:
                results.append(result)
            print()

        print('----------- csv ---------')
        with open(args.output, 'wt') as f:
            string = 'expname,exptype,time_elapsed,#warnings,#wait,#targetmethod reg:cov'
            string += ',#strategy MH,#strategy all,#invoc in main,#invoc in all'
            string += ',ts strategy changed,ts first met'
            string += ',#crashes'
            string += ',methods'
            f.write(string)
            f.write('\n')
            print(string)
            for result in results:
                f.write(result)
                f.write('\n')
                print(result)
