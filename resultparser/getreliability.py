import javaobj
import sys, os, re, glob
from common import classReadJavaList, readJavaList
from model import StateTransition
from tree import GUITreeTransition

if __name__ == "__main__":
	exception_directories = []
	for directory in sorted(sys.argv[1:]):
		objfs = glob.glob(os.path.join(directory, 'ape', 'sata-*', 'sataModel.obj'))
		if len(objfs) == 1:
			try:

				# analysis for directory
				# total gui tree transitions


				# [(# target gts, #gts)]
				# (value, cnt) - st>=3, avg_{st|len(st)>=3}( 4r(1-r) )
				with open(objfs[0], 'rb') as f:
					model = javaobj.loads(f.read())
				graph = model.graph

				stids = []
				allvalues = []
				myfuncval = []
				for gt in graph.treeTransitionHistory:
					st = StateTransition.init(gt.stateTransition)
					if id(st.get_object()) in stids:
						continue
					stids.append(id(st.get_object()))
					metcnt = 0
					friends = st.getGUITreeTransitions()
					for gt2 in friends:
						if gt2.hasMetTargetMethod:
							metcnt += 1
					allvalues.append((metcnt, len(friends)))

				print('Directory', directory)
				print(allvalues)
			except Exception as e:
				exception_directories.append((directory, e))

	for d, e in exception_directories:
		print('Exception Directory', d)
		print(e)