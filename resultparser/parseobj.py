''' What to do?
1. Number of InTransitions and OutTransitions for targetState
2. First met of targeting ~ Total count for transition may be correlated
3. After targetState is met, What kind of next transitions would be there before targetState..?
4. precision / recall on GUITreeTransition ~ metTarget

Start s1 s2 ... targetState ~ si ~ targetState ~ sj end

[Model.java]
    NamingManager namingManager;
    Graph graph;
    List<ActionRecord> actionHistory = new ArrayList<ActionRecord>();
    EnumCounters<ModelEvent> eventCounters = new EnumCounters<ModelEvent>() { ... }

[Graph.java]
    String graphId;
    int timestamp;
    Map<String, ActivityNode> activities
    Map<StateTransition, StateTransition> edges;
    Set<GUITree> entryGUITrees;
    Set<GUITree> cleanEntryGUITrees;
    Set<State> entryStates;
    Set<State> cleanEntryStates;
    Map<StateKey, State> keyToState;
    Map<String, Map<Name, Set<ModelAction>>> nameToActions;
    Map<Naming, Set<State>> namingToStates;
    Map<State, Map<StateTransition, StateTransition>> stateToInStateTransitions;
    Map<State, Map<StateTransition, StateTransition>> stateToOutStateTransitions;
    Map<ModelAction, Map<StateTransition, StateTransition>> actionToOutStateTransitions;
    Set<ModelAction> unvisitedActions;
    Set<ModelAction> visitedActions;
    List<GUITreeTransition> treeTransitionHistory;
    List<GUITree> metTargetMethodGUITrees;

[GUITree.java]
    int timestamp;
    final GUITreeNode rootNode;
    final String activityClassName;
    final String activityPackageName;
    Naming currentNaming;
    State currentState;
    Name[] currentNames; // names for the nodes at the same index in currentNodes
    Object[] currentNodes; // An element of this array may be a node or an array of nodes

[State.java]

[GUITreeTransition.java]
    final GUITree source;
    final GUITree target;
    final GUITreeAction action;
    StateTransition stateTransition;
    int metTargetMethodScore;

[GUITree.java]
    int timestamp;
    final GUITreeNode rootNode;
    final String activityClassName;
    final String activityPackageName;
    Naming currentNaming;
    State currentState;
    Name[] currentNames; // names for the nodes at the same index in currentNodes
    Object[] currentNodes; // An element of this array may be a node or an array of nodes
'''

import sys
import javaobj

graph = None
model = None




def Describe(javaobj):
    # clsname = javaobj.get_class().name
    # if clsname == 'State':
    #     return State_toString(javaobj)
    # elif clsname == 
    pass

def Namer(obj):
    if obj is None:
        return None
    if obj.get_class().name == 'com.android.commands.monkey.ape.naming.EmptyNamer':
        return ''
    if obj.get_class().name == 'com.android.commands.monkey.ape.naming.ActionPatchNamer':
        return ('ActionPatchNamer', Namer(obj.baseNamer))
    elif obj.get_class().name == 'com.android.commands.monkey.ape.naming.TypeNamer':
        return 'TypeNamer' # TypeNamer[type,resource-id]
    elif obj.get_class().name == 'com.android.commands.monkey.ape.naming.CompoundNamer':
        return ('CompoundNamer', tuple(map(Namer, obj.namers)))
    elif obj.get_class().name == 'com.android.commands.monkey.ape.naming.IndexNamer':
        return 'IndexNamer' # IndexNamer[index]
    elif obj.get_class().name == 'com.android.commands.monkey.ape.naming.ParentNamer':
        return ('ParentNamer', Namer(obj.namer))
    elif obj.get_class().name == 'com.android.commands.monkey.ape.naming.TextNamer':
        return 'TextNamer' # TextNamer[text,content-desc]
    elif obj.get_class().name == 'com.android.commands.monkey.ape.naming.AncestorNamer$AncestorName':
        return ('AncestorNamer', Namer(obj.namer))
    else:
        raise NotImplementedError(obj.get_class().name)

def Namelet(obj):
    if obj is None:
        return None
    assert obj.get_class().name == 'com.android.commands.monkey.ape.naming.Namelet', obj
    return (obj.type.constant, obj.exprStr, Namer(obj.namer))

def Naming(obj):
    if obj is None:
        return None
    assert obj.get_class().name == 'com.android.commands.monkey.ape.naming.Naming', obj
    return set(Namelet(nl) for nl in obj.namelets)

