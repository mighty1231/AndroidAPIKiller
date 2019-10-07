from androidkit import run_cmd, run_adb_cmd, RunCmdError
import time

# error_log_cmd = "adb -s #{@emulator_serial} logcat AndroidRuntime:E CrashAnrDetector:D ActivityManager:E *:F *:S > #{@error_log_file_name} &"
# "AndroidRuntime:E CrashAnrDetector:D ActivityManager:E SQLiteDatabase:E WindowManager:E ActivityThread:E Parcel:E *:F *:S"

def start_catcher(output_fname, serial = None):
    run_adb_cmd("logcat -c", serial = serial)

    with open(output_fname, 'wt') as f:
        try:
            run_adb_cmd("logcat art:I AndroidRuntime:E CrashAnrDetector:D ActivityManager:E SQLiteDatabase:E WindowManager:E ActivityThread:E Parcel:E *:F *:S",
                serial = serial,
                stdout_callback = lambda t:f.write("O: " + t + '\n'),
                stderr_callback = lambda t:f.write("E: " + t + '\n'))
        except RunCmdError as e:
            pass

def kill_generated_logcat_processes():
    import psutil
    import os

    this_proc = psutil.Process(os.getpid())
    for child in this_proc.children(recursive=True):
        cmdline = child.cmdline()
        if 'adb' in cmdline and 'logcat' in cmdline:
            child.terminate()

def generate_catcher_thread(output_fname, serial = None):
    import threading

    thread = threading.Thread(target=start_catcher, args=(output_fname, serial))
    thread.daemon = True
    thread.start()

if __name__ == "__main__":
    import time
    generate_catcher_thread("temp.txt")

    time.sleep(3)

    kill_generated_logcat_processes()
