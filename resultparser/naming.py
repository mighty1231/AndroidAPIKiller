import javaobj
from common import readJavaList, classReadJavaList, JavaClass, enumToString
from utils import getFromMapMap, Forward, addToMapMap
import lxml.etree as etree
import tree as treeModule
import model
import dom

class StateNamingManager(JavaClass):
    def __init__(self, namingManager):
        super(StateNamingManager, self).__init__(namingManager, "com.android.commands.monkey.ape.naming.StateNamingManager")

    def getNaming(self, tree):
        # Omit caching: self.treeToNaming[tree]
        naming = self.getNaming(tree, tree.getActivityName(), tree.getDocument())
        assert naming is not None, "Cannot get naming for raw GUI tree."
        return naming

    def getNaming(self, *args):
        if len(args) == 3:
            tree, activityName, document = args
        else:
            assert len(args) == 1, args
            tree = args[0]
            activityName = tree.getActivityName()
            document = tree.getDocument()
        source = self.getBaseNaming()
        while 1:
            state = self.getStateKey(source, tree)
            target = getFromMapMap(self.namingToEdge, Naming, source, model.StateKey, state)
            if target is None:
                return source
            source = target

    def getStateKey(self, source, tree):
        source = Naming.init(source)
        tree = treeModule.GUITree.init(tree)
        return treeModule.GUITreeBuilder_getStateKey(source, tree)

    def getBaseNaming(self):
        return Naming.init(self.namingFactory.base)

class NamerFactory:
    PATCHED_ALL = dict()
    ALL = dict()
    TYPE, TEXT, INDEX, PARENT, ANCESTOR, PATCH = \
            'TYPE', 'TEXT', 'INDEX', 'PARENT', 'ANCESTOR', 'PATCH'
    for key in [tuple(), (TYPE,), (TEXT,), (INDEX,), (PARENT,), \
            (PARENT, TYPE), (PARENT, TEXT), (PARENT, INDEX), \
            (TYPE, TEXT), (TYPE, INDEX), (TEXT, INDEX), \
            (PARENT, TYPE, TEXT), (PARENT, TYPE, INDEX), \
            (TYPE, TEXT, INDEX), (TYPE, TEXT, INDEX), \
            (PARENT, TYPE, TEXT, INDEX)]:
        attrdict = {'getNamerTypes': lambda :set(key)}
        if len(key) >= 1 and key[0] == PARENT:
            attrdict['namer'] = ALL[key[1:]]
        elif len(key) >= 2:
            namers = []
            for k in key:
                namers.append(ALL[(k,)])
            attrdict['names'] = namers
        forward = Forward(attrdict)
        ALL[key] = forward
        ALL[(ANCESTOR,) + key] = Forward({
            'getNamerTypes': lambda :set((ANCESTOR,) + key),
            'namer': forward
        })
    PATCHED_ALL = dict()
    for key, forward in ALL.items():
        PATCHED_ALL[key] = Forward({
            'getNamerTypes': forward.getNamerTypes,
            'baseNamer': forward
        })

    @staticmethod
    def namerTypeIsLocal(namerType):
        return namerType != NamerFactory.PARENT and namerType != NamerFactory.ANCESTOR

    @staticmethod
    def register(obj):
        assert isinstance(obj, Namer), obj
        namerType = obj.getNamerTypes()
        target = NamerFactory.getNamer(namerType)
        if not target.isAssigned():
            target.assign(obj)
            clsname = obj.get_classname()
            if clsname == 'com.android.commands.monkey.ape.naming.ActionPatchNamer':
                NamerFactory.register(Namer.init(obj.baseNamer))
            elif clsname == 'com.android.commands.monkey.ape.naming.CompoundNamer':
                for namer in obj.namers:
                    NamerFactory.register(Namer.init(namer))
            elif clsname == 'com.android.commands.monkey.ape.naming.ParentNamer':
                NamerFactory.register(Namer.init(obj.namer))

    @staticmethod
    def getNamer(types):
        assert isinstance(types, set) and \
                (len(types) == 0 or isinstance(next(iter(types)), str)), types
        for key, value in NamerFactory.PATCHED_ALL.items():
            if set(key) == types:
                return value
        from common import setGlobalObject
        setGlobalObject((NamerFactory.PATCHED_ALL, types))
        raise KeyError(types)

    @staticmethod
    def getLocalNamer(namer):
        newTypes = set()
        for namerType in namer.getNamerTypes():
            if NamerFactory.namerTypeIsLocal(namerType):
                newTypes.add(namerType)
        return NamerFactory.getNamer(newTypes)