def StateKey(obj):
    if obj is None:
        return None
    assert obj.get_class().name == 'com.android.commands.monkey.ape.model.StateKey', obj
    return (obj.activity, Naming(obj.naming), [Name_toString(name) for name in obj.widgets])

def State(obj):
    if obj is None:
        return None
    assert obj.get_class().name == 'com.android.commands.monkey.ape.model.State', obj
    return StateKey(obj.stateKey)

def describeGUITree(guitree):
    print('GUITree ---')
    print('  timestamp', guitree.timestamp)
    print('  activityClassName', guitree.activityClassName)
    print('  activityPackageName', guitree.activityPackageName)
    print('  rootNode', guitree.rootNode)

namerPatches = [
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
assert len(namerPatches) == 32

def Name_toString(nm):
    if nm is None or nm.get_class().name == 'com.android.commands.monkey.ape.naming.EmptyNamer$1':
        return ''
    if nm.get_class().name == 'com.android.commands.monkey.ape.naming.ActionPatchNamer$ActionPatchName':
        return Name_toString(nm.baseName) + namerPatches[nm.patch]
    elif nm.get_class().name == 'com.android.commands.monkey.ape.naming.TypeNamer$TypeName':
        if nm.resourceId is None or len(nm.resourceId) == 0:
            return 'class={};'.format(nm.klass)
        return 'class={};resource-id={};'.format(nm.klass, nm.resourceId)
    elif nm.get_class().name == 'com.android.commands.monkey.ape.naming.CompoundNamer$CompoundName':
        return ''.join(Name_toString(c) for c in nm.names)
    elif nm.get_class().name == 'com.android.commands.monkey.ape.naming.IndexNamer$IndexName':
        return 'index={};'.format(nm.index)
    elif nm.get_class().name == 'com.android.commands.monkey.ape.naming.ParentNamer$ParentName':
        return '{}/{}'.format(Name_toString(nm.parentName), Name_toString(nm.localName))
    elif nm.get_class().name == 'com.android.commands.monkey.ape.naming.TextNamer$TextName':
        if nm.contentDesc is None or len(nm.contentDesc) == 0:
            return 'text={};'.format(nm.text)
        return 'text={};content-desc={};'.format(nm.text, nm.contentDesc)
    elif nm.get_class().name == 'com.android.commands.monkey.ape.naming.AncestorNamer$AncestorName':
        return '/{}'.format('/'.join([Name_toString(c) for c in nm.names]))
    else:
        raise NotImplementedError(nm.get_class().name)

def Namelet_toString(nl):
    return '[{}][{}][{]][{}][{}]'.format(
        nl.type.constant,
        nl.depth,
        nl.exprStr,
        nl.namer.get_class().name,
        Namelet_toString(nl.parent))

def State_toString(st):
    # State extends GraphElement
    # super.toString() + this.stateKey.toString() + "[A=" + this.actions.length + "]";
    stateKey = st.stateKey
    def getGraphId(elem):
        assert isinstance(elem.id, javaobj.JavaString)
        return elem.id
    ret = '{}[{},{}][{}]'.format(getGraphId(st),
            st.firstVisitTimestamp, st.lastVisitTimestamp,
            st.visitedCount)
    ret += '{}@{}@{}@[W={}]'.format(stateKey.activity, stateKey.hashCode,
            stateKey.naming.namingName, len(stateKey.widgets))
    ret += '[A={}]'.format(len(st.actions))
    # additional for naming namelets
    ret += '/'.join([','.join([e.constant for e in nl.namer.namerType.elements]) for nl in stateKey.naming.namelets])

    return ret

def GUITreeNode_getIndexPath(node):
    if node.indexPath:
        return node.indexPath
    if node.parent:
        return '{}-{}'.format(GUITreeNode_getIndexPath(node.parent), node.index)
    return str(node.index)

def describeGUITreeNode(node):
    print('IndexPath [{}]'.format(GUITreeNode_getIndexPath(node)))
    print(' - resourceId', node.resourceId)
    print(' - className', node.className)
    print(' - packageName', node.packageName)

def describeGUITreeAction(action):
    typ = action.action.type.constant
    print('Action type {}'.format(typ))
    guitreenode = action.node
    if guitreenode:
        describeGUITreeNode(guitreenode)

def describeActionRecord(ar):
    if ar.modelAction:
        print('ModelAction type', ar.modelAction.type.constant)
    if ar.guiAction:
        describeGUITreeAction(ar.guiAction)

def readJavaList(l):
    if l.get_class().name == 'java.util.Collections$SingletonList':
        return [l.element]
    else:
        assert l.get_class().name == 'java.util.ArrayList', l.get_class().name
        return l

def getTargetStates(model, graph):
    guitrees = readJavaList(graph.metTargetMethodGUITrees)
    states = set()
    for guitree in guitrees:
        states.add(guitree.currentState)

    return states

def getTargetTransitions(model, graph):
    ret = []
    for gt in graph.treeTransitionHistory:
        if gt.metTargetMethodScore == 0:
            ret.append(gt)

    return ret

def getTargetTransitions_nt(model, graph):
    ret = []
    for gt in graph.treeTransitionHistory:
        if gt.action.node and gt.action.node.resourceId == 'org.gnucash.android:id/fab_create_account' and \
                gt.action.action.type.constant == 'MODEL_CLICK':
            ret.append(gt)

    return ret

def getTargetStates_nt(model, graph):
    ret = set()
    transitions = getTargetTransitions_nt(model, graph)
    for tr in transitions:
        ret.add(tr.source.currentState)

    return ret

def getSubsequences(model, graph, verbose = False):
    # evaluate subsequences
    # transitions from graph.treeTransitionHistory
    # subsequences = [[transition#1, transition#2], [transition#3, transition#4, ...] ...]
    subsequences = []
    nonModelActions = ['EVENT_START', 'EVENT_RESTART', 'EVENT_CLEAN_RESTART',
        'FUZZ', 'EVENT_ACTIVATE', 'PHANTOM_CRASH', 'MODEL_BACK']
    nonModelActionsWOBack = nonModelActions[:-1]
    curguitree = None
    records = model.actionHistory
    record_idx = 0
    last_match_idx = 0
    for i, gt in enumerate(readJavaList(graph.treeTransitionHistory)):
        # evaluate matching between ActionRecords and GUITreeTransitions
        # Assumption: ActionRecords' actions contain all of GUITreeTransitions' actions.
        if verbose:
            print('i, record_idx', i, record_idx)
        if records[record_idx].guiAction is None or (id(gt.action) != id(records[record_idx].guiAction) and records[record_idx].modelAction.type.constant == 'MODEL_BACK'):
            if verbose:
                print('strategy #1')
            if gt.action.action.type.constant == 'MODEL_BACK':
                actionsToAvoid = nonModelActionsWOBack
                curidx = last_match_idx + 1
            else:
                actionsToAvoid = nonModelActions
                curidx = record_idx
            nxtNonModelActionIdx = []
            while curidx < len(records) and records[curidx].modelAction.type.constant in actionsToAvoid:
                nxtNonModelActionIdx.append(curidx)
                curidx += 1
            if verbose:
                print('strategy #1 ', nxtNonModelActionIdx)
            if nxtNonModelActionIdx:
                curguitree = None
                record_idx = nxtNonModelActionIdx[-1] + 1
        # if there is no match, check next nonModelAction group induced a crash
        elif id(gt.action) != id(records[record_idx].guiAction):
            if verbose:
                print('strategy #2')
            if gt.action.action.type.constant == 'MODEL_BACK':
                actionsToAvoid = nonModelActionsWOBack
                curidx = last_match_idx + 1
            else:
                actionsToAvoid = nonModelActions
                curidx = record_idx + 1
            nxtNonModelActionIdx = []
            crashed_or_back = False
            while curidx < len(records) and records[curidx].modelAction.type.constant in actionsToAvoid:
                nxtNonModelActionIdx.append(curidx)
                if records[curidx].modelAction.type.constant in ['MODEL_BACK', 'PHANTOM_CRASH']:
                    crashed_or_back = True
                # print('records[curidx].modelAction.type.constant', records[curidx].modelAction.type.constant, crashed_or_back)
                curidx += 1
            if verbose:
                print('strategy #2 ', nxtNonModelActionIdx)
            if crashed_or_back:
                curguitree = None
                record_idx = nxtNonModelActionIdx[-1] + 1
            else:
                print('ActionOnTransition #{} ----'.format(i))
                describeGUITreeAction(gt.action)
                print()
                print('ActionRecords #{} ----'.format(record_idx))
                describeActionRecord(records[record_idx])
                print()
                return None
        # DEBUG
        # if gt.source:
        #     print('source')
        #     describeGUITree(gt.source)
        #     for name in gt.source.currentNames:
        #         print(' ', Name_toString(name))
        # if gt.target:
        #     print('target')
        #     describeGUITree(gt.target)
        #     for name in gt.target.currentNames:
        #         print(' ', Name_toString(name))

        # curguitree is target state of previous transition
        if curguitree is None:
            subsequences.append([gt])
            last_match_idx = record_idx
        else:
            assert id(curguitree) == id(gt.source)
            subsequences[-1].append(gt)
            last_match_idx = record_idx
        curguitree = gt.target
        record_idx += 1
    return subsequences

def getSubsequences2(model, graph):
    records = model.actionHistory
    transitions = graph.treeTransitionHistory
    curguitree = None
    sequences = []
    ar_idx = 0
    for tr_idx, gt in enumerate(readJavaList(transitions)):
        cur_action = transitions[tr_idx].action
        assert cur_action is not None, tr_idx
        cur_action_id = id(cur_action)
        tmp_idx = ar_idx
        while not (records[tmp_idx].guiAction and id(records[tmp_idx].guiAction) == cur_action_id):
            tmp_idx += 1
        if curguitree is None or tmp_idx != ar_idx:
            sequences.append([gt])
        else:
            assert id(curguitree) == id(gt.source), (tr_idx, ar_idx)
            sequences[-1].append(gt)
        curguitree = gt.target
        ar_idx = tmp_idx + 1
    return sequences

def debugTransitions(model, graph, tridx, aridx, interval = 3):
    print('[TRANSITIONS]')
    ttrs = graph.treeTransitionHistory
    for idx in range(max(0, tridx-interval), min(tridx+interval-1, len(ttrs)-1)):
        print(' - transition #{}{}'.format(idx, ' <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<' if idx == tridx else ''))
        describeGUITreeAction(ttrs[idx].action)
        print()
    print('[ACTIONRECORDS]')
    ars = model.actionHistory
    for idx in range(max(0, aridx-interval), min(aridx+interval-1, len(ars)-1)):
        print(' - actionrecord #{}{}'.format(idx, ' <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<' if idx == aridx else ''))
        describeActionRecord(ars[idx])
        print()

def check0(model, graph):
    # stateToInStateTransitions[state][statetr1] = statetr1 for any statetr1
    s2i = graph.stateToInStateTransitions
    s2o = graph.stateToOutStateTransitions
    for st2st in s2i.values():
        assert all(id(st2st[k]) == id(k) for k in st2st)

    for st2st in s2o.values():
        assert all(id(st2st[k]) == id(k) for k in st2st)

    # targets and gui transition's targets check
    stateTransitions = []
    for gt in graph.treeTransitionHistory:
        st = gt.stateTransition
        if st.missingCount >= 1:
            if id(st) not in stateTransitions:
                stateTransitions.append(id(st))
                for gt in readJavaList(st.treeTransitions):
                    assert id(gt.source.currentState) == id(st.source)
                    assert id(gt.target.currentState) == id(st.target)
                    # print('%08X %08X' % (id(gtransition.source.currentState), id(gtransition.target.currentState)))
        else:
            assert id(gt.source.currentState) == id(st.source)
            assert id(gt.target.currentState) == id(st.target)

    # @TODO actions would be non-deterministic


# 1. Number of InTransitions and OutTransitions for targetState
def check1(model, graph):
    '''
    Map<State, Map<StateTransition, StateTransition>> stateToInStateTransitions;
    Map<State, Map<StateTransition, StateTransition>> stateToOutStateTransitions;
    '''
    targets = getTargetStates(model, graph)
    targetTransitions = getTargetTransitions(model, graph)
    s2i = graph.stateToInStateTransitions
    s2o = graph.stateToOutStateTransitions
    print('#Target States {} #Target Transitions {}'.format(len(targets), len(targetTransitions)))
    for target in targets:
        print(' - state {} numIn {} numOut {}'.format(State_toString(target), len(s2i[target]), len(s2o[target])))

    # describe targetTransitions
    targetTransitions


# 2. First met of targeting ~ Total count for transition may be correlated
def check2(model, graph):
    transitions = graph.treeTransitionHistory
    metTargetTransition = None
    for t in transitions:
        if t.metTargetMethodScore == 0:
            metTargetTransition = t

    if metTargetTransition is None:
        return

# 3. After targetState is met, What kind of next transitions would be there before targetState..?
def check3(model, graph):
    targetStates = getTargetStates(model, graph)
    targetStateIds = list(map(id, targetStates))

    class SubSequence:
        def __init__(self, tr = None):
            self.transitions = []
            if tr is not None:
                self.transitions.append(tr)
            self._hash = None
            self._score = None
            self._ssq = None

        def append(self, tr):
            assert tr.get_class().name == "com.android.commands.monkey.ape.tree.GUITreeTransition"
            self.transitions.append(tr)

        def __hash__(self):
            if self._hash is None:
                val = 0
                for tr in self.transitions:
                    val += hash(tr.stateTransition)
                    val *= 31
                    val &= 0xFFFFFFFF
                self._hash = val
            return self._hash

        def __eq__(self, other):
            if len(other.transitions) != len(self.transitions):
                return False
            return all(id(self.transitions[i].stateTransition) == id(other.transitions[i].stateTransition) \
                    for i in range(len(self.transitions)))

        @property
        def score(self):
            if self._score is not None:
                return self._score
            score = 0
            if id(self.transitions[0].source.currentState) in targetStateIds:
                score += 2
            if id(self.transitions[-1].target.currentState) in targetStateIds:
                score += 1
            self._score = score
            return score

        def __lt__(self, other):
            selfScore = self.score
            otherScore = other.score
            if selfScore == otherScore:
                if len(self.transitions) == len(other.transitions):
                    for setr, ottr in zip(self.transitions, other.transitions):
                        if id(setr.stateTransition) != id(ottr.stateTransition):
                            seFirstVisitTimestamp = setr.stateTransition.firstVisitTimestamp
                            otFirstVisitTimestamp = ottr.stateTransition.firstVisitTimestamp
                            assert seFirstVisitTimestamp != otFirstVisitTimestamp
                            return seFirstVisitTimestamp < otFirstVisitTimestamp
                    return False
                return len(self.transitions) < len(other.transitions)
            return selfScore < otherScore

        def getStateSequence(self):
            # just state sequence, but consecutive same states are compressed to single state
            if self._ssq is not None:
                return self._ssq

            ret = [self.transitions[0].source.currentState]
            for tr in self.transitions:
                state = tr.target.currentState
                if id(state) != id(ret[-1]):
                    ret.append(state)

            self._ssq = ret
            return ret

        def __repr__(self):
            # print states
            return '<SubSequence len={}, states={}>'.format(len(self.transitions),
                ','.join(map(lambda s:str(s.firstVisitTimestamp), self.getStateSequence())))

    subsequences_list = getSubsequences2(model, graph)
    if subsequences_list is None:
        sys.exit(1)
    subseqCounter = dict()
    for seq in subsequences_list:
        cursubseq = SubSequence(seq[0])
        for tr in seq[1:]:
            if id(tr.source.currentState) in targetStateIds:
                try:
                    subseqCounter[cursubseq] += 1
                except KeyError:
                    subseqCounter[cursubseq] = 1
                cursubseq = SubSequence(tr)
            else:
                cursubseq.append(tr)
        try:
            subseqCounter[cursubseq] += 1
        except KeyError:
            subseqCounter[cursubseq] = 1
    print("Num subsequences", len(subseqCounter))
    print("Subsequences called >= 3 times :", len([0 for seq in subseqCounter if subseqCounter[seq] >= 3]))
    for seq in sorted(subseqCounter.keys(), key=lambda k:subseqCounter[k]):
        if subseqCounter[seq] >= 3:
            print(subseqCounter[seq], seq)

    return subseqCounter

# sanity 
def sanity_gt_st(model, graph):
    st2gt = {}
    for gt in graph.treeTransitionHistory:
        st = gt.stateTransition
        try:
            st2gt[st].append(gt)
        except KeyError:
            st2gt[st] = [gt]

    for st in st2gt:
        # list with single element is java.util.Collections$SingletonList
        # How about the case of list with no element?
        treeTransitions = st.treeTransitions
        if treeTransitions.get_class().name == 'java.util.Collections$SingletonList':
            assert len(st2gt[st]) == 1 and id(treeTransitions.element) == id(st2gt[st][0])
        else:
            assert len(treeTransitions) == len(st2gt[st]), (len(treeTransitions), len(st2gt[st]))
            assert set(treeTransitions) == set(st2gt[st])

def checkobj(fname):
    global model, graph
    with open(fname, "rb") as fd:
        jobj = fd.read()
    model = javaobj.loads(jobj)
    graph = model.graph
    check0(model, graph)
    check1(model, graph)
    check3(model, graph)

if __name__ == "__main__":
    checkobj(sys.argv[1])
