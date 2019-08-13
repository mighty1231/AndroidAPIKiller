import re
from androidkit import get_uid, get_pids, run_adb_cmd

def b2u4(buf, idx = 0):
    assert isinstance(buf, bytes)
    return buf[idx] \
        + (buf[idx + 1] << 8) \
        + (buf[idx + 2] << 16) \
        + (buf[idx + 3] << 24)

def b2u2(buf, idx = 0):
    assert isinstance(buf, bytes)
    return buf[idx] + (buf[idx + 1] << 8)

def parse(dataf, threads_infof, methods_infof):
    threads = dict()
    with open(threads_infof, 'rt') as f:
        for line in f:
            tid, name = line.rstrip().split('\t')
            if tid in threads:
                print('Same tid with different thread name case is found!')
                print('Thread tid={} name {} <-> {}'.format(tid, threads[tid], name))
                sys.exit(1)
            threads[tid] = name
    
    methods = dict()
    with open(methods_infof, 'rt') as f:
        for line in f:
            if line.rstrip() == '':
                break
            tokens = line.rstrip().split('\t')
            assert len(tokens) == 5

            methods[int(tokens[0], 16)] = \
                (tokens[1], tokens[2], tokens[3], tokens[4])

    kMiniTraceMethodEnter = 0x00
    kMiniTraceMethodExit = 0x01
    kMiniTraceUnroll = 0x02
    kMiniTraceFieldRead = 0x03
    kMiniTraceFieldWrite = 0x04
    kMiniTraceMonitorEnter = 0x05
    kMiniTraceMonitorExit = 0x06
    kMiniTraceExceptionCaught = 0x07
    kMiniTraceActionMask = 0x07

    actions = [
        kMiniTraceMethodEnter,
        kMiniTraceMethodExit,
        kMiniTraceUnroll,
        kMiniTraceFieldRead,
        kMiniTraceFieldWrite,
        kMiniTraceMonitorEnter,
        kMiniTraceMonitorExit,
        kMiniTraceExceptionCaught
    ]
    action_to_string = [
        '%10s Entering  method 0x%08X %s \t %s',
        '%10s Exiting   method 0x%08X %s \t %s',
        '%10s Unrolling method 0x%08X %s \t %s',
        '%10s Reading field 0x%08X object 0x%08X dex 0x%08X',
        '%10s Writing field 0x%08X object 0x%08X dex 0x%08X',
        '%10s Entering monitor 0x%08X dex 0x%08X',
        '%10s Exiting  monitor 0x%08X dex 0x%08X',
        '%10s ExceptionCaught----\n%s\n----ExceptionCaught'
    ]

    with open(dataf, 'rb') as f:
        data = f.read()

    idx = 0
    while idx < len(data):
        tid = b2u2(data, idx)
        tname = threads[tid]
        value = b2u4(data, idx+2)

        action = value & kMiniTraceActionMask;
        if action <= 2:
            fptr = value & ~kMiniTraceActionMask
            finfos = methods[fptr]
            print(action_to_string[action] % \
                    (tname, fptr, finfos[0], finfos[1]))
            idx += 6
        elif action <= 4:
            field_value = value & ~kMiniTraceActionMask
            object_value = b2u4(data, idx+6)
            dex_value = b2u4(data, idx+10)
            print(action_to_string[action] % \
                    (tname, field_value, object_value, dex_value))
            idx += 14
        elif action <= 6:
            object_value = value & ~kMiniTraceActionMask
            dex_pc = b2u4(data, idx+6)
            print(action_to_string[action] % \
                    (tname, object_value, dex_pc))
            idx += 10
        else:
            length = (value & ~kMiniTraceActionMask) >> 3
            string = data[idx+6:idx+length-1].decode()
            print(action_to_string[action] % \
                    (tname, string))
            idx += length


if __name__ == "__main__":
    parse('')