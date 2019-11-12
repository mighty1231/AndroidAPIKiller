from common import readJavaList, classReadJavaList, JavaClass
from utils import getFromMapMap
import dom
import naming as namingModule
import model

class GUITree(JavaClass):
    def __init__(self, guitree):
        super(GUITree, self).__init__(guitree, "com.android.commands.monkey.ape.tree.GUITree")

    def getDocument(self):
        return dom.buildDocumentFromGUITree(self)

    def getCurrentNaming(self):
        return namingModule.Naming.init(self.currentNaming)

    def getCurrentState(self):
        return model.State.init(self.currentState)

    def getActivityName(self):
        return (self.activityPackageName, self.activityClassName)

    def setCurrentNaming(self, current, currentWidgets, currentNodes):
        self.currentNaming = current
        self.currentNames = currentWidgets
        self.currentNodes = currentNodes

    def setCurrentState(self, state):
        state = model.State.init(state)
        if state is not None:
            raise NotImplementedError
        self.currentState = state

class GUITreeNode(JavaClass):
    def __init__(self, guitreenode):
        super(GUITreeNode, self).__init__(guitreenode, "com.android.commands.monkey.ape.tree.GUITreeNode")

    def getIndexPath(self):
        if self.indexPath:
            return self.indexPath
        if self.parent:
            return '{}-{}'.format(GUITreeNode.init(self.parent).getIndexPath(), self.index)
        return str(self.index)

    def describe(self):    
        print('IndexPath [{}]'.format(self.getIndexPath()))
        print(' - resourceId', self.resourceId)
        print(' - className', self.className)
        print(' - packageName', self.packageName)

    def getScrollType(self):
        if not self.isScrollable():
            return "none"
        elif self.className in ["android.widget.ScrollView", "android.widget.ListView", \
                "android.widget.ExpandableListView", \
                "android.support.v17.leanback.widget.VerticalGridView"]:
            return "vertical"
        elif self.className in ["android.widget.HorizontalScrollView", \
                "android.support.v17.leanback.widget.HorizontalGridView", \
                "android.support.v4.view.ViewPager"]:
            return "horizontal"
        elif self.scrollable == 1:
            return "vertical"
        elif self.scrollable == 2:
            return "horizontal"
        else:
            return "all"

    def isEnabled(self):
        return self.enabled

    def isClickable(self):
        return self.clickable

    def isCheckable(self):
        return self.checkable

    def isLongClickable(self):
        return self.longClickable

    def isScrollable(self):
        return self.scrollable != 0

    def getClassName(self):
        return self.className

    def getResourceID(self):
        return self.resourceId

    def getIndex(self):
        return self.index

    def getParent(self):
        return GUITreeNode.init(self.parent)

    def getText(self):
        return self.text

    def getContentDesc(self):
        return self.contentDesc

    # def getStateKey(self):
    #     return model.StateKey.init(self.stateKey)

    def getTempXPathName(self):
        return namingModule.Name.init(self.tempXPathName)

    def getXPathName(self):
        return namingModule.Name.init(self.xpathName)


def GUITreeBuilder_getStateKey(naming, tree):
    naming = namingModule.Naming.init(naming)
    tree = GUITree.init(tree)

    if tree.getCurrentNaming() == naming:
        current = tree.getCurrentState()
        if current is not None:
            return current.getStateKey()

    result = model.State.buildStateKey(naming, (tree.activityPackageName, tree.activityClassName),
        tree.currentNames)
    return model.StateKey.init(result)
