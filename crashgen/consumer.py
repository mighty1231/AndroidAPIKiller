import os, glob
import re
import sys
import pickle
import argparse
import datetime

kMiniTraceMethodEnter = 0x00
kMiniTraceMethodExit = 0x01
kMiniTraceUnroll = 0x02
kMiniTraceFieldRead = 0x03
kMiniTraceFieldWrite = 0x04
kMiniTraceExceptionCaught = 0x05
kMiniTraceActionMask = 0x07

def b2u2(buf, idx = 0):
    assert isinstance(buf, bytes)
    return buf[idx] + (buf[idx + 1] << 8)

def b2u4(buf, idx = 0):
    assert isinstance(buf, bytes)
    return buf[idx] \
        + (buf[idx + 1] << 8) \
        + (buf[idx + 2] << 16) \
        + (buf[idx + 3] << 24)

def b2u8(buf, idx = 0):
    assert isinstance(buf, bytes)
    return buf[idx] \
        + (buf[idx + 1] << 8) \
        + (buf[idx + 2] << 16) \
        + (buf[idx + 3] << 24) \
        + (buf[idx + 4] << 32) \
        + (buf[idx + 5] << 40) \
        + (buf[idx + 6] << 48) \
        + (buf[idx + 7] << 56)

def parse_threadinfo(threadinfo_fname):
    threads = dict()
    with open(threadinfo_fname, 'rt') as f:
        for line in f:
            if line[-1] != '\n':
                break
            tid, name = line.rstrip().split('\t')
            tid = int(tid)
            assert tid not in threads, (prefix, tid, thread[tid], name)
            threads[tid] = name

    return threads

class Methods:
    def __init__(self, methodinfo_fname):
        # ptr -> [classname, methodname, signature, sourcefile]
        methods = dict()
        with open(methodinfo_fname, 'rt') as f:
            for line in f:
                if line[-1] != '\n':
                    break
                tokens = line.rstrip().split('\t')
                assert len(tokens) == 5, (methodinfo_fname, line)

                method_ptr = int(tokens[0], 16)
                assert method_ptr not in methods, (methodinfo_fname, line)

                methods[method_ptr] = tokens[1:]

        self.methods = methods

    def items(self, *args):
        return self.methods.items()

    def values(self, *args):
        return self.methods.values()

    def __getitem__(self, *args):
        return self.methods.__getitem__(*args)

    def __setitem__(self, *args):
        self.methods.__setitem__(*args)

    def __contains__(self, *args):
        return self.methods.__contains__(*args)

    def __iter__(self, *args):
        return self.methods.__iter__(*args)

    def __len__(self, *args):
        return self.methods.__len__(*args)

    def find_method_ptr(self, classname, methodname, signature=None):
        for ptr in self.methods:
            c, m, sig, sf = self.methods[ptr]
            if c == classname and m == methodname and (signature == None or sig == signature):
                return ptr

        raise KeyError

def parse_methodinfo(methodinfo_fname):
    return Methods(methodinfo_fname)

def parse_fieldinfo(fieldinfo_fname):
    fields = dict()
    with open(fieldinfo_fname, 'rt') as f:
        for line in f:
            if line[-1] != '\n':
                break
            tokens = line.rstrip().split('\t')
            assert len(tokens) == 5, (fieldinfo_fname, line)

            field_ptr = int(tokens[0], 16)
            field_det_idx = int(tokens[1])

            fields[(field_ptr, field_det_idx)] = tokens[2:]

    return fields

class StopParsingData(Exception):
    pass

