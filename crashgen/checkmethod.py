from androidkit import run_cmd, getConfig
import sys, os
import glob
import re
import argparse

def findDexDump():
    pattern = os.path.join(getConfig('SDK_PATH'), 'build-tools', '*', 'dexdump')
    candidates = glob.glob(pattern)
    if len(candidates) == 0:
        raise RuntimeError("dexdump not found on " + pattern)
    return max(candidates)

def getMethods(fname):
    # return clsnames
    dexdump = findDexDump()
    out = run_cmd('{} {}'.format(dexdump, fname))

    lines = out.split('\n')
    ret = []
    for i, line in enumerate(lines):
        gpmtd = re.match(r"\s+name\s+:\s'(.*)'", line)
        if gpmtd:
            gpsig = re.match(r"\s+type\s+:\s'(.*)'", lines[i+1])
            assert gpsig, lines[i+1]
            gpcls = re.match(r"\s+#[0-9]+\s+:\s\(in (.*)\)", lines[i-1])
            assert gpcls, lines[i-1]
            ret.append((gpcls.group(1), gpmtd.group(1), gpsig.group(1)))

    return sorted(ret)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Analyze methods in apk')
    subparsers = parser.add_subparsers(dest='func')

    dump_parser = subparsers.add_parser('dump')
    dump_parser.add_argument('apk_path')

    bymtdname_parser = subparsers.add_parser('name')
    bymtdname_parser.add_argument('apk_path')
    bymtdname_parser.add_argument('mtdname')

    args = parser.parse_args()
    if args.func == 'dump':
        methods = getMethods(args.apk_path)
        for clsname, mtdname, signature in methods:
            print('\t'.join([clsname, mtdname, signature]))
    elif args.func == 'name':
        methods = getMethods(args.apk_path)
        for clsname, mtdname, signature in methods:
            if mtdname == args.mtdname:
                print('{}\t{}'.format(clsname, signature))
    else:
        raise ValueError
