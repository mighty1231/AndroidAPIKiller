import sys, os
import glob, re
import csv

'''
1. Time consumed (ms)
2. Event generated
3. Event counter
4. State count
5. Target states' inTransition
'''
_temp = '''
[APE]      0  TRIVIAL_ACTIVITY
[APE]      0  SATURATED_STATE
[APE]      2  USE_BUFFER
[APE]    231  EARLY_STAGE
[APE]      2  MCMC
[APE]      4  EPSILON_GREEDY
[APE]      0  RANDOM
[APE]      0  NULL
[APE]      1  BUFFER_LOSS
[APE]     56  FILL_BUFFER
[APE]      0  BAD_STATE
'''

strategies = []
for line in _temp.split('\n'):
    if line == '':
        continue
    strategies.append(line[line.rindex(' ') + 1:])
class Result:
    def __init__(self, filename):
        self.filename = filename
        self.parse(filename)

    def parse(self, logfname):
        time_start = 0
        time_end = 0
        time_elapsed = 0
        with open(logfname, 'rt') as f:
            it = iter(f)
            numTargetStatesHist = []
            target_tuples = []
            for line in it:
                line = line.rstrip()
                gp = re.match(r'\[APE_MT\] ([0-9]+)/([0-9]+)', line)
                if gp:
                    if time_start == 0:
                        time_start = int(gp.group(1))
                    time_end = int(gp.group(2))
                    continue

                gp = re.match(r'\[APE\] Sata Strategy: buffer size \(([0-9]+)\)', line)
                if gp:
                    nums = [re.match(r'\[APE\] *([0-9]+)  ' + strategy, next(it).rstrip()) for strategy in strategies]
                    nums = list(map(lambda gp:int(gp.group(1)), nums))
                    continue

                if line.startswith('[APE] GSTG('):
                    gp = re.match(r'\[APE\] GSTG\(g([0-9]+)\): activities \(([0-9]+)\), states \(([0-9]+)\), ' \
                        'edges \(([0-9]+)\), unvisited actions \(([0-9]+)\), visited actions \(([0-9]+)\)', line)
                    assert gp, line
                    gidx, na, ns, ne, nua, nva = map(int, gp.groups())
                    continue
                if line.startswith('[APE_MT] MET_TARGET state'):
                    lines = []
                    lines.append(line)
                    lines.append(next(it).rstrip())
                    lines.append(next(it).rstrip())
                    tup = []
                    for i, t in enumerate(['state', 'action', 'transition']):
                        assert lines[i].startswith('[APE_MT] MET_TARGET ' + t), lines[i]
                        tup.append(lines[i][len('[APE_MT] MET_TARGET ') + len(t) + 1:])
                    tup = tuple(tup)
                    target_tuples.append(tup)
                    continue
                if line.startswith('## Network stats: elapsed time='):
                    gp = re.match(r'## Network stats: elapsed time=([0-9]+)ms \(([0-9]+)ms mobile, ([0-9]+)ms wifi, ([0-9]+)ms not connected\)', line)
                    assert gp, line
                    total, mob, wifi, total2 = gp.groups()
                    assert total == total2 and mob == wifi, line
                    time_elapsed = int(total)
                    continue
                gp = re.match(r'\[APE_MT\] targetStates.size = ([0-9]+)', line)
                if gp:
                    sz = int(gp.group(1))
                    if not numTargetStatesHist or numTargetStatesHist[-1] != sz:
                        numTargetStatesHist.append(sz)
                    continue

        self.infos = {
            'Time consumed/action(ms)': time_end - time_start,
            'Time consumed/end(ms)': time_elapsed,
            '# activities': na,
            '# states': ns,
            '# edges': ne,
            # '# unvisited actions': nua,
            '# visited actions': nva
        }
        for strategy, cnt in zip(strategies, nums):
            self.infos['# S:' + strategy] = cnt

if __name__ == "__main__":
    ape_logs = glob.glob('gnucash30_tr_cmpState/ape_output_t_*/ape_stdout*')
    results = []
    for ape_log in ape_logs:
        print(ape_log)
        _, filename = os.path.split(ape_log)
        results.append(Result(ape_log))

    with open('result_t.csv', 'w') as csvf:
        fieldnames = sorted(results[0].infos.keys())
        writer = csv.DictWriter(csvf, fieldnames = fieldnames)

        writer.writeheader()
        for result in results:
            writer.writerow(result.infos)

