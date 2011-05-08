"""
clearquest.task: module for simplifying ClearQuest migrations.
"""

#===============================================================================
# Imports
#===============================================================================

import os, sys, time, traceback

from itertools import count, repeat
from pprint import pprint, pformat

from lxml.etree import XML
from os.path import basename, dirname
from ConfigParser import ConfigParser, NoOptionError

from clearquest import api, callback
from clearquest.util import cache, joinPath, Dict

from twisted.python.reflect import namedClass
from zope.interface import Interface


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

#===============================================================================
# Classes
#===============================================================================
    
class Config(ConfigParser):
    """
    Base configuration class that provides a slightly customised ConfigParser
    interface.  Inherited by TaskManagerConfig.
    """
    def __init__(self, file):
        ConfigParser.__init__(self)
        self.file = file
        self.readfp(open(self.file))
        self.default = self.defaults()
        
        """
        Dictionary interface to the configuration file; keyed by the name of the
        section, the corresponding value will be another dictionary with that
        section's key/value pairs.
        """
        self.data = Dict([(s, Dict(self.items(s))) for s in self.sections()])                                                  
        
    def optionxform(self, option):
        """
        Default implementation of ConfigParser.optionxform() converts options
        to lowercase, which we don't want, so override and return the exact name
        that was passed in.
        """
        return option
    
    def getDefaultConfigSection(self):
        """
        @return: a string representing the default configuration section the
        get() method should use when attempting to fetch config values.
        """
        return 'DEFAULT'
    
    def __getitem__(self, name):
        try:
            return self.data[self.getDefaultConfigSection()][name]
        except KeyError:
            return self.default[name]
    
class TaskManagerConfig(Config):
    def __init__(self, manager, file=None):
        self.manager = manager
        if not file:
            base = basename(sys.modules[manager.__module__].__file__)
            file = joinPath(manager.runDir, base[:base.rfind('.')] + '.ini')
        Config.__init__(self, file)
        
    def tasks(self):
        """
        @return: list of class objects for each task defined in the current
        configuration.  
        """
        allTasks = self.get('allTasks').split(',')
        excludeTasks = self.get('excludeTasks').split(',')
        
        return [ namedClass(t) for t in allTasks if not t in excludeTasks ]
    
    def get(self, setting, default=None):
        """
        Retrieve the value of @param setting from the section identified by
        self.defaultConfigSection, if it's present, or from the [DEFAULT]
        section if not.  If the setting isn't present in [DEFAULT] and @param
        default is None, then a ConfigParser.NoOptionError is raised, otherwise
        @param default is returned.
        """
        try:
            return Config.get(self, self.getDefaultConfigSection(), setting)
        except NoOptionError, error:
            if default is None:
                raise error
            else:
                return default
    
    @cache
    def toDict(self):
        m = self.defaults()
        m.update(**dict(self.items(self.getDefaultConfigSection())))
        return m

class TaskManager(object):
    def __init__(self, runDir=dirname(sys.modules['__main__'].__file__)):
        self.runDir = runDir
        self.conf = self.createConfig()
        
        callbackType = self.conf.get('callback', 'ConsoleCallback')
        self.cb = getattr(callback, callbackType)(self)
        
        # Need to modify to support arbitrary tasks in any module, not just
        # those present in the source module.
        self._taskCount = count(0)
        self.tasks = self.conf.tasks()
        self.task = dict()
        
    @cache
    def getSourceConf(self):
        return self.conf[self.sourceTarget]
    
    @cache
    def getDestConf(self):
        return self.conf[self.destTarget]
    
    def _getSession(self, sessionClassType, conf):
        if sessionClassType == api.SessionClassType.User:
            fmt = "Logging on to user database %(db)s [%(dbset)s] as "
        else:
            fmt = "Logging on to schema %(dbset)s as "
        fmt += "%(login)s/%(passwd)s..."
        self.cb.write(fmt % conf)
        start = time.time()
        session = api.getSession(sessionClassType, conf)
        self.cb.write("done (%.3f secs)\n" % (time.time() - start))
        return session
    
    @cache
    def getSourceSession(self, sessionClassType):
        return self._getSession(sessionClassType, self.getSourceConf())
    
    @cache
    def getDestSession(self, sessionClassType):
        return self._getSession(sessionClassType, self.getDestConf())
    
    def createConfig(self):
        return TaskManagerConfig(self)
        
    def run(self):
        raise NotImplementedError

