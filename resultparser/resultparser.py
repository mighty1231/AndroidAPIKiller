import sys, os
import argparse
import csv
import glob
import re
from parseobj import checkobj

'''
Task 1. Given experiment folder (marked/non-marked common)
for each run, evaluate follow infos over each experiments
 - total target method invocation
 - Time consumed(ms)
 - Number of activities
 - Number of states
 - Number of edges
 - Number of visited actions
 - Count of each strategies
Task 2. Analyze marked version experiment
 - Number of total target method invocation
 - Number of targetStates
 - Number of InTransitions and OutTransitions for targetStates
 - Number of kinds of transition sequences
Task 3. Based on some information from marked version
 - GUITree, GUITreeTransitions
 - TargetState / TargetStateTransition
 - getTargetStates' GUITrees -> put naming, get state..!
'''

def cleanupExperiments(directory):
    # return [exptype, expidx, ape_directory, mt_directory]
    ape_logfnames = glob.glob(os.path.join(directory, '*', 'ape_stdout_stderr.txt'))
    # if len(ape_logfnames) != 20:
    for f in ape_logfnames:
        print(f)
    if len(ape_logfnames) <= 2:
        print("Error: currently experiment catched:")
        return []

    # find match
    ape_logfnames.sort()
    experiments = []
    for ape_logfname in ape_logfnames:
        dirname, filename = os.path.split(ape_logfname)
        assert filename == 'ape_stdout_stderr.txt', filename
        basedirname, expname = os.path.split(dirname)
        gp = re.match(r'(nt|t)_([0-9]+)', expname)
        assert gp, "Unable to parse {}".format(ape_logfname)
        exptype, expidx = gp.groups()
        experiments.append((exptype, int(expidx), dirname))
    return experiments

def analyzeCommon(directory):
    '''
    Make result.csv at the directory
    '''
    outf = os.path.join(directory, 'result.csv')
    assert not os.path.isfile(outf)

    sys.path.append('../crashgen')
    from consumer import parse_data
    from parse_aperes import Result
    experiments = cleanupExperiments(directory)

    class Counter(object):
        def __init__(self):
            self.cnt = 0
        def inc(self, value):
            self.cnt += 1

    results = []
    for exptype, expidx, directory in experiments:
        print('type {} idx {}'.format(exptype, expidx))
        result = Result(os.path.join(directory, 'ape_stdout_stderr.txt')).infos
        binaries = glob.glob(os.path.join(directory, 'mt_data/*/data_*.bin'))
        counter = Counter()
        for binary in sorted(binaries, key=lambda b:int(b.split('/')[-2])):
            parse_data(binary, {10: counter.inc, 11: counter.inc, 12: counter.inc}, verbose=False)
        result['type'] = exptype
        result['idx'] = expidx
        result['# Invocation'] = counter.cnt
        results.append(result)

    with open(outf, 'w') as csvf:
        fieldnames = sorted(results[0].keys())
        writer = csv.DictWriter(csvf, fieldnames = fieldnames)

        writer.writeheader()
        for result in results:
            writer.writerow(result)

def analyzeMarked(directory):
    '''
    print information for marked
    '''
    experiments = cleanupExperiments(directory)
    for exptype, expidx, directory in experiments:
        if exptype == 'nt':
            continue
        assert exptype == 't', exptype
        print('expidx {}'.format(expidx))
        models = glob.glob(os.path.join(directory, 'ape/sata-*', 'sataModel.obj'))
        if len(models) != 1:
            print('WARNING: experiment {}_{} has model {}'.format(exptype, expidx, models))
            continue
        checkobj(models[0])

def analyzeMarkedAll(directory):
    for model in directory:
        print('[Analyzing model {}]'.format(model))
        checkobj(model)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Result parser')
    subparsers = parser.add_subparsers(dest='func')

    common_parser = subparsers.add_parser('common')
    common_parser.add_argument('directory', type=str)

    marked_parser = subparsers.add_parser('marked')
    marked_parser.add_argument('directory', type=str)

    markedall_parser = subparsers.add_parser('markedall')
    markedall_parser.add_argument('pattern', nargs='+')

    args = parser.parse_args()
    if args.func == "common":
        analyzeCommon(args.directory)
    elif args.func == "marked":
        analyzeMarked(args.directory)
    elif args.func == "markedall":
        analyzeMarkedAll(args.pattern)
    else:
        raise RuntimeError("func {} is not implemented".format(args.func))
