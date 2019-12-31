from common import readJavaList, classReadJavaList, JavaClass
import naming as namingModule
import tree as treeModule

class StateKey(JavaClass):
    def __init__(self, *args):
        if len(args) == 1:
            super(StateKey, self).__init__(args[0], "com.android.commands.monkey.ape.model.StateKey")
        elif len(args) == 3:
            super(StateKey, self).__init__(None)
            self.activity, self.naming, self.widgets = args
        else:
            raise ValueError("# arguments must be 1 or 3")

    def __hash__(self):
        return hash((self.activity, namingModule.Naming.init(self.naming), \
            tuple(classReadJavaList(self.widgets, namingModule.Name))))

    def __eq__(self, other):
        other = StateKey.init(other)
        if other is None:
            return False
        if self.activity != other.activity:
            return False
        if namingModule.Naming.init(self.naming) != namingModule.Naming.init(other.naming):
            return False
        return classReadJavaList(self.widgets, namingModule.Name) == classReadJavaList(other.widgets, namingModule.Name)

    def getNaming(self):
        return namingModule.Naming.init(self)

class State(JavaClass):
    def __init__(self, state):
        super(State, self).__init__(state, 'com.android.commands.monkey.ape.model.State')

    def __eq__(self, other):
        other = State.init(other)
        if other is None:
            return False
        return StateKey.init(self.stateKey) == StateKey.init(other.stateKey)

    def __hash__(self):
        result = 1
        result = 31  * result + 0 if self.stateKey is None else hash(StateKey.init(self.stateKey))
        return result

    def __repr__(self):
        # State extends GraphElement
        # super.toString() + this.stateKey.toString() + "[A=" + this.actions.length + "]";
        stateKey = self.stateKey
        ret = '{}[{},{}][{}]'.format(self.id,
                self.firstVisitTimestamp, self.lastVisitTimestamp,
                self.visitedCount)
        ret += '{}@{}@{}@[W={}]'.format(stateKey.activity, stateKey.hashCode,
                stateKey.naming.namingName, len(readJavaList(stateKey.widgets)))
        ret += '[A={}]'.format(len(readJavaList(self.actions)))
        # additional for naming namelets
        ret += '/'.join([','.join([e.constant for e in nl.namer.namerType.elements]) for nl in stateKey.naming.namelets])

        return ret

    def getGraphId(self):
        return self.id if self.id is not None else ""

    @staticmethod
    def buildStateKey(naming, componentName, currentNames):
        naming = namingModule.Naming.init(naming)
        widgets = classReadJavaList(currentNames, namingModule.Name)
        return StateKey(componentName, naming, widgets)

class StateTransition(JavaClass):
    def __init__(self, statetransition):
        super(StateTransition, self).__init__(statetransition, 'com.android.commands.monkey.ape.model.StateTransition')

    def getGUITreeTransitions(self):
        return classReadJavaList(self.treeTransitions, treeModule.GUITreeTransition)

    def getGraphId(self):
        return self.id if self.id is not None else ""

    def metTargetRatio(self):
        treeTransitions = self.getGUITreeTransitions()
        totalValue = 0
        for gtransition in treeTransitions:
            if gtransition.hasMetTargetMethod:
                totalValue += 1

        if len(treeTransitions) == 0:
            return 0.0
        else:
            return totalValue / len(treeTransitions)

    def __repr__(self):
        # StateTransition extends GraphElement
        super_toString = "%s[%d,%d][%d]" \
            % (self.getGraphId(), self.firstVisitTimestamp, self.lastVisitTimestamp, self.visitedCount)

        return "%s@[H(%d),M(%d),T(%f)] %s =[%s]=> %s" \
            % (super_toString, self.hittingCount, self.missingCount, self.theta,
                State.init(self.source).getGraphId(),
                ModelAction.init(self.action).getGraphId(),
                State.init(self.target).getGraphId())

class ActionRecord(JavaClass):
    '''
        public final long clockTimestamp;
        public final int agentTimestamp;
        public final Action modelAction;
        public final GUITreeAction guiAction;
    '''
    def __init__(self, actionrecord):
        super(ActionRecord, self).__init__(actionrecord, 'com.andorid.commands.monkey.ape.model.Model$ActionRecord')

    def getAgentTimestamp(self):
        return self.agentTimestamp

class ModelAction(JavaClass):
    def __init__(self, modelaction):
        super(ModelAction, self).__init__(modelaction, 'com.android.commands.monkey.ape.model.ModelAction')

    def getGraphId(self):
        return self.id if self.id is not None else ""

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
    def __init__(self, graph):
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

    def size(self):
        return len(self.keyToState)

    def getOutStateTransitions(self, state):
        # Map<StateTransition, StateTransition> ret = stateToOutStateTransitions.get(state);
        return self.stateToOutStateTransitions[state]

    def metTargetScore(self, state):
        if isinstance(state, State):
            state = state.get_object()
        transitions = self.getOutStateTransitions(state)
        score = 0.0
        for transition in transitions:
            transition = StateTransition.init(transition)
            new_score = transition.metTargetRatio()
            if new_score > score:
                score = new_score

        return score