class MultiSessionTaskManager(TaskManager):
    """
    Extended version of TaskManager that supports multiple user source sessions
    and a single user destination session.  
    """
    
    def __init__(self, *args):
        TaskManager.__init__(self, *args)
        self._validateConf()
    
    def _validateConf(self):
        """
        Raises a KeyError exception if any of our mandatory configuration vars
        aren't present in our config file.  Called from __init__().
        """
        self.conf['dbset']
        self.conf['login']
        self.conf['passwd']
        self.conf['destSession']
        self.conf['sourceSessions']
        
    def _getSession(self, db):
        details = self.conf.data[self.conf.getDefaultConfigSection()]
        details['db'] = db
        fmt = "Logging on to user database %(db)s [%(dbset)s] as " \
              "%(login)s/%(passwd)s..."
        self.cb.write(fmt % details)
        start = time.time()
        session = api.getSession(api.SessionClassType.User, details)
        self.cb.write("done (%.3f secs)\n" % (time.time() - start))
        return session
    
    @cache
    def getSourceSessions(self):
        return [
            self.getSourceSession(db)
                for db in self.conf['sourceSessions']
        ]
    
    @cache
    def getSourceSession(self, db):
        if db not in self.conf['sourceSessions']:
            raise RuntimeError("Unknown database: %s" % db)
        return self._getSession(db)
    
    @cache
    def getDestSession(self, sessionClassType):
        return self._getSession(self.conf['destSession'])
    
    def getSourceSession(self, sessionClassType):
        raise NotImplementedError
    
    def getSourceConf(self):
        return self.conf
    
    def getDestConf(self):
        return self.conf

    
class Task(object):
    def __init__(self, manager):
        self.manager = manager
        self.cb = self.getCallback()
        self.destSession = manager.getDestSession(self.getSessionClassType())
        
        """
        If there's an .ini file lying around with the same name as this class,
        assume it's a data configuration file (which can store various mappings
        and other values of interest to subclasses) and make it accessible via
        a Dict interface through self.data.
        """
        self.data = self._data()
        
        self.id = self.manager._taskCount.next()
        
    def getSessionClassType(self):
        """
        @return: a value corresponding to api.SessionClassType (either User or
        Admin).  Must be implemented by subclass.
        """
        raise NotImplementedError
    
    def getCallback(self):
        """
        @returns: an object that implements the Callback interface.  Defaults
        to whatever callback class the parent TaskManager is using.
        """
        return self.manager.cb.__class__(self)
    
    def previous(self):
        """
        @returns: the task that ran previous to us, or None if we're the first
        task.
        """
        try:
            return self.manager.task[self.manager.tasks[self.id-1].__name__]
        except IndexError:
            return None
    
    def next(self):
        """
        @returns: the task that's meant to be run after we complete, or None
        if we're the last task.
        """
        try:
            return self.manager.task[self.manager.tasks[self.id+1].__name__]
        except IndexError:
            return None
    
    def completed(self):
        """
        If the parent Task Manager supports it, this method will be called when
        the task's run() method completes successfully.  If the task supports
        rollbackToCompletionPoint(), it is likely it will need to perform some 
        sort of action here to save the state.
        """
        pass
    
    def failed(self):
        """
        If the parent Task Manager supports it, this method will be called when
        the task's run() method completes successfully.  By default, it calls
        the previous task's rollbackToCompletionPoint() method.
        """
        try:
            self.previous().rollbackToCompletionPoint()
        except AttributeError:
            pass
            
    
    def rollbackToCompletionPoint(self):
        """
        If a task execution after us fails, we may be called on to rollback to
        the point at which we were complete; i.e. restoring a database to a
        snapshot we took when complete() was called. 
        """
        pass
    
    def run(self):
        pass
    
    def _data(self):
        name = self.__class__.__name__.lower()
        file = joinPath(self.manager.runDir, name + '.ini')
        if os.path.isfile(file):
            self.conf = Config(file)
            return self.conf.data