class Name(JavaClass):
    action_patches = [
        "",
        "enabled=true;",
        "clickable=true;",
        "enabled=true;clickable=true;",
        "checkable=true;",
        "enabled=true;checkable=true;",
        "clickable=true;checkable=true;",
        "enabled=true;clickable=true;checkable=true;",
        "long-clickable=true;",
        "enabled=true;long-clickable=true;",
        "clickable=true;long-clickable=true;",
        "enabled=true;clickable=true;long-clickable=true;",
        "checkable=true;long-clickable=true;",
        "enabled=true;checkable=true;long-clickable=true;",
        "clickable=true;checkable=true;long-clickable=true;",
        "enabled=true;clickable=true;checkable=true;long-clickable=true;",
        "scrollable=true;",
        "enabled=true;scrollable=true;",
        "clickable=true;scrollable=true;",
        "enabled=true;clickable=true;scrollable=true;",
        "checkable=true;scrollable=true;",
        "enabled=true;checkable=true;scrollable=true;",
        "clickable=true;checkable=true;scrollable=true;",
        "enabled=true;clickable=true;checkable=true;scrollable=true;",
        "long-clickable=true;scrollable=true;",
        "enabled=true;long-clickable=true;scrollable=true;",
        "clickable=true;long-clickable=true;scrollable=true;",
        "enabled=true;clickable=true;long-clickable=true;scrollable=true;",
        "checkable=true;long-clickable=true;scrollable=true;",
        "enabled=true;checkable=true;long-clickable=true;scrollable=true;",
        "clickable=true;checkable=true;long-clickable=true;scrollable=true;",
        "enabled=true;clickable=true;checkable=true;long-clickable=true;scrollable=true;",
    ]

    def __init__(self, name_or_tuple):
        if isinstance(name_or_tuple, javaobj.JavaObject):
            super(Name, self).__init__(name_or_tuple, [
                'com.android.commands.monkey.ape.naming.EmptyNamer$1',
                'com.android.commands.monkey.ape.naming.ActionPatchNamer$ActionPatchName',
                'com.android.commands.monkey.ape.naming.TypeNamer$TypeName',
                'com.android.commands.monkey.ape.naming.CompoundNamer$CompoundName',
                'com.android.commands.monkey.ape.naming.IndexNamer$IndexName',
                'com.android.commands.monkey.ape.naming.ParentNamer$ParentName',
                'com.android.commands.monkey.ape.naming.TextNamer$TextName',
                'com.android.commands.monkey.ape.naming.AncestorNamer$AncestorName',
            ])
            self._tuple = None
        else:
            assert isinstance(name_or_tuple, tuple), name_or_tuple
            self._tuple = name_or_tuple
            if name_or_tuple == tuple():
                return
            nametype = name_or_tuple[0]
            if nametype == 'ActionPatch':
                self.baseName = name_or_tuple[1]
                self.patch = name_or_tuple[2]
                self.scrollType = enumToString(name_or_tuple[3])
            elif nametype == 'Type':
                self.klass = name_or_tuple[1]
                self.resourceId = None if len(name_or_tuple) != 3 else name_or_tuple[2]
            elif nametype == 'Compound':
                self.names = name_or_tuple[1]
            elif nametype == 'Index':
                self.index = name_or_tuple[1]
            elif nametype == 'Parent':
                self.parentName = name_or_tuple[1]
                self.localName = name_or_tuple[2]
            elif nametype == 'Text':
                self.text = name_or_tuple[1]
                self.contentDesc = None if len(name_or_tuple) != 3 else name_or_tuple[2]
            elif nametype == 'Ancestor':
                self.names = name_or_tuple[1]
            else:
                raise NotImplementedError(nametype)

    def __eq__(self, other):
        other = Name.init(other)
        return self.tuple == other.tuple

    @property
    def tuple(self):
        if self._tuple is None:
            clsname = self.get_classname()
            if clsname == 'com.android.commands.monkey.ape.naming.EmptyNamer$1':
                self._tuple = tuple()
            elif clsname == 'com.android.commands.monkey.ape.naming.ActionPatchNamer$ActionPatchName':
                self._tuple = ('ActionPatch', Name.init(self.baseName), self.patch,
                        enumToString(self.scrollType))
            elif clsname == 'com.android.commands.monkey.ape.naming.TypeNamer$TypeName':
                if self.resourceId is None or len(self.resourceId) == 0:
                    self._tuple = ('Type', self.klass)
                else:
                    self._tuple = ('Type', self.klass, self.resourceId)
            elif clsname == 'com.android.commands.monkey.ape.naming.CompoundNamer$CompoundName':
                self._tuple = ('Compound', tuple(classReadJavaList(self.names, Name)))
            elif clsname == 'com.android.commands.monkey.ape.naming.IndexNamer$IndexName':
                self._tuple = ('Index', self.index)
            elif clsname == 'com.android.commands.monkey.ape.naming.ParentNamer$ParentName':
                self._tuple = ('Parent', Name.init(self.parentName), Name.init(self.localName))
            elif clsname == 'com.android.commands.monkey.ape.naming.TextNamer$TextName':
                if self.contentDesc is None or self.contentDesc == "":
                    self._tuple = ('Text', self.text)
                else:
                    self._tuple = ('Text', self.text, self.contentDesc)
            elif clsname == 'com.android.commands.monkey.ape.naming.AncestorNamer$AncestorName':
                self._tuple = ('Ancestor', tuple(classReadJavaList(self.names, Name)))
            else:
                raise NotImplementedError(clsname)
        return self._tuple

    def __hash__(self):
        return hash(self.tuple)

    def __repr__(self):
        return repr(self.tuple)

