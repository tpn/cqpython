"""
clearquest: core classes 
"""

#===============================================================================
# Imports
#===============================================================================

import os
import sys
import pythoncom

from win32com.client import DispatchBaseClass

#===============================================================================
# Globals
#===============================================================================

__rcsid__ = '$Id$'
__rcsurl__ = '$URL$'
__copyright__ = 'Copyright 2008 OnResolve Ltd'

#===============================================================================
# Classes
#===============================================================================

class CQBaseObject(DispatchBaseClass):
    def __init__(self, *args, **kwds):
        for key, value in kwds.items():
            self.__dict__[key] = value
        props = self._prop_map_get_.keys()
        props += [ p for p in self._prop_map_put_.keys() if p not in props ]    
        module = sys.modules[self.__module__]
        topLevelObjects = getattr(module, 'TopLevelObjects')
        if not args and self.__class__.__name__ in topLevelObjects:
            args = (pythoncom.new(self.coclass_clsid),)
        DispatchBaseClass.__init__(self, *args)
        