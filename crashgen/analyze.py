import os
import sys
import pickle

import glob
import json
import pprint
import re
from consumer import Methods, b2u2, b2u4, b2u8

class MessageParse:
    rEXECTRANSACT = 1
    rDISPATCHINPUTEVENT = 2
    rNATIVEPOLLONCE = 3
    rMESSAGE = 4
    rWHAT = 5
    whats = []
    def __init__(self, msgname):
        '''
        [id ##] ptr { callback=@@ target=@@ } /r $REASON

        { callback=android.view.View$CheckForLongPress target=android.view.ViewRootImpl$ViewRootHandler } (queued 400ms) /r [Message id 3764]

        $REASON
        [Thread main(2423) - nativePollOnce/dispatchVsync this:0x12d2af10 J:37049998518 I:0 I:202]
        '''
        # parse
        assert msgname.count(' /r ') == 1
        idx = msgname.index(' /r ')
        content, reason = msgname[:idx], msgname[idx+4:]
        print(msgname)
        self.parse_content(content)
        self.parse_reason(reason)

    def parse_content(self, content):
        gp = re.match(r'\[id ([0-9]+)\] 0x([0-9a-f]+) \{ (.*) \} \(queued ([0-9]+)ms\)', content)
        if gp:
            self.msgid, self.msgptr, self.content, self.qtime = gp.groups()
            self.msgid = int(self.msgid)
            self.msgptr = int(self.msgptr, 16)
            self.qtime = int(self.qtime)
            # self.content_summary = '[id %d %s (%dms)]' % (self.msgid, self.content, self.qtime)
            self.content_summary = '[%s (%dms)]' % (self.content, self.qtime)
            return

        gp = re.search(r'\[id ([0-9]+)\] 0x([0-9a-f]+) \{ (.*) \}', content)
        if gp:
            self.msgid, self.msgptr, self.content = gp.groups()
            self.msgid = int(self.msgid)
            self.msgptr = int(self.msgptr, 16)
            self.qtime = 0
            # self.content_summary = '[id %d %s]' % (self.msgid, self.content)
            self.content_summary = '[%s]' % self.content
            return

        raise RuntimeError("Unable to parse content [%s]" % content)

    def parse_reason(self, reason):
        '''
            "[Thread %s(%d) - execTransact(%s) ARGUMENTS]",
            "[Thread %s(%d) - dispatchInputEvent ARGUMENTS]",
            "[Thread %s(%d) - nativePollOnce/%s ARGUMENTS]",
        '''
        gp = re.match(r'\[Thread (.*)\(([0-9]+)\) - execTransact\(([^ ]+)\) (.*)\]', reason)
        if gp:
            self.rtype = MessageParse.rEXECTRANSACT
            self.rtname, self.rtid, self.rcontent, self.rargs = gp.groups()
            return

        gp = re.match(r'\[Thread (.*)\(([0-9]+)\) - dispatchInputEvent (.*)\]', reason)
        if gp:
            self.rtype = MessageParse.rDISPATCHINPUTEVENT
            self.rtname, self.rtid, self.rargs = gp.groups()
            self.rcontent = None
            return

        gp = re.match(r'\[Thread (.*)\(([0-9]+)\) - nativePollOnce/([^ ]+) (.*)\]', reason)
        if gp:
            self.rtype = MessageParse.rNATIVEPOLLONCE
            self.rtname, self.rtid, self.rcontent, self.rargs = gp.groups()
            return

        gp = re.match(r'\[Message id ([0-9]+)\]', reason)
        if gp:
            self.rtype = MessageParse.rMESSAGE
            self.rmsgid = int(gp.groups()[0])
            return

        gp = re.match(r'\[Thread (.*)\(([0-9]+)\)\]', reason)
        if gp:
            self.rtype = MessageParse.rWHAT
            self.rtname, self.rtid = gp.groups()
            MessageParse.whats.append(self.msgid)
            return

        raise RuntimeError("Unable to parse reason [%s]" % reason)

    def simple_reason(self, messages, put_prefix=True):
        prefix = 'Q' if self.qtime > 0 else 'N'
        if not put_prefix:
            prefix = ''
        if self.rtype == MessageParse.rEXECTRANSACT:
            return prefix + 'Thread %s execTransact(%s)' % (self.rtname, self.rcontent)
        elif self.rtype == MessageParse.rDISPATCHINPUTEVENT:
            return prefix + 'Thread %s dispatchInputEvent' % self.rtname
        elif self.rtype == MessageParse.rNATIVEPOLLONCE:
            return prefix + 'Thread %s nativePollOnce(%s)' % (self.rtname, self.rcontent)
        elif self.rtype == MessageParse.rMESSAGE:
            # return prefix + 'Message %s' % MessageParse(messages[self.rmsgid]).content_summary
            # ancestor
            return prefix + MessageParse(messages[self.rmsgid]).simple_reason(messages, False)
        elif self.rtype == MessageParse.rWHAT:
            return prefix + 'Thread %s' % self.rtname
        else:
            raise RuntimeError('Unknown')


