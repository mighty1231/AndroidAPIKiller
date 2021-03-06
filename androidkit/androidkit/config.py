import json, os

_config = None

default_config = {}

def getConfig(target):
    global _config, default_config

    if _config:
        return _config[target]

    folder, filename = os.path.split(__file__)
    config_json_path = os.path.join(folder, 'config.json')
    if not os.path.isfile(config_json_path):
        with open(config_json_path, 'wt') as f:
            f.write("{\n")
            f.write("\t\"SDK_PATH\":\"/SOMETHING/Android/Sdk\",\n")
            f.write("\t\"AAPT_PATH\":\"/SOMETHING/Android/Sdk/SOMETHING/aapt\",\n")
            f.write("\t\"ADB_PATH\":\"/SOMETHING/Android/Sdk/platform-tools/adb\",\n")
            f.write("\t\"AVDMANAGER_PATH\":\"/SOMETHING/Android/Sdk/tools/bin/avdmanager\"\n")
            f.write("}\n")
        print("Fill the configuration file {}".format(config_json_path))
        exit(1)
    with open(config_json_path, 'rt') as f:
        _config = json.load(f)

    # load default config
    for key in default_config:
        if key not in _config:
            _config[key] = default_config[key]

    # using environment variables
    if not 'SDK_PATH' in _config:
        if 'ANDROID_HOME' in os.environ:
            _config['SDK_PATH'] = os.environ['ANDROID_HOME']
        elif 'ANDROID_SDK_ROOT' in os.environ:
            _config['SDK_PATH'] = os.environ['ANDROID_SDK_ROOT']
        else:
            raise RuntimeError("Please set ANDROID_HOME or ANDROID_SDK_ROOT")
    else:
        assert os.path.isdir(_config['SDK_PATH']), 'Unknown path {} on config file {}'.format(_config['SDK_PATH'], config_json_path)

    if not 'ADB_PATH' in _config:
        _config['ADB_PATH'] = os.path.join(_config['SDK_PATH'], 'platform-tools/adb')

    if not 'AVDMANAGER_PATH' in _config:
        _config['AVDMANAGER_PATH'] = os.path.join(_config['SDK_PATH'], 'tools/bin/avdmanager')

    return _config[target]