class CreateObject(Task):
    def __init__(self, manager):
        Task.__init__(self, manager)
        
    def expectedCount(self):
        """
        @returns: the number of destination objects that will be created.  Used
        by the callback mechanism to track progress.
        """
        raise NotImplementedError
    
    def getDestObjectNames(self):
        """
        @returns: a list of object names to create/update.
        """
        raise NotImplementedError
    
    def getDestObject(self, destObjectName):
        """
        @return: a two-part tuple, the first element containing an instance of 
        an api.CQProxyObject, configured with a behaviour type that implements
        api.DeferredWriteBehaviour, the second element being a boolean that is
        True if the entity was created from scratch, or False if it already
        existed and a reference was obtained.
        """
        raise NotImplementedError
    
    def preCommit(self, destObject, created):
        """
        Callback that's invoked when the entity is in an editable state, but
        before it's been committed.  Provides an opportunity for a subclass to
        customise the entity's values before being commited.
        @param destEntity: instance of api.DeferredWriteEntityProxy
        @param created: True if destObject was created, False if it already
        existed
        """
        pass
    
    def postCommit(self, destObject, changesApplied):
        """
        Callback that's invoked after successfully committing the entity.  If an
        exception was raised during validation or commit, this callback will not
        be invoked.
        @param destObject: instance of api.DeferredWriteEntityProxy
        @param changesApplied: bool indicating whether or not any changes were
        actually applied to destEntity.  If no unique changes are detected by
        DeferredWriteEntityProxy.applyChangesAndCommit() for a destEntity that
        already existed, it won't bother with attempting to modify then commit
        the entity.
        """
        pass
    
    def run(self):
        """
        For each object name returned by getDestObjectNames(), get a reference
        to the object via getDestObject(), call preCommit() to allow the
        subclass to customise values, call applyChangesAndCommit() against the
        object, then, assuming no exceptions were thrown, call postCommit(),
        allowing for the subclass to carry out any additional tasks once the
        object's been created.
        """
        cb = self.cb
        cb.expected = self.expectedCount()
        for destObjectName in self.getDestObjectNames():
            cb.next(destObjectName)
            try:
                destObject, created = self.getDestObject(destObjectName)
                counter = 'created' if created else 'updated'
               
                self.preCommit(destObject, created)
                
                try:
                    changesApplied = destObject.applyChangesAndCommit()
                except:
                    destObject.revert()
                    raise
                
                if not changesApplied:
                    counter = 'skipped'
                cb[counter] += 1
                
                self.postCommit(destObject, changesApplied)
                
            except Exception:
                cb.error(traceback.format_exc())
                cb.failed += 1
                
        cb.finished()
    
    
class CreateSchemaObject(CreateObject):
    def __init__(self, manager, schemaObjectClass):
        self._schemaObjectClass = schemaObjectClass
        CreateObject.__init__(self, manager)
        
    def getSessionClassType(self):
        return api.SessionClassType.Admin
    
    def getDestObject(self, destObjectName):
        """
        @param destObjectName: name of the schema object being created
        @return: instance of an api.DeferredWriteSchemaObjectProxy object
        """
        destObject = None
        className = self._schemaObjectClass.__name__
        get = getattr(self.destSession, 'Get' + className)
        create = getattr(self.destSession, 'Create' + className)
        try:
            destObject = get(destObjectName)
            created = False
        except:
            pass
        
        if destObject is None:
            destObject = create(destObjectName)
            created = True
        
        return (api.DeferredWriteSchemaObjectProxy(destObject), created)