class ResultData:
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
        - info_f.log (field, but empty)
        - col_msgs.pk (dict : msgid -> message_name)
        - col_mpm.pk (dict: msgid -> {invoked_methods -> entered_count})
        - col_idle.pk (list of tuples (timestamp, list: msgids, dict: {invoked_methods -> entered_count}))
    '''
    def __init__(self, folder, ape_dir='ape_output_msg', mt_dir='mt_output_msg'):
        self.ape_output_dir = os.path.join(folder, ape_dir)
        self.mt_output_dir = os.path.join(folder, mt_dir)

    def diff_on_crash(self):
        '''
        Step 1. classify crash/non-crash sequences
        Q1. PHANTOM_CRASH events really means the end of mt_?

        Step 2. 
        '''
        ape_log_fname = os.path.join(self.ape_output_dir, "ape_stdout_stderr.txt")
        if check_log_nativecrash(ape_log_fname): # if native crash, don't consider
            return

        tuples = [] # (action, start, next_action_starttime)
        if True:
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
                        if tuples:
                            tuples[-1] = tuples[-1][:-1] + (acttime,)
                        tuples.append((cur_action, acttime, -1))
                        ready_to_receive_times = False
                    elif line.startswith('[APE_MT]'):
                        assert line == '[APE_MT] Dumping total actions...'
                        break

        # parse action-histories
        action_history_files = glob.glob(os.path.join(self.ape_output_dir, 'sata-*', 'action-history.log'))
        histories = []
        if action_history_files == []:
            print('No match', os.path.join(self.ape_output_dir, 'sata-*', 'action-history.log'))
            return
        assert len(action_history_files) == 1, action_history_files
        with open(action_history_files[0], 'rt') as f:
            for line in f:
                line = line.rstrip()
                if line == '':
                    continue
                sep = line.index(' ')
                histories.append((int(line[:sep]), json.loads(line[sep+1:])))

        # fetch all mt_data
        mt_idx_to_timestamps = {}
        for mt_fname in os.listdir(self.mt_output_dir):
            match = re.match(r'mt_([0-9]*)_data_0\.bin', mt_fname)
            if match:
                with open(os.path.join(self.mt_output_dir, mt_fname), 'rb') as f:
                    magic = f.read(4)
                    assert magic == b'MiTr'
                    version = b2u2(f.read(2))
                    offset = b2u2(f.read(2))
                    log_flag = b2u4(f.read(4))
                    timestamp = b2u8(f.read(8)) # timestamp to start log
                mt_idx_to_timestamps[int(match.groups()[0])] = timestamp

        # check basic rule
        sorted_mt_idxes = sorted(mt_idx_to_timestamps.keys())
        assert all([mt_idx_to_timestamps[sorted_mt_idxes[i]] < mt_idx_to_timestamps[sorted_mt_idxes[i+1]] \
                for i in range(len(mt_idx_to_timestamps)-1)]), pprint.pformat(mt_idx_to_timestamps)

        # just see... whats happening
        ts_list = [(mt_idx_to_timestamps[mt_idx], 'mt', mt_idx) for mt_idx in sorted_mt_idxes]
        for history in histories:
            ts_list.append((history[0], 'action', history[1]))
        ts_list.sort(key=lambda t:t[0])

        # remove mt-mt case
        for i in range(len(ts_list)-1, 0, -1):
            if ts_list[i][1] == 'mt' == ts_list[i-1][1]:
                mt_idx_to_remove = ts_list[i-1][2]
                del ts_list[i-1]
                assert mt_idx_to_remove in sorted_mt_idxes
                sorted_mt_idxes.remove(mt_idx_to_remove)

        # idx of app starting events
        start_events = dict()
        last_start_index = -1
        last_fetched_crash = -1
        def siprint(start_idx, end_idx):
            ret = []
            for idx in range(start_idx, end_idx):
                ts, typ, content = ts_list[idx]
                if typ == 'mt':
                    content = content
                else:
                    content = content['actionType']
                ret.append('{} : {} {} {}'.format(idx, ts, typ, content))
            return '\n'.join(ret)
        for index, (ts, typ, content) in enumerate(ts_list):
            if typ == 'mt':
                assert ts_list[index-1][1] == 'action'
                action_before = ts_list[index-1][2]['actionType']

                action_after = None
                if index < len(ts_list) - 1:
                    assert ts_list[index+1][1] == 'action', siprint(index-10, index+10)
                    action_after = ts_list[index+1][2]['actionType']

                '''
                SE = [EVENT_START, EVENT_RESTART, EVENT_CLEAN_RESTART]
                SE - mt - event
                mt - events... - CRASH - mt - CRASH
                mt - events... - mt - CRASH - events...
                '''

                if action_before in ['EVENT_START', 'EVENT_RESTART', 'EVENT_CLEAN_RESTART']:
                    start_events[content] = index - 1
                    last_start_index = index - 1
                elif action_before == 'PHANTOM_CRASH':
                    if action_after == 'PHANTOM_CRASH':
                        assert last_fetched_crash == index-1, siprint(index-10, index+10)
                        # print("crash-mt-crash case. this mt should be removed", file=sys.stderr)
                        # assert ts_list[index-1][1] == 'mt'
                        # start_events[content] = index+1
                        last_fetched_crash = index+1
                    else:
                        start_events[content] = index
                        last_start_index = index
                        last_fetched_crash = index-1
                else:
                    assert action_after == 'PHANTOM_CRASH', siprint(index-3, index+3)
                    assert index+2 < len(ts_list) and ts_list[index+2][1] == 'mt', siprint(index-3, index+4)
                    start_events[content] = index+2
                    last_start_index = index+2
                    last_fetched_crash = index+1


        class Sequence:
            def __init__(self, idx, end_known):
                self.idx = idx
                self.end_known = end_known
                self.events = []
                self.end_become_known = False
                self.made_crash = False
                self.timestamp = 0

            def register_event(self, timestamp, event):
                '''
                crash appeared!
                 - was unknown -> end became known, and after it registered events are ignored
                 - was known -> all additional events should raise error
                '''
                # first event
                if self.timestamp == 0:
                    self.timestamp = timestamp

                if self.made_crash:
                    if self.end_become_known:
                        return
                    else:
                        raise RuntimeError("event after PHANTOM_CRASH")

                if event['actionType'] == 'PHANTOM_CRASH':
                    self.made_crash = True
                    if self.end_known == False:
                        self.end_known = True
                        self.end_become_known = True

                self.events.append((timestamp, event))

            def __repr__(self):
                ret = '<Sequence #{} {} events, end_known={}, crash={}>'.format(
                        self.idx, len(self.events), self.end_known, self.made_crash)
                # for ts, ev in self.events:
                #     ret += ' +{}ms {}\n'.format(ts - self.timestamp, ev['actionType'])
                return ret


        # step1. classify sequences
        # some sequences' end is unknown
        event_sequences = []
        for i in range(len(sorted_mt_idxes)):
            mt_idx = sorted_mt_idxes[i]
            end_known = mt_idx+1 in mt_idx_to_timestamps
            new_sequence = Sequence(mt_idx, end_known)

            start_idx = start_events[mt_idx]
            end_idx = start_events[sorted_mt_idxes[i+1]] if i < len(sorted_mt_idxes) - 1 else -1

            for ts_idx in range(start_idx, end_idx):
                timestamp, typ, content = ts_list[ts_idx]
                if typ == 'mt':
                    assert content == mt_idx or ts_list[ts_idx+1][2]['actionType'] == 'PHANTOM_CRASH'
                    continue
                new_sequence.register_event(timestamp, content)
            event_sequences.append(new_sequence)

        return event_sequences

        # resolved_idx = []
        # mt_idx = 0
        # cur_action_idx = 0
        # cur_timestamp = action_tuples[0][0]
        # action_string = lambda idx: "Action #{} {} {}~ +{}ms".format(idx, action_tuples[idx][0],
        #     action_tuples[idx][1], action_tuples[idx][2]-action_tuples[idx][1] \
        #     if action_tuples[idx][2] != -1 else "inf")
        # print(action_string(0))
        # while True:
        #     prefix = os.path.join(mt_output_dir, 'mt_{}_'.format(mt_idx))
        #     if not os.path.isfile(prefix + "col_msgs.pk") or \
        #             not os.path.isfile(prefix + "col_mpm.pk") or \
        #             not os.path.isfile(prefix + "col_idle.pk"):
        #         break

        #     print("---------------------------")
        #     print("Analyzing with prefix={}".format(prefix))
        #     resolved_idx.append(mt_idx)

        #     with open(prefix + "col_msgs.pk", 'rb') as pkfile:
        #         messages = pickle.load(pkfile)
        #     with open(prefix + "col_mpm.pk", 'rb') as pkfile:
        #         mtds_per_message = pickle.load(pkfile)
        #     with open(prefix + "col_idle.pk", 'rb') as pkfile:
        #         idle_infos = pickle.load(pkfile)

        #     for timestamp, msgids, mtdcnt in idle_infos:
        #         if action_tuples[cur_action_idx][2] != -1 and \
        #                 timestamp > action_tuples[cur_action_idx][2]: # compare idletime
        #             cur_action_idx += 1
        #             # if cur_action_idx == len(action_tuples):
        #             #     break
        #             print(action_string(cur_action_idx))

        #         # print(' - Idle ~{}'.format(timestamp))
        #         # for msgid in msgids:
        #         #     # print(' - {}'.format(messages[msgid]))
        #         #     print(' --- {}'.format(msgid))
        #         if len(msgids) == 1:
        #             try:
        #                 print(' - Idle ~{}(+{}ms), msg {}'.format(
        #                     timestamp,
        #                     timestamp - action_tuples[cur_action_idx][1],
        #                     messages[msgids[0]]))
        #             except KeyError:
        #                 # 0001~0026
        #                 print(' - Idle ~{}(+{}ms), msg {}'.format(
        #                     timestamp,
        #                     timestamp - action_tuples[cur_action_idx][1],
        #                     msgids[0]))
        #         else:
        #             print(' - Idle ~{}(+{}ms), len(msgs)={}'.format(
        #                 timestamp,
        #                 timestamp - action_tuples[cur_action_idx][1],
        #                 len(msgids)))

        #     mt_idx += 1
        # print('Resolved idx', resolved_idx)


def is_framehandler(msgname):
    frameMsgPattern = r'\[id ([0-9]+)\] (0x[0-9a-f]*) \{ callback=(.*) target=(.*) \} /r \[Thread main\([0-9]*\) - nativePollOnce/dispatchVsync [^\]]*\]'
    match = re.match(frameMsgPattern, msgname)
    if 'dispatchVsync' in msgname and not match:
        print(msgname)
        raise RuntimeError
    if match:
        assert match.groups()[2:4] == \
            ('android.view.Choreographer$FrameDisplayEventReceiver', 'android.view.Choreographer$FrameHandler')
        return True
    return False

def message_test(prefix):
    with open(prefix + "col_msgs.pk", 'rb') as pkfile:
        messages = pickle.load(pkfile)
    with open(prefix + "col_mpm.pk", 'rb') as pkfile:
        mtds_per_message = pickle.load(pkfile)

    framehandlers = []
    for msgid in messages:
        if is_framehandler(messages[msgid]):
            framehandlers.append(msgid)

    mtd_counter = dict()
    for msgid in framehandlers:
        # print(len(mtds_per_message[msgid].keys()))
        for funcptr in mtds_per_message[msgid].keys():
            try:
                mtd_counter[funcptr] += 1
            except KeyError:
                mtd_counter[funcptr] = 1

    methods = Methods(prefix + 'info_m.log')
    for mtd in sorted(mtd_counter.keys(), key = lambda ptr:-mtd_counter[ptr]):
        print(mtd_counter[mtd], methods[mtd])


def find_crash():
    history_fname = '../data/apk_with_reports/*/ape_output_msg/*/action-history.log'
    histories_with_crash = set()
    histories = glob.glob(history_fname)
    for history in sorted(histories):
        cur_stack_traces = []
        with open(history, 'rt') as f:
            ln = -1
            for line in f:
                line = line.rstrip()
                ln += 1

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
                        cur_stack_traces.append((ln, stack_trace))

        for ln, stack_trace in cur_stack_traces:
            print('l', ln, stack_trace.split('\n')[0])
                
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

        print("---------------------------")
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
                try:
                    print(' - Idle ~{}(+{}ms), msg {}'.format(
                        timestamp,
                        timestamp - action_tuples[cur_action_idx][1],
                        messages[msgids[0]]))
                except KeyError:
                    # 0001~0026
                    print(' - Idle ~{}(+{}ms), msg {}'.format(
                        timestamp,
                        timestamp - action_tuples[cur_action_idx][1],
                        msgids[0]))
            else:
                print(' - Idle ~{}(+{}ms), len(msgs)={}'.format(
                    timestamp,
                    timestamp - action_tuples[cur_action_idx][1],
                    len(msgids)))
                msgobj = MessageParse(messages[msgids[0]])
                reason = msgobj.simple_reason(messages)
                print(' - reason {}'.format(reason))
                if reason in ['QThread main dispatchInputEvent', 'QThread main nativePollOnce(dispatchInputEventFinished)']:
                    print('SPECIALOBJECT ' + msgobj.content)

        print('MessageParse idx {} whats {}'.format(mt_idx, MessageParse.whats))
        MessageParse.whats = []

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

def check_end():
    crash_seqs = [
        (34, 3),
        (39, 0), (39, 1), (39, 5),
        ()

    ]


if __name__ == "__main__":
    folder = '../data/apk_with_reports/0034'
    draw_timeline(os.path.join(folder, 'ape_output_msg'),
        os.path.join(folder, 'mt_output_msg'))
    import sys
    sys.exit(0)

    # for fname in glob.glob('../data/*/*/mt_output_msg/*_m.log'):
    #     print('checking ', fname)
    #     make_hash(fname)

    # 
    # find_crash()

    # message_test('../data/apk_with_reports/0026/mt_output_msg/mt_0_')
    def get_all_methods(prefix):
        ret = set()
        methods = Methods(prefix + 'info_m.log')
        for c, m, si, so in methods.values():
            # val = hash(c + m + si)
            ret.add((c, m, si))
            # cur_hashes.append(val)

        return ret

    def get_main_methods(prefix):
        ret = set()
        methods = Methods(prefix + 'info_m.log')
        with open(prefix + 'col_mpm.pk', 'rb') as pkfile :
            mtds_per_message = pickle.load(pkfile)
        for m2c in mtds_per_message.values():
            for funcptr in m2c:
                c, m, si, so = methods[funcptr]
                ret.add((c, m, si))

        return ret

    for i in [34, 39, 61, 62]:
        base_dir = '../data/apk_with_reports/00{}/'.format(i)
        sequences = ResultData(base_dir).diff_on_crash()

        # event to idle
        seq_with_crashes = [s for s in sequences if s.end_known and s.made_crash]
        seq_without_crashes = [s for s in sequences if s.end_known and not s.made_crash]
        # print(' '.join(map(lambda t:str(t.idx), seq_with_crashes)))
        # print(' '.join(map(lambda t:str(t.idx), seq_without_crashes)))

        print('Basedir {} - # sequences with crash/non-crash {}/{}'.format(base_dir, len(seq_with_crashes), len(seq_without_crashes)))

        # choose one
        # get_methods = get_main_methods
        get_methods = get_all_methods

        #######################
        # MAIN THREAD VERSION #
        #######################
        # evaluate all from without crash
        method_used = dict()
        mx_val = 0
        for seq in seq_without_crashes:
            # collect all called methods
            cur_methods = get_methods(os.path.join(base_dir, 'mt_output_msg/mt_{}_'.format(seq.idx)))
            for method in cur_methods:
                try:
                    method_used[method] += 1
                    if mx_val < method_used[method]:
                        mx_val = method_used[method]
                except KeyError:
                    method_used[method] = 1

        # for each crash cases
        len_normal_sequences = len(seq_without_crashes)
        for seq in seq_with_crashes:
            total_methods = get_methods(os.path.join(base_dir, 'mt_output_msg/mt_{}_'.format(seq.idx)))
            print('finding seq', seq, len(total_methods))
            print(seq.events[-1])

            stat = dict()
            for method in total_methods:
                stat[method] = method_used.get(method, 0)

            freq_of_method = dict() # freq -> appeared cnt
            zeroes_func = []
            for c, m, si in sorted(stat.keys(), key=lambda key:(stat[key], key[0], key[1], key[2])):
                val = stat[(c, m, si)]
                if val == 0:
                    zeroes_func.append((c, m, si))
                try:
                    freq_of_method[val] += 1
                except KeyError:
                    freq_of_method[val] = 1
                # if stat[method] < mx_val:
                #     print(seq.idx, stat[method], c, m, si)
            print(mx_val, freq_of_method)
            # for c, m, si in zeroes_func:
            #     print(c, m, si)



    # import traceback
    # exceptions = dict()
    # for i in range(31, 69):
    #     try:
    #         print('report #{}'.format(i))
    #         ResultData('../data/apk_with_reports/00{}/'.format(i)).diff_on_crash()
    #     except Exception as e:
    #         exceptions[i] = ''.join(traceback.format_exception(None, e, e.__traceback__))
    # for i in exceptions:
    #     print('report #{} - exception'.format(i))
    #     print(exceptions[i])
