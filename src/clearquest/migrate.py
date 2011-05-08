"""
clearquest.task: module for simplifying ClearQuest migrations.
"""

#===============================================================================
# Imports
#===============================================================================

import os
import sys
import time
import inspect
import traceback

from functools import wraps
from itertools import repeat
from os.path import basename, dirname
from ConfigParser import ConfigParser, NoOptionError
from lxml.etree import XML

from clearquest import api, callback
from clearquest.util import cache, joinPath, Dict, spliceWork
from clearquest.task import CreateSchemaObject, Task, TaskManager, \
                            TaskManagerConfig

#===============================================================================
# Globals
#===============================================================================
__rcsid__ = '$Id$'
__rcsurl__ = '$URL$'
__copyright__ = 'Copyright 2008 OnResolve Ltd'

#===============================================================================
# Decorators
#===============================================================================

#===============================================================================
# Helper Methods
#===============================================================================

def copyUsers(src, dst):
    users = src.Users
    failed = []
    startTime = time.time()
    for user in users:
        try:
            dst.createUserFromXml(user.toXml())
        except:
            failed.append(user.Name)
    stopTime = time.time()
    created = len(users) - len(failed)
    print "created %d users in %s seconds\nfailed: %s" % \
          (created, str(stopTime - startTime), ", ".join(failed))

#===============================================================================
# Classes
#===============================================================================

class MigrationManager(TaskManager):
    def __init__(self):
        TaskManager.__init__(self)
        try:
            self.sourceTarget, self.destTarget = sys.argv[1].split(',')
        except IndexError:
            self.sourceTarget, self.destTarget = self.default['targets'] \
                                                     .split(',')

    def getDefaultConfigSection(self):
        return self.destTarget
    
    def run(self):
        upgradeDb = False
        for task in self.tasks:
            t = task(self)
            t.run()
            # Keep a copy of the task so other tasks can access it.
            self.task[t.__class__.__name__] = t
            
            # Any schema tasks will require the affected destination database to
            # be upgraded in order for the changes to be applied at the end of
            # the task run.
            if isinstance(t, CreateSchemaObject):
                upgradeDb = True
        
        if upgradeDb:
            adminSession = self.getDestSession(api.SessionClassType.Admin)
            dbs = adminSession.Databases
            for db in dbs:
                if db.Name == self.getDestConf().get('db'):
                    self.cb.write("upgrading database '%s'..." % db.Name)
                    start = time.time()
                    db.UpgradeMasterUserInfo()
                    self.cb.write("done (%.3f secs)\n" % (time.time() - start))
                    break
    
