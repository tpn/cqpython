"""
clearquest.interfaces
"""

from zope.interface import Interface

class ITaskManager(Interface):
    pass


class ITask(Interface):
    
    def getSessionClassType():
        """
        Get the type of session required by this task.
        
        @return: An L{api.SessionClassType} constant.
        """
    
    def run():
        """
        Marks the task as ready to run.
        
        """
    