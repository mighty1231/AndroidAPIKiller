import os
import sys
import pickle

import glob
import json
import pprint

class Message:
    def __init__(self, msgname):
        '''
        [id ##] ptr { callback=@@ target=@@ } /r $REASON

        $REASON
        [Thread main(2423) - nativePollOnce/dispatchVsync this:0x12d2af10 J:37049998518 I:0 I:202]
        '''
        pass

def find_crash():
    history_fname = '../data/apk_with_reports/*/ape_output_msg/*/action-history.log'
    histories_with_crash = set()
    histories = glob.glob(history_fname)
    for history in sorted(histories):
        cur_stack_traces = []
        with open(history, 'rt') as f:
            for line in f:
                line = line.rstrip()

                if line == '':
                    continue

                sep = line.index(' ')
                try:
                    actid = int(line[:sep])
                    act = json.loads(line[sep+1:])
                except Exception as e:
                    print(e)
                    print('line', line)
                    raise

                # if act["actionType"] == "PHANTOM_CRASH":
                #     if not history in histories_with_crash:
                #         print(history)
                #     histories_with_crash.add(history)
                #     if 'Native' in act['crash']['longMsg']:
                #         if 'local reference table overflow' not in act['crash']['stackTrace']:
                #             print(act['crash']['stackTrace'])

                if act["actionType"] == "PHANTOM_CRASH" and 'Native' not in act['crash']['longMsg']:
                    if not history in histories_with_crash:
                        print(history)
                    histories_with_crash.add(history)
                    stack_trace = act['crash']['stackTrace']
                    if stack_trace not in cur_stack_traces:
                        cur_stack_traces.append(stack_trace)

        for stack_trace in cur_stack_traces:
            print(stack_trace.split('\n')[0])
                
    pprint.pprint(histories_with_crash)

def check_log_nativecrash(ape_log_fname):
    crash = False
    counter = 0
    # grep "Native Crash" log -A 30
    with open(ape_log_fname, 'rt') as f:
        for line in f:
            line = line.rstrip()
            if 'Native crash' in line:
                crash = True
                counter = 30
            if counter > 0:
                print(line)
                counter -= 1
    return crash

def draw_timeline(ape_output_dir, mt_output_dir):
    '''
    Contents on ape output folder
     - ape_stdout_stderr.txt
     - sata-{:packagename}-ape-sata-running-minutes-{:running_minutes}
    Contents on mt output folder
     - logcat.txt
     - mt_#_
        - data_#.bin
        - info_t.log (thread)
        - info_m.log (method)
        - info_f.log (empty)
        - col_msgs.pk (dict : msgid -> message_name)
        - col_mpm.pk (dict: msgid -> {invoked_methods -> entered_count})
        - col_idle.pk (list of tuples (timestamp, list: msgids, dict: {invoked_methods -> entered_count}))
    '''
    ape_log_fname = os.path.join(ape_output_dir, "ape_stdout_stderr.txt")
    if check_log_nativecrash(ape_log_fname):
        return

    action_tuples = [] # (action, start, next_action_starttime)
    cur_action = ''
    ready_to_receive_times = False
    with open(ape_log_fname, 'rt') as f:
        for line in f:
            line = line.rstrip()
            if line.startswith('[APE_MT] ACTION '):
                ready_to_receive_times = True
                cur_action = line[len('[APE_MT] ACTION '):]
            elif ready_to_receive_times and line.startswith('[APE_MT] '):
                acttime, last_event_time = map(int, line[len('[APE_MT] '):].split('/'))
                if action_tuples:
                    action_tuples[-1] = action_tuples[-1][:-1] + (acttime,)
                action_tuples.append((cur_action, acttime, -1))
                ready_to_receive_times = False
            elif line.startswith('[APE_MT]'):
                assert line == '[APE_MT] Dumping total actions...'
                break

    # for action, start, idle in action_tuples:
    #     print(start, idle, action)

    '''
    Action ##
        msg ##
        msg ##
        msg ##
        msg ##
    '''
    resolved_idx = []
    mt_idx = 0
    cur_action_idx = 0
    cur_timestamp = action_tuples[0][0]
    action_string = lambda idx: "Action #{} {} {}~ +{}ms".format(idx, action_tuples[idx][0],
        action_tuples[idx][1], action_tuples[idx][2]-action_tuples[idx][1] \
        if action_tuples[idx][2] != -1 else "inf")
    print(action_string(0))
    while True:
        prefix = os.path.join(mt_output_dir, 'mt_{}_'.format(mt_idx))
        if not os.path.isfile(prefix + "col_msgs.pk") or \
                not os.path.isfile(prefix + "col_mpm.pk") or \
                not os.path.isfile(prefix + "col_idle.pk"):
            break

        print("Analyzing with prefix={}".format(prefix))
        resolved_idx.append(mt_idx)

        with open(prefix + "col_msgs.pk", 'rb') as pkfile:
            messages = pickle.load(pkfile)
        with open(prefix + "col_mpm.pk", 'rb') as pkfile:
            mtds_per_message = pickle.load(pkfile)
        with open(prefix + "col_idle.pk", 'rb') as pkfile:
            idle_infos = pickle.load(pkfile)

        for timestamp, msgids, mtdcnt in idle_infos:
            if action_tuples[cur_action_idx][2] != -1 and \
                    timestamp > action_tuples[cur_action_idx][2]: # compare idletime
                cur_action_idx += 1
                # if cur_action_idx == len(action_tuples):
                #     break
                print(action_string(cur_action_idx))

            # print(' - Idle ~{}'.format(timestamp))
            # for msgid in msgids:
            #     # print(' - {}'.format(messages[msgid]))
            #     print(' --- {}'.format(msgid))
            if len(msgids) == 1:
                print(' - Idle ~{}(+{}ms), msg {}'.format(
                    timestamp,
                    timestamp - action_tuples[cur_action_idx][1],
                    messages[msgids[0]]))
            else:
                print(' - Idle ~{}(+{}ms), len(msgs)={}'.format(
                    timestamp,
                    timestamp - action_tuples[cur_action_idx][1],
                    len(msgids)))

        mt_idx += 1
    print('Resolved idx', resolved_idx)


        # methods = parse_methodinfo(prefix + "info_m.log")
        # get_method_info = lambda ptr:methods[ptr] if ptr in methods else ["method_%08X" % ptr]

        # for msgid in sorted(messages.keys()):
        #     print('[Message] {}'.format(messages[msgid]))
        #     for ptr in sorted(mtds_per_message[msgid], key=lambda ptr:-mtds_per_message[msgid][ptr]):
        #         print('0x%08X\t%d\t%s' % (
        #             ptr,
        #             mtds_per_message[msgid][ptr],
        #             '\t'.join(get_method_info(ptr))))

        # print('---------------------------------------------')

        # # flush mtds_per_idle
        # for timestamp, msgs, mtds in idle_infos:
        #     print('[Idle %d %s]' % (
        #         timestamp,
        #         datetime.datetime.fromtimestamp(timestamp//1000).strftime("%Y/%m/%d %H:%M:%S")))

        #     print('[Idle] Dispatched messages')
        #     for msg in msgs:
        #         print(msg)

        #     print('[Idle] Executed methods')
        #     for ptr in sorted(mtds, key=lambda ptr:-mtds[ptr]):
        #         print('0x%08X\t%d\t%s' %
        #             (ptr,
        #              mtds[ptr],
        #              '\t'.join(get_method_info(ptr))))