class CreateEntity(CreateObject):
    """
    Creates (or updates) a new entity.
    """
    def getSessionClassType(self):
        return api.SessionClassType.User
    
    def getDestEntityDefName(self):
        """
        @returns: name of the entity to create/update.
        """
        raise NotImplementedError
    
    @cache
    def getDestEntityDef(self):
        """
        @returns: instance of an api.EntityDef object for the destination entity
        name returned by destEntityDefName().
        """
        return self.destSession.GetEntityDef(self.getDestEntityDefName())
    
    def getDestObject(self, destDisplayName):
        """
        @param destDisplayName: new entity's display name.
        @returns: instance of an api.DeferredWriteEntityProxy for the entity
        identified by @param destDisplayName. If no existing entity can be found
        matching the display name, then a new one is created via BuildEntity.
        Note: for stateless entities with complex unique keys (more than one
        field), if the entity doesn't already exist and has to be created with 
        BuildEntity, this method will make a crude attempt to 'prime' the new
        entity's display name (that is, set each individual field) with the
        relevant values.  This can only be done if each field in the unique key
        doesn't contain a space, given that ClearQuest uses spaces to separate
        each fields.  So, the number of spaces found in the display name must
        be one less than the number of fields in the destEntity's unique key.
        If this isn't the case, a ValueError will be raised.  (We'll need to
        change this down the track, perhaps by adding a setDestDisplayName()
        method that subclasses can override.)
        """
        session = self.destSession
        destEntityDefName = self.getDestEntityDefName()
        destEntityDef = self.getDestEntityDef()
        
        fields = [ f[0] for f in destEntityDef.getUniqueKey().selectFields() ]
        if len(fields) == 1:
            parts = (destDisplayName,)
        else:
            parts = destDisplayName.split(' ')
            
        if len(parts) != len(fields):
            raise ValueError, "could not discern unique key parts (%s) " \
                              "for entity '%s' from display name '%s'" % \
                              (", ".join(fields), \
                               destEntityDefName, \
                               destDisplayName)
        else:
            changes = dict([(f, v) for f, v in zip(fields, parts)])
        
        args = (destEntityDefName, destDisplayName)
        dbid = session.lookupEntityDbIdByDisplayName(*args)
        if dbid:
            entity = session.GetEntityByDbId(destEntityDefName, dbid)
            created = False
        else:
            entity = session.BuildEntity(destEntityDefName)
            created = True
        
        return (api.DeferredWriteEntityProxy(entity, changes=changes), created)
    