class Namer(JavaClass):
    def __init__(self, namer):
        super(Namer, self).__init__(namer, [
            'com.android.commands.monkey.ape.naming.EmptyNamer',
            'com.android.commands.monkey.ape.naming.ActionPatchNamer',
            'com.android.commands.monkey.ape.naming.TypeNamer',
            'com.android.commands.monkey.ape.naming.CompoundNamer',
            'com.android.commands.monkey.ape.naming.IndexNamer',
            'com.android.commands.monkey.ape.naming.ParentNamer',
            'com.android.commands.monkey.ape.naming.TextNamer',
            'com.android.commands.monkey.ape.naming.AncestorNamer',
        ])
        NamerFactory.register(self)

    def naming(self, node):
        node = treeModule.GUITreeNode.init(node)
        clsname = self.get_classname()
        if clsname == 'com.android.commands.monkey.ape.naming.EmptyNamer':
            return Name(tuple())
        elif clsname == 'com.android.commands.monkey.ape.naming.ActionPatchNamer':
            interactiveProperties = ["isEnabled", "isClickable", "isScrollable",
                    "isLongClickable", "isScrollable"]
            patch = 0
            for prop in interactiveProperties:
                patch <<= 1
                if getattr(node, prop)():
                    patch |= 1
            scrollType = node.getScrollType()
            return Name(('ActionPatch',
                Namer.init(self.baseNamer).naming(node),
                patch,
                enumToString(scrollType)))
        elif clsname == 'com.android.commands.monkey.ape.naming.TypeNamer':
            return Name(('Type', node.getClassName(), node.getResourceID()))
        elif clsname == 'com.android.commands.monkey.ape.naming.CompoundNamer':
            names = []
            for namer in classReadJavaList(self.namers, Namer):
                names.append(namer.naming(node))
            return Name(('Compound', names))
        elif clsname == 'com.android.commands.monkey.ape.naming.IndexNamer':
            return Name(('Index', node.getIndex()))
        elif clsname == 'com.android.commands.monkey.ape.naming.ParentNamer':
            parentNode = node.getParent()
            localName = Namer.init(self.namer).naming(node)
            if parentNode is not None:
                parentName = parentNode.getTempXPathName()
                if parentName is None:
                    parentName = parentNode.getXPathName()
                assert parentName is not None, "Parent name should not be null"
                return Name(('Parent', parentName, localName))
            return Name(('Parent', tuple(), localName))
        elif clsname == 'com.android.commands.monkey.ape.naming.TextNamer':
            return Name(('Text', node.getText(), node.getContentDesc()))
        elif clsname == 'com.android.commands.monkey.ape.naming.AncestorNamer':
            parentNode = node.getParent()
            namerTypes = self.getNamerTypes()
            localNamer = NamerFactory.getLocalNamer(self)
            if parentNode is not None:
                useParent = 'PARENT' in namerTypes
                names = [localNamer.naming(node)]
                if useParent:
                    while parentNode is not None:
                        tempName = parentNode.getTempXPathName()
                        if tempName is None:
                            tempName = parentNode.getXPathName();
                        assert tempName is not None, "Temp name of a parent node should be set."
                        tempNamer = tempName.getNamer()
                        parentNamer = NamerFactory.getLocalNamer(tempNamer)
                        names.append(parentNamer.naming(parentNode))
                        parentNode = parentNode.getParent()
                else:
                    while parentNode is not None:
                        names.append(localNamer.naming(parentNode))
                        parentNode = parentNode.getParent()
                return Name(('Ancestor', reversed(names)))
            return Name(('Ancestor', localNamer.naming(node)))
        else:
            raise NotImplementedError(clsname)

    def getNamerTypes(self):
        ret = set()
        for namerType in self.namerType.elements:
            ret.add(enumToString(namerType))
        return ret