def check_all_hash(method_fnames):
    from consumer import Methods
    hash_vals = []
    name_tuples = []
    for method_f in method_fnames:
        print(len(hash_vals))
        methods = Methods(method_f)

        for ptr in methods:
            c, m, si, so = methods[ptr]
            val = hash(c + m + si)
            try:
                assert (c, m, si) == name_tuples[hash_vals.index(val)]
            except ValueError:
                pass
            hash_vals.append(val)
            name_tuples.append((c, m, si))

def make_hash(method_f):
    # try hashing func candidate #1
    # hash(classname + methodname + signature)
    from consumer import Methods
    methods = Methods(method_f)

    def _hash(info):
        classname, methodname, signature, sourcefile = info
        return hash(classname + methodname + signature)

    hash_list = []
    print('len methods', len(methods))
    for ptr in methods:
        # ptr -> [classname, methodname, signature, sourcefile]
        hashval = _hash(methods[ptr])
        if hashval in hash_list:
            raise
        hash_list.append(hashval)

    return _hash

def get_all_methods_cnt(ape_output_dir, mt_output_dir):
    ape_log_fname = os.path.join(ape_output_dir, "ape_stdout_stderr.txt")
    if check_log_nativecrash(ape_log_fname):
        return
    mt_idx = 0
    while True:
        prefix = os.path.join(mt_output_dir, 'mt_{}_'.format(mt_idx))
        if not os.path.isfile(prefix + "col_msgs.pk") or \
                not os.path.isfile(prefix + "col_mpm.pk") or \
                not os.path.isfile(prefix + "col_idle.pk"):
            break

        print("Analyzing with prefix={}".format(prefix))
        resolved_idx.append(mt_idx)

        with open(prefix + "col_msgs.pk", 'rb') as pkfile:
            messages = pickle.load(pkfile)
        with open(prefix + "col_mpm.pk", 'rb') as pkfile:
            mtds_per_message = pickle.load(pkfile)
        with open(prefix + "col_idle.pk", 'rb') as pkfile:
            idle_infos = pickle.load(pkfile)

        for timestamp, msgids, mtdcnt in idle_infos:
            if action_tuples[cur_action_idx][2] != -1 and \
                    timestamp > action_tuples[cur_action_idx][2]: # compare idletime
                cur_action_idx += 1
                # if cur_action_idx == len(action_tuples):
                #     break
                print(action_string(cur_action_idx))

            # print(' - Idle ~{}'.format(timestamp))
            # for msgid in msgids:
            #     # print(' - {}'.format(messages[msgid]))
            #     print(' --- {}'.format(msgid))
            if len(msgids) == 1:
                print(' - Idle ~{}(+{}ms), msg {}'.format(
                    timestamp,
                    timestamp - action_tuples[cur_action_idx][1],
                    messages[msgids[0]]))
            else:
                print(' - Idle ~{}(+{}ms), len(msgs)={}'.format(
                    timestamp,
                    timestamp - action_tuples[cur_action_idx][1],
                    len(msgids)))

        mt_idx += 1
    print('Resolved idx', resolved_idx)


        # methods = parse_methodinfo(prefix + "info_m.log")

if __name__ == "__main__":
    # folder = '../data/apk_with_reports/00{}'.format(sys.argv[1])
    # draw_timeline(os.path.join(folder, 'ape_output_msg'),
    #     os.path.join(folder, 'mt_output_msg'))

    # find_crash()

    # for fname in glob.glob('../data/*/*/mt_output_msg/*_m.log'):
    #     print('checking ', fname)
    #     make_hash(fname)

    # 
    find_crash()