class CopyObject(CreateObject):
    def __init__(self, manager):
        CreateObject.__init__(self, manager)
        self.sourceSession=manager.getSourceSession(self.getSessionClassType())
    
    def getSourceObjectName(self, destObjectName):
        """
        Given a destination object name, return the corresponding object name
        of the source object we're copying.  Called by getSourceObject() in
        order to get a reference to the source object before copying.
        @returns: unless overridden by a subclass, this method simply returns
        destObjectName.
        """
        return destObjectName

    def getSourceObject(self, sourceObjectName):
        """
        @param sourceObjectName: source object's name
        @returns: instance of an api.CQProxyObject configured with the behaviour
        api.ReadOnlyBehaviour.
        """
        raise NotImplementedError
    
    def skipObject(self, sourceObject):
        """
        Callback that's invoked after the sourceObject has been created, but
        before the destObject has been created.  Provides an opportunity for a
        subclass to indicate if the sourceObject should be 'skipped over'.
        @return: True if the object should be skipped (no destObject will be
        created), False otherwise.  Default is False.
        """
        return False
    
    def preCommit(self, sourceObject, destObject, created):
        """
        Callback that's invoked when the entity is in an editable state, but
        before it's been committed.  Provides an opportunity for a subclass to
        customise the entity's values before being commited.
        @param sourceEntity: instance of api.ReadOnlyEntityProxy
        @param destEntity: instance of api.DeferredWriteEntityProxy
        @param created: True if destObject was created, False if it already
        existed
        @return: True if the the current copy operation should continue, False
        if creation/modification of this destObject should be skipped.
        """
        pass
    
    def postCommit(self, sourceObject, destObject, changesApplied):
        """
        Callback that's invoked after successfully committing the entity.  If an
        exception was raised during validation or commit, this callback will not
        be invoked.
        @param sourceEntity: instance of api.ReadOnlyEntityProxy
        @param destEntity: instance of api.DeferredWriteEntityProxy
        @param changesApplied: bool indicating whether or not any changes were
        actually applied to destEntity.  If no unique changes are detected by
        DeferredWriteEntityProxy.applyChangesAndCommit() for a destEntity that
        already existed, it won't bother with attempting to modify then commit
        the entity.
        """
        pass
    
    def commonFieldNames(self, sourceObject, destObject):
        """
        @param sourceObject: instance of api.ReadOnlyObjectProxy
        @param destEntity: instance of api.DeferredWriteObjectProxy
        @returns: list of identically named fields shared by sourceObject and 
        destObject.  copyCommonFields() is the intended consumer of this method.
        """
        pass
    
    def copyCommonFields(self, sourceObject, destObject, skipFields=list()):
        """
        Convenience method that copies any identical fields in the source object
        to the destination object.  See subclasses for additional information.
        """
        fields = self.commonFieldNames(sourceObject, destObject)
        getter = repeat(lambda f: sourceObject.get(f))
        destObject.addChanges(dict([
            (f, v) for (f, v) in [
                (f, v(f)) for (f, v) in zip(fields, getter)
                    if not f in skipFields
            ] if v
        ]))
    
    def run(self):
        """
        For each display name returned by destDisplayNames(), get a reference to
        the new dest entity (either via BuildEntity if it doesn't exist, or 
        GetEntity if it does) as well as the source entity, call preCommit()
        with both sourceEntity and destEntity, allowing subclass customisation,
        then validate and commit the destEntity if any changes were made, and
        then finally call postCommit() with both entities again allowing the
        subclass to perform any final tasks.  Called by TaskManager.  The logic
        in this method is identical to that of CreateEntity.run(), except for
        the support of an additional source entity.
        """
        cb = self.cb
        cb.expected = self.expectedCount()
        for destObjectName in self.getDestObjectNames():
            cb.next(destObjectName)
            try:
                sourceObjectName = self.getSourceObjectName(destObjectName)
                sourceObject = self.getSourceObject(sourceObjectName)
                
                if self.skipObject(sourceObject):
                    cb.skipped += 1
                    continue
                
                destObject, created = self.getDestObject(destObjectName)
                counter = 'created' if created else 'updated'
               
                self.preCommit(sourceObject, destObject, created)
                
                try:
                    changesApplied = destObject.applyChangesAndCommit()
                except:
                    destObject.revert()
                    raise
                
                if not changesApplied:
                    counter = 'skipped'
                cb[counter] += 1
                
                self.postCommit(sourceObject, destObject, changesApplied)
                
            except Exception:
                cb.error(traceback.format_exc())
                cb.failed += 1
        
        cb.finished()
    
class CopySchemaObject(CopyObject, CreateSchemaObject):
    def __init__(self, manager, schemaObjectClass):
        self._schemaObjectClass = schemaObjectClass
        CopyObject.__init__(self, manager)
        
        collectionName = schemaObjectClass.__name__ + 's'
        self._sourceObjects = getattr(self.sourceSession, collectionName)
        
    def expectedCount(self):
        return len(self._sourceObjects)
    
    def getDestObjectNames(self):
        for sourceObject in self._sourceObjects:
            self._currentSourceObject = sourceObject
            yield sourceObject.Name        
    
    def getSourceObject(self, sourceObjectName):
        """
        @param sourceObjectName: source object's name
        @returns: instance of an api.CQProxyObject configured with the behaviour
        api.ReadOnlyBehaviour.
        """
        assert(sourceObjectName == self._currentSourceObject.Name)
        return api.ReadOnlySchemaObjectProxy(self._currentSourceObject)
    
    def commonFieldNames(self, sourceObject, destObject):
        """
        @return: list of properties for the given schema object (taken from
        the keys of the schema object's _prop_map_get_ dict).
        """
        assert(sourceObject._proxiedObject.__class__.__name__ ==
                 destObject._proxiedObject.__class__.__name__)
        return sourceObject._proxiedObject._prop_map_get_.keys()
        
