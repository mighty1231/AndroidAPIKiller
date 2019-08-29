import os, glob
import re
import sys
import pickle

kMiniTraceMethodEnter = 0x00
kMiniTraceMethodExit = 0x01
kMiniTraceUnroll = 0x02
kMiniTraceFieldRead = 0x03
kMiniTraceFieldWrite = 0x04
kMiniTraceExceptionCaught = 0x05
kMiniTraceActionMask = 0x07
action_to_string = [
    '%10s Entering  method 0x%08X %s \t %s',
    '%10s Exiting   method 0x%08X %s \t %s',
    '%10s Unrolling method 0x%08X %s \t %s',
    '%10s Reading field 0x%08X object 0x%08X dex 0x%08X',
    '%10s Writing field 0x%08X object 0x%08X dex 0x%08X',
    '%10s ExceptionCaught----\n%s\n----ExceptionCaught'
]

def b2u4(buf, idx = 0):
    assert isinstance(buf, bytes)
    return buf[idx] \
        + (buf[idx + 1] << 8) \
        + (buf[idx + 2] << 16) \
        + (buf[idx + 3] << 24)

def b2u2(buf, idx = 0):
    assert isinstance(buf, bytes)
    return buf[idx] + (buf[idx + 1] << 8)

def parse_threadinfo(threadinfo_fname):
    threads = dict()
    with open(thread_fname, 'rt') as f:
        for line in f:
            if line[-1] != '\n':
                break
            tid, name = line.rstrip().split('\t')
            tid = int(tid)
            assert tid not in threads, (prefix, tid, thread[tid], name)
            threads[tid] = name

    return threads

def parse_methodinfo(methodinfo_fname):
    methods = dict()
    with open(method_fname, 'rt') as f:
        for line in f:
            if line[-1] != '\n':
                break
            tokens = line.rstrip().split('\t')
            assert len(tokens) == 5, (prefix, line)

            method_loc = int(tokens[0], 16)
            assert method_loc not in methods, (prefix, line)

            methods[method_loc] = \
                (tokens[1], tokens[2], tokens[3], tokens[4])

    return methods

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
    field_fname = prefix + "info_f.log"
    method_fname = prefix + "info_m.log"
    thread_fname = prefix + "info_t.log"
    out_fname = prefix + "collapse.txt"

    threads = parse_threadinfo(thread_fname)
    methods = parse_methodinfo(method_fname)

    # Collapse binary log. Get count of method invocation for each thread
    ret = dict() # DICT RET : tid -> (DICT : method_loc -> count)
    def log_to_ret(tid, method_loc):
        if tid not in ret:
            ret[tid] = {method_loc: 1}
        else:
            try:
                ret[tid][method_loc] += 1
            except KeyError as e:
                ret[tid][method_loc] = 1

    with open(data_fname, 'rb') as f:
        i = 0
        while True:
            tid = f.read(2)
            if len(tid) < 2:
                break
            tid = b2u2(tid)
            value = f.read(4)
            if len(value) < 4:
                break
            value = b2u4(value)
            action = value & kMiniTraceActionMask
            fptr = value & ~kMiniTraceActionMask
            if action == 0:
                if fptr in methods:
                    log_to_ret(tid, fptr)
                else:
                    print("Warning on collapse: function %08X" % fptr, file=sys.stderr)
            else:
                print("Warning on collapse: action {}, expected 0".format(action), file=sys.stderr)
                cur_location = f.tell()
                file_size = f.seek(0, 2)
                if file_size - cur_location >= 6:
                    print("Remaining size is {}, expected <= 6".format(file_size-cur_location), file=sys.stderr)

                break
            i += 1
            
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
    os.remove(field_fname)

    return 0

def collapse_v2(prefix, files):
    # data_fname = prefix + "data_#.bin"
    field_fname = prefix + "info_f.log"
    method_fname = prefix + "info_m.log"
    thread_fname = prefix + "info_t.log"

    if not all(f in files for f in [field_fname, method_fname, thread_fname]):
        print('Failure on collapse', file = sys.stderr)
        print('Files:', ', '.join(files), file = sys.stderr)
        return

    files.remove(field_fname)
    files.remove(method_fname)
    files.remove(thread_fname)

    # all the other filenames should follow {prefix}data_#.bin
    matches = list(map(lambda f:re.match(r'data_([0-9]*)\.bin', f[len(prefix):]),
            files))
    if not all(matches):
        print('Failure on collapse', file = sys.stderr)
        print('Non-info files:', ', '.join(files), file = sys.stderr)
        return

    threads = parse_threadinfo(thread_fname)
    methods = parse_methodinfo(method_fname)
    with open(thread_fname + '.pk', 'wb') as pkfile:
        pickle.dump(threads, pkfile)
    with open(method_fname + '.pk', 'wb') as pkfile:
        pickle.dump(methods, pkfile)

    for data_fname, idx in zip(files, matches):
        out_fname = prefix + "collapse_{}.pk".format(idx.group(1))

        # Collapse binary log. Get count of method invocation for each thread
        counter = dict() # DICT COUNTER : tid -> (DICT : method_loc -> count)
        def log_to_counter(tid, method_loc):
            if tid not in counter:
                counter[tid] = {method_loc: 1}
            else:
                try:
                    counter[tid][method_loc] += 1
                except KeyError as e:
                    counter[tid][method_loc] = 1

        with open(data_fname, 'rb') as f:
            i = 0
            while True:
                tid = f.read(2)
                if len(tid) < 2:
                    break
                tid = b2u2(tid)
                value = f.read(4)
                if len(value) < 4:
                    break
                value = b2u4(value)
                action = value & kMiniTraceActionMask
                fptr = value & ~kMiniTraceActionMask
                if action == 0:
                    if fptr in methods:
                        log_to_counter(tid, fptr)
                    else:
                        print("Warning on collapse: function %08X" % fptr, file=sys.stderr)
                else:
                    print("Warning on collapse: action {}, expected 0".format(action), file=sys.stderr)
                    cur_location = f.tell()
                    file_size = f.seek(0, 2)
                    if file_size - cur_location >= 6:
                        print("Remaining size is {}, expected <= 6".format(file_size-cur_location), file=sys.stderr)

                    break

        os.remove(data_fname)
        with open(out_fname, 'wb') as pkfile:
            pickle.dump(counter, pkfile)

    return 0


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

if __name__ == "__main__":
    # collapse("mt_output/mt_0_")
    # sort_method_count_pair('mt_output/mt_0_enterexit_method_count.txt')
    # collapse_reader("mt_output/mt_0_collapse.txt")
    # collapse_directory('../data/apk_with_reports/0001/mt_output_check')
    collapse_directory()
