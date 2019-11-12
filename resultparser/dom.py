import lxml.etree as etree
from lxml.etree import Element
import tree

GUI_TREE_NODE_TAG_NAME = "node"
# GUI_TREE_NODE_PROP_NAME = "GUITreeNode"
# GUI_TREE_PROP_NAME = "GUITree"

elem2node = dict()

def getGUITreeNode(element):
    global elem2node
    return tree.GUITreeNode.init(elem2node[element])

def boolToString(b):
    if b == True:
        return 'true'
    elif b == False:
        return 'false'
    else:
        raise ValueError(b)

def createNodeElement(node):
    node = tree.GUITreeNode.init(node)
    elem = etree.Element(GUI_TREE_NODE_TAG_NAME)
    elem.set("index", str(node.index))
    elem.set("text", node.text)
    elem.set("resource-id", node.resourceId)
    elem.set("class", node.className)
    elem.set("content-desc", node.contentDesc)
    elem.set("package", node.packageName)
    elem.set("checkable", boolToString(node.checkable))
    elem.set("checked", boolToString(node.checked))
    elem.set("clickable", boolToString(node.clickable))
    elem.set("enabled", boolToString(node.enabled))
    elem.set("focusable", boolToString(node.isFocusable))
    elem.set("focused", boolToString(node.focused))
    elem.set("scrollable", boolToString(node.scrollable != 0))
    elem.set("long-clickable", boolToString(node.longClickable))
    elem.set("password", boolToString(node.isPassword))
    elem.set("scrollType", node.getScrollType())

    global elem2node
    elem2node[elem] = node.get_object()
    return elem

def treeNodeToXmlNode(guitreenode):
    guitreenode = tree.GUITreeNode.init(guitreenode)
    xml = createNodeElement(guitreenode)
    curnode = guitreenode.children
    while curnode is not None:
        xml.append(treeNodeToXmlNode(curnode))
        curnode = curnode.sibling
    return xml

def buildDocumentFromGUITree(guitree):
    guitree = tree.GUITree.init(guitree)
    return treeNodeToXmlNode(guitree.rootNode)
