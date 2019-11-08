import sys, os
import argparse
import csv
import glob
import re

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
    ape_logfnames = glob.glob(os.path.join(directory, 'ape_output_*', 'ape_stdout_stderr.txt'))
    # if len(ape_logfnames) != 20:
    if len(ape_logfnames) != 20:
        print("Error: currently experiment catched:")
        for f in ape_logfnames:
            print(f)
        return

    # find match
    ape_logfnames.sort()
    experiments = []
    for ape_logfname in ape_logfnames:
        dirname2, filename = os.path.split(ape_logfname)
        dirname1, subdirname = os.path.split(dirname2)
        gp = re.match(r'ape_output_(nt|t)_([0-9]+)', subdirname)
        assert gp, "Unable to parse {}".format(ape_logfname)
        exptype, expidx = gp.groups()
        mt_directory = os.path.join(directory, 'mt_output_{}_{}'.format(exptype, expidx))
        assert os.path.isdir(mt_directory), mt_directory
        experiments.append((exptype, int(expidx), dirname2, mt_directory))
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
    for exptype, expidx, ape_dir, mt_dir in experiments:
        print('type {} idx {}'.format(exptype, expidx))
        result = Result(os.path.join(ape_dir, 'ape_stdout_stderr.txt')).infos
        binaries = glob.glob(os.path.join(mt_dir, "mt_*_data_*.bin"))
        counter = Counter()
        for binary in binaries:
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
    from parseobj import checkobj
    experiments = cleanupExperiments(directory)
    for exptype, expidx, ape_dir, mt_dir in experiments:
        if exptype == 'nt':
            continue
        assert exptype == 't', exptype
        print('expidx {}'.format(expidx))
        models = glob.glob(os.path.join(ape_dir, 'sata-*', 'sataModel.obj'))
        if len(models) != 1:
            print('WARNING: experiment {}_{} has model {}'.format(exptype, expidx, models))
            continue
        checkobj(models[0])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Result parser')
    subparsers = parser.add_subparsers(dest='func')

    common_parser = subparsers.add_parser('common')
    common_parser.add_argument('directory', type=str)

    marked_parser = subparsers.add_parser('marked')
    marked_parser.add_argument('directory', type=str)

    # list_parser.add_argument('--detail', action='store_true')

    # run_parser = subparsers.add_parser('run',
    #     help='Run Android emulator')
    # run_parser.add_argument('avd_name', type=str)
    # run_parser.add_argument('--port', default=None)
    # run_parser.add_argument('--snapshot', default=None)
    # run_parser.add_argument('--wipe_data', action='store_true')
    # run_parser.add_argument('--writable_system', action='store_true')
    # run_parser.add_argument('--partition_size', help='Disk size for emulator in MB', default=None)

    # arbi_parser = subparsers.add_parser('exec')
    # arbi_parser.add_argument('expression', type=str)

    # setup_parser = subparsers.add_parser('setup')
    # setup_parser.add_argument('serial', type=str)

    # create_parser = subparsers.add_parser('create',
    #     help='Create Android Virtual Device')
    # create_parser.add_argument('name')
    # create_parser.add_argument('--sdkversion', default='android-22')
    # create_parser.add_argument('--tag', default='default')
    # create_parser.add_argument('--device', default='Nexus 5')
    # create_parser.add_argument('--sdcard', default='512M')

    # extract_parser = subparsers.add_parser('extractapk',
    #     help='Extract installed apk file from device')
    # extract_parser.add_argument('package')


    args = parser.parse_args()
    if args.func == "common":
        analyzeCommon(args.directory)
    elif args.func == "marked":
        analyzeMarked(args.directory)
    else:
        raise RuntimeError("func {} is not implemented".format(args.func))