class Namelet(JavaClass):
    def __init__(self, namelet):
        super(Namelet, self).__init__(namelet, 'com.android.commands.monkey.ape.naming.Namelet')

    def __lt__(self, other):
        other = Namelet.init(other)
        if self.depth == other.depth:
            return self.exprStr < other.exprStr
        return self.depth < other.depth

    # to tuple
    def __iter__(self):
        yield self.type.constant
        yield self.exprStr
        yield Namer.init(self.namer)

    def toString(self):
        parent = Namelet.init(self.parent)
        return '[{}][{}][{]][{}][{}]'.format(
            self.type.constant,
            self.depth,
            self.exprStr,
            self.namer.get_class().name,
            parent.toString() if parent is not None else "")

    def filter_Object(self, tree):
        assert isinstance(tree, etree._Element), tree
        print(self.exprStr)
        return etree.XPath(self.exprStr)(tree)

class Naming(JavaClass):
    def __init__(self, naming):
        super(Naming, self).__init__(naming, 'com.android.commands.monkey.ape.naming.Naming')

    def equivalent(self, other):
        other = Naming(other)
        return set(Namelet.init(nl) for nl in self.namelets) == \
                set(Namelet.init(nl) for nl in other.namelets)

    def select_Document(self, document):
        assert isinstance(document, etree._Element)
        ret = dict()
        for namelet in classReadJavaList(self.namelets, Namelet):
            nodes = namelet.filter_Object(document)
            for node in nodes:
                try:
                    ret[node].append(namelet)
                except KeyError:
                    ret[node] = [namelet]
        return ret

    def select_LNamelet(self, namelets):
        namelets = classReadJavaList(namelets, Namelet)
        if len(namelets) == 1:
            return namelets[0]
        namelets.sort()
        for i in range(len(namelets)):
            namelet = Namelet.init(namelets[i].parent)
            while namelet is not None:
                if namelet < namelets[0]:
                    break
                namelet = Namelet.init(namelet.parent)
            if namelet is None:
                return namelets[i]
        return None

    def namingInternal_DocumentBoolean(self, tree, updateNodeName):
        # document
        # results = namingInternal(document, true)
        # results : Name -> (tree.GUITreeNode -> Namelet)
        nameToNodes = dict()
        elementToNamelets = self.select_Document(tree)
        queue = [tree]
        while queue:
            current_element = queue.pop(0)
            from common import setGlobalObject
            setGlobalObject((self, tree, elementToNamelets, current_element))
            namelets = elementToNamelets[current_element]
            assert namelets
            namelet = self.select_LNamelet(namelets)
            assert namelet
            namer = namelet.namer
            treeNode = dom.getGUITreeNode(current_element)

            name = Namer.init(namer).naming(treeNode)
            addToMapMap(nameToNodes, Name, name, treeModule.GUITreeNode, treeNode, namelet)
            treeNode.xpathName = name
            treeNode.currentNamelet = namelet

            children = current_element.getchildren()
            for child in children:
                if child is not None:
                    queue.append(child)
        results = NamingResult(nameToNodes)
        return results

    def naming(self, tree, updateNodeName):
        tree = treeModule.GUITree.init(tree)
        document = tree.getDocument()
        results = self.namingInternal_DocumentBoolean(document, updateNodeName)
        # self.treeToNamingResult.put(tree, results)
        return results

class NamingResult:
    def __init__(self, nameToNodes):
        names = list(nameToNodes.keys())
        nodes = []
        namelets = []
        nodeSize = 0
        for i, name in enumerate(names):
            m = nameToNodes[name]
            if len(m) == 1:
                nodeSize += 1
                nodes.append(next(iter(m.keys())))
                namelets.append(next(iter(m.values())))
            else:
                nodelist, nameletlist = [], []
                for node, namelet in m.items():
                    nodelist.append(node)
                    nameletlist.append(namelet)
                    nodeSize += 1
                nodes.append(nodelist)
                namelets.append(nameletlist)

        self.names = names
        self.nodes = nodes
        self.namelets = namelets
        self.nodeSize = nodeSize

    def getNames(self):
        return self.names

    def getNodes(self):
        return self.nodes
