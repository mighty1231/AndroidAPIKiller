from common import readJavaList, classReadJavaList, JavaClass
import naming as namingModule

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
            classReadJavaList(self.widgets, namingModule.Name)))

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

    @staticmethod
    def buildStateKey(naming, componentName, currentNames):
        naming = namingModule.Naming.init(naming)
        widgets = classReadJavaList(currentNames, namingModule.Name)
        return StateKey(componentName, naming, widgets)

