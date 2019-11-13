''' What to do?
1. Number of InTransitions and OutTransitions for targetState
2. Subsequences with crash
3. After targetState is met, What kind of next transitions would be there before targetState..?
4. First met of targeting ~ Total count for transition may be correlated
5. precision / recall on GUITreeTransition ~ metTarget

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
from common import readJavaList, JavaClass
from tree import GUITree, GUITreeBuilder_getStateKey
from model import StateKey, State
from naming import StateNamingManager

graph = None
model = None

class Model(JavaClass):
    def __init__(self, model):
        super(Model, self).__init__(model, "com.android.commands.monkey.ape.model.Model")

    def rebuild(self, tree):
        '''
        GUITreeBuilder treeBuilder = new GUITreeBuilder(namingManager, tree);
        return treeBuilder.getGUITree();
        '''
        tree = GUITree.init(tree)
        namingManager = StateNamingManager.init(self.namingManager)
        activity = tree.getActivityName()
        document = tree.getDocument()

        # GUITreeBuilder.rebuildGUITree()
        current = namingManager.getNaming(tree)
        results = current.naming(tree, True)
        tree.setCurrentNaming(current, results.getNames(), results.getNodes())
        tree.setCurrentState(None)

        return tree

    def getState(self, tree):
        naming = tree.getCurrentNaming()
        stateKey = GUITreeBuilder_getStateKey(naming, tree)
        state = Graph.init(self.graph).getOrCreateState(stateKey)
        # tree.setCurrentState(state)
        return state

class Graph(JavaClass):
    def __init__(self, grpah):
        super(Graph, self).__init__(graph, "com.android.commands.monkey.ape.model.Graph")

    def getOrCreateState(self, stateKey):
        stateKey = StateKey.init(stateKey)
        state = None
        for key, value in self.keyToState.items():
            if StateKey(key) == stateKey:
                state = value
        if state is None:
            print('Warning: unknown state, newly create state')
            return None
        return State.init(state)

def GUITreeToState(model, graph, tree):
    # Model.rebuild(GUITree tree)
    # GetState(tree)
    model = Model.init(model)
    namingManager = model.namingManager
    return model.getState(model.rebuild(tree))


    # # Naming getNaming(GUITree tree) from AbstractNamingManager
    # if id(guitree) in map(id, namingManager.treeToNaming.keys()):
    #     return namingManager.treeToNaming[guitree]

    # componentName = (guitree.activityPackageName, guitree.activityClassName)
    # guitreenode = guitree.rootNode
    # document = treeNodeToXmlNode(guitreenode)

    # namingManager
    # tree.document
    # tree.activityName
    
    # # GUITreeBuilder.rebuildGUITree
    # # Naming current = namingManager.getNaming(tree);
    # current = None
    # if 1:
    #     # getBaseNaming
    #     source = namingManager.namingFactory.base
    #     while 1:
    #         state = getStateKey(source, tree)
    #         if source not in namingManager.namingToEdge:
    #             target = None
    #         else:
    #             tmp = namingManager.namingToEdge[source]
    #             if state not in tmp:
    #                 target = None
    #             else:
    #                 target = namingManager.namingToEdge[source][state]
    #         if target is None:
    #             current = source
    #             break
    #         source = target

    # # NamingResult results = current.naming(tree, true);
    # if 1:
    #     results = Naming.init(current).namingInternal_DocumentBoolean(document, True)
    #     # tree.setCurrentNaming(current, results.names, results.nodes);
    #     if 1:
    #         tree.currentNaming = current
    #         tree.currentNames = results.names
    #         tree.currentNode = results.nodes
    #     tree.currentState = None

    # # Model.checkAndAddStateData
    # if 1:
    #     # Naming naming = tree.getCurrentNaming();
    #     naming = tree.currentNaming

    #     # StateKey stateKey = GUITreeBuilder.getStateKey(naming, tree);
    #     stateKey = StateKey.init(naming, tree.activityName, tree.currentNames)

    #     # State state = graph.getOrCreateState(stateKey);
    #     for prevStateKey in readJavaList(graph.keyToState):
    #         if stateKey == StateKey.init(stateKey):
    #             return graph.keyToState[prevStateKey]
    # return None

def describeGUITreeAction(action):
    typ = action.action.type.constant
    print('Action type {}'.format(typ))
    guitreenode = action.node
    if guitreenode:
        GUITreeNode(guitreenode).describe()

def describeActionRecord(ar):
    if ar.modelAction:
        print('ModelAction type', ar.modelAction.type.constant)
    if ar.guiAction:
        describeGUITreeAction(ar.guiAction)

def getTargetStates(model, graph):
    guitrees = readJavaList(graph.metTargetMethodGUITrees)
    states = set()
    for guitree in guitrees:
        states.add(guitree.currentState)

    return states

def getTargetTransitions(model, graph):
    ret = []
    for gt in graph.treeTransitionHistory:
        assert gt.hasMetTargetMethod in [True, False]
        if gt.hasMetTargetMethod:
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

def reportCrash(crash):
    import datetime
    print("Crash at {}".format(
            datetime.datetime.fromtimestamp(crash.timeMillis / 1000).strftime("%Y-%m-%d %H:%M:%S")))
    print("Short Message", crash.shortMsg)
    print("Long Message", crash.longMsg)
    print("Stacktrace")
    for line in crash.stackTrace.split('\n'):
        print(" $", line)

class Subsequence:
    idx = 0
    def __init__(self, gt):
        self.treeTransitions = [gt]
        self.actionRecordsAtEnd = []
        self.idx = Subsequence.idx
        Subsequence.idx += 1

    def append(self, gt):
        self.treeTransitions.append(gt)

    def crashReport(self):
        if len(self.actionRecordsAtEnd) == 0:
            return
        directCrash = self.actionRecordsAtEnd[0].modelAction.type.constant == 'PHANTOM_CRASH'
        if directCrash:
            print("Subsequence #{} CRASH".format(self.idx))
            reportCrash(self.actionRecordsAtEnd[0].modelAction.crash)
        else:
            actions = []
            for ar in self.actionRecordsAtEnd:
                action = ar.modelAction
                constant = action.type.constant
                actions.append(action)
                if constant == 'PHANTOM_CRASH':
                    print('Subsequence #{} indirect CRASH'.format(self.idx))
                    print(' - records [{}]'.format(' / '.join(map(lambda act:act.type.constant, actions))))
                    reportCrash(action.crash)

    def appendActionRecord(self, act):
        self.actionRecordsAtEnd.append(act)

    def __getattr__(self, attr):
        return self.treeTransitions.__getattr__(attr)

    def __getitem__(self, item):
        return self.treeTransitions.__getitem__(item)

    def __len__(self):
        return self.treeTransitions.__len__()

class TargetSubsequence:
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

def getSubsequences(model, graph):
    # nonModelActions = ['EVENT_START', 'EVENT_RESTART', 'EVENT_CLEAN_RESTART',
    #     'FUZZ', 'EVENT_ACTIVATE', 'PHANTOM_CRASH', 'MODEL_BACK']
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
            if sequences:
                sequences[-1].appendActionRecord(records[tmp_idx])
            tmp_idx += 1
        if curguitree is None or tmp_idx != ar_idx:
            sequences.append(Subsequence(gt))
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
        print(' - state {} numIn {} numOut {}'.format(State.init(target), len(s2i[target]), len(s2o[target])))

    # describe targetTransitions
    targetTransitions

# 2. Subsequeces with crashes
def check2(model, graph):
    subsequences = getSubsequences(model, graph)
    for subsequence in subsequences:
        subsequence.crashReport()
    return subsequences


# 3. After targetState is met, What kind of next transitions would be there before targetState..?
def check3(model, graph, subsequences):
    targetStates = getTargetStates(model, graph)
    targetStateIds = list(map(id, targetStates))

    if subsequences is None:
        sys.exit(1)
    subseqCounter = dict()
    for seq in subsequences:
        targetSubsequence = TargetSubsequence(seq[0])
        for tr in seq[1:]:
            if id(tr.source.currentState) in targetStateIds:
                try:
                    subseqCounter[targetSubsequence] += 1
                except KeyError:
                    subseqCounter[targetSubsequence] = 1
                targetSubsequence = TargetSubsequence(tr)
            else:
                targetSubsequence.append(tr)
        try:
            subseqCounter[targetSubsequence] += 1
        except KeyError:
            subseqCounter[targetSubsequence] = 1
    print("Num subsequences", len(subseqCounter))
    print("Subsequences called >= 3 times :", len([0 for seq in subseqCounter if subseqCounter[seq] >= 3]))
    for seq in sorted(subseqCounter.keys(), key=lambda k:subseqCounter[k]):
        if subseqCounter[seq] >= 3:
            print(subseqCounter[seq], seq)

    return subsequences

# 4. First met of targeting ~ Total count for transition may be correlated
def check4(model, graph):
    transitions = graph.treeTransitionHistory
    metTargetTransition = None
    for t in transitions:
        if t.metTargetMethodScore == 0:
            metTargetTransition = t

    if metTargetTransition is None:
        return

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
    subsequences = check2(model, graph)
    check3(model, graph, subsequences)
    return subsequences

if __name__ == "__main__":
    if len(sys.argv) >= 2:
        subsequences = checkobj(sys.argv[1])

        # transitions = graph.treeTransitionHistory
        # trees = [GUITree.init(t.source) for t in transitions]
        # tree = trees[0]
        # print(tree.getCurrentState())
        # state = GUITreeToState(model, graph, tree)
