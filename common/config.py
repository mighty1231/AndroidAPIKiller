import json, os

_config = None

default_config = {}

def getConfig():
    global _config, default_config

    folder, filename = os.path.split(__file__)
    config_json_path = os.path.join(folder, 'config.json')
    if _config is None:
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

        _config['EMMA_JAR_PATH'] = os.path.join(_config['SDK_PATH'], 'tools/lib/emma.jar')
        _config['ADB_PATH'] = os.path.join(_config['SDK_PATH'], 'platform-tools/adb')
    return _config