class CopyEntity(CopyObject, CreateEntity):
    """
    Similar to CreateEntity, except that our destination entity is created
    from the values in a source entity.  
    """
    def __init__(self, manager):
        CopyObject.__init__(self, manager)
        
    def getSourceEntityDefName(self):
        """
        @returns: name of the source entity being copied, must be implemented by
        subclass.
        """
        raise NotImplementedError
    
    @cache
    def getSourceEntityDef(self):
        """
        @returns: instance of an api.EntityDef object for the source entity
        name returned by getSourceEntityDefName().
        """
        return self.sourceSession.GetEntityDef(self.getSourceEntityDefName())
    
    def getSourceObject(self, sourceDisplayName):
        """
        @param sourceDisplayName: source entity's display name as a string
        @returns: instance of an api.ReadOnlyEntityProxy for the entity
        identified by @param sourceDisplayName.
        """
        s = self.sourceSession
        n = self.getSourceEntityDefName()
        return api.ReadOnlyEntityProxy(s.GetEntity(n, sourceDisplayName))

    
    @cache
    def commonFieldNames(self, sourceEntity, destEntity):
        """
        @param sourceEntity: instance of api.ReadOnlyEntityProxy
        @param destEntity: instance of api.DeferredWriteEntityProxy
        @returns: list of identically named fields shared by sourceEntity and 
        destEntity, excluding any system owned fields.  copyCommonFields() is
        the intended consumer of this method.
        """
        sourceEntityDef = sourceEntity.getEntityDef()
        destEntityDef = destEntity.getEntityDef()
        loweredFields = [ f.lower() for f in destEntityDef.GetFieldDefNames() ]
        destFields = api.listToMap(loweredFields)
        return [
            f for f in [ n.lower() for n in sourceEntityDef.GetFieldDefNames() ]
                if not sourceEntityDef.IsSystemOwnedFieldDefName(f) and
                       f in destFields
        ]

class MergeEntity(CopyEntity):
    def __init__(self, manager, entityDefName):
        self.entityDefName = entityDefName
    
    def getSourceEntityDefName(self):
        return self.entityDefName
    
    def getDestEntityDefName(self):
        return self.entityDefName
    
    def preCommit(self, srcEntity, dstEntity, changesApplied):
        pass

class CreateUser(CreateSchemaObject):
    def __init__(self, manager):
        CreateSchemaObject.__init__(self, manager, api.User)

class CreateGroup(CreateSchemaObject):
    def __init__(self, manager):
        CreateSchemaObject.__init__(self, manager, api.Group)

class CreateDatabase(CreateSchemaObject):
    def __init__(self, manager):
        CreateSchemaObject.__init__(self, manager, api.Database)

class CopyUser(CopySchemaObject):
    def __init__(self, manager):
        CopySchemaObject.__init__(self, manager, api.User)

class CopyGroup(CopySchemaObject):
    def __init__(self, manager):
        CopySchemaObject.__init__(self, manager, api.Group)

class CopyDatabase(CopySchemaObject):
    def __init__(self, manager):
        CopySchemaObject.__init__(self, manager, api.Database)

class UpdateDynamicLists(Task):
    def __init__(self, manager):
        Task.__init__(self, manager)
    
    def getSessionClassType(self):
        return api.SessionClassType.User
        
    def getXmlFileName(self):
        return joinPath(self.manager.runDir, 'dynamiclists.xml')
    
    def loadXml(self):
        return XML(open(self.getXmlFileName(), 'r').read())
    
    def run(self):
        cb = self.cb
        xml = self.loadXml()
        dynamicLists = api.loadDynamicLists(xml)
        cb.expected = len(dynamicLists)
        for dl in dynamicLists:
            name = dl.Name
            cb.next(name)
            try:
                old = list(self.destSession.getDynamicList(name).values or [])
                new = list(self.destSession.updateDynamicList(dl).values or [])
                old.sort()
                new.sort()
                if old != new:
                    cb.updated += 1
                else:
                    cb.skipped += 1
            except Exception, details:
                cb.error((details, traceback.format_exc()))
                cb.failed += 1                
        cb.finished()
