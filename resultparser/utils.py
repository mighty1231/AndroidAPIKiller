

class Forward:
    def __init__(self, attrdict = {}):
        self.obj = None
        self._attrdict = attrdict

    def __getattr__(self, attr):
        if self.isAssigned():
            return getattr(self.obj, attr)
        if attr in self._attrdict:
            return self._attrdict[attr]
        raise AttributeError

    def __eq__(self, other):
        assert self.isAssigned() and other.isAssigned()
        return self.obj == other.obj

    def isAssigned(self):
        return self.obj is not None

    def assign(self, obj):
        assert obj is not None and self.obj is None, (self.obj, obj)
        self.obj = obj

def getFromMapMap(mapMap, K, key, K2, key2):
    key = K.init(key)
    key2 = K2.init(key2)
    values = None
    for k, v in mapMap.items():
        if K.init(k) == key:
            values = v
            break
    if values is None:
        return None

    for k, v in values.items():
        if K2.init(k) == key2:
            return v
    return None

def addToMapMap(mapMap, K, key, K2, key2, value):
    key = K.init(key)
    key2 = K2.init(key2)
    values = None
    for k, v in mapMap.items():
        if K.init(k) == key:
            v[key2] = value
    if values is None:
        mapMap[key] = {key2:value}
