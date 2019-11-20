import javaobj

g = None
def setGlobalObject(obj):
    global g
    g = obj

def enumToString(e):
    from common import setGlobalObject
    setGlobalObject(e)
    if isinstance(e, str):
        return e
    if isinstance(e, javaobj.JavaEnum):
        return e.constant
    return e.type.name

def readJavaList(l):
    if l.get_class().name == 'java.util.Collections$SingletonList':
        return [l.element]
    elif l.get_class().name == 'java.util.ArrayList':
        return l
    else:
        assert l.get_class().name.startswith('[L'), l.get_class().name
        return l

def classReadJavaList(l, cls):
    if isinstance(l, javaobj.JavaObject):
        l = readJavaList(l)
    if isinstance(l, list):
        if l == []:
            return l
        if isinstance(l[0], cls):
            return l
        else:
            return list(map(cls.init, l))
    else:
        raise RuntimeError("Unknown data " + repr(l))

class JavaClass:
    def __init__(self, obj = None, clsname = None):
        if clsname is not None:
            assert obj is not None
            if isinstance(clsname, str):
                assert obj.get_class().name == clsname, (obj.get_class().name, clsname)
            else:
                assert isinstance(clsname, list) or isinstance(clsname, tuple), clsname
                assert obj.get_class().name in clsname, (obj.get_class().name, clsname)
        assert obj is None or isinstance(obj, javaobj.JavaObject)
        self._javaobj = obj

    def __eq__(self, other):
        assert isinstance(other, JavaClass)
        if self._javaobj is None:
            if other._javaobj is None:
                return True
            return False
        return id(self._javaobj) == id(other._javaobj)

    def __hash__(self):
        assert self._javaobj is not None
        return hash(self._javaobj)

    def __getattr__(self, attr):
        if self._javaobj is not None:
            return getattr(self._javaobj, attr)
        raise AttributeError

    def get_object(self):
        return self._javaobj

    def get_classname(self):
        return self._javaobj.get_class().name

    @classmethod
    def init(cls, *obj):
        if len(obj) == 1:
            obj = obj[0]
            if obj is None:
                return None
            if isinstance(obj, cls):
                return obj
            return cls(obj)
        return cls(*obj)