def parse_data(data_fname, callbacks=[]):
    '''
    Callback for method events 0, 1, 2
        - argument [tid, ptr]
    Callback for field events 3, 4
        - argument [tid, ptr, obj, dex, detail_idx]
    Callback for exception / messages 5, 6
        - argument [tid, content_in_string]
    Callback for idle events 7
        - argument [datetime_object]
    Callback for ping events 8
        - argument [datetime_object]
    Callback for thread kill 9
        - agrument [@TODO]
    Callback for target entring/exiting/unwinding 10/11/12
        - argument [method_id]
    '''
    if isinstance(callbacks, dict):
        callbacks = [callbacks.get(i, None) for i in range(13)]
    elif isinstance(callbacks, list):
        for _ in range(13-len(callbacks)):
            callbacks.append(None)
    else:
        raise RuntimeError
    with open(data_fname, 'rb') as f:
        # read header
        # Header format:
        # u4  magic ('MiTr')
        # u2  version
        # u2  offset to data
        # u4  log_flag
        # u8  starting timestamp in milliseconds
        #     in C:
        #       gettimeofday(&now, NULL); int64_t timestamp = now.tv_sec * 1000LL + now.tv_usec / 1000;
        #     in JAVA:
        #       System.currentTimeMillis();
        #     interpret in Python:
        #       datetime.datetime.fromtimestamp(timestamp/1000.0)
        magic = f.read(4)
        assert magic == b'MiTr'
        version = b2u2(f.read(2))
        offset = b2u2(f.read(2))
        log_flag = b2u4(f.read(4))
        timestamp = b2u8(f.read(8))

        assert offset == 20
        print("MiniTrace Log Version {}".format(version))
        print("Log with flag {}, timestamp {}".format(
            hex(log_flag),
            datetime.datetime.fromtimestamp(timestamp//1000).strftime("%Y/%m/%d %H:%M:%S")))

        try:
            while True:
                tid = f.read(2)
                if len(tid) < 2:
                    break
                tid = b2u2(tid)
                if tid == 0:
                    # Idle event
                    value = f.read(8)
                    if len(value) < 8:
                        break
                    if callbacks[7]:
                        timestamp = b2u8(value)
                        callbacks[7](timestamp)
                    continue
                elif tid == 1:
                    # Pinging event
                    value = f.read(8)
                    if len(value) < 8:
                        break
                    if callbacks[8]:
                        timestamp = b2u8(value)
                        callbacks[8](timestamp)
                    continue
                elif tid == 2:
                    value = f.read(4)
                    if len(value) < 4:
                        break
                    if callbacks[9]:
                        tid = b2u4(value)
                        callbacks[9](tid)
                    continue
                elif tid in [3, 4, 5]:
                    value = f.read(4)
                    if len(value) < 4:
                        break
                    if callbacks[10-3+tid]:
                        value = b2u4(value)
                        callbacks[10-3+tid](value)
                    continue

                value = f.read(4)
                if len(value) < 4:
                    break
                value = b2u4(value)
                action = value & kMiniTraceActionMask
                value = value & ~kMiniTraceActionMask

                if action <= 2: # method event
                    if callbacks[action]:
                        callbacks[action](tid, value)
                elif action <= 4: # field event
                    extra_data = f.read(10)
                    if len(extra_data) != 10:
                        break
                    if callbacks[action]:
                        obj = b2u4(extra_data, 0)
                        dex = b2u4(extra_data, 4)
                        detail_idx = b2u2(extra_data, 8)
                        callbacks[action](tid, value, obj, dex, detail_idx)
                elif action <= 6: # exception / message
                    length = (value >> 3) - 6
                    buf = f.read(length)
                    if len(buf) != length:
                        break
                    if callbacks[action]:
                        # ended with null character
                        try:
                            callbacks[action](tid, buf[:-1].decode())
                        except UnicodeDecodeError:
                            print("Failed to decode ->", buf[:min(len(buf)-1, 100)], file=sys.stderr)
                            raise
                else:
                    raise RuntimeError

        except StopParsingData:
            pass

def pprint_counter(dic, methods, threads):
    # store to collapsed file
    for tid in dic:
        tname = threads[tid]

        # sort methods by invocation count
        m2c = dic[tid]
        for method_ptr in sorted(m2c.keys(), key=lambda method_ptr:-m2c[method_ptr]):
            line = tname
            line += "\t%d\t%08X\t" % (m2c[method_ptr], method_ptr)
            line += '\t'.join(methods[method_ptr])
            print(line)

def collapse(prefix):
    # At now, it only collapses for MethodEntered event
    data_fname = prefix + "data.bin"
    method_fname = prefix + "info_m.log"
    thread_fname = prefix + "info_t.log"
    out_fname = prefix + "collapse.txt"

    threads = parse_threadinfo(thread_fname)
    methods = parse_methodinfo(method_fname)

    # Collapse binary log. Get count of method invocation for each thread
    ret = dict() # DICT RET : tid -> (DICT : method_loc -> count)
    def count_method(tid, fptr):
        if fptr in methods:
            if tid not in ret:
                ret[tid] = {fptr: 1}
            else:
                try:
                    ret[tid][fptr] += 1
                except KeyError as e:
                    ret[tid][fptr] = 1
        else:
            print("Warning on collapse: function %08X not found" % fptr, file=sys.stderr)

    parse_data(data_fname, {kMiniTraceMethodEnter: count_method})

    with open(out_fname, 'wt') as f:
        # store to collapsed file
        for tid in ret:
            tname = threads[tid]

            # sort methods by invocation count
            m2c = ret[tid]
            for method_ptr in sorted(m2c.keys(), key=lambda method_ptr:-m2c[method_ptr]):
                f.write(tname)
                f.write("\t%d\t%08X\t" % (m2c[method_ptr], method_ptr))
                f.write('\t'.join(methods[method_ptr]))
                f.write('\n')

    os.remove(data_fname)
    return 0

def collapse_v2(prefix):
    method_fname = prefix + "info_m.log"
    thread_fname = prefix + "info_t.log"

    if not os.path.isfile(method_fname) or not os.path.isfile(thread_fname):
        print('Failure on collapse', file = sys.stderr)
        print('Files', ', '.join(glob.glob(prefix + '*')))
        return

    methods = parse_methodinfo(method_fname)
    threads = parse_threadinfo(thread_fname)


    for data_fname in glob.glob(prefix + "data_*.bin"):
        idx = re.match(r"data_(.*)\.bin", data_fname[len(prefix):]).group(1)
        out_fname = prefix + "collapse_{}.pk".format(idx)

        # Collapse binary log. Get count of method invocation for each thread
        counter = dict() # DICT COUNTER : tid -> (DICT : fptr -> count)

        def count_method(tid, fptr):
            if fptr in methods:
                if tid not in counter:
                    counter[tid] = {fptr: 1}
                else:
                    try:
                        counter[tid][fptr] += 1
                    except KeyError as e:
                        counter[tid][fptr] = 1
            else:
                print("Warning on collapse: function %08X not found" % fptr, file=sys.stderr)

        parse_data(data_fname, {kMiniTraceMethodEnter: count_method})

        os.remove(data_fname)
        with open(out_fname, 'wb') as pkfile:
            pickle.dump(counter, pkfile)

    return 0

def collapse_per_message(prefix):
    method_fname = prefix + "info_m.log"
    thread_fname = prefix + "info_t.log"

    if not os.path.isfile(method_fname) or not os.path.isfile(thread_fname):
        print('Failure on collapse', file = sys.stderr)
        print('Files', ', '.join(glob.glob(prefix + '*')))
        return

    methods = parse_methodinfo(method_fname)
    threads = parse_threadinfo(thread_fname)

    data_files = glob.glob(prefix + "data_*.bin") # remaining binaries should be removed

    class Counter:
        def __init__(self, threads, methods, outf):
            self.threads = threads
            self.methods = methods
            self.outf = outf
            self.dict = dict()
            self.cur_message = "Initial"

        def method_callback(self, tid, fptr):
            if fptr in self.methods:
                if tid not in self.dict:
                    self.dict[tid] = {fptr : 1}
                else:
                    try:
                        self.dict[tid][fptr] += 1
                    except KeyError as e:
                        self.dict[tid][fptr] = 1
            else:
                print("Warning on collapse: function %08X not found" % fptr, file=sys.stderr)

        def message_callback(self, tid, content):
            # store to file
            self.outf.write("[Message] {}\n".format(self.cur_message))
            for tid in self.dict:
                try:
                    tname = self.threads[tid]
                except KeyError:
                    tname = 'Thread-{}'.format(tid)

                # sort methods by invocation count
                m2c = self.dict[tid]
                for method_ptr in sorted(m2c.keys(), key=lambda method_ptr:-m2c[method_ptr]):
                    self.outf.write(tname)
                    self.outf.write("\t%d\t%08X\t" % (m2c[method_ptr], method_ptr))
                    self.outf.write('\t'.join(self.methods[method_ptr]))
                    self.outf.write('\n')

            # make new line
            self.cur_message = content
            self.dict.clear()


    with open(prefix + "per_message.txt", 'wt') as outf:
        # Get count of method invocation for each thread, seperate for each message called
        # DICT COUNTER: tid -> (DICT : method_loc -> count)
        counter = Counter(threads, methods, outf)
        idx = 0
        data_fname = prefix + "data_{}.bin".format(idx)
        while os.path.isfile(data_fname):
            parse_data(data_fname, {0: counter.method_callback, 6: counter.message_callback})

            # iterate
            data_files.remove(data_fname)
            os.remove(data_fname)
            idx += 1
            data_fname = prefix + "data_{}.bin".format(idx)

        # remove files for files with incomplete index
        # if data files with index 0, 1, 3 and 4, without 2, due to some problem..(?)
        # data files with index 3, 4 should be removed.
        for data_fname in data_files:
            print("Warning on collapse: data file {} was thrown".format(data_fname))
            os.remove(data_fname)

    return 0

def print_data(prefix, idx = 0):
    threads = parse_threadinfo(prefix + "info_t.log")
    methods = parse_methodinfo(prefix + "info_m.log")
    fields = parse_fieldinfo(prefix + "info_f.log")

    get_method_info = lambda ptr:methods[ptr] if ptr in methods else ["method_%08X" % ptr]
    get_field_info = lambda ptr, detidx:fields[ptr, detidx] if (ptr, detidx) in fields else ["field_%08X" % ptr]
    get_thread_name = lambda tid:"%s(%d)" % (threads[tid], tid) if tid in threads else "Thread-%d" % tid

    parse_data(prefix + "data_{}.bin".format(idx), [
        lambda tid, ptr: print('%10s Entering  method 0x%08X %s' % \
                (get_thread_name(tid), ptr, '\t'.join(get_method_info(ptr)))),
        lambda tid, ptr: print('%10s Exiting   method 0x%08X %s' % \
                (get_thread_name(tid), ptr, '\t'.join(get_method_info(ptr)))),
        lambda tid, ptr: print('%10s Unrolling method 0x%08X %s' % \
                (get_thread_name(tid), ptr, '\t'.join(get_method_info(ptr)))),
        lambda tid, ptr, obj, dex, detidx: print('%10s Reading field 0x%08X object 0x%08X dex 0x%08X %s' % \
                (get_thread_name(tid), ptr, obj, dex, '\t'.join(get_field_info(ptr, detidx)))),
        lambda tid, ptr, obj, dex, detidx: print('%10s Writing field 0x%08X object 0x%08X dex 0x%08X %s' % \
                (get_thread_name(tid), ptr, obj, dex, '\t'.join(get_field_info(ptr, detidx)))),
        lambda tid, msg: print('%10s ExceptionCaught----\n%s\n----ExceptionCaught' % \
                (get_thread_name(tid), msg)),
        lambda tid, msg: print('%10s Dispatched Message %s' % \
                (get_thread_name(tid), msg)),
        lambda timestamp: print('Idle Timestamp %s %d' % \
                (datetime.datetime.fromtimestamp(timestamp//1000).strftime("%Y/%m/%d %H:%M:%S"),
                 timestamp)),
        lambda timestamp: print('Ping Timestamp %s %d' % \
                (datetime.datetime.fromtimestamp(timestamp//1000).strftime("%Y/%m/%d %H:%M:%S"),
                 timestamp)),
        lambda tid: print('Thread %s(%d) was terminated' % (get_thread_name(tid), tid)),
        lambda func_id: print('TargetMethod #%d be entered' % func_id),
        lambda func_id: print('TargetMethod #%d be exited' % func_id),
        lambda func_id: print('TargetMethod #%d be unwinded' % func_id),
    ])

def print_target_data(prefix, idx = 0):
    threads = parse_threadinfo(prefix + "info_t.log")
    methods = parse_methodinfo(prefix + "info_m.log")
    fields = parse_fieldinfo(prefix + "info_f.log")

    get_method_info = lambda ptr:methods[ptr] if ptr in methods else ["method_%08X" % ptr]
    get_field_info = lambda ptr, detidx:fields[ptr, detidx] if (ptr, detidx) in fields else ["field_%08X" % ptr]
    get_thread_name = lambda tid:"%s(%d)" % (threads[tid], tid) if tid in threads else "Thread-%d" % tid

    parse_data(prefix + "data_{}.bin".format(idx), {
        10: lambda func_id: print('TargetMethod #%d be entered' % func_id),
        11: lambda func_id: print('TargetMethod #%d be exited' % func_id),
        12: lambda func_id: print('TargetMethod #%d be unwinded' % func_id),
    })


def inspect_stack(prefix, idx = 0, stack_depth = -1, end_condition = None):
    # See method stack with specific moment
    threads = parse_threadinfo(prefix + "info_t.log")
    methods = parse_methodinfo(prefix + "info_m.log")

    get_method_info = lambda ptr:methods[ptr] if ptr in methods else ["method_%08X" % ptr]
    get_thread_name = lambda tid:"%s(%d)" % (threads[tid], tid) if tid in threads else "Thread-%d" % tid

    stack_depth_func = lambda st:len(st) - stack_depth if stack_depth > 0 else -1

    def pretty_print_stack(st):
        for i in range(len(st)-1, max(-1, stack_depth_func(st)), -1):
            content = st[i]
            if content == 'u':
                print("{} : {}".format(i, 'u'))
            else:
                ptr, finfos = content
                print("%d : 0x%08X %s" % (i, ptr, ', '.join(finfos)))

    def remove_stack_until(st, fptr, finfos):
        for i in range(len(st)-1, -1, -1):
            print(st[i])
            if st[i] != (fptr, finfos) and st[i] != 'u' and st[i][1][0] == "Ljava/lang/ThreadLocal$Values;":
                st.pop()
            else:
                break

    class MethodStackPerThread:
        def __init__(self, threads, methods):
            self.stack_per_thread = {} # tid -> stack
            self.threads = threads
            self.methods = methods

        def get_stack(self, tid):
            try:
                return self.stack_per_thread[tid]
            except KeyError:
                self.stack_per_thread[tid] = []
                return self.stack_per_thread[tid]

        def enter(self, tid, ptr):
            stack = self.get_stack(tid)
            old_level = len(stack)
            finfos = get_method_info(ptr)
            if len(stack) > 1 and stack[-1] == 'u' and stack[-2][0] == ptr:
                stack.pop()
                stack.pop()
            stack.append((ptr, get_method_info(ptr)))

            print('%10s %d -> %d Entering  method 0x%08X %s' % \
                    (get_thread_name(tid), old_level, len(stack), ptr, '\t'.join(finfos)))
            pretty_print_stack(stack)
            print()

            # To inspect stack for specific moment
            if end_condition is not None:
                if end_condition(finfos):
                    for i in range(len(stack)-1, -1, -1):
                        print("{} : {}".format(i, stack[i]))
                    raise StopParsingData

        def exit(self, tid, ptr):
            stack = self.get_stack(tid)
            old_level = len(stack)
            finfos = get_method_info(ptr)
            if len(stack) > 0:
                top_elem = stack.pop()
                if top_elem == 'u': # unroll
                    top_elem = stack.pop()
                    if top_elem != (ptr, finfos):
                        top_elem = stack.pop()
                        if top_elem != (ptr, finfos):
                            remove_stack_until(stack, ptr, finfos)
                            top_elem = stack.pop()
                            if top_elem != (ptr, finfos):
                                # print(action)
                                print(top_elem)
                                print((ptr, finfos))
                                raise RuntimeError
                else:
                    if top_elem != (ptr, finfos):
                        remove_stack_until(stack, ptr, finfos)
                        top_elem = stack.pop()
                        if top_elem != (ptr, finfos):
                            # print(action)
                            print(top_elem)
                            print((ptr, finfos))
                            raise RuntimeError

            print('%10s %d -> %d Exiting   method 0x%08X %s' % \
                    (get_thread_name(tid), old_level, len(stack), ptr, '\t'.join(finfos)))
            pretty_print_stack(stack)
            print()

        def unroll(self, tid, ptr):
            stack = self.get_stack(tid)
            old_level = len(stack)
            finfos = get_method_info(ptr)
            while len(stack) > 0 and stack[-1][0] != ptr:
                stack.pop()
            stack.append('u')

            print('%10s %d -> %d Unrolling method 0x%08X %s' % \
                    (get_thread_name(tid), old_level, len(stack), ptr, '\t'.join(finfos)))
            pretty_print_stack(stack)
            print()

    mstack = MethodStackPerThread(threads, methods)
    parse_data(prefix + "data_{}.bin".format(idx), {
        0: mstack.enter,
        1: mstack.exit,
        2: mstack.unroll,
        6: lambda tid, msg: print('%10s Dispatched Message %s' % \
                (get_thread_name(tid), msg)),
        7: lambda timestamp: print('Idle Timestamp %s %d' % \
                (datetime.datetime.fromtimestamp(timestamp//1000).strftime("%Y/%m/%d %H:%M:%S"),
                 timestamp)),
        8: lambda timestamp: print('Ping Timestamp %s %d' % \
                (datetime.datetime.fromtimestamp(timestamp//1000).strftime("%Y/%m/%d %H:%M:%S"),
                 timestamp))
    })

def inspect_stack2(prefix, targetmtdlist, idx = 0):
    # See method stack with specific moment
    threads = parse_threadinfo(prefix + "info_t.log")
    methods = parse_methodinfo(prefix + "info_m.log")

    get_method_info = lambda ptr:methods[ptr] if ptr in methods else ["method_%08X" % ptr]
    get_thread_name = lambda tid:"%s(%d)" % (threads[tid], tid) if tid in threads else "Thread-%d" % tid

    stack_depth_func = lambda st:len(st) - stack_depth if stack_depth > 0 else -1

    def compress_stack(st):
        ret = []
        for content in st:
            if content == 'u':
                continue
            ret.append(content[0]) # ptr
        return tuple(ret)

    def remove_stack_until(st, fptr, finfos):
        for i in range(len(st)-1, -1, -1):
            if st[i] != (fptr, finfos) and st[i] != 'u' and st[i][1][0] == "Ljava/lang/ThreadLocal$Values;":
                st.pop()
            else:
                break

    class MethodStackPerThread:
        def __init__(self, threads, methods):
            self.stack_per_thread = {} # tid -> stack
            self.threads = threads
            self.methods = methods
            self.targetmtdlist = targetmtdlist
            self.mtd_to_stack = {ptr:set() for ptr in targetmtdlist}

        def get_stack(self, tid):
            try:
                return self.stack_per_thread[tid]
            except KeyError:
                self.stack_per_thread[tid] = []
                return self.stack_per_thread[tid]

        def enter(self, tid, ptr):
            stack = self.get_stack(tid)
            old_level = len(stack)
            finfos = get_method_info(ptr)
            if len(stack) > 1 and stack[-1] == 'u' and stack[-2][0] == ptr:
                stack.pop()
                stack.pop()
            stack.append((ptr, get_method_info(ptr)))

            if ptr in self.targetmtdlist:
                print('Entering', get_method_info(ptr))
                self.mtd_to_stack[ptr].add(compress_stack(stack))

        def exit(self, tid, ptr):
            stack = self.get_stack(tid)
            old_level = len(stack)
            finfos = get_method_info(ptr)
            if len(stack) > 0:
                top_elem = stack.pop()
                if top_elem == 'u': # unroll
                    top_elem = stack.pop()
                    if top_elem != (ptr, finfos):
                        top_elem = stack.pop()
                        if top_elem != (ptr, finfos):
                            remove_stack_until(stack, ptr, finfos)
                            top_elem = stack.pop()
                            if top_elem != (ptr, finfos):
                                raise RuntimeError
                else:
                    if top_elem != (ptr, finfos):
                        remove_stack_until(stack, ptr, finfos)
                        top_elem = stack.pop()
                        if top_elem != (ptr, finfos):
                            raise RuntimeError

        def unroll(self, tid, ptr):
            stack = self.get_stack(tid)
            old_level = len(stack)
            finfos = get_method_info(ptr)
            while len(stack) > 0 and stack[-1][0] != ptr:
                stack.pop()
            stack.append('u')

        def print_stacks(self):
            for ptr in self.mtd_to_stack:
                stacks = self.mtd_to_stack[ptr]
                print('METHOD {}'.format(get_method_info(ptr)))
                for stack in stacks:
                    for idx, mtd in enumerate(reversed(stack)):
                        print("{}: {}".format(idx, get_method_info(mtd)))
                    print()
                print()

    mstack = MethodStackPerThread(threads, methods)
    parse_data(prefix + "data_{}.bin".format(idx), {
        0: mstack.enter,
        1: mstack.exit,
        2: mstack.unroll,
    })
    mstack.print_stacks()

def collapse_reader(fname):
    global_m2c = dict()
    m2i = dict()
    with open(fname, 'rt') as f:
        for line in f:
            tname, count, method_ptr, *method_infos = line.rstrip().split('\t')
            count = int(count)
            method_ptr = int(method_ptr, 16)

            try:
                global_m2c[method_ptr] += count
            except KeyError:
                global_m2c[method_ptr] = count
                m2i[method_ptr] = method_infos

    for mptr in sorted(global_m2c.keys(), key=lambda mptr:-global_m2c[mptr]):
        print("{}\t{}".format(global_m2c[mptr], '\t'.join(m2i[mptr])))

def sort_method_count_pair(fname):
    infos = []
    with open(fname) as f:
        for line in f:
            line = line.rstrip()
            a, *others = line.split('\t')
            infos.append((int(a), others))

    for item in sorted(infos, key=lambda t:t[0]):
        a, others = item
        print('{}\t{}'.format(a, '\t'.join(others)))

def collapse_directory():
    files = glob.glob('../data/apk_with_reports/00*/mt_output_check/mt_*_collapse.txt')
    if files == []:
        return

    special_threads = ["main", "FinalizerWatchdogDaemon", "ReferenceQueueDaemon", "FinalizerDaemon",
        "HeapTrimmerDaemon", "GCDaemon", "SharedPreferencesImpl-load", "CleanupReference", "JavaBridge"]
    total_counts = dict()
    thread_total_counts = dict([(t, dict()) for t in special_threads])
    for file in files:
        apkf = int(re.match(r'\.\./data/apk_with_reports/([0-9]+)/mt_output_check/mt_.*_collapse.txt', file).groups()[0])
        if apkf >= 126:
            continue
        with open(file, 'rt') as f:
            for line in f:
                if line == '':
                    break
                thread, cnt, ptr, *mtdinfos = line.rstrip().split('\t')
                cnt = int(cnt)
                try:
                    total_counts[tuple(mtdinfos)] += cnt
                except KeyError:
                    total_counts[tuple(mtdinfos)] = cnt

                if thread in special_threads:
                    try:
                        thread_total_counts[thread][tuple(mtdinfos)] += cnt
                    except KeyError:
                        thread_total_counts[thread][tuple(mtdinfos)] = cnt

    # save to file
    with open('summary.txt', 'wt') as f:
        for mtdkey in sorted(total_counts.keys(), key=lambda k:-total_counts[k]):
            f.write('{}\t{}\n'.format(total_counts[mtdkey], '\t'.join(mtdkey)))

    for thread in special_threads:
        # save to file
        with open('summary_{}.txt'.format(thread), 'wt') as f:
            for mtdkey in sorted(thread_total_counts[thread].keys(), key=lambda k:-thread_total_counts[thread][k]):
                f.write('{}\t{}\n'.format(thread_total_counts[thread][mtdkey], '\t'.join(mtdkey)))

def collapse_per_message_2(prefix):
    # See method stack with specific moment
    threads = parse_threadinfo(prefix + "info_t.log")
    methods = parse_methodinfo(prefix + "info_m.log")

    get_method_info = lambda ptr:methods[ptr] if ptr in methods else ["method_%08X" % ptr]

    main_tid = min(threads.keys())
    dispatchMessage_ptr = methods.find_method_ptr("Landroid/os/Handler;", "dispatchMessage")
    # Assume only non-basic, non-app methods are logged
    class MsgCollapser:
        def __init__(self):
            self.cur_message_name = None
            self.mtds_per_message = dict() # per message

            self.cur_idle_idx = 0
            self.mtds_per_idle = dict() # per idle
            self.msgs_per_idle = []

        def enter(self, tid, ptr):
            if tid == main_tid:
                if self.cur_message_name is not None:
                    try:
                        self.mtds_per_message[ptr] += 1
                    except KeyError:
                        self.mtds_per_message[ptr] = 1

            try:
                self.mtds_per_idle[ptr] += 1
            except KeyError:
                self.mtds_per_idle[ptr] = 1

        def exit(self, tid, ptr):
            if ptr == dispatchMessage_ptr:
                # flush main functions
                print('[Message %s]' % self.cur_message_name)
                for ptr in sorted(self.mtds_per_message, key=lambda ptr:-self.mtds_per_message[ptr]):
                    print('0x%08X\t%d\t%s' % (
                        ptr,
                        self.mtds_per_message[ptr],
                        '\t'.join(get_method_info(ptr))))
                self.mtds_per_message.clear()
                self.cur_message_name = None

        def unroll(self, tid, ptr):
            # self.exit(tid, ptr)
            if ptr == dispatchMessage_ptr:
                self.cur_msg_id = -1

        # this is called by just below the entering dispatchMessage event
        def message_dispatched(self, tid, msg):
            # flush buffer out
            assert self.mtds_per_message == dict() and self.cur_message_name is None
            self.cur_message_name = msg
            self.msgs_per_idle.append(msg)

        def idle(self, timestamp):
            # flush mtds_per_idle
            print('[Idle id=%d] %s %d' % (
                self.cur_idle_idx,
                datetime.datetime.fromtimestamp(timestamp//1000).strftime("%Y/%m/%d %H:%M:%S"),
                timestamp))

            print('[Idle id=%d] Executed messages' % self.cur_idle_idx)
            for msg in self.msgs_per_idle:
                print(msg)

            for ptr in sorted(self.mtds_per_idle, key=lambda ptr:-self.mtds_per_idle[ptr]):
                print('0x%08X\t%d\t%s' %
                    (ptr,
                     self.mtds_per_idle[ptr],
                     '\t'.join(get_method_info(ptr))))

            self.mtds_per_idle.clear()
            self.msgs_per_idle.clear()
            self.cur_idle_idx += 1

    collapser = MsgCollapser()

    idx = 0
    bin_name = prefix + "data_{}.bin".format(idx)
    done_names = []
    while os.path.isfile(bin_name):
        parse_data(bin_name, {
            0: collapser.enter,
            1: collapser.exit,
            2: collapser.unroll,
            6: collapser.message_dispatched,
            7: collapser.idle
        })
        done_names.append(bin_name)

        idx += 1
        bin_name = prefix + "data_{}.bin".format(idx)

    print('Collapsing files done: ', done_names)
    # os.remove()

def collapse_per_message_binary(prefix):
    # See method stack with specific moment
    threads = parse_threadinfo(prefix + "info_t.log")
    methods = parse_methodinfo(prefix + "info_m.log")

    main_tid = min(threads.keys())
    dispatchMessage_ptr = methods.find_method_ptr("Landroid/os/Handler;", "dispatchMessage")
    '''
    messages.pickle = dict: msgid -> message_name
    mtds_per_message.pickle = dict: msgid -> {invoked_methods -> entered_count}
    idle_infos.pickle = list of tuple: (timestamp, list: messages, dict: {invoked_methods -> entered_count})
    '''
    # Assume only non-basic, non-app methods are logged
    class MsgCollapser:
        def __init__(self):
            self.messages = dict()
            self.cur_msg_id = -1
            self.mtds_per_message = dict() # per message

            self.idle_infos = []
            self.cur_msgs_per_idle = []
            self.cur_mtds_per_idle = dict()

        # this is called by just below the entering dispatchMessage event
        # msg starts with [id ##]
        def message_dispatched(self, tid, msg):
            assert self.cur_msg_id == -1
            self.cur_msg_id = int(msg[4:msg.index(']')])
            self.messages[self.cur_msg_id] = msg
            self.cur_msgs_per_idle.append(self.cur_msg_id)
            self.mtds_per_message[self.cur_msg_id] = dict()

        def enter(self, tid, ptr):
            if tid == main_tid:
                if self.cur_msg_id != -1:
                    try:
                        self.mtds_per_message[self.cur_msg_id][ptr] += 1
                    except KeyError:
                        self.mtds_per_message[self.cur_msg_id][ptr] = 1

            try:
                self.cur_mtds_per_idle[ptr] += 1
            except KeyError:
                self.cur_mtds_per_idle[ptr] = 1

        def exit(self, tid, ptr):
            if ptr == dispatchMessage_ptr:
                self.cur_msg_id = -1

        def unroll(self, tid, ptr):
            # self.exit(tid, ptr)
            if ptr == dispatchMessage_ptr:
                self.cur_msg_id = -1

        def idle(self, timestamp):
            self.idle_infos.append((
                timestamp,
                self.cur_msgs_per_idle,
                self.cur_mtds_per_idle
            ))

            self.cur_msgs_per_idle = []
            self.cur_mtds_per_idle = dict()

        def make_pickle(self, messages_fname, mtds_per_message_fname, idle_infos_fname):
            with open(messages_fname, 'wb') as pkfile:
                pickle.dump(self.messages, pkfile)
            with open(mtds_per_message_fname, 'wb') as pkfile:
                pickle.dump(self.mtds_per_message, pkfile)
            with open(idle_infos_fname, 'wb') as pkfile:
                pickle.dump(self.idle_infos, pkfile)

    collapser = MsgCollapser()

    idx = 0
    bin_name = prefix + "data_{}.bin".format(idx)
    done_names = []
    while os.path.isfile(bin_name):
        parse_data(bin_name, {
            0: collapser.enter,
            1: collapser.exit,
            2: collapser.unroll,
            6: collapser.message_dispatched,
            7: collapser.idle
        })
        done_names.append(bin_name)

        idx += 1
        bin_name = prefix + "data_{}.bin".format(idx)

    print('Collapsing files done: ', done_names)
    # os.remove()
    collapser.make_pickle(prefix + "col_msgs.pk", prefix + "col_mpm.pk", prefix + "col_idle.pk")

def analyze_collapsed_pickle(prefix):
    with open(prefix + "col_msgs.pk", 'rb') as pkfile:
        messages = pickle.load(pkfile)
    with open(prefix + "col_mpm.pk", 'rb') as pkfile:
        mtds_per_message = pickle.load(pkfile)
    with open(prefix + "col_idle.pk", 'rb') as pkfile:
        idle_infos = pickle.load(pkfile)
    methods = parse_methodinfo(prefix + "info_m.log")
    get_method_info = lambda ptr:methods[ptr] if ptr in methods else ["method_%08X" % ptr]

    for msgid in sorted(messages.keys()):
        print('[Message] {}'.format(messages[msgid]))
        for ptr in sorted(mtds_per_message[msgid], key=lambda ptr:-mtds_per_message[msgid][ptr]):
            print('0x%08X\t%d\t%s' % (
                ptr,
                mtds_per_message[msgid][ptr],
                '\t'.join(get_method_info(ptr))))

    print('---------------------------------------------')

    # flush mtds_per_idle
    for timestamp, msgs, mtds in idle_infos:
        print('[Idle %d %s]' % (
            timestamp,
            datetime.datetime.fromtimestamp(timestamp//1000).strftime("%Y/%m/%d %H:%M:%S")))

        print('[Idle] Dispatched messages')
        for msg in msgs:
            print(msg)

        print('[Idle] Executed methods')
        for ptr in sorted(mtds, key=lambda ptr:-mtds[ptr]):
            print('0x%08X\t%d\t%s' %
                (ptr,
                 mtds[ptr],
                 '\t'.join(get_method_info(ptr))))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Manager for logs from MiniTrace')

    subparsers = parser.add_subparsers(dest='func')

    print_parser = subparsers.add_parser('print',
        help='Print all log to read')
    print_parser.add_argument('prefix')

    target_parser = subparsers.add_parser('target',
        help='Print for just target method called')
    target_parser.add_argument('prefix')

    stack_parser = subparsers.add_parser('stack',
        help='Print function stack for every method enter/exit')
    stack_parser.add_argument('prefix')
    stack_parser.add_argument('--classname', default=None)
    stack_parser.add_argument('--methodname', default=None)
    stack_parser.add_argument('--count', default=None)
    stack_parser.add_argument('--depth', default='7')

    stack2_parser = subparsers.add_parser('stack2',
        help='Print function stack for given methods')
    stack2_parser.add_argument('prefix')
    stack2_parser.add_argument('mtdptrs')

    collapse_parser = subparsers.add_parser('collapse',
        help='Collapse MiniTrace logs')
    collapse_parser.add_argument('prefix')

    collapse_analyzer_parser = subparsers.add_parser('analyze',
        help='Analyze collapsed data')
    collapse_analyzer_parser.add_argument('prefix')

    args = parser.parse_args()
    if args.func == 'print':
        print_data(args.prefix)
    elif args.func == 'stack':
        count = 0
        if args.count is None:
            if args.classname == args.methodname == None:
                limit = -1
            else:
                limit = 1
        else:
            limit = int(args.count)
        depth = int(args.depth)
        def end_condition(finfos):
            global count
            if len(finfos) > 1 \
                    and (args.classname is None or finfos[0] == args.classname) \
                    and (args.methodname is None or finfos[1] == args.methodname):
                count += 1
                if count == limit:
                    return True
            return False

        inspect_stack(args.prefix, stack_depth = depth, end_condition = end_condition)
    elif args.func == 'target':
        print_target_data(args.prefix)
    elif args.func == 'stack2':
        mtdptrs = list(map(lambda s:int(s,16), args.mtdptrs.split(',')))
        inspect_stack2(args.prefix, mtdptrs)
    elif args.func == 'collapse':
        collapse_per_message_2(args.prefix)
    elif args.func == 'analyze':
        analyze_collapsed_pickle(args.prefix)
    else:
        raise
