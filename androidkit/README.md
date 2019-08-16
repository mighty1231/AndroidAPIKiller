# Androidkit

----
## What is Androidkit?
Python module for managing AVD and emulators

----
## How to install?
    python3 -m pip install -e .

----
## How to use as script?
### Check AVD and emuluator status
    python3 -m androidkit status
    python3 -m androidkit status --detail

### Create AVD
    python3 -m androidkit create AVDNAME --sdkversion android-22 --tag google_apis --device "Nexus 5" --sdcard 1024M

### Run emulator with 1024MB partition
    python3 -m androidkit run AVDNAME --partition_size 1024

### Get activity stack on running emulator
    python3 -m androidkit activitystack --serial emulator-5554

### Get UID of installed package
    python3 -m androidkit getuid com.android.mms
