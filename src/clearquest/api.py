# -*- coding: mbcs -*-
# Created by makepy.py version 0.4.95
# By python version 2.5.1 (r251:54863, May  1 2007, 17:47:05) [MSC v.1310 32 bit (Intel)]
# From type library 'cqole.dll'
# On Fri Nov 02 19:34:26 2007
""""""
makepy_version = '0.4.95'
python_version = 0x20501f0

"""
clearquest.api: module that wraps the main ClearQuest COM API.

    Created by makepy.py version 0.4.95
    By python version 2.5.1 (r251:54863, May  1 2007, 17:47:05) [MSC v.1310 32 bit (Intel)]
    From type library 'cqole.dll'
    On Fri Nov 02 19:34:26 2007
"""

#===============================================================================
# Imports
#===============================================================================

import os
import re
import sys
import time
import itertools
import win32com.client.CLSIDToClass, pythoncom
import win32com.client.util
from pywintypes import IID
from win32com.client import Dispatch
from functools import wraps
from itertools import chain, repeat
from lxml.etree import XML, _Element
from genshi.template import Context, MarkupTemplate, TemplateLoader, \
                            TemplateNotFound, TextTemplate

# Import both clearquest.db and clearquest.database as we're in the progress of
# deprecating the former in favour for the latter.
from clearquest import db
from clearquest import database
from clearquest.db import selectAll, selectSingle, getConnectOptionsFromRegistry
from clearquest.constants import *
from clearquest.util import cache, concat, connectStringToMap, Dict, iterable, \
                            joinPath, listToMap, symbols, symbolMap, toList

# Disable the distributed stuff for now.
#from clearquest.distributed import distributed, Cluster

#===============================================================================
# makepy Globals
#===============================================================================

makepy_version = '0.4.95'
python_version = 0x20501f0

# The following 3 lines may need tweaking for the particular server
# Candidates are pythoncom.Missing, .Empty and .ArgNotFound
defaultNamedOptArg=pythoncom.Empty
defaultNamedNotOptArg=pythoncom.Empty
defaultUnnamedArg=pythoncom.Empty

CLSID = IID('{B805FDF6-BEA8-11D1-B36D-00A0C9851B52}')
MajorVersion = 1
MinorVersion = 0
LibraryFlags = 8
LCID = 0x0

#===============================================================================
# Globals
#===============================================================================

CQXmlNamespaceUri =  'http://www.onresolve.com/cq/2008.1'
CQXmlNamespace =     'xmlns="%s"' % CQXmlNamespaceUri
GenshiXmlNamespace = 'xmlns:py="http://genshi.edgewall.org/"'
DefaultXmlNamespace = '%s %s' % (CQXmlNamespace, GenshiXmlNamespace)

#===============================================================================
# Exceptions 
#===============================================================================

class EntityFieldManipulationError(Exception): pass
class EntitySetFieldValueError(EntityFieldManipulationError): pass
class EntityAddFieldValueError(EntityFieldManipulationError): pass
class EntityDeleteFieldValueError(EntityFieldManipulationError): pass
class EntityValidationError(Exception): pass
class EntityCommitError(Exception): pass
class UserUpgradeInfoError(Exception): pass
class DatabaseApplyPropertyChangesError(Exception): pass   
class DatabaseVendorNotDiscernableFromConnectString(Exception): pass
class SchemaNameNotFoundError(Exception): pass

#===============================================================================
# Miscellaneous Helper Methods
#===============================================================================

def extractLogonArgs(sessionClassType, d):
    if sessionClassType == SessionClassType.User:
        return (d['login'],
                d['passwd'],
                d['db'],
                d.get('type', SessionType.Shared),
                d['dbset'])
    elif sessionClassType == SessionClassType.Admin:
        return (d['login'],
                d['passwd'],
                d['dbset'])
    else:
        raise TypeError, "'%d' is not a valid SessionClassType" % \
                         sessionClassType

def getSession(sessionClassType, conf):
    args = extractLogonArgs(sessionClassType, conf)
    session = SessionClassTypeMap[sessionClassType]()
    SessionClassTypeLogonMethod[sessionClassType](session, *args)
    return session

def addWorkspaceItemNature(object=None, **kwds):
    if object is not None:
        k = object.__dict__
    else:
        k = kwds
    
    # Top level 'Folder' objects, those created via workspace.GetPublicFolder()
    # or workspace.GetPersonalFolder(), will not have a 'dbid' property set,
    # however, we can derive it from the folder.GetDbId() method.
    if not 'dbid' in k and object.__class__ == Folder:
        k['dbid'] = object.GetDbId()
    
    dbid = k['dbid']
    ws = k['workspace']
    
    args = (dbid, WorkspaceNameOption.NotExtended)
    k['Name'] = ws.GetWorkspaceItemName(*args)
    k['Type'] = ws.GetWorkspaceItemType(dbid)
    k['PathName'] = "/".join(ws.GetWorkspaceItemPathName(*args))
    k['MasterReplicaName'] = ws.GetWorkspaceItemMasterReplicaName(dbid)
    k['SiteExtendedName'] = ws.GetWorkspaceItemSiteExtendedName(dbid)
    k['SiteExtendedNameRequired'] = ws.SiteExtendedNameRequired(dbid)
    
    if object is None:
        return k
    
@cache
def getLinkedServerAwareTablePrefix(targetSession, otherSessions):
    """
    Returns a table prefix for target session that is suitable for use over
    linked database instances.
    """
    qualify = False
    if targetSession not in otherSessions:
        us = targetSession.connectStringToMap()['SERVER']
        for them in [ Session.connectStringToMap(s) for s in otherSessions ]:
            if them['SERVER'] != us:
                qualify = True
                break
        
    prefix = targetSession.getTablePrefix()
    if qualify:
        return '[%s].%s' % (us, prefix)
    else:
        return prefix

#===============================================================================
# XML Template Loader
#===============================================================================

_XmlTemplateDir = joinPath(os.path.dirname(__file__), 'xml')
_XmlLoader = TemplateLoader(_XmlTemplateDir, auto_reload=True)

#===============================================================================
# Decorators 
#===============================================================================

def xml(*args, **kwds):
    if not args:
        args = [ 'Name' ]
    def decorator(f):
        fname = f.func_name.replace('FromXml', '')
        typename = kwds.get('returns')
        if not typename:
            i = 0
            while not fname[i].isupper():
                i += 1
            typename = fname[i:]

        @wraps(f)
        def newf(*_args, **_kwds):
            self = _args[0]
            xml = XML(_args[1])
            props = _kwds.get('props', dict())
            
            # XXX TODO: The following logic was added to support the derivation
            # of 'CreateUser' from 'CreateUsers'.  Needs to be finished
            method = kwds.get('method', fname[0].upper() + fname[1:])
            if not hasattr(self, method):
                if method.endswith('s'):
                    if hasattr(self, method[:len(method)-1]):
                        method = method[:len(method)-1]
                        
            obj = getattr(self, method)(*[ xml.get(arg) for arg in args ])
            obj.applyXml(xml, **props)
            return obj
        return newf
    return decorator

def returns(typename, **kwds):
    def decorator(f):
        @wraps(f)
        def newf(*_args, **_kwds):
            self = _args[0]
            props = dict(_kwds)
            props['parent'] = self
            for name, index in kwds.items():
                props[name] = _args[index]
            for name in CQObject._SharedProperties:
                if hasattr(self, name):
                    props[name] = self.__dict__[name]
            if type(typename) == str:
                module = sys.modules[self.__class__.__module__]
                cast = getattr(module, typename)
            else:
                cast = typename
            result = f(*_args, **_kwds)
            if result is None:
                return result
            elif type(result) in (list, tuple):
                return [ cast(r, **props) for r in result ]
            else:
                return cast(result, **props)
        return newf
    return decorator

def raiseExceptionOnError(exceptionType):
    def decorator(f):
        types = (str, unicode, list, tuple, dict, int)
        @wraps(f)
        def newfn(*_args, **_kwds):
            error = f(*_args, **_kwds)
            if error:
                args = [ a for a in _args if type(a) in types ] + toList(error)
                raise exceptionType(*args)
            return
        return newfn
    return decorator

#===============================================================================
# Our Classes
#===============================================================================
    
from win32com.client import DispatchBaseClass
class CQObject(DispatchBaseClass):
    """
    When a child object is created via a @returns(typename) decorator, it will
    inherit any of the properties defined in the sharedProperties tuple below,
    assuming the parent also has such a property.
    """
    _SharedProperties = ('session', 'adminSession', 'workspace')
    
    """
    If an object in the following list is created without any arguments, the
    __init__ method of this class will automatically create the underlying COM
    object based on the class's CoClass CLSID (coclass_clsid).
    """
    _TopLevelObjects = ('AdminSession', 'Session', 'Workspace')
    
    def __init__(self, *args, **kwds):
        for key, value in kwds.items():
            self.__dict__[key] = value
        props = self._prop_map_get_.keys()
        props += [ p for p in self._prop_map_put_.keys() if p not in props ]
        self.__dict__['trait_names'] = lambda: props
        self.__dict__['xmlFileName'] = self.__class__.__name__ + '.xml'
        self.__dict__['api'] = sys.modules[self.__class__.__module__]
        if not args and self.__class__.__name__ in self._TopLevelObjects:
            args = (pythoncom.new(self.coclass_clsid),)
        DispatchBaseClass.__init__(self, *args)
    
    def toXml(self, ns=CQXmlNamespaceUri, cachedOk=False):
        if cachedOk:
            if not hasattr(self, '_xml'):
                self.__dict__['_xml'] = self._toXml(ns)
        else:
            self.__dict__['_xml'] = self._toXml(ns)
        return self.__dict__['_xml']
                
    def _toXml(self, ns=CQXmlNamespaceUri):
        return self._XmlLoader.load(self.xmlFileName)                             \
                              .generate(this=self,
                                        api=self.api,
                                        ns={'xmlns': ns}) \
                              .render('xml')
                          
    def saveXml(self):
        if self.__class__.__name__ == 'Entity':
            filename = self.GetEntityDefName() + '-' + \
                       self.GetDisplayName() + '.xml'
            file = open(filename, 'w')
            file.write('<?xml version="1.0"?>\n')
            file.write(self._toXml())
            file.close()
    
    
    # XXX TODO: consider a CQCollection object that overrides this method and
    # deals with XML content with multiple child elements.
    def applyXml(self, xml, **props):
        # Check that the root node of the XML text matches our class name.
        expected = '{%s}%s' % (CQXmlNamespaceUri, self.__class__.__name__)
        if xml.tag != expected:
            raise ValueError, "%s is not a valid root node, expecting: %s" % \
                              (xml.tag, expected)
        
        for (property, value) in xml.items():
            # Is this property overridden in 'props'?
            if property in props:
                value = props[property]
                
            # If not, we'll use the value in the XML.  But first, do some crude 
            # type conversions.
            elif value == 'True':
                value = True
            elif value == 'False':
                value = False
            elif value.isdigit():
                value = int(value)
                
            self.getSetterForProperty(property)(value)
        
        try:
            finalise = self._prop_map_put_ex_['_finalise']
        except KeyError:
            pass
        else:
            finalise(self)

    def getSetterForProperty(self, property):
        """
        @return: setter method for a given property
        """
        try:
            extendedPropMap = self._prop_map_put_ex_
        except AttributeError:
            extendedPropMap = {}
        
        if property in extendedPropMap:
            return lambda v: extendedPropMap[property](self, property, v)
        elif property in self._prop_map_put_:
            return lambda v: setattr(self, property, v)
        elif hasattr(self, 'Set' + property):
            return lambda v: getattr(self, 'Set' + property)(v)
        elif property[:2] == 'Is' and hasattr(self, 'Set' + property[2:]):
            return lambda v: getattr(self, 'Set' + property[2:])(v)
        else:
            raise ValueError, "property '%s' not recognised for object '%s'" \
                              (property, self.__class__.__name__)
    
    def __getattr__(self, attr):
        """
        Try our extended property get dictionary first (_prop_map_get_ex_); if
        the attribute isn't there, forward to the DispatchBaseClass, which will
        perform the lookup via _prop_map_put_.
        
        If our attribute name is plural (ends with an 's'), check to see if
        there's a class by the same name.  If there is, wrap our result in an
        instance of this class.  We do this because a lot of properties return
        collections as 'COMObjects' that we can't wrap using normal @returns
        decorator methods, e.g. AdminSession.Users returns a Users class.       
        """
        if attr.startswith('_'):
            return DispatchBaseClass.__getattr__(self, attr) 
        
        try:
            extendedPropMap = self._prop_map_get_ex_
        except AttributeError:
            extendedPropMap = {}
        
        if attr in extendedPropMap:
            return extendedPropMap[attr](self)
        
        value = DispatchBaseClass.__getattr__(self, attr)
        if attr.endswith('s') and hasattr(self.api, attr):
            try:
                value = getattr(self.api, attr)(value)
            except:
                pass
        return value
    
    def commit(self):
        pass

    def revert(self):
        pass

class CQCollection(CQObject):
    
    def __eq__(self, other):
        other = iterable(other)
        if len(self) != len(other):
            return False
        elif len(self) == 0 and len(other) == 0:
            return True
        try:
            # Only permit comparisons on equal types.
            if type(self[0]) != type(other[0]):
                return False
        except IndexError:
            return False
        
        this =  [ u.Name for u in self  ]
        other = [ o.Name for o in other ]
        this.sort()
        other.sort()
            
        equal = True
        for (l, r) in zip(this, other):
            if l == r:
                continue
            else:
                equal = False
                break
        return equal
    
    def __ne__(self, other):
        return not self.__eq__(other)

class CQXmlProxyObject(object):
    def __init__(self, name, **kwds):
        props = dict(**kwds)
        for (key, value) in props.items():
            # Only keep values that aren't object instances.
            if 'instance' == type(value).__name__:
                del props[key]
        self._xml = MarkupTemplate('<%s %s py:attrs="props"/>' % \
                                   (name, GenshiXmlNamespace))   \
                                  .generate(props=props).render('xml')
    def toXml(self):
        return self._xml

class CQWorkspaceItemXmlProxy(CQXmlProxyObject):
    def __init__(self, name, **kwds):
        CQXmlProxyObject.__init__(self, name, **addWorkspaceItemNature(**kwds))

class CQWorkspaceItem(CQObject):
    def __init__(self, *args, **kwds):
        CQObject.__init__(self, *args, **kwds)
        addWorkspaceItemNature(self)

class CQIterator(object):
    def __call__(self, iterator, *args, **kwds):
        self._iter = iterator
        return self
    def __init__(self, cast):
        self.cast = cast
    def __iter__(self):
        return self
    def next(self):
        return self.cast(self._iter.next())
    
class NormalBehaviour(object):
    def __init__(self, parent, *args, **kwds):
        self._parent = parent
        self._proxiedObject = parent._proxiedObject
        self._proxiedFields = parent._proxiedFields        
    
    def __getattr__(self, attr):
        if attr.startswith('_') or not attr in self._parent._proxiedFields:
            return object.__getattribute__(self, attr)
        else:
            return self._proxiedFields.get(attr)
    
    def __setattr__(self, attr, value):
        if attr.startswith('_'):
            object.__setattr__(self, attr, value)
        elif attr in self._parent._fields:
            self._proxiedObject.set(attr, value)
        else:
            raise AttributeError, attr
        
class CQProxyObject(object):
    def __init__(self, proxiedObject, behaviourType=None, *args, **kwds):
        object.__init__(self)
        self._ourSymbols = symbolMap(self)
        self._proxiedObject = proxiedObject
        self._proxiedFields = listToMap(self.getProxiedFields())
        self._proxiedSymbols = symbolMap(self._proxiedObject)
        self._behaviourType = behaviourType or NormalBehaviour
        self._behaviour = behaviourType(self, *args, **kwds)
        self._behaviourSymbols = symbolMap(self._behaviour)
        self._symbols =                   \
            self._ourSymbols.keys()     + \
            self._proxiedFields.keys()  + \
            self._proxiedSymbols.keys() + \
            self._behaviourSymbols.keys()
            
    def trait_names(self):
        return self._symbols
        
    def getProxiedFields(self):
        """
        @return: list of fields/attributes that we'll be proxying.  Must be
        implemented by subclass.
        """
        raise NotImplementedError
    
    def get(self, field):
        """
        @return: value for the given field (the type will vary depending on the
        nature of the field; will typically be either a unicode string for
        string values or a tuple for list values.  Must be implemented by
        subclass.
        """
        raise NotImplementedError
    
    def set(self, field, value):
        """
        Sets the field to the value provided.  Must be implemented by subclass.
        @param field: name of the field to set
        @param value: value to set
        """
        raise NotImplementedError
    
    def __getattribute__(self, attr):
        if attr.startswith('_') or attr in self._ourSymbols:
            return object.__getattribute__(self, attr)
        elif attr in self._proxiedFields or hasattr(self._behaviour, attr):
            return getattr(self._behaviour, attr)
        elif attr in self._proxiedSymbols:
            return getattr(self._proxiedObject, attr)
        else:
            raise AttributeError, "unknown attribute: %s" % attr
        
    def __setattr__(self, attr, value):
        if attr.startswith('_') or not attr in self._proxiedFields:
            object.__setattr__(self, attr, value)
        else:
            setattr(self._behaviour, attr, value)
    
class SchemaObjectProxy(CQProxyObject):
    def __init__(self, proxiedObject, behaviourType, *args, **kwds):
        CQProxyObject.__init__(self, proxiedObject, behaviourType, *args,**kwds)
    
    def getProxiedFields(self):
        fields = listToMap(self._proxiedObject._prop_map_put_.keys())
        fields.update(listToMap(self._proxiedObject._prop_map_get_.keys()))
        for ex in '_prop_map_put_ex_', '_prop_map_get_ex_':
            try:
                extended = getattr(self._proxiedObject, ex)
            except AttributeError:
                pass
            else:
                fields.update(listToMap(extended.keys()))
        
        return fields.keys()
    
    def get(self, field):
        return getattr(self._proxiedObject, field)
    
    def set(self, field, value):
        self._proxiedObject.getSetterForProperty(field)(value)
    
class EntityProxy(CQProxyObject):
    def __init__(self, proxiedObject, behaviourType, *args, **kwds):
        CQProxyObject.__init__(self, proxiedObject, behaviourType, *args,**kwds)
    
    def getProxiedFields(self):
        return self._proxiedObject.GetFieldNames()
    
    def get(self, field):
        return self._proxiedObject.get(field)

    def set(self, field, value):
        self._proxiedObject.set(field, value)
        
class ReadOnlyBehaviour(object):
    def __init__(self, parent, *args, **kwds):
        self._parent = parent
        self._proxiedObject = parent._proxiedObject
        self._proxiedFields = parent._proxiedFields
    
    def __getattr__(self, attr):
        if attr.startswith('_') or not attr in self._proxiedFields:
            return object.__getattribute__(self, attr)
        else:
            return self._parent.get(attr)
    
    def __setattr__(self, attr, value):
        if attr.startswith('_') or not attr in self._proxiedFields:
            object.__setattr__(self, attr, value)
        else:
            raise AttributeError, "error setting attribute '%s' to '%s': " \
                                  "object is read only" % (attr, str(value))

class ReadOnlyEntityProxy(EntityProxy):
    def __init__(self, proxiedObject, *args, **kwds):
        EntityProxy.__init__(self,
                             proxiedObject,
                             ReadOnlyBehaviour,
                             *args, **kwds)
        
class ReadOnlySchemaObjectProxy(SchemaObjectProxy):
    def __init__(self, proxiedObject, *args, **kwds):
        SchemaObjectProxy.__init__(self,
                                   proxiedObject,
                                   ReadOnlyBehaviour,
                                   *args, **kwds)

class DeferredWriteBehaviour(object):
    def __init__(self, parent, *args, **kwds):
        self._parent = parent
        self._proxiedObject = parent._proxiedObject
        self._proxiedFields = parent._proxiedFields
        self._changes = dict(**kwds.get('changes', {}))
        
    def preApplyChanges(self):
        pass

    def postApplyChanges(self):
        pass
    
    def postCommit(self, changesApplied):
        pass
    
    def addChanges(self, changes):
        if changes:
            self._changes.update(changes)
            
    def getChanges(self):
        changes = []
        for field, value in self._changes.items():
            existing = self._parent.get(field)
            if type(existing) == tuple:
                existing = list(existing)
                if type(value) in (str, unicode):
                    value = [value,]
            if existing != value:
                changes.append((field, value))
        return changes
    
    def applyChanges(self, changes=dict()):
        self.addChanges(changes)
        changes = self.getChanges()
        if not changes:
            return False
        
        self.preApplyChanges()
        for field, value in changes:
            self._parent.set(field, value)
        self.postApplyChanges()
        
        return True
        
    def applyChangesAndCommit(self, changes=dict()):
        """
        Validate and commit pending changes.  @returns True if changes were
        applied, False otherwise.  Note that False does not indicate an error
        occurred when trying to save (an exception will be thrown for errors),
        it just means that no fields were changed.  However, if there were no
        fields changed, but the entity is in an editable state, Commit() is
        called anyway.
        """
        self.addChanges(changes)
        changesApplied = self.applyChanges(changes)
        if changesApplied:
            self._parent.commit()
        self.postCommit(changesApplied)
        return changesApplied

    def save(self):
        """
        Convenience method; invokes applyChangesAndCommit(), but returns the
        object rather than a boolean indicating whether or not changes were
        applied.
        """
        self.applyChangesAndCommit()
        return self
        
    def __getattr__(self, attr):
        if attr.startswith('_') or not attr in self._proxiedFields:
            return object.__getattribute__(self, attr)
        else:
            return self._changes.get(attr, self._parent.get(attr))
    
    def __setattr__(self, attr, value):
        if attr.startswith('_') or not attr in self._proxiedFields:
            object.__setattr__(self, attr, value)
        else:
            self._changes[attr] = value

class DeferredWriteEntityBehaviour(DeferredWriteBehaviour):
    def __init__(self, parent, *args, **kwds):
        DeferredWriteBehaviour.__init__(self, parent, *args, **kwds)
        
    def preApplyChanges(self):
        entity = self._proxiedObject
        if not entity.IsEditable():
            entity.session.EditEntity(entity, 'Modify') 
    
    def postApplyChanges(self):
        self._proxiedObject.Validate()
    
    def postCommit(self, changesApplied):
        entity = self._proxiedObject
        if entity.IsEditable():
            if changesApplied:
                entity.commit()
            else:
                entity.revert()  
    
class DeferredWriteEntityProxy(EntityProxy):
    def __init__(self, entity, *args, **kwds):
        EntityProxy.__init__(self, entity,
                             DeferredWriteEntityBehaviour,
                             *args, **kwds)
        
class DeferredWriteSchemaObjectProxy(SchemaObjectProxy):
    def __init__(self, object, *args, **kwds):
        SchemaObjectProxy.__init__(self, object,
                                   DeferredWriteBehaviour,
                                   *args, **kwds)

class UniqueKey(object):
    
    def __init__(self, entityDef, tableAlias='t1'):
        self.session = entityDef.session
        self.entityDef = entityDef
        self._tableAlias = tableAlias
    
    def _alias(self, column):
        return '%s.%s' % (self._tableAlias, column)
        
    def lookupDisplayNameByDbId(self, dbid):
        sql = self._buildSql(where='t1.dbid')
        return self.session.db().selectSingle(sql, dbid)
    
    def lookupDbIdByDisplayName(self, displayName):
        sql = self._buildSql(select='t1.dbid')
        return self.session.db().selectSingle(sql, displayName)
    
    def _lookupDbIdFromForeignSessionSql(self, column, otherSession):
        # TODO: we should probably assert that our current session and the other
        # session are using identical schemas and database vendors.
        collateTo = False
        if self.session.getDatabaseVendor()==DatabaseVendor.SQLServer  and \
            self.session.getCollation() != otherSession.getCollation() and \
            self.hasTextColumnsInKey():
                collateTo = self.session.getCollation()
                
        dstSql = self._buildSql(select='t1.dbid')[:-1]
        srcSql = otherSession.GetEntityDef(self.entityDef.GetName()) \
                             .getUniqueKey()                         \
                             ._buildSql(where='t1.dbid')[:-1]
        if collateTo:
            srcSql = srcSql.replace('FROM', 'COLLATE %s FROM' % collateTo)
        
        if isinstance(dbid, (int, long)):
            dbid = str(dbid)
        return '%s(%s%s)' % (dstSql, srcSql, dbid)
            
    @cache
    @db.selectAll
    def selectFields(self):
        return self.entityDef.GetName()

    @cache
    def getEntityTableName(self):
        csm = connectStringToMap(self.session.connectString())
        return '%s.%s.%s' % (
            csm['DATABASE'],
            csm['UID'],
            self.entityDef.GetDbName(),
        )

    @cache
    def _info(self, depth=1, visited=dict()):
        alias = 't' + str(depth)
        entityDef = self.entityDef
        entityDefName = entityDef.GetName()
        
        # Reset our visited dict if we're starting from scratch.
        if depth == 1:
            visited = dict()
        
        # Crude attempt to prevent infinite recursion if a reference field in
        # a unique key refers to an entity that features a reference back to us
        # in their unique key.  (Not even sure if ClearQuest allows this, but
        # it's better to raise an exception rather than than overflow our stack
        # and die in a far less graceful manner.)
        if entityDefName in visited:
            raise RuntimeError, "recursive unique key detected in %s, already "\
                                "visited this entity at depth %d (current " \
                                "depth: %d)" % (entityDefName,
                                                visited[entityDefName],
                                                depth)
        else:
            visited[entityDefName] = depth
        
        text = []
        joins = []
        where = []
        fields = []
        
        joins.append('%s %s' % (self.getEntityTableName(), alias))
        
        for field, dbname in self.selectFields():
            fieldType = entityDef.GetFieldDefType(field) 
            if fieldType != FieldType.Reference:
                fields.append('%s.%s' % (alias, dbname))
                if fieldType in FieldType.textTypes:
                    text.append((alias, dbname))
            else:
                info = entityDef.GetFieldReferenceEntityDef(field) \
                                .getUniqueKey() \
                                ._info(depth+1, visited)
                fields += info['fields'] 
                joins += info['joins']
                where += info['where']
                where.append('%s.%s = %s.dbid' % (alias, dbname, info['alias']))
                text += info['text']
        
        return {
            'alias'  : alias,
            'joins'  : joins,
            'where'  : where,
            'fields' : fields,
            'text'   : text,
        }
    
    @cache
    def hasTextColumnsInKey(self):
        return bool(self._info()['text'])
    
    @cache
    def _getDisplayNameSql(self):
        r = repeat("' '")
        fs = self._info()['fields']
        try:
            return concat(*[f for f in chain(*zip(fs[:-1], r))] + [fs[-1]])
        except IndexError:
            return fs[0]
    
    @cache
    def _buildSql(self, **kwds):
        
        displayNameSql = self._getDisplayNameSql()
        
        info = self._info()
        joins  = ", ".join(info['joins'])
        where  = " AND ".join(['t1.dbid <> 0'] + info['where'])
        
        return 'SELECT %s FROM %s WHERE %s AND %s = ' % \
                (kwds.get('select', displayNameSql), joins, where,
                 kwds.get('where', displayNameSql)) + '?'

class DynamicList(object):
    _xmlTemplate =  MarkupTemplate(                                            \
        '<DynamicList %s py:attrs="ns" Name="${this.Name}">'                   \
            '<Value py:for="v in this">${v}</Value>'                           \
        '</DynamicList>' % GenshiXmlNamespace)
           
    def __init__(self, name, values):
        self.Name = name
        self.values = iterable(values)
        
    def __len__(self):
        return len(self.values)
    
    def __getitem__(self, index):
        return self.values[index]
        
    def __iter__(self):
        return iter(self.values)
        
    def toXml(self, ns=CQXmlNamespaceUri):
        return self._xmlTemplate \
                   .generate(this=self, ns={'xmlns': ns}) \
                   .render('xml')

class DynamicLists(object):
    _xmlTemplate = MarkupTemplate(                                             \
        '<DynamicLists %s py:attrs="ns">'                                      \
            '<py:for each="dl in this">${Markup(dl.toXml(ns=None))}</py:for>'  \
        '</DynamicLists>' % GenshiXmlNamespace)
    
    def __init__(self, dynamicLists):
        self.dynamicLists = dynamicLists
        
    def __len__(self):
        return len(self.dynamicLists)
    
    def __getitem__(self, index):
        return self.dynamicLists[index]
        
    def __iter__(self):
        return iter(self.dynamicLists)

    def toXml(self, ns=CQXmlNamespaceUri):
        return self._xmlTemplate \
                   .generate(this=self, ns={'xmlns': ns}) \
                   .render('xml')
    
def loadDynamicList(name, obj):
    if isinstance(obj, Session):
        values = obj.GetListMembers(name)
        return DynamicList(name, values)
    
    if isinstance(obj, (str, unicode)):
        xml = XML(open(obj, 'r').read())
    elif isinstance(obj, _Element):
        xml = obj
    
    expected = '{%s}DynamicList' % CQXmlNamespaceUri
    if xml.tag != expected:
        raise ValueError, "%s is not a valid root node, expecting: %s" % \
                          (xml.tag, expected)
    
    expected = '{%s}Value' % CQXmlNamespaceUri
    name = xml.attrib['Name']
    values = [ v.text for v in xml.getchildren() if v.tag == expected ]
    return DynamicList(name, values)


def loadDynamicLists(obj):
    if isinstance(obj, Session):
        return DynamicLists([
            DynamicList(name, obj.GetListMembers(name))
                for name in obj.GetListDefNames()
        ]) 
    
    if isinstance(obj, (str, unicode)):
        if os.path.exists(obj):
            xml = XML(open(obj, 'r').read())
        else:
            xml = XML(obj)
    elif isinstance(obj, _Element):
        xml = obj
    else:
        raise RuntimeError("unknown type for obj: %s" % type(obj))
    
    expected = '{%s}DynamicLists' % CQXmlNamespaceUri
    if xml.tag != expected:
        raise ValueError, "%s is not a valid root node, expecting: %s" % \
                          (xml.tag, expected)
    
    valTag = '{%s}Value' % CQXmlNamespaceUri
    dynListTag = '{%s}DynamicList' % CQXmlNamespaceUri
    
    def strip(c): return c.text
    def values(e): return [strip(c) for c in e.getchildren() if c.tag == valTag]
    return DynamicLists([
        DynamicList(e.get('Name'), values(e))
            for e in xml.getchildren() if e.tag == dynListTag
    ])
    
    
#===============================================================================
# ClearQuest API Classes
#===============================================================================
        
class AdminSession(CQObject):
    CLSID = IID('{B48005F5-CF24-11D1-B37A-00A0C9851B52}')
    coclass_clsid = IID('{B48005F6-CF24-11D1-B37A-00A0C9851B52}')
    
    #@distributed
    def __init__(self, *args, **kwds):
        self.__dict__['session'] = self
        self.__dict__['_databaseName'] = 'MASTR'
        CQObject.__init__(self, *args)

    def AddSchemaRepoLocationFile(self, filePath=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(16, LCID, 1, (24, 0), ((8, 0),),filePath
            )

    def CQDataCodePageIsSet(self):
        return self._oleobj_.InvokeTypes(29, LCID, 1, (11, 0), (),)

    @returns('Database')
    def CreateDatabase(self, DbName=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(10, LCID, 1, (9, 0), ((8, 0),),DbName
            )
        if ret is not None:
            ret = Dispatch(ret, 'CreateDatabase', None, UnicodeToString=0)
        return ret

    @returns('Group')
    def CreateGroup(self, GroupName=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(7, LCID, 1, (9, 0), ((8, 0),),GroupName
            )
        if ret is not None:
            ret = Dispatch(ret, 'CreateGroup', None, UnicodeToString=0)
        return ret

    @returns('User')
    def CreateUser(self, LoginName=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(5, LCID, 1, (9, 0), ((8, 0),),LoginName
            )
        if ret is not None:
            ret = Dispatch(ret, 'CreateUser', None, UnicodeToString=0)
        return ret

    def CreateUserLDAPAuthenticated(self, LDAPloginName=defaultNamedNotOptArg, CQloginName=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(37, LCID, 1, (9, 0), ((8, 0), (8, 0)),LDAPloginName
            , CQloginName)
        if ret is not None:
            ret = Dispatch(ret, 'CreateUserLDAPAuthenticated', None, UnicodeToString=0)
        return ret

    def DeleteDatabase(self, DbName=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(11, LCID, 1, (24, 0), ((8, 0),),DbName
            )

    def DropSchemaRepoLocationFile(self, filePath=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(17, LCID, 1, (24, 0), ((8, 0),),filePath
            )

    def GetAttribute(self, obj=defaultNamedNotOptArg, func=defaultNamedNotOptArg):
        return self._ApplyTypes_(20, 1, (12, 0), ((9, 0), (8, 0)), 'GetAttribute', None,obj
            , func)

    def GetAttribute1(self, obj=defaultNamedNotOptArg, func=defaultNamedNotOptArg, field=defaultNamedNotOptArg):
        return self._ApplyTypes_(21, 1, (12, 0), ((9, 0), (8, 0), (8, 0)), 'GetAttribute1', None,obj
            , func, field)

    def GetAttribute2(self, obj=defaultNamedNotOptArg, func=defaultNamedNotOptArg, field=defaultNamedNotOptArg, arg=defaultNamedNotOptArg):
        return self._ApplyTypes_(22, 1, (12, 0), ((9, 0), (8, 0), (8, 0), (8, 0)), 'GetAttribute2', None,obj
            , func, field, arg)

    def GetAttribute3(self, obj=defaultNamedNotOptArg, func=defaultNamedNotOptArg, field=defaultNamedNotOptArg, arg1=defaultNamedNotOptArg
            , arg2=defaultNamedNotOptArg):
        return self._ApplyTypes_(23, 1, (12, 0), ((9, 0), (8, 0), (8, 0), (8, 0), (8, 0)), 'GetAttribute3', None,obj
            , func, field, arg1, arg2)

    def GetAuthenticationAlgorithm(self):
        return self._oleobj_.InvokeTypes(36, LCID, 1, (3, 0), (),)

    def GetAuthenticationLoginName(self):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(40, LCID, 1, (8, 0), (),)

    def GetCQDataCodePage(self):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(32, LCID, 1, (8, 0), (),)

    def GetCQLDAPMap(self):
        return self._oleobj_.InvokeTypes(42, LCID, 1, (3, 0), (),)

    def GetClientCodePage(self):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(33, LCID, 1, (8, 0), (),)

    @returns('Database')
    def GetDatabase(self, DbName=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(9, LCID, 1, (9, 0), ((8, 0),),DbName
            )
        if ret is not None:
            ret = Dispatch(ret, 'GetDatabase', None, UnicodeToString=0)
        return ret

    def GetEveryoneGroupName(self):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(43, LCID, 1, (8, 0), (),)

    @returns('Group')
    def GetGroup(self, GroupName=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(8, LCID, 1, (9, 0), ((8, 0),),GroupName
            )
        if ret is not None:
            ret = Dispatch(ret, 'GetGroup', None, UnicodeToString=0)
        return ret

    def GetLastSchemaRepoInfo(self, Vendor=pythoncom.Missing, Server=pythoncom.Missing, database=pythoncom.Missing, ROLogin=pythoncom.Missing
            , ROPassword=pythoncom.Missing):
        return self._ApplyTypes_(15, 1, (11, 0), ((16392, 2), (16392, 2), (16392, 2), (16392, 2), (16392, 2)), 'GetLastSchemaRepoInfo', None,Vendor
            , Server, database, ROLogin, ROPassword)

    def GetLastSchemaRepoInfoByDbSet(self, dbset=defaultNamedNotOptArg, Vendor=pythoncom.Missing, Server=pythoncom.Missing, database=pythoncom.Missing
            , ROLogin=pythoncom.Missing, ROPassword=pythoncom.Missing):
        return self._ApplyTypes_(26, 1, (11, 0), ((8, 0), (16392, 2), (16392, 2), (16392, 2), (16392, 2), (16392, 2)), 'GetLastSchemaRepoInfoByDbSet', None,dbset
            , Vendor, Server, database, ROLogin, ROPassword
            )

    @returns('User')
    def GetUser(self, LoginName=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(6, LCID, 1, (9, 0), ((8, 0),),LoginName
            )
        if ret is not None:
            ret = Dispatch(ret, 'GetUser', None, UnicodeToString=0)
        return ret

    def GetUserLoginName(self):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(38, LCID, 1, (8, 0), (),)

    def InstallAddDbSet(self, dbset=defaultNamedNotOptArg, dbVendor=defaultNamedNotOptArg, serverArg=defaultNamedNotOptArg, database=defaultNamedNotOptArg
            , ROLogin=defaultNamedNotOptArg, ROPassword=defaultNamedNotOptArg):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(13, LCID, 1, (8, 0), ((8, 0), (8, 0), (8, 0), (8, 0), (8, 0), (8, 0)),dbset
            , dbVendor, serverArg, database, ROLogin, ROPassword
            )

    def InstallDropDbSet(self, dbset=defaultNamedNotOptArg):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(14, LCID, 1, (8, 0), ((8, 0),),dbset
            )

    def IsClientCodePageCompatibleWithCQDataCodePage(self):
        return self._oleobj_.InvokeTypes(31, LCID, 1, (11, 0), (),)

    def IsMultisiteActivated(self):
        return self._oleobj_.InvokeTypes(25, LCID, 1, (11, 0), (),)

    def IsReplicated(self):
        return self._oleobj_.InvokeTypes(24, LCID, 1, (11, 0), (),)

    def IsSiteWorkingMaster(self):
        return self._oleobj_.InvokeTypes(41, LCID, 1, (11, 0), (),)

    def IsStringInCQDataCodePage(self, string=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(28, LCID, 1, (11, 0), ((8, 0),),string
            )

    def IsUnsupportedClientCodePage(self):
        return self._oleobj_.InvokeTypes(30, LCID, 1, (11, 0), (),)

    def Logon(self, Name=defaultNamedNotOptArg, password=defaultNamedNotOptArg, masterDbName=defaultNamedNotOptArg):
        self.__dict__['_loginName'] = Name
        self.__dict__['_password'] = password
        self.__dict__['_databaseSet'] = masterDbName
        return self._oleobj_.InvokeTypes(12, LCID, 1, (24, 0), ((8, 0), (8, 0), (8, 0)),Name
            , password, masterDbName)

    def LookupSchemaRepoLocationFiles(self):
        return self._ApplyTypes_(18, 1, (12, 0), (), 'LookupSchemaRepoLocationFiles', None,)

    def RegisterSchemaRepoFromFile(self, filePath=defaultNamedNotOptArg):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(19, LCID, 1, (8, 0), ((8, 0),),filePath
            )

    def RegisterSchemaRepoFromFileByDbSet(self, dbset=defaultNamedNotOptArg, filePath=defaultNamedNotOptArg):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(27, LCID, 1, (8, 0), ((8, 0), (8, 0)),dbset
            , filePath)

    def SetAuthenticationAlgorithm(self, authMode=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(35, LCID, 1, (24, 0), ((3, 0),),authMode
            )

    def ValidateStringInCQDataCodePage(self, string=defaultNamedNotOptArg):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(34, LCID, 1, (8, 0), ((8, 0),),string
            )

    def ValidateUserCredentials(self, login=defaultNamedNotOptArg, pw=defaultNamedNotOptArg):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(39, LCID, 1, (8, 0), ((8, 0), (8, 0)),login
            , pw)

    _prop_map_get_ = {
        "Databases": (3, 2, (9, 0), (), "Databases", None),
        "Groups": (2, 2, (9, 0), (), "Groups", None),
        "Schemas": (4, 2, (9, 0), (), "Schemas", None),
        "Users": (1, 2, (9, 0), (), "Users", None),
    }
    _prop_map_put_ = {
        "Databases" : ((3, LCID, 4, 0),()),
        "Groups" : ((2, LCID, 4, 0),()),
        "Schemas" : ((4, LCID, 4, 0),()),
        "Users" : ((1, LCID, 4, 0),()),
    }
    
    @cache
    def connectOptions(self, name='MASTR'):
        return ';'.join([
            c for c in getConnectOptionsFromRegistry(self._databaseSet, name)
                if c.startswith(('INSTANCE', 'PORT'))
        ])
    
    @cache
    def connectString(self, name='MASTR'):
        connectOptions = self.connectOptions(name)
        class _wrap(object):
            def __init__(self, obj):
                self._obj = obj
                self._obj.__dict__['ConnectOptions'] = connectOptions
            def __getitem__(self, item):
                return getattr(self._obj, item)
        
        db = self.GetDatabase(name)
        if not db:
            raise ValueError, "Unknown database name: '%s'" % name
            
        if db.Vendor == DatabaseVendor.Oracle:
            return "Driver={Rational DataDirect 5.X Oracle Wire Protocol};"    \
                   "UID=%(DBOLogin)s;PWD=%(DBOPassword)s;HostName=%(Server)s;" \
                   "SID=%(DatabaseName)s;%(ConnectOptions)s" %                 \
                   _wrap(db)
        elif db.Vendor == DatabaseVendor.SQLServer:
            return "Driver={SQL Server};UID=%(DBOLogin)s;PWD=%(DBOPassword)s;" \
                   "SERVER=%(Server)s;DATABASE=%(DatabaseName)s;"              \
                   "%(ConnectOptions)s" %                                      \
                   _wrap(db)
        elif db.Vendor == DatabaseVendor.DB2:
            cs = "Driver={Rational DataDirect 5.X DB2 Wire Protocol};"         \
                 "UID=%(DBOLogin)s;PWD=%(DBOPassword)s;IP=%(Server)s;"         \
                 "DB=%(DatabaseName)s;%(ConnectOptions)s" %                    \
                  _wrap(db)
            if 'PORT=' not in cs:
                cs += ';PORT=50000'
            return cs
        elif db.Vendor == DatabaseVendor.Access:
            return "Driver={Microsoft Access Driver (*.mdb)};"                 \
                   "DBQ=%(DatabaseName)s" %                                    \
                   _wrap(db)
        else:
            raise db.DatabaseVendorNotSupported, DatabaseVendor[db.Vendor]        
    
    @cache
    def db(self):
        return db.Connection(self)
    
    def addUsers(self, users, **props):
        if not users.__class__ == Users:
            raise TypeError, "expecting Users, got: %s" % users.__class__
        return self.addUsersFromXml(XML(users.toXml()), **props)

    def addUsersFromXml(self, usersXml, **props):
        if not usersXml.__class__ == _Element:
            raise TypeError, "expecting etree._Element type"
        existing = self.Users
        for userXml in usersXml.iterchildren():
            name = userXml.get('Name')
            if name in existing:
                user = self.GetUser(name)
            else:
                user = self.CreateUser(name)
            user.applyXml(userXml, **props)
    
    @cache
    def getSchema(self, name):
        schemas = self.Schemas
        found = False
        schema = None
        count = schemas.Count
        for i in xrange(0, schemas.Count):
            schema = schemas[i]
            if schema.Name == name:
                found = True
                break
        
        if not found:
            raise ValueError, "no schema named '%s' found" % name
        else:
            return schema
        
    
    def createDatabase(self, logicalName, dbName, schemaName, schemaRev,**kwds):
        """
        @param logicalName: L{string} logical name of the database (e.g. CLSIC).
        @param databaseName: L{string} physical name of the database
        @param databaseVendorName:
                    L{string} name of the vendor (should correspond to the 
                    string values present in L{constants.DatabaseVendor}.
        @param databaseLogin: L{string} database login name
        @param databasePassword: L{string} password for the account above
        @param serverName: L{string} database server name
        @param description: L{string} description of the database
        @param schemaName:
                    L{string} name of the schema to use for the new database
                    (L{ValueError} is thrown if the schema name can not be 
                    found)
        @param **kwds: Optional parameters are as follows:
               'databaseLogin'      
               'databasePassword'
               'description'
               'databaseVendorName': L{constants.DatabaseVendor}
               'databaseServer' 
        """
        schema = self.getSchema(schemaName)
        revision = schema.getRevision(schemaRev)
        master = self.GetDatabase('MASTR')
        
        db = self.CreateDatabase(logicalName)
        try:
            vendor = getattr(DatabaseVendor, kwds['databaseVendorName'])
        except KeyError:
            vendor = master.Vendor
        finally:
            db.Vendor = vendor
        
        db.Name = logicalName
        db.Description = kwds.get('description', '')
        db.DatabaseName = dbName
        db.Server = kwds.get('databaseServer', master.Server)
        
        login = kwds.get('databaseLogin', master.DBOLogin)
        password = kwds.get('databasePassword', master.DBOPassword)
        db.ROLogin = login
        db.RWLogin = login
        db.DBOLogin = login
        db.ROPassword = password
        db.RWPassword = password
        db.DBOPassword = password
        
        db.SetInitialSchemaRev(revision)
        db.ApplyPropertyChanges()
        
        return db
                        
    @cache
    @selectSingle
    def getTablePrefix(self, name): pass
    
    @xml()
    def createUserFromXml(self, xmlText, **kwds): pass
    
    @xml(method='GetUser')
    def updateUserFromXml(self, xmlText, **kwds): pass
    
    @xml()
    def createUsersFromXml(self, xmlText): pass
    
    @xml()
    def createGroupFromXml(self, xmlText): pass
    
    @xml()
    def createGroupsFromXml(self, xmlText): pass
    
    @xml()
    def createDatabaseFromXml(self, xmlText): pass
    
    @xml()
    def createDatabasesFromXml(self, xmlText): pass
    
    def setVisible(self, visible, databaseName):
        v = int(bool(visible))
        if v not in (0, 1):
            raise ValueError("visible must be boolean")
        self.db().execute(
            "UPDATE master_dbs SET is_visible = %d WHERE name = '%s'" % (
                v, databaseName
            )
        )
        

class ChartMgr(CQObject):
    CLSID = IID('{4C183050-FF8F-11D0-A051-00A0C9233DE1}')
    coclass_clsid = IID('{4C183051-FF8F-11D0-A051-00A0C9233DE1}')

    def MakeJPEG(self, pszPathName=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(9, LCID, 1, (11, 0), ((8, 0),),pszPathName
            )

    def MakePNG(self, pszPathName=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(10, LCID, 1, (11, 0), ((8, 0),),pszPathName
            )

    def SetResultSet(self, lpResultSet=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(8, LCID, 1, (24, 0), ((9, 0),),lpResultSet
            )

    _prop_map_get_ = {
        "GrayScale": (3, 2, (11, 0), (), "GrayScale", None),
        "Height": (7, 2, (2, 0), (), "Height", None),
        "Interlaced": (5, 2, (11, 0), (), "Interlaced", None),
        "OptimizeCompression": (4, 2, (11, 0), (), "OptimizeCompression", None),
        "Progressive": (2, 2, (11, 0), (), "Progressive", None),
        "Quality": (1, 2, (2, 0), (), "Quality", None),
        "Width": (6, 2, (2, 0), (), "Width", None),
    }
    _prop_map_put_ = {
        "GrayScale" : ((3, LCID, 4, 0),()),
        "Height" : ((7, LCID, 4, 0),()),
        "Interlaced" : ((5, LCID, 4, 0),()),
        "OptimizeCompression" : ((4, LCID, 4, 0),()),
        "Progressive" : ((2, LCID, 4, 0),()),
        "Quality" : ((1, LCID, 4, 0),()),
        "Width" : ((6, LCID, 4, 0),()),
    }

class Attachment(CQObject):
    CLSID = IID('{CE573C27-3B54-11D1-B2BF-00A0C9851B52}')
    coclass_clsid = IID('{CE573C28-3B54-11D1-B2BF-00A0C9851B52}')

    def Load(self, TempFile=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(5, LCID, 1, (11, 0), ((8, 0),),TempFile
            )

    _prop_map_get_ = {
        "Description": (3, 2, (8, 0), (), "Description", None),
        "DisplayName": (4, 2, (8, 0), (), "DisplayName", None),
        "FileSize": (2, 2, (3, 0), (), "FileSize", None),
        "filename": (1, 2, (8, 0), (), "filename", None),
    }
    _prop_map_put_ = {
        "Description" : ((3, LCID, 4, 0),()),
        "DisplayName" : ((4, LCID, 4, 0),()),
        "FileSize" : ((2, LCID, 4, 0),()),
        "filename" : ((1, LCID, 4, 0),()),
    }

class AttachmentField(CQObject):
    CLSID = IID('{CE573C23-3B54-11D1-B2BF-00A0C9851B52}')
    coclass_clsid = IID('{CE573C24-3B54-11D1-B2BF-00A0C9851B52}')

    _prop_map_get_ = {
        "Attachments": (3, 2, (9, 0), (), "Attachments", None),
        "DisplayNameHeader": (2, 2, (12, 0), (), "DisplayNameHeader", None),
        "fieldname": (1, 2, (8, 0), (), "fieldname", None),
    }
    _prop_map_put_ = {
        "Attachments" : ((3, LCID, 4, 0),()),
        "DisplayNameHeader" : ((2, LCID, 4, 0),()),
        "fieldname" : ((1, LCID, 4, 0),()),
    }

class AttachmentFields(CQObject):
    CLSID = IID('{CE573C21-3B54-11D1-B2BF-00A0C9851B52}')
    coclass_clsid = IID('{CE573C22-3B54-11D1-B2BF-00A0C9851B52}')

    @returns(AttachmentField)
    def item(self, Index=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(0, LCID, 1, (9, 0), ((16396, 0),),Index
            )
        if ret is not None:
            ret = Dispatch(ret, 'item', None, UnicodeToString=0)
        return ret

    _prop_map_get_ = {
        "Count": (1, 2, (3, 0), (), "Count", None),
    }
    _prop_map_put_ = {
        "Count" : ((1, LCID, 4, 0),()),
        "_NewEnum" : ((-4, LCID, 4, 0),()),
    }
    # Default method for this class is 'item'
    @returns(AttachmentField)
    def __call__(self, Index=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(0, LCID, 1, (9, 0), ((16396, 0),),Index
            )
        if ret is not None:
            ret = Dispatch(ret, '__call__', None, UnicodeToString=0)
        return ret

    # str(ob) and int(ob) will use __call__
    def __unicode__(self, *args):
        try:
            return unicode(self.__call__(*args))
        except pythoncom.com_error:
            return repr(self)
    def __str__(self, *args):
        return str(self.__unicode__(*args))
    def __int__(self, *args):
        return int(self.__call__(*args))
    
    @returns(CQIterator(AttachmentField))
    def __iter__(self):
        "Return a Python iterator for this object"
        ob = self._oleobj_.InvokeTypes(-4,LCID,3,(13, 10),())
        return win32com.client.util.Iterator(ob)
    def _NewEnum(self):
        "Create an enumerator from this object"
        return win32com.client.util.WrapEnum(self._oleobj_.InvokeTypes(-4,LCID,3,(13, 10),()),None)
    @returns(AttachmentField)
    def __getitem__(self, index):
        "Allow this class to be accessed as a collection"
        if not self.__dict__.has_key('_enum_'):
            self.__dict__['_enum_'] = self._NewEnum()
        return self._enum_.__getitem__(index)
    #This class has Count() property - allow len(ob) to provide this
    def __len__(self):
        return self._ApplyTypes_(*(1, 2, (3, 0), (), "Count", None))
    #This class has a __len__ - this is needed so 'if object:' always returns TRUE.
    def __nonzero__(self):
        return True

class Attachments(CQObject):
    CLSID = IID('{CE573C25-3B54-11D1-B2BF-00A0C9851B52}')
    coclass_clsid = IID('{CE573C26-3B54-11D1-B2BF-00A0C9851B52}')

    def Add(self, filename=defaultNamedNotOptArg, Description=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(2, LCID, 1, (11, 0), ((8, 0), (8, 0)),filename
            , Description)

    def Delete(self, Subscript=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(3, LCID, 1, (11, 0), ((12, 0),),Subscript
            )

    @returns(Attachment)
    def item(self, Index=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(0, LCID, 1, (9, 0), ((16396, 0),),Index
            )
        if ret is not None:
            ret = Dispatch(ret, 'item', None, UnicodeToString=0)
        return ret

    _prop_map_get_ = {
        "Count": (1, 2, (3, 0), (), "Count", None),
    }
    _prop_map_put_ = {
        "Count" : ((1, LCID, 4, 0),()),
        "_NewEnum" : ((-4, LCID, 4, 0),()),
    }
    # Default method for this class is 'item'
    @returns(Attachment)
    def __call__(self, Index=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(0, LCID, 1, (9, 0), ((16396, 0),),Index
            )
        if ret is not None:
            ret = Dispatch(ret, '__call__', None, UnicodeToString=0)
        return ret

    # str(ob) and int(ob) will use __call__
    def __unicode__(self, *args):
        try:
            return unicode(self.__call__(*args))
        except pythoncom.com_error:
            return repr(self)
    def __str__(self, *args):
        return str(self.__unicode__(*args))
    def __int__(self, *args):
        return int(self.__call__(*args))
    @returns(CQIterator(Attachment))
    def __iter__(self):
        "Return a Python iterator for this object"
        ob = self._oleobj_.InvokeTypes(-4,LCID,3,(13, 10),())
        return win32com.client.util.Iterator(ob)
    def _NewEnum(self):
        "Create an enumerator from this object"
        return win32com.client.util.WrapEnum(self._oleobj_.InvokeTypes(-4,LCID,3,(13, 10),()),None)
    @returns(Attachment)
    def __getitem__(self, index):
        "Allow this class to be accessed as a collection"
        if not self.__dict__.has_key('_enum_'):
            self.__dict__['_enum_'] = self._NewEnum()
        return self._enum_.__getitem__(index)
    #This class has Count() property - allow len(ob) to provide this
    def __len__(self):
        return self._ApplyTypes_(*(1, 2, (3, 0), (), "Count", None))
    #This class has a __len__ - this is needed so 'if object:' always returns TRUE.
    def __nonzero__(self):
        return True

class Database(CQObject):
    CLSID = IID('{B48005F0-CF24-11D1-B37A-00A0C9851B52}')
    coclass_clsid = IID('{B48005F2-CF24-11D1-B37A-00A0C9851B52}')

    def ApplyPropertyChanges(self, varForceEmpty=defaultNamedOptArg):
        # Result is a Unicode object - return as-is for this version of Python
        self.__dict__['_applyPropertyChangesLog'] = \
            self._oleobj_.InvokeTypes(19, LCID, 1, (8, 0), ((12, 16),),varForceEmpty
            )
        return

    def ApplyPropertyChangesWithCopy(self, varForceEmpty=defaultNamedOptArg):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(20, LCID, 1, (8, 0), ((12, 16),),varForceEmpty
            )

    def ApplyTimeoutValuesToDb(self):
        return self._oleobj_.InvokeTypes(22, LCID, 1, (24, 0), (),)

    def GetAllUsers(self, include_inactive=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(27, LCID, 1, (9, 0), ((11, 0),),include_inactive
            )
        if ret is not None:
            ret = Dispatch(ret, 'GetAllUsers', None, UnicodeToString=0)
        return ret

    def SetInitialSchemaRev(self, schemaRev=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(18, LCID, 1, (24, 0), ((9, 0),),schemaRev
            )

    def Upgrade(self, schemaRev=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(17, LCID, 1, (24, 0), ((9, 0),),schemaRev
            )

    def UpgradeMasterUserInfo(self):
        return self._oleobj_.InvokeTypes(21, LCID, 1, (24, 0), (),)

    _prop_map_get_ = {
        "CheckTimeoutInterval": (12, 2, (3, 0), (), "CheckTimeoutInterval", None),
        "ConnectHosts": (23, 2, (12, 0), (), "ConnectHosts", None),
        "ConnectProtocols": (24, 2, (12, 0), (), "ConnectProtocols", None),
        "DBOLogin": (10, 2, (8, 0), (), "DBOLogin", None),
        "DBOPassword": (11, 2, (8, 0), (), "DBOPassword", None),
        "DatabaseFeatureLevel": (26, 2, (3, 0), (), "DatabaseFeatureLevel", None),
        "DatabaseName": (4, 2, (8, 0), (), "DatabaseName", None),
        "Description": (3, 2, (8, 0), (), "Description", None),
        "IsMaster": (25, 2, (11, 0), (), "IsMaster", None),
        "Name": (2, 2, (8, 0), (), "Name", None),
        "ROLogin": (6, 2, (8, 0), (), "ROLogin", None),
        "ROPassword": (7, 2, (8, 0), (), "ROPassword", None),
        "RWLogin": (8, 2, (8, 0), (), "RWLogin", None),
        "RWPassword": (9, 2, (8, 0), (), "RWPassword", None),
        "Server": (5, 2, (8, 0), (), "Server", None),
        "SubscribedGroups": (15, 2, (9, 0), (), "SubscribedGroups", None),
        "SubscribedUsers": (14, 2, (9, 0), (), "SubscribedUsers", None),
        "TimeoutInterval": (13, 2, (3, 0), (), "TimeoutInterval", None),
        "Vendor": (1, 2, (2, 0), (), "Vendor", None),
        "SchemaRev": (16, 2, (9, 0), (), "schemaRev", None),
    }
    _prop_map_put_ = {
        "CheckTimeoutInterval" : ((12, LCID, 4, 0),()),
        "ConnectHosts" : ((23, LCID, 4, 0),()),
        "ConnectProtocols" : ((24, LCID, 4, 0),()),
        "DBOLogin" : ((10, LCID, 4, 0),()),
        "DBOPassword" : ((11, LCID, 4, 0),()),
        "DatabaseFeatureLevel" : ((26, LCID, 4, 0),()),
        "DatabaseName" : ((4, LCID, 4, 0),()),
        "Description" : ((3, LCID, 4, 0),()),
        "IsMaster" : ((25, LCID, 4, 0),()),
        "Name" : ((2, LCID, 4, 0),()),
        "ROLogin" : ((6, LCID, 4, 0),()),
        "ROPassword" : ((7, LCID, 4, 0),()),
        "RWLogin" : ((8, LCID, 4, 0),()),
        "RWPassword" : ((9, LCID, 4, 0),()),
        "Server" : ((5, LCID, 4, 0),()),
        "SubscribedGroups" : ((15, LCID, 4, 0),()),
        "SubscribedUsers" : ((14, LCID, 4, 0),()),
        "TimeoutInterval" : ((13, LCID, 4, 0),()),
        "Vendor" : ((1, LCID, 4, 0),()),
        "SchemaRev" : ((16, LCID, 4, 0),()),
    }
    
    def commit(self):
        self.ApplyPropertyChanges()

class DatabaseDesc(CQObject):
    CLSID = IID('{D267C190-245F-11D1-A4ED-00A0C9243B7B}')
    coclass_clsid = IID('{D267C191-245F-11D1-A4ED-00A0C9243B7B}')

    def GetDatabaseConnectString(self):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(3, LCID, 1, (8, 0), (),)

    def GetDatabaseName(self):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(1, LCID, 1, (8, 0), (),)

    def GetDatabaseSetName(self):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(2, LCID, 1, (8, 0), (),)

    def GetDescription(self):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(5, LCID, 1, (8, 0), (),)

    def GetIsMaster(self):
        return self._oleobj_.InvokeTypes(4, LCID, 1, (11, 0), (),)

    def GetLogin(self):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(6, LCID, 1, (8, 0), (),)

    def GetPassword(self):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(7, LCID, 1, (8, 0), (),)

    _prop_map_get_ = {
    }
    _prop_map_put_ = {
    }
    
    @cache
    def getDatabasePhysicalName(self):
        return re.findall('DATABASE=([^;]+).*$',
                          self.GetDatabaseConnectString(),
                          re.IGNORECASE)[0]
    

class Databases(CQCollection):
    CLSID = IID('{1F632611-D0B1-11D1-B37A-00A0C9851B52}')
    coclass_clsid = IID('{1F632613-D0B1-11D1-B37A-00A0C9851B52}')

    @returns(Database)
    def item(self, Index=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(0, LCID, 1, (9, 0), ((16396, 0),),Index
            )
        if ret is not None:
            ret = Dispatch(ret, 'item', None, UnicodeToString=0)
        return ret

    _prop_map_get_ = {
        "Count": (1, 2, (3, 0), (), "Count", None),
    }
    _prop_map_put_ = {
        "Count" : ((1, LCID, 4, 0),()),
        "_NewEnum" : ((-4, LCID, 4, 0),()),
    }
    # Default method for this class is 'item'
    @returns(Database)
    def __call__(self, Index=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(0, LCID, 1, (9, 0), ((16396, 0),),Index
            )
        if ret is not None:
            ret = Dispatch(ret, '__call__', None, UnicodeToString=0)
        return ret

    # str(ob) and int(ob) will use __call__
    def __unicode__(self, *args):
        try:
            return unicode(self.__call__(*args))
        except pythoncom.com_error:
            return repr(self)
    def __str__(self, *args):
        return str(self.__unicode__(*args))
    def __int__(self, *args):
        return int(self.__call__(*args))
    @returns(CQIterator(Database))
    def __iter__(self):
        "Return a Python iterator for this object"
        ob = self._oleobj_.InvokeTypes(-4,LCID,3,(13, 10),())
        return win32com.client.util.Iterator(ob)
    def _NewEnum(self):
        "Create an enumerator from this object"
        return win32com.client.util.WrapEnum(self._oleobj_.InvokeTypes(-4,LCID,3,(13, 10),()),None)
    @returns(Database)
    def __getitem__(self, index):
        "Allow this class to be accessed as a collection"
        if not self.__dict__.has_key('_enum_'):
            self.__dict__['_enum_'] = self._NewEnum()
        return self._enum_.__getitem__(index)
    #This class has Count() property - allow len(ob) to provide this
    def __len__(self):
        return self._ApplyTypes_(*(1, 2, (3, 0), (), "Count", None))
    #This class has a __len__ - this is needed so 'if object:' always returns TRUE.
    def __nonzero__(self):
        return True

class Entity(CQObject):
    CLSID = IID('{E9F82951-73A9-11D0-A42E-00A024DED613}')
    coclass_clsid = IID('{E9F82952-73A9-11D0-A42E-00A024DED613}')
    
    def __init__(self, *args, **kwds):
        CQObject.__init__(self, *args, **kwds)
        self.__dict__['_postCommitTasks'] = list()
        self.__dict__['_allowUnsupportedUpdates'] = False
    
    def AddAttachmentFieldValue(self, attachment_fieldname=defaultNamedNotOptArg, filename=defaultNamedNotOptArg, Description=defaultNamedNotOptArg):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(39, LCID, 1, (8, 0), ((8, 0), (8, 0), (8, 0)),attachment_fieldname
            , filename, Description)

    @raiseExceptionOnError(EntityAddFieldValueError)
    def AddFieldValue(self, fieldname=defaultNamedNotOptArg, new_value=defaultNamedNotOptArg):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(27, LCID, 1, (8, 0), ((8, 0), (12, 0)),fieldname
            , new_value)

    def BeginNewFieldUpdateGroup(self):
        return self._oleobj_.InvokeTypes(36, LCID, 1, (24, 0), (),)

    @raiseExceptionOnError(EntityCommitError)
    def Commit(self):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(25, LCID, 1, (8, 0), (),)

    def DeleteAttachmentFieldValue(self, attachment_fieldname=defaultNamedNotOptArg, element_displayname=defaultNamedNotOptArg):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(40, LCID, 1, (8, 0), ((8, 0), (8, 0)),attachment_fieldname
            , element_displayname)

    @raiseExceptionOnError(EntityDeleteFieldValueError)
    def DeleteFieldValue(self, fieldname=defaultNamedNotOptArg, new_value=defaultNamedNotOptArg):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(28, LCID, 1, (8, 0), ((8, 0), (12, 0)),fieldname
            , new_value)

    def EditAttachmentFieldDescription(self, attachment_fieldname=defaultNamedNotOptArg, element_displayname=defaultNamedNotOptArg, new_description=defaultNamedNotOptArg):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(41, LCID, 1, (8, 0), ((8, 0), (8, 0), (8, 0)),attachment_fieldname
            , element_displayname, new_description)

    def EditEntity(self, entity=defaultNamedNotOptArg, edit_action_name=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(56, LCID, 1, (24, 0), ((9, 0), (8, 0)),entity
            , edit_action_name)

    def FireNamedHook(self, hookName=defaultNamedNotOptArg, parameter=defaultNamedNotOptArg):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(45, LCID, 1, (8, 0), ((8, 0), (12, 0)),hookName
            , parameter)

    def GetActionDefForm(self, action_def_name=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(19, LCID, 1, (9, 0), ((8, 0),),action_def_name
            )
        if ret is not None:
            ret = Dispatch(ret, 'GetActionDefForm', None, UnicodeToString=0)
        return ret

    def GetActionName(self):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(48, LCID, 1, (8, 0), (),)

    def GetActionType(self):
        return self._oleobj_.InvokeTypes(49, LCID, 1, (3, 0), (),)

    def GetAllDuplicates(self):
        return self._ApplyTypes_(24, 1, (12, 0), (), 'GetAllDuplicates', None,)

    @returns('FieldInfo')
    def GetAllFieldValues(self):
        return self._ApplyTypes_(31, 1, (12, 0), (), 'GetAllFieldValues', None,)

    def GetAttachmentDisplayName(self, fieldname=defaultNamedNotOptArg, attachDBID=defaultNamedNotOptArg):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(57, LCID, 1, (8, 0), ((8, 0), (8, 0)),fieldname
            , attachDBID)

    def GetAttachmentDisplayNameHeader(self, attachment_fieldname=defaultNamedNotOptArg):
        return self._ApplyTypes_(43, 1, (12, 0), ((8, 0),), 'GetAttachmentDisplayNameHeader', None,attachment_fieldname
            )

    def GetDbId(self):
        return self._oleobj_.InvokeTypes(14, LCID, 1, (3, 0), (),)

    def GetDefaultActionName(self):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(50, LCID, 1, (8, 0), (),)

    def GetDisplayName(self):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(11, LCID, 1, (8, 0), (),)

    def GetDuplicates(self):
        return self._ApplyTypes_(23, 1, (12, 0), (), 'GetDuplicates', None,)

    def GetEntityDefName(self):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(3, LCID, 1, (8, 0), (),)

    def GetFieldChoiceList(self, fieldname=defaultNamedNotOptArg):
        return self._ApplyTypes_(10, 1, (12, 0), ((8, 0),), 'GetFieldChoiceList', None,fieldname
            )

    def GetFieldChoiceType(self, fieldname=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(44, LCID, 1, (3, 0), ((8, 0),),fieldname
            )

    def GetFieldMaxLength(self, fieldname=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(47, LCID, 1, (3, 0), ((8, 0),),fieldname
            )

    def GetFieldNames(self):
        return self._ApplyTypes_(4, 1, (12, 0), (), 'GetFieldNames', None,)

    def GetFieldOriginalValue(self, fieldname=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(30, LCID, 1, (9, 0), ((8, 0),),fieldname
            )
        if ret is not None:
            ret = Dispatch(ret, 'GetFieldOriginalValue', None, UnicodeToString=0)
        return ret

    def GetFieldReferencedEntityDefName(self, fieldname=defaultNamedNotOptArg):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(51, LCID, 1, (8, 0), ((8, 0),),fieldname
            )

    def GetFieldRequiredness(self, fieldname=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(8, LCID, 1, (3, 0), ((8, 0),),fieldname
            )

    def GetFieldStringValue(self, fieldname=defaultNamedNotOptArg):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(58, LCID, 1, (8, 0), ((8, 0),),fieldname
            ) or u''

    def GetFieldStringValueAsList(self, fieldname=defaultNamedNotOptArg):
        return self._ApplyTypes_(59, 1, (12, 0), ((8, 0),), 'GetFieldStringValueAsList', None,fieldname
            ) or []

    def GetFieldStringValues(self, varfieldNames=defaultNamedNotOptArg):
        return self._ApplyTypes_(61, 1, (12, 0), ((12, 0),), 'GetFieldStringValues', None,varfieldNames
            ) or []

    def GetFieldType(self, fieldname=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(7, LCID, 1, (3, 0), ((8, 0),),fieldname
            )

    @returns('FieldInfo')
    def GetFieldValue(self, fieldname=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(29, LCID, 1, (9, 0), ((8, 0),),fieldname
            )
        if ret is not None:
            ret = Dispatch(ret, 'GetFieldValue', None, UnicodeToString=0)
        return ret

    def GetFieldsUpdatedThisAction(self):
        return self._ApplyTypes_(35, 1, (12, 0), (), 'GetFieldsUpdatedThisAction', None,)

    def GetFieldsUpdatedThisEntireAction(self):
        return self._ApplyTypes_(62, 1, (12, 0), (), 'GetFieldsUpdatedThisEntireAction', None,)

    def GetFieldsUpdatedThisGroup(self):
        return self._ApplyTypes_(34, 1, (12, 0), (), 'GetFieldsUpdatedThisGroup', None,)

    def GetFieldsUpdatedThisSetValue(self):
        return self._ApplyTypes_(33, 1, (12, 0), (), 'GetFieldsUpdatedThisSetValue', None,)

    def GetHistoryDisplayNameHeader(self):
        return self._ApplyTypes_(38, 1, (12, 0), (), 'GetHistoryDisplayNameHeader', None,)

    def GetHistoryFieldValue(self):
        ret = self._oleobj_.InvokeTypes(37, LCID, 1, (9, 0), (),)
        if ret is not None:
            ret = Dispatch(ret, 'GetHistoryFieldValue', None, UnicodeToString=0)
        return ret

    def GetInvalidFieldValues(self):
        return self._ApplyTypes_(32, 1, (12, 0), (), 'GetInvalidFieldValues', None,)

    def GetLegalAccessibleActionDefNames(self):
        return self._ApplyTypes_(63, 1, (12, 0), (), 'GetLegalAccessibleActionDefNames', None,)

    def GetLegalActionDefNames(self):
        return self._ApplyTypes_(18, 1, (12, 0), (), 'GetLegalActionDefNames', None,)

    def GetOriginal(self):
        ret = self._oleobj_.InvokeTypes(16, LCID, 1, (9, 0), (),)
        if ret is not None:
            ret = Dispatch(ret, 'GetOriginal', None, UnicodeToString=0)
        return ret

    def GetOriginalId(self):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(17, LCID, 1, (8, 0), (),)

    @returns('Session')
    def GetSession(self):
        ret = self._oleobj_.InvokeTypes(20, LCID, 1, (9, 0), (),)
        if ret is not None:
            ret = Dispatch(ret, 'GetSession', None, UnicodeToString=0)
        return ret

    def GetType(self):
        return self._oleobj_.InvokeTypes(12, LCID, 1, (3, 0), (),)

    def HasDuplicates(self):
        return self._oleobj_.InvokeTypes(21, LCID, 1, (11, 0), (),)

    def InvalidateFieldChoiceList(self, fieldname=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(53, LCID, 1, (24, 0), ((8, 0),),fieldname
            )

    def IsDuplicate(self):
        return self._oleobj_.InvokeTypes(15, LCID, 1, (11, 0), (),)

    def IsEditable(self):
        return self._oleobj_.InvokeTypes(5, LCID, 1, (11, 0), (),)

    def IsOriginal(self):
        return self._oleobj_.InvokeTypes(22, LCID, 1, (11, 0), (),)

    def LoadAttachment(self, attachment_fieldname=defaultNamedNotOptArg, element_displayname=defaultNamedNotOptArg, destination_filename=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(42, LCID, 1, (3, 0), ((8, 0), (8, 0), (8, 0)),attachment_fieldname
            , element_displayname, destination_filename)

    def LookupStateName(self):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(13, LCID, 1, (8, 0), (),)

    def Reload(self):
        return self._oleobj_.InvokeTypes(54, LCID, 1, (24, 0), (),)

    def Revert(self):
        return self._oleobj_.InvokeTypes(6, LCID, 1, (24, 0), (),)

    def SetFieldChoiceList(self, fieldname=defaultNamedNotOptArg, choiceList=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(52, LCID, 1, (24, 0), ((8, 0), (12, 0)),fieldname
            , choiceList)

    def SetFieldRequirednessForCurrentAction(self, fieldname=defaultNamedNotOptArg, newValue=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(46, LCID, 1, (24, 0), ((8, 0), (3, 0)),fieldname
            , newValue)

    @raiseExceptionOnError(EntitySetFieldValueError)
    def SetFieldValue(self, fieldname=defaultNamedNotOptArg, new_value=defaultNamedNotOptArg):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(9, LCID, 1, (8, 0), ((8, 0), (12, 0)),fieldname
            , new_value)

    def SetFieldValues(self, varfieldNames=defaultNamedNotOptArg, varvalues=defaultNamedNotOptArg):
        return self._ApplyTypes_(60, 1, (12, 0), ((12, 0), (12, 0)), 'SetFieldValues', None,varfieldNames
            , varvalues)

    def SiteHasMastership(self):
        return self._oleobj_.InvokeTypes(55, LCID, 1, (11, 0), (),)

    @raiseExceptionOnError(EntityValidationError)
    def Validate(self):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(26, LCID, 1, (8, 0), (),)

    _prop_map_get_ = {
        "AttachmentFields": (1, 2, (9, 0), (), "AttachmentFields", None),
        "HistoryFields": (2, 2, (9, 0), (), "HistoryFields", None),
    }
    _prop_map_put_ = {
        "AttachmentFields" : ((1, LCID, 4, 0),()),
        "HistoryFields" : ((2, LCID, 4, 0),()),
    }
    
    def get(self, field):
        type = self.GetFieldType(field)
        if type in FieldType.scalarTypes:
            return self.GetFieldStringValue(field)
        elif type in FieldType.listTypes:
            return self.GetFieldStringValueAsList(field)
        else:
            raise RuntimeError, "unknown field type: %d" % type
    
    def add(self, field, value):
        for v in iterable(value):
            self.AddFieldValue(field, v)
            
    def delete(self, field, value):
        for v in iterable(value):
            self.DeleteFieldValue(field, v)
            
    def set(self, field, value):
        fieldType = self.GetFieldType(field)
        if fieldType in FieldType.writeableScalarTypes:
            if value is None:
                value = u''
            self.SetFieldValue(field, value)
        elif fieldType in FieldType.writeableListTypes:
            old = listToMap(self.get(field))
            new = listToMap(iterable(value))
            # Synchronise the values of this list-based field by adding those
            # that aren't present and deleting those that we don't want.
            [ self.add(field, v) for v in [ n for n in new if not n in old ] ]
            [ self.delete(field, v) for v in [ o for o in old if not o in new ]]
        elif not self._allowUnsupportedUpdates:
            raise TypeError, "unknown field type: %d" % fieldType
        else:
            try:
                setter = getattr(self, '_set' + FieldType[fieldType])
            except AttributeError:
                raise TypeError, "unsupported field type '%s' for field '%s'" %\
                                 (FieldType[fieldType], field)
            setter(value)
    
    def _setId(self, id):
        pass
    
    def _setJournal(self, history):
        pass
        
    def setMandatory(self, field):
        self.SetFieldRequirednessForCurrentAction(field, Behavior.Mandatory)
        
    def setOptional(self, field):
        self.SetFieldRequirednessForCurrentAction(field, Behavior.Optional)
        
    def setReadOnly(self, field):
        self.SetFieldRequirednessForCurrentAction(field, Behavior.ReadOnly)
    
    @cache
    def getProxy(self, behaviourType=NormalBehaviour):
        return EntityProxy(self, behaviourType)
    
    def modify(self, action='Modify'):
        self.session.EditEntity(self, action)
    
    def commit(self):
        self.Validate()
        self.Commit()
        for task in self._postCommitTasks:
            task(self)
    
    def revert(self):
        self.Revert()
    
    def getEntityDef(self):
        return self.session.GetEntityDef(self.GetEntityDefName())
    
    def addPostCommitTask(self, task):
        self._postCommitTasks.append(task)
    
    def removePostCommitTask(self, task):
        self._postCommitTasks.remove(task)
        
    def enableUnsupportedUpdates(self):
        self._allowUnsupportedUpdates = True
        
    def disableUnsupportedUpdates(self):
        self._allowUnsupportedUpdates = False
        
    
class EntityActionHookEvents:
    CLSID = CLSID_Sink = IID('{E9F82951-73A9-11D0-A42E-10A024DED613}')
    coclass_clsid = IID('{E9F82952-73A9-11D0-A42E-00A024DED613}')
    _public_methods_ = [] # For COM Server support
    _dispid_to_func_ = {
                1 : "OnAccessControl",
                5 : "OnNotification",
                2 : "OnInitialization",
                6 : "OnNamedHook",
                4 : "OnCommit",
                3 : "OnValidation",
        }

    def __init__(self, oobj = None):
        if oobj is None:
            self._olecp = None
        else:
            import win32com.server.util
            from win32com.server.policy import EventHandlerPolicy
            cpc=oobj._oleobj_.QueryInterface(pythoncom.IID_IConnectionPointContainer)
            cp=cpc.FindConnectionPoint(self.CLSID_Sink)
            cookie=cp.Advise(win32com.server.util.wrap(self, usePolicy=EventHandlerPolicy))
            self._olecp,self._olecp_cookie = cp,cookie
    def __del__(self):
        try:
            self.close()
        except pythoncom.com_error:
            pass
    def close(self):
        if self._olecp is not None:
            cp,cookie,self._olecp,self._olecp_cookie = self._olecp,self._olecp_cookie,None,None
            cp.Unadvise(cookie)
    def _query_interface_(self, iid):
        import win32com.server.util
        if iid==self.CLSID_Sink: return win32com.server.util.wrap(self)

    # Event Handlers
    # If you create handlers, they should have the following prototypes:
#   def OnAccessControl(self, actionname=defaultNamedNotOptArg, actiontype=defaultNamedNotOptArg, username=defaultNamedNotOptArg):
#   def OnNotification(self, actionname=defaultNamedNotOptArg, actiontype=defaultNamedNotOptArg):
#   def OnInitialization(self, actionname=defaultNamedNotOptArg, actiontype=defaultNamedNotOptArg):
#   def OnNamedHook(self, hookName=defaultNamedNotOptArg, parm=defaultNamedNotOptArg, pDispEntity=defaultNamedNotOptArg):
#   def OnCommit(self, actionname=defaultNamedNotOptArg, actiontype=defaultNamedNotOptArg):
#   def OnValidation(self, actionname=defaultNamedNotOptArg, actiontype=defaultNamedNotOptArg):


class EntityDef(CQObject):
    CLSID = IID('{04A2C910-C552-11D0-A47F-00A024DED613}')
    coclass_clsid = IID('{04A2C920-C552-11D0-A47F-00A024DED613}')
    
    def __init__(self, *args, **kwds):
        CQObject.__init__(self, *args, **kwds)
        
        self.__dict__.update(self.session.db().selectAllAsDict(
            "SELECT * FROM entitydef WHERE name = ?",
            self.GetName())[0]
        )

    def CanBeSecurityContext(self):
        return self._oleobj_.InvokeTypes(22, LCID, 1, (11, 0), (),)

    def CanBeSecurityContextField(self, Name=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(24, LCID, 1, (11, 0), ((8, 0),),Name
            )

    def DoesTransitionExist(self, sourceState=defaultNamedNotOptArg, destState=defaultNamedNotOptArg):
        return self._ApplyTypes_(15, 1, (12, 0), ((8, 0), (8, 0)), 'DoesTransitionExist', None,sourceState
            , destState)

    def GetActionDefForm(self, action_def_name=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(8, LCID, 1, (9, 0), ((8, 0),),action_def_name
            )
        if ret is not None:
            ret = Dispatch(ret, 'GetActionDefForm', None, UnicodeToString=0)
        return ret

    def GetActionDefNames(self):
        return self._ApplyTypes_(3, 1, (12, 0), (), 'GetActionDefNames', None,)

    def GetActionDefType(self, action_def_name=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(6, LCID, 1, (3, 0), ((8, 0),),action_def_name
            )

    def GetActionDestStateName(self, action_def_name=defaultNamedNotOptArg):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(18, LCID, 1, (8, 0), ((8, 0),),action_def_name
            )

    def GetActionSourceStateNames(self, action_def_name=defaultNamedNotOptArg):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(19, LCID, 1, (8, 0), ((8, 0),),action_def_name
            )

    def GetActionTypeName(self, actiontype=defaultNamedNotOptArg):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(28, LCID, 1, (8, 0), ((3, 0),),actiontype
            )

    def GetDbName(self):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(20, LCID, 1, (8, 0), (),)

    def GetFieldDefNames(self):
        return self._ApplyTypes_(2, 1, (12, 0), (), 'GetFieldDefNames', None,)

    def GetFieldDefType(self, field_def_name=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(5, LCID, 1, (3, 0), ((8, 0),),field_def_name
            )
    
    def GetFieldReferenceEntityDef(self, field):
        # This is a bit dodgy; instead of just returning the results of the
        # underlying API call, return the results of session.GetEntityDef(),
        # which will reuse cached versions.  We wouldn't need to create the
        # interim entityDef object if the API provided a way to get the entity
        # name from the field alone.
        name = self._GetFieldReferenceEntityDef(field).GetName()
        return self.session.GetEntityDef(name)
    
    @returns('EntityDef')
    def _GetFieldReferenceEntityDef(self, fieldname=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(14, LCID, 1, (9, 0), ((8, 0),),fieldname
            )
        if ret is not None:
            ret = Dispatch(ret, 'GetFieldReferenceEntityDef', None, UnicodeToString=0)
        return ret

    def GetFieldRequiredness(self, field_name=defaultNamedNotOptArg, state_name=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(27, LCID, 1, (3, 0), ((8, 0), (8, 0)),field_name
            , state_name)

    def GetHookDefNames(self):
        return self._ApplyTypes_(16, 1, (12, 0), (), 'GetHookDefNames', None,)

    def GetLocalFieldPathNames(self, visible_only=defaultNamedNotOptArg):
        return self._ApplyTypes_(13, 1, (12, 0), ((11, 0),), 'GetLocalFieldPathNames', None,visible_only
            )

    def GetName(self):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(1, LCID, 1, (8, 0), (),)

    def GetStateDefNames(self):
        return self._ApplyTypes_(4, 1, (12, 0), (), 'GetStateDefNames', None,)

    def GetType(self):
        return self._oleobj_.InvokeTypes(7, LCID, 1, (3, 0), (),)

    def IsActionDefName(self, Name=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(10, LCID, 1, (11, 0), ((8, 0),),Name
            )

    def IsFamily(self):
        return self._oleobj_.InvokeTypes(17, LCID, 1, (11, 0), (),)

    def IsFieldDefName(self, Name=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(9, LCID, 1, (11, 0), ((8, 0),),Name
            )

    def IsSecurityContext(self):
        return self._oleobj_.InvokeTypes(21, LCID, 1, (11, 0), (),)

    def IsSecurityContextField(self, Name=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(23, LCID, 1, (11, 0), ((8, 0),),Name
            )

    def IsStateDefName(self, Name=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(11, LCID, 1, (11, 0), ((8, 0),),Name
            )

    def IsSystemOwnedFieldDefName(self, field_name=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(12, LCID, 1, (11, 0), ((8, 0),),field_name
            )

    def LookupFieldDefDbNameByName(self, field_name=defaultNamedNotOptArg):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(26, LCID, 1, (8, 0), ((8, 0),),field_name
            )

    def LookupFieldDefNameByDbName(self, field_db_name=defaultNamedNotOptArg):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(25, LCID, 1, (8, 0), ((8, 0),),field_db_name
            )

    _prop_map_get_ = {
    }
    _prop_map_put_ = {
    }
    
    def isStateful(self):
        return self.GetType() == EntityType.Stateful
    
    def isStateless(self):
        return self.GetType() == EntityType.Stateless
    
    @cache
    def getUniqueKey(self):
        return UniqueKey(self)
    
    def lookupDisplayNameByDbId(self, dbid):
        return self.getUniqueKey().lookupDisplayNameByDbId(dbid)
    
    def lookupDbIdByDisplayName(self, displayName):
        return self.getUniqueKey().lookupDbIdByDisplayName(displayName)

    def getFieldDbName(self, fieldDefName):
        return self.getFieldNameToDbColumnMap().get(fieldDefName)
    
    @db.execute
    def disablePrimaryAndUniqueIndexes(self): pass
    
    @db.execute
    def enablePrimaryAndUniqueIndexes(self): pass
    
    @db.execute
    def disableAllIndexes(self): pass        
    
    @db.execute
    def enableAllIndexes(self): pass
    
    @db.selectAll
    def listIndexes(self): pass
    
    @cache
    def getAllEntityDefsForReferenceFields(self):
        return dict([
            (f, self.GetFieldReferenceEntityDef(f))
                for f in self.getReferenceFieldNames()
        ])
    
    @cache
    @selectAll
    def getReferenceFieldNames(self): pass
    
    @cache
    @selectAll
    def getReferenceListFieldNames(self): pass
    
    @cache
    @selectAll
    def getBackReferenceFieldNames(self): pass
    
    @cache
    @selectAll
    def getBackReferenceListFieldNames(self): pass
    
    @selectSingle
    def getCount(self): pass
    
    @cache
    def isReferenceField(self, fieldName):
        return fieldName in self.getReferenceFieldNames()
    
    @cache
    def isReferenceListField(self, fieldName):
        return fieldName in self.getReferenceListFieldNames()
    
    @cache
    def isBackReferenceField(self, fieldName):
        return fieldName in self.getBackReferenceFieldNames()
    
    @cache
    def isBackReferenceListField(self, fieldName):
        return fieldName in self.getBackReferenceListFieldNames()
    
    @cache
    def getFieldNameToDbColumnMap(self):
        sql = 'SELECT name, db_name FROM fielddef WHERE entitydef_id = ?'
        return dict(self.session.db().selectAll(sql, self.id))

class EntityDefs(CQObject):
    CLSID = IID('{B9F132EB-96A9-11D2-B40F-00A0C9851B52}')
    coclass_clsid = IID('{B9F132EC-96A9-11D2-B40F-00A0C9851B52}')

    def Remove(self, Subscript=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(2, LCID, 1, (11, 0), ((12, 0),),Subscript
            )

    @returns(EntityDef)
    def item(self, Index=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(0, LCID, 1, (9, 0), ((16396, 0),),Index
            )
        if ret is not None:
            ret = Dispatch(ret, 'item', None, UnicodeToString=0)
        return ret

    _prop_map_get_ = {
        "Count": (1, 2, (3, 0), (), "Count", None),
    }
    _prop_map_put_ = {
        "Count" : ((1, LCID, 4, 0),()),
        "_NewEnum" : ((-4, LCID, 4, 0),()),
    }
    # Default method for this class is 'item'
    def __call__(self, Index=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(0, LCID, 1, (9, 0), ((16396, 0),),Index
            )
        if ret is not None:
            ret = Dispatch(ret, '__call__', None, UnicodeToString=0)
        return ret

    # str(ob) and int(ob) will use __call__
    def __unicode__(self, *args):
        try:
            return unicode(self.__call__(*args))
        except pythoncom.com_error:
            return repr(self)
    def __str__(self, *args):
        return str(self.__unicode__(*args))
    def __int__(self, *args):
        return int(self.__call__(*args))
    @returns(CQIterator(EntityDef))
    def __iter__(self):
        "Return a Python iterator for this object"
        ob = self._oleobj_.InvokeTypes(-4,LCID,3,(13, 10),())
        return win32com.client.util.Iterator(ob)
    def _NewEnum(self):
        "Create an enumerator from this object"
        return win32com.client.util.WrapEnum(self._oleobj_.InvokeTypes(-4,LCID,3,(13, 10),()),None)
    @returns(EntityDef)
    def __getitem__(self, index):
        "Allow this class to be accessed as a collection"
        if not self.__dict__.has_key('_enum_'):
            self.__dict__['_enum_'] = self._NewEnum()
        return self._enum_.__getitem__(index)
    #This class has Count() property - allow len(ob) to provide this
    def __len__(self):
        return self._ApplyTypes_(*(1, 2, (3, 0), (), "Count", None))
    #This class has a __len__ - this is needed so 'if object:' always returns TRUE.
    def __nonzero__(self):
        return True

class EventObject(CQObject):
    CLSID = IID('{5ED34A11-D4B3-11D1-B37D-00A0C9851B52}')
    coclass_clsid = IID('{5ED34A13-D4B3-11D1-B37D-00A0C9851B52}')

    _prop_map_get_ = {
        "CheckState": (6, 2, (11, 0), (), "CheckState", None),
        "ControlDispatch": (8, 2, (9, 0), (), "ControlDispatch", None),
        "EditText": (5, 2, (8, 0), (), "EditText", None),
        "EventType": (1, 2, (3, 0), (), "EventType", None),
        "ItemName": (2, 2, (8, 0), (), "ItemName", None),
        "ListSelection": (7, 2, (12, 0), (), "ListSelection", None),
        "ObjectItem": (4, 2, (9, 0), (), "ObjectItem", None),
        "StringItem": (3, 2, (8, 0), (), "StringItem", None),
    }
    _prop_map_put_ = {
        "CheckState" : ((6, LCID, 4, 0),()),
        "ControlDispatch" : ((8, LCID, 4, 0),()),
        "EditText" : ((5, LCID, 4, 0),()),
        "EventType" : ((1, LCID, 4, 0),()),
        "ItemName" : ((2, LCID, 4, 0),()),
        "ListSelection" : ((7, LCID, 4, 0),()),
        "ObjectItem" : ((4, LCID, 4, 0),()),
        "StringItem" : ((3, LCID, 4, 0),()),
    }

class Field(CQObject):
    CLSID = IID('{754F0160-B0EF-11D0-A475-00A024DED613}')
    coclass_clsid = IID('{754F0173-B0EF-11D0-A475-00A024DED613}')

    _prop_map_get_ = {
    }
    _prop_map_put_ = {
    }

class FieldFilter(CQObject):
    CLSID = IID('{24A57401-3F6C-11D1-B2C0-00A0C9851B52}')
    coclass_clsid = IID('{24A57411-3F6C-11D1-B2C0-00A0C9851B52}')

    def IsLegalCompOp(self, compOs=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(8, LCID, 1, (11, 0), ((3, 0),),compOs
            )

    def IsLegalValues(self, values=defaultNamedNotOptArg, errMsg=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(9, LCID, 1, (11, 0), ((12, 0), (16396, 0)),values
            , errMsg)

    _prop_map_get_ = {
        "CompOp": (2, 2, (3, 0), (), "CompOp", None),
        "FieldPath": (1, 2, (8, 0), (), "FieldPath", None),
        "FieldType": (6, 2, (3, 0), (), "FieldType", None),
        "LegalCompOps": (7, 2, (12, 0), (), "LegalCompOps", None),
        "Prompt": (5, 2, (8, 0), (), "Prompt", None),
        "StringExpression": (4, 2, (8, 0), (), "StringExpression", None),
        "choiceList": (10, 2, (12, 0), (), "choiceList", None),
        "values": (3, 2, (12, 0), (), "values", None),
    }
    _prop_map_put_ = {
        "CompOp" : ((2, LCID, 4, 0),()),
        "FieldPath" : ((1, LCID, 4, 0),()),
        "FieldType" : ((6, LCID, 4, 0),()),
        "LegalCompOps" : ((7, LCID, 4, 0),()),
        "Prompt" : ((5, LCID, 4, 0),()),
        "StringExpression" : ((4, LCID, 4, 0),()),
        "choiceList" : ((10, LCID, 4, 0),()),
        "values" : ((3, LCID, 4, 0),()),
    }

class FieldFilters(CQObject):
    CLSID = IID('{24A57412-3F6C-11D1-B2C0-00A0C9851B52}')
    coclass_clsid = IID('{24A57420-3F6C-11D1-B2C0-00A0C9851B52}')

    def Add(self, fieldname=defaultNamedNotOptArg, CompOp=defaultNamedNotOptArg, values=defaultNamedNotOptArg, isUnique=defaultNamedOptArg):
        ret = self._oleobj_.InvokeTypes(2, LCID, 1, (9, 0), ((8, 0), (3, 0), (12, 0), (12, 16)),fieldname
            , CompOp, values, isUnique)
        if ret is not None:
            ret = Dispatch(ret, 'Add', None, UnicodeToString=0)
        return ret

    def Remove(self, Subscript=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(3, LCID, 1, (11, 0), ((12, 0),),Subscript
            )

    @returns('Filter')
    def item(self, Index=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(0, LCID, 1, (9, 0), ((16396, 0),),Index
            )
        if ret is not None:
            ret = Dispatch(ret, 'item', None, UnicodeToString=0)
        return ret

    _prop_map_get_ = {
        "Count": (1, 2, (3, 0), (), "Count", None),
    }
    _prop_map_put_ = {
        "Count" : ((1, LCID, 4, 0),()),
        "_NewEnum" : ((-4, LCID, 4, 0),()),
    }
    # Default method for this class is 'item'
    def __call__(self, Index=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(0, LCID, 1, (9, 0), ((16396, 0),),Index
            )
        if ret is not None:
            ret = Dispatch(ret, '__call__', None, UnicodeToString=0)
        return ret

    # str(ob) and int(ob) will use __call__
    def __unicode__(self, *args):
        try:
            return unicode(self.__call__(*args))
        except pythoncom.com_error:
            return repr(self)
    def __str__(self, *args):
        return str(self.__unicode__(*args))
    def __int__(self, *args):
        return int(self.__call__(*args))
    def __iter__(self):
        "Return a Python iterator for this object"
        ob = self._oleobj_.InvokeTypes(-4,LCID,3,(13, 10),())
        return win32com.client.util.Iterator(ob)
    def _NewEnum(self):
        "Create an enumerator from this object"
        return win32com.client.util.WrapEnum(self._oleobj_.InvokeTypes(-4,LCID,3,(13, 10),()),None)
    def __getitem__(self, index):
        "Allow this class to be accessed as a collection"
        if not self.__dict__.has_key('_enum_'):
            self.__dict__['_enum_'] = self._NewEnum()
        return self._enum_.__getitem__(index)
    #This class has Count() property - allow len(ob) to provide this
    def __len__(self):
        return self._ApplyTypes_(*(1, 2, (3, 0), (), "Count", None))
    #This class has a __len__ - this is needed so 'if object:' always returns TRUE.
    def __nonzero__(self):
        return True

class FieldHookEvents:
    CLSID = CLSID_Sink = IID('{754F0160-B0EF-11D0-A475-10A024DED613}')
    coclass_clsid = IID('{754F0173-B0EF-11D0-A475-00A024DED613}')
    _public_methods_ = [] # For COM Server support
    _dispid_to_func_ = {
                4 : "OnValueChanged",
                1 : "OnDefaultValue",
                3 : "OnchoiceList",
                5 : "OnValidation",
                2 : "OnPermission",
        }

    def __init__(self, oobj = None):
        if oobj is None:
            self._olecp = None
        else:
            import win32com.server.util
            from win32com.server.policy import EventHandlerPolicy
            cpc=oobj._oleobj_.QueryInterface(pythoncom.IID_IConnectionPointContainer)
            cp=cpc.FindConnectionPoint(self.CLSID_Sink)
            cookie=cp.Advise(win32com.server.util.wrap(self, usePolicy=EventHandlerPolicy))
            self._olecp,self._olecp_cookie = cp,cookie
    def __del__(self):
        try:
            self.close()
        except pythoncom.com_error:
            pass
    def close(self):
        if self._olecp is not None:
            cp,cookie,self._olecp,self._olecp_cookie = self._olecp,self._olecp_cookie,None,None
            cp.Unadvise(cookie)
    def _query_interface_(self, iid):
        import win32com.server.util
        if iid==self.CLSID_Sink: return win32com.server.util.wrap(self)

    # Event Handlers
    # If you create handlers, they should have the following prototypes:
#   def OnValueChanged(self, fieldname=defaultNamedNotOptArg):
#   def OnDefaultValue(self, fieldname=defaultNamedNotOptArg):
#   def OnchoiceList(self, fieldname=defaultNamedNotOptArg, listobject=defaultNamedNotOptArg):
#   def OnValidation(self, fieldname=defaultNamedNotOptArg):
#   def OnPermission(self, fieldname=defaultNamedNotOptArg, username=defaultNamedNotOptArg):


class FieldInfo(CQObject):
    CLSID = IID('{21E00E8C-3996-11D1-A4F4-00A0C9243B7B}')
    coclass_clsid = IID('{21E00E99-3996-11D1-A4F4-00A0C9243B7B}')

    def GetMessageText(self):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(6, LCID, 1, (8, 0), (),)

    def GetName(self):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(1, LCID, 1, (8, 0), (),)

    def GetRequiredness(self):
        return self._oleobj_.InvokeTypes(3, LCID, 1, (3, 0), (),)

    def GetType(self):
        return self._oleobj_.InvokeTypes(2, LCID, 1, (3, 0), (),)

    def GetValidationStatus(self):
        return self._oleobj_.InvokeTypes(5, LCID, 1, (3, 0), (),)

    def GetValue(self):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(7, LCID, 1, (8, 0), (),) or u''

    def GetValueAsList(self):
        return self._ApplyTypes_(8, 1, (12, 0), (), 'GetValueAsList', None,) or []

    def GetValueStatus(self):
        return self._oleobj_.InvokeTypes(4, LCID, 1, (3, 0), (),)

    def ValidityChangedThisAction(self):
        return self._oleobj_.InvokeTypes(14, LCID, 1, (11, 0), (),)

    def ValidityChangedThisGroup(self):
        return self._oleobj_.InvokeTypes(13, LCID, 1, (11, 0), (),)

    def ValidityChangedThisSetValue(self):
        return self._oleobj_.InvokeTypes(9, LCID, 1, (11, 0), (),)

    def ValueChangedThisAction(self):
        return self._oleobj_.InvokeTypes(12, LCID, 1, (11, 0), (),)

    def ValueChangedThisGroup(self):
        return self._oleobj_.InvokeTypes(11, LCID, 1, (11, 0), (),)

    def ValueChangedThisSetValue(self):
        return self._oleobj_.InvokeTypes(10, LCID, 1, (11, 0), (),)

    _prop_map_get_ = {
    }
    _prop_map_put_ = {
    }
    
    def getValue(self):
        type = self.GetType()
        if type in FieldType.scalarTypes:
            return self.GetValue()
        elif type in FieldType.listTypes:
            return self.GetValueAsList()
        else:
            raise RuntimeError, "unknown field type: %d" % type
    
    def hasValue(self):
        return self.GetValueStatus() == ValueStatus.HasValue
    
    def hasNoValue(self):
        return self.GetValueStatus() in (ValueStatus.HasNoValue,
                                         ValueStatus.ValueNotAvailable)
        

class FilterNode(CQObject):
    CLSID = IID('{24A57421-3F6C-11D1-B2C0-00A0C9851B52}')
    coclass_clsid = IID('{24A5742F-3F6C-11D1-B2C0-00A0C9851B52}')

    def AddChild(self, boolOp=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(5, LCID, 1, (9, 0), ((3, 0),),boolOp
            )
        if ret is not None:
            ret = Dispatch(ret, 'AddChild', None, UnicodeToString=0)
        return ret

    def DeleteChild(self, Index=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(7, LCID, 1, (24, 0), ((12, 0),),Index
            )

    def GetChild(self, N=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(6, LCID, 1, (9, 0), ((2, 0),),N
            )
        if ret is not None:
            ret = Dispatch(ret, 'GetChild', None, UnicodeToString=0)
        return ret

    _prop_map_get_ = {
        "ChildCount": (3, 2, (3, 0), (), "ChildCount", None),
        "FieldFilters": (4, 2, (9, 0), (), "FieldFilters", None),
        "FieldFiltersRecursive": (8, 2, (9, 0), (), "FieldFiltersRecursive", None),
        "boolOp": (1, 2, (3, 0), (), "boolOp", None),
        "parent": (2, 2, (9, 0), (), "parent", None),
    }
    _prop_map_put_ = {
        "ChildCount" : ((3, LCID, 4, 0),()),
        "FieldFilters" : ((4, LCID, 4, 0),()),
        "FieldFiltersRecursive" : ((8, LCID, 4, 0),()),
        "boolOp" : ((1, LCID, 4, 0),()),
        "parent" : ((2, LCID, 4, 0),()),
    }

class Folder(CQWorkspaceItem):
    CLSID = IID('{98720365-0491-4910-82A5-93266CFC84B2}')
    coclass_clsid = IID('{98720366-0491-4910-82A5-93266CFC84B2}')
    
    def AddPermissions(self, pOapermissions=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(25, LCID, 1, (24, 0), ((9, 0),),pOapermissions
            )

    def CommitPermissions(self):
        return self._oleobj_.InvokeTypes(27, LCID, 1, (24, 0), (),)

    def CreateFolder(self, Name=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(8, LCID, 1, (9, 0), ((8, 0),),Name
            )
        if ret is not None:
            ret = Dispatch(ret, 'CreateFolder', None, UnicodeToString=0)
        return ret

    def DeleteFolder(self, Name=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(9, LCID, 1, (24, 0), ((8, 0),),Name
            )

    def DiscoverPermissionsForGroup(self, GroupName=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(22, LCID, 1, (9, 0), ((8, 0),),GroupName
            )
        if ret is not None:
            ret = Dispatch(ret, 'DiscoverPermissionsForGroup', None, UnicodeToString=0)
        return ret

    def DiscoverPermissionsForUser(self, username=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(23, LCID, 1, (9, 0), ((8, 0),),username
            )
        if ret is not None:
            ret = Dispatch(ret, 'DiscoverPermissionsForUser', None, UnicodeToString=0)
        return ret

    def GetAllGroupPermissions(self, kindAsName=defaultNamedNotOptArg):
        return self._ApplyTypes_(29, 1, (12, 0), ((3, 0),), 'GetAllGroupPermissions', None,kindAsName
            )

    def GetAppliedPermissions(self):
        ret = self._oleobj_.InvokeTypes(19, LCID, 1, (9, 0), (),)
        if ret is not None:
            ret = Dispatch(ret, 'GetAppliedPermissions', None, UnicodeToString=0)
        return ret

    def GetAppliedPermissionsForGroup(self, GroupName=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(20, LCID, 1, (9, 0), ((8, 0),),GroupName
            )
        if ret is not None:
            ret = Dispatch(ret, 'GetAppliedPermissionsForGroup', None, UnicodeToString=0)
        return ret

    def GetAppliedPermissionsForUser(self, username=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(21, LCID, 1, (9, 0), ((8, 0),),username
            )
        if ret is not None:
            ret = Dispatch(ret, 'GetAppliedPermissionsForUser', None, UnicodeToString=0)
        return ret

    def GetChildDbIds(self, itemType=defaultNamedNotOptArg):
        return self._ApplyTypes_(14, 1, (12, 0), ((3, 0),), 'GetChildDbIds', None,itemType
            )

    def GetChildNames(self, item_type=defaultNamedNotOptArg, asFullPathname=defaultNamedNotOptArg, name_option=defaultNamedNotOptArg):
        return self._ApplyTypes_(13, 1, (12, 0), ((3, 0), (11, 0), (3, 0)), 'GetChildNames', None,item_type
            , asFullPathname, name_option)

    def GetDbId(self):
        return self._oleobj_.InvokeTypes(3, LCID, 1, (3, 0), (),)

    def GetMasterReplicaName(self):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(6, LCID, 1, (8, 0), (),)

    def GetName(self):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(1, LCID, 1, (8, 0), (),)

    @returns('Folder')
    def GetParent(self):
        ret = self._oleobj_.InvokeTypes(4, LCID, 1, (9, 0), (),)
        if ret is not None:
            ret = Dispatch(ret, 'GetParent', None, UnicodeToString=0)
        return ret

    def GetPathname(self, extend_option=defaultNamedNotOptArg):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(2, LCID, 1, (8, 0), ((3, 0),),extend_option
            )

    def GetPermission(self):
        ret = self._oleobj_.InvokeTypes(16, LCID, 1, (9, 0), (),)
        if ret is not None:
            ret = Dispatch(ret, 'GetPermission', None, UnicodeToString=0)
        return ret

    def GetPermissionForGroup(self, GroupName=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(17, LCID, 1, (9, 0), ((8, 0),),GroupName
            )
        if ret is not None:
            ret = Dispatch(ret, 'GetPermissionForGroup', None, UnicodeToString=0)
        return ret

    def GetPermissionForUser(self, username=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(18, LCID, 1, (9, 0), ((8, 0),),username
            )
        if ret is not None:
            ret = Dispatch(ret, 'GetPermissionForUser', None, UnicodeToString=0)
        return ret

    def GetPossiblePermissions(self):
        ret = self._oleobj_.InvokeTypes(15, LCID, 1, (9, 0), (),)
        if ret is not None:
            ret = Dispatch(ret, 'GetPossiblePermissions', None, UnicodeToString=0)
        return ret

    @returns('Folder')
    def GetSubfolders(self):
        ret = self._oleobj_.InvokeTypes(12, LCID, 1, (9, 0), (),)
        if ret is not None:
            ret = Dispatch(ret, 'GetSubfolders', None, UnicodeToString=0)
        return ret

    def Refresh(self):
        return self._oleobj_.InvokeTypes(11, LCID, 1, (24, 0), (),)

    def RemovePermissions(self, pOapermissions=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(26, LCID, 1, (24, 0), ((9, 0),),pOapermissions
            )

    def RenameFolder(self, oldName=defaultNamedNotOptArg, newName=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(10, LCID, 1, (24, 0), ((8, 0), (8, 0)),oldName
            , newName)

    def RevertPermissions(self):
        return self._oleobj_.InvokeTypes(28, LCID, 1, (24, 0), (),)

    def SetMasterReplicaName(self, replicaName=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(7, LCID, 1, (24, 0), ((8, 0),),replicaName
            )

    def SetPermissions(self, pOapermissions=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(24, LCID, 1, (24, 0), ((9, 0),),pOapermissions
            )

    def SiteHasMastership(self):
        return self._oleobj_.InvokeTypes(5, LCID, 1, (11, 0), (),)

    _prop_map_get_ = {
    }
    _prop_map_put_ = {
    }
    
    def getChildWorkspaceItems(self):
        ws = self.workspace
        items = lambda t: ws.GetWorkspaceItemDbIdList(0, t, self.dbid, '') or []
        kwds = {
            'parent'    : self,
            'session'   : self.session,
            'workspace' : ws,
        }
        r = []
        typeMap = WorkspaceItemTypeMap
        for itemType in WorkspaceItemType:
            for dbid in items(itemType):
                kwds['dbid'] = dbid
                r.append(CQWorkspaceItemXmlProxy(typeMap[itemType], **kwds))
        return r
        

class Folders(CQObject):
    CLSID = IID('{950B1875-3E96-481B-8C26-84E0B4CB54A7}')
    coclass_clsid = IID('{AC15542A-5B43-4433-B5DE-DC29322376EA}')

    @returns(Folder)
    def ItemByName(self, strIndex=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(2, LCID, 1, (9, 0), ((8, 0),),strIndex
            )
        if ret is not None:
            ret = Dispatch(ret, 'ItemByName', None, UnicodeToString=0)
        return ret

    @returns(Folder)
    def item(self, Index=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(0, LCID, 1, (9, 0), ((16396, 0),),Index
            )
        if ret is not None:
            ret = Dispatch(ret, 'item', None, UnicodeToString=0)
        return ret

    _prop_map_get_ = {
        "Count": (1, 2, (3, 0), (), "Count", None),
    }
    _prop_map_put_ = {
        "Count" : ((1, LCID, 4, 0),()),
    }
    # Default method for this class is 'item'
    def __call__(self, Index=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(0, LCID, 1, (9, 0), ((16396, 0),),Index
            )
        if ret is not None:
            ret = Dispatch(ret, '__call__', None, UnicodeToString=0)
        return ret

    # str(ob) and int(ob) will use __call__
    def __unicode__(self, *args):
        try:
            return unicode(self.__call__(*args))
        except pythoncom.com_error:
            return repr(self)
    def __str__(self, *args):
        return str(self.__unicode__(*args))
    def __int__(self, *args):
        return int(self.__call__(*args))
    #This class has Count() property - allow len(ob) to provide this
    def __len__(self):
        return self._ApplyTypes_(*(1, 2, (3, 0), (), "Count", None))
    #This class has a __len__ - this is needed so 'if object:' always returns TRUE.
    def __nonzero__(self):
        return True

class Group(CQObject):
    CLSID = IID('{B48005EA-CF24-11D1-B37A-00A0C9851B52}')
    coclass_clsid = IID('{B48005EC-CF24-11D1-B37A-00A0C9851B52}')

    def AddGroup(self, group=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(15, LCID, 1, (24, 0), ((9, 0),),group
            )

    def AddUser(self, user=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(6, LCID, 1, (24, 0), ((9, 0),),user
            )

    def IsSubscribedToAllDatabases(self):
        return self._oleobj_.InvokeTypes(10, LCID, 1, (11, 0), (),)

    def RemoveGroup(self, group=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(16, LCID, 1, (24, 0), ((9, 0),),group
            )

    def RemoveUser(self, user=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(12, LCID, 1, (24, 0), ((9, 0),),user
            )

    def SetSubscribedToAllDatabases(self, bIsSubAll=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(11, LCID, 1, (24, 0), ((11, 0),),bIsSubAll
            )

    def SiteHasMastership(self):
        return self._oleobj_.InvokeTypes(13, LCID, 1, (11, 0), (),)

    def SubscribeDatabase(self, database=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(7, LCID, 1, (24, 0), ((9, 0),),database
            )

    def UnsubscribeAllDatabases(self):
        return self._oleobj_.InvokeTypes(9, LCID, 1, (24, 0), (),)

    def UnsubscribeDatabase(self, database=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(8, LCID, 1, (24, 0), ((9, 0),),database
            )

    _prop_map_get_ = {
        "Active": (2, 2, (11, 0), (), "Active", None),
        "Databases": (4, 2, (9, 0), (), "Databases", None),
        "Groups": (14, 2, (9, 0), (), "Groups", None),
        "Name": (1, 2, (8, 0), (), "Name", None),
        "SubscribedDatabases": (5, 2, (9, 0), (), "SubscribedDatabases", None),
        "Users": (3, 2, (9, 0), (), "Users", None),
    }
    _prop_map_put_ = {
        "Active" : ((2, LCID, 4, 0),()),
        "Databases" : ((4, LCID, 4, 0),()),
        "Groups" : ((14, LCID, 4, 0),()),
        "Name" : ((1, LCID, 4, 0),()),
        "SubscribedDatabases" : ((5, LCID, 4, 0),()),
        "Users" : ((3, LCID, 4, 0),()),
    }
    
    def setUsers(self, users):
        # Python crashes if we try and iterate over self.Users directly in the
        # list comprehension, yet it works fine if we take a copy first, weird.
        oldUsers = self.Users
        old = dict([ (u.Name, u) for u in oldUsers ])
        new = dict([ (u.Name, u) for u in users ])
        for login in [ n for n in new if not n in old ]:
            self.AddUser(new[login])
        
        for login in [ o for o in old if not o in new ]:
            self.RemoveUser(old[login])
    
    _prop_map_put_ex_ = {
        'Users' : lambda g, *args: g.setUsers(args[1]),
    }
    
    

class Groups(CQCollection):
    CLSID = IID('{B48005ED-CF24-11D1-B37A-00A0C9851B52}')
    coclass_clsid = IID('{B48005EF-CF24-11D1-B37A-00A0C9851B52}')

    @returns(Group)
    def item(self, Index=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(0, LCID, 1, (9, 0), ((16396, 0),),Index
            )
        if ret is not None:
            ret = Dispatch(ret, 'item', None, UnicodeToString=0)
        return ret

    _prop_map_get_ = {
        "Count": (1, 2, (3, 0), (), "Count", None),
    }
    _prop_map_put_ = {
        "Count" : ((1, LCID, 4, 0),()),
        "_NewEnum" : ((-4, LCID, 4, 0),()),
    }
    # Default method for this class is 'item'
    @returns(Group)
    def __call__(self, Index=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(0, LCID, 1, (9, 0), ((16396, 0),),Index
            )
        if ret is not None:
            ret = Dispatch(ret, '__call__', None, UnicodeToString=0)
        return ret

    # str(ob) and int(ob) will use __call__
    def __unicode__(self, *args):
        try:
            return unicode(self.__call__(*args))
        except pythoncom.com_error:
            return repr(self)
    def __str__(self, *args):
        return str(self.__unicode__(*args))
    def __int__(self, *args):
        return int(self.__call__(*args))
    @returns(CQIterator(Group))
    def __iter__(self):
        "Return a Python iterator for this object"
        ob = self._oleobj_.InvokeTypes(-4,LCID,3,(13, 10),())
        return win32com.client.util.Iterator(ob)
    def _NewEnum(self):
        "Create an enumerator from this object"
        return win32com.client.util.WrapEnum(self._oleobj_.InvokeTypes(-4,LCID,3,(13, 10),()),None)
    @returns(Group)
    def __getitem__(self, index):
        "Allow this class to be accessed as a collection"
        if not self.__dict__.has_key('_enum_'):
            self.__dict__['_enum_'] = self._NewEnum()
        return self._enum_.__getitem__(index)
    #This class has Count() property - allow len(ob) to provide this
    def __len__(self):
        return self._ApplyTypes_(*(1, 2, (3, 0), (), "Count", None))
    #This class has a __len__ - this is needed so 'if object:' always returns TRUE.
    def __nonzero__(self):
        return True

    def __contains__(self, groupName):
        if not 'Names' in self.__dict__:
            self.__dict__['Names'] = [ group.Name for group in self ]
        return groupName in self.__dict__['Names']    

class HistoryField(CQObject):
    CLSID = IID('{CE573C89-3B54-11D1-B2BF-00A0C9851B52}')
    coclass_clsid = IID('{CE573C97-3B54-11D1-B2BF-00A0C9851B52}')

    _prop_map_get_ = {
        "DisplayNameHeader": (2, 2, (12, 0), (), "DisplayNameHeader", None),
        "Histories": (3, 2, (9, 0), (), "Histories", None),
        "fieldname": (1, 2, (8, 0), (), "fieldname", None),
    }
    _prop_map_put_ = {
        "DisplayNameHeader" : ((2, LCID, 4, 0),()),
        "Histories" : ((3, LCID, 4, 0),()),
        "fieldname" : ((1, LCID, 4, 0),()),
    }

class HistoryFields(CQObject):
    CLSID = IID('{CE573C7A-3B54-11D1-B2BF-00A0C9851B52}')
    coclass_clsid = IID('{CE573C88-3B54-11D1-B2BF-00A0C9851B52}')

    @returns(HistoryField)
    def item(self, Index=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(0, LCID, 1, (9, 0), ((16396, 0),),Index
            )
        if ret is not None:
            ret = Dispatch(ret, 'item', None, UnicodeToString=0)
        return ret

    _prop_map_get_ = {
        "Count": (1, 2, (3, 0), (), "Count", None),
    }
    _prop_map_put_ = {
        "Count" : ((1, LCID, 4, 0),()),
    }
    # Default method for this class is 'item'
    @returns(HistoryField)
    def __call__(self, Index=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(0, LCID, 1, (9, 0), ((16396, 0),),Index
            )
        if ret is not None:
            ret = Dispatch(ret, '__call__', None, UnicodeToString=0)
        return ret

    # str(ob) and int(ob) will use __call__
    def __unicode__(self, *args):
        try:
            return unicode(self.__call__(*args))
        except pythoncom.com_error:
            return repr(self)
    def __str__(self, *args):
        return str(self.__unicode__(*args))
    def __int__(self, *args):
        return int(self.__call__(*args))
    #This class has Count() property - allow len(ob) to provide this
    def __len__(self):
        return self._ApplyTypes_(*(1, 2, (3, 0), (), "Count", None))
    #This class has a __len__ - this is needed so 'if object:' always returns TRUE.
    def __nonzero__(self):
        return True
    
class History(CQObject):
    CLSID = IID('{CE573CA7-3B54-11D1-B2BF-00A0C9851B52}')
    coclass_clsid = IID('{CE573CB5-3B54-11D1-B2BF-00A0C9851B52}')

    _prop_map_get_ = {
        "value": (1, 2, (8, 0), (), "value", None),
    }
    _prop_map_put_ = {
        "_NewEnum" : ((-4, LCID, 4, 0),()),
        "value" : ((1, LCID, 4, 0),()),
    }
    # Default property for this class is 'value'
    def __call__(self):
        return self._ApplyTypes_(*(1, 2, (8, 0), (), "value", None))
    # str(ob) and int(ob) will use __call__
    def __unicode__(self, *args):
        try:
            return unicode(self.__call__(*args))
        except pythoncom.com_error:
            return repr(self)
    def __str__(self, *args):
        return str(self.__unicode__(*args))
    def __int__(self, *args):
        return int(self.__call__(*args))
    def __iter__(self):
        "Return a Python iterator for this object"
        ob = self._oleobj_.InvokeTypes(-4,LCID,3,(13, 10),())
        return win32com.client.util.Iterator(ob)
    def _NewEnum(self):
        "Create an enumerator from this object"
        return win32com.client.util.WrapEnum(self._oleobj_.InvokeTypes(-4,LCID,3,(13, 10),()),None)
    def __getitem__(self, index):
        "Allow this class to be accessed as a collection"
        if not self.__dict__.has_key('_enum_'):
            self.__dict__['_enum_'] = self._NewEnum()
        return self._enum_.__getitem__(index)

class Histories(CQObject):
    CLSID = IID('{CE573C98-3B54-11D1-B2BF-00A0C9851B52}')
    coclass_clsid = IID('{CE573CA6-3B54-11D1-B2BF-00A0C9851B52}')

    @returns(History)
    def item(self, Index=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(0, LCID, 1, (9, 0), ((16396, 0),),Index
            )
        if ret is not None:
            ret = Dispatch(ret, 'item', None, UnicodeToString=0)
        return ret

    _prop_map_get_ = {
        "Count": (1, 2, (3, 0), (), "Count", None),
    }
    _prop_map_put_ = {
        "Count" : ((1, LCID, 4, 0),()),
        "_NewEnum" : ((-4, LCID, 4, 0),()),
    }
    # Default method for this class is 'item'
    @returns(History)
    def __call__(self, Index=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(0, LCID, 1, (9, 0), ((16396, 0),),Index
            )
        if ret is not None:
            ret = Dispatch(ret, '__call__', None, UnicodeToString=0)
        return ret

    # str(ob) and int(ob) will use __call__
    def __unicode__(self, *args):
        try:
            return unicode(self.__call__(*args))
        except pythoncom.com_error:
            return repr(self)
    def __str__(self, *args):
        return str(self.__unicode__(*args))
    def __int__(self, *args):
        return int(self.__call__(*args))
    @returns(CQIterator(History))
    def __iter__(self):
        "Return a Python iterator for this object"
        ob = self._oleobj_.InvokeTypes(-4,LCID,3,(13, 10),())
        return win32com.client.util.Iterator(ob)
    def _NewEnum(self):
        "Create an enumerator from this object"
        return win32com.client.util.WrapEnum(self._oleobj_.InvokeTypes(-4,LCID,3,(13, 10),()),None)
    @returns(CQIterator(History))
    def __getitem__(self, index):
        "Allow this class to be accessed as a collection"
        if not self.__dict__.has_key('_enum_'):
            self.__dict__['_enum_'] = self._NewEnum()
        return self._enum_.__getitem__(index)
    #This class has Count() property - allow len(ob) to provide this
    def __len__(self):
        return self._ApplyTypes_(*(1, 2, (3, 0), (), "Count", None))
    #This class has a __len__ - this is needed so 'if object:' always returns TRUE.
    def __nonzero__(self):
        return True


class HookChoices(CQObject):
    CLSID = IID('{60A7B420-B5A3-11D0-A477-00A024DED613}')
    coclass_clsid = IID('{60A7B42E-B5A3-11D0-A477-00A024DED613}')

    def AddItem(self, item=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(1, LCID, 1, (24, 0), ((8, 0),),item
            )

    def AddItems(self, items=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(3, LCID, 1, (24, 0), ((12, 0),),items
            )

    def Sort(self, sortAscending=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(2, LCID, 1, (24, 0), ((12, 0),),sortAscending
            )

    _prop_map_get_ = {
    }
    _prop_map_put_ = {
    }

class Item(CQObject):
    CLSID = IID('{B9F132E4-96A9-11D2-B40F-00A0C9851B52}')
    coclass_clsid = IID('{B9F132E5-96A9-11D2-B40F-00A0C9851B52}')

    _prop_map_get_ = {
        "value": (1, 2, (12, 0), (), "value", None),
    }
    _prop_map_put_ = {
        "value" : ((1, LCID, 4, 0),()),
    }
    # Default property for this class is 'value'
    def __call__(self):
        return self._ApplyTypes_(*(1, 2, (12, 0), (), "value", None))
    # str(ob) and int(ob) will use __call__
    def __unicode__(self, *args):
        try:
            return unicode(self.__call__(*args))
        except pythoncom.com_error:
            return repr(self)
    def __str__(self, *args):
        return str(self.__unicode__(*args))
    def __int__(self, *args):
        return int(self.__call__(*args))

class Items(CQObject):
    CLSID = IID('{B9F132E9-96A9-11D2-B40F-00A0C9851B52}')
    coclass_clsid = IID('{B9F132EA-96A9-11D2-B40F-00A0C9851B52}')

    @returns(Item)
    def item(self, Index=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(0, LCID, 1, (9, 0), ((16396, 0),),Index
            )
        if ret is not None:
            ret = Dispatch(ret, 'item', None, UnicodeToString=0)
        return ret

    _prop_map_get_ = {
        "Count": (1, 2, (3, 0), (), "Count", None),
    }
    _prop_map_put_ = {
        "Count" : ((1, LCID, 4, 0),()),
        "_NewEnum" : ((-4, LCID, 4, 0),()),
    }
    # Default method for this class is 'item'
    @returns(Item)
    def __call__(self, Index=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(0, LCID, 1, (9, 0), ((16396, 0),),Index
            )
        if ret is not None:
            ret = Dispatch(ret, '__call__', None, UnicodeToString=0)
        return ret

    # str(ob) and int(ob) will use __call__
    def __unicode__(self, *args):
        try:
            return unicode(self.__call__(*args))
        except pythoncom.com_error:
            return repr(self)
    def __str__(self, *args):
        return str(self.__unicode__(*args))
    def __int__(self, *args):
        return int(self.__call__(*args))
    @returns(CQIterator(Item))
    def __iter__(self):
        "Return a Python iterator for this object"
        ob = self._oleobj_.InvokeTypes(-4,LCID,3,(13, 10),())
        return win32com.client.util.Iterator(ob)
    def _NewEnum(self):
        "Create an enumerator from this object"
        return win32com.client.util.WrapEnum(self._oleobj_.InvokeTypes(-4,LCID,3,(13, 10),()),None)
    @returns(Item)
    def __getitem__(self, index):
        "Allow this class to be accessed as a collection"
        if not self.__dict__.has_key('_enum_'):
            self.__dict__['_enum_'] = self._NewEnum()
        return self._enum_.__getitem__(index)
    #This class has Count() property - allow len(ob) to provide this
    def __len__(self):
        return self._ApplyTypes_(*(1, 2, (3, 0), (), "Count", None))
    #This class has a __len__ - this is needed so 'if object:' always returns TRUE.
    def __nonzero__(self):
        return True

class Link(CQObject):
    CLSID = IID('{9EC2BB70-1892-11D1-A4E4-00A0C9243B7B}')
    coclass_clsid = IID('{9EC2BB71-1892-11D1-A4E4-00A0C9243B7B}')

    @returns(Entity)
    def GetChildEntity(self):
        ret = self._oleobj_.InvokeTypes(7, LCID, 1, (9, 0), (),)
        if ret is not None:
            ret = Dispatch(ret, 'GetChildEntity', None, UnicodeToString=0)
        return ret

    @returns(EntityDef)
    def GetChildEntityDef(self):
        ret = self._oleobj_.InvokeTypes(5, LCID, 1, (9, 0), (),)
        if ret is not None:
            ret = Dispatch(ret, 'GetChildEntityDef', None, UnicodeToString=0)
        return ret

    def GetChildEntityDefName(self):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(6, LCID, 1, (8, 0), (),)

    def GetChildEntityId(self):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(8, LCID, 1, (8, 0), (),)

    @returns(Entity)
    def GetParentEntity(self):
        ret = self._oleobj_.InvokeTypes(3, LCID, 1, (9, 0), (),)
        if ret is not None:
            ret = Dispatch(ret, 'GetParentEntity', None, UnicodeToString=0)
        return ret

    @returns(EntityDef)
    def GetParentEntityDef(self):
        ret = self._oleobj_.InvokeTypes(1, LCID, 1, (9, 0), (),)
        if ret is not None:
            ret = Dispatch(ret, 'GetParentEntityDef', None, UnicodeToString=0)
        return ret

    def GetParentEntityDefName(self):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(2, LCID, 1, (8, 0), (),)

    def GetParentEntityId(self):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(4, LCID, 1, (8, 0), (),)

    _prop_map_get_ = {
    }
    _prop_map_put_ = {
    }

class PackageRev(CQObject):
    CLSID = IID('{B9F132EF-96A9-11D2-B40F-00A0C9851B52}')
    coclass_clsid = IID('{B9F132F0-96A9-11D2-B40F-00A0C9851B52}')

    _prop_map_get_ = {
        "PackageName": (2, 2, (8, 0), (), "PackageName", None),
        "RevString": (1, 2, (8, 0), (), "RevString", None),
    }
    _prop_map_put_ = {
        "PackageName" : ((2, LCID, 4, 0),()),
        "RevString" : ((1, LCID, 4, 0),()),
    }

class PackageRevs(CQObject):
    CLSID = IID('{B9F132ED-96A9-11D2-B40F-00A0C9851B52}')
    coclass_clsid = IID('{B9F132EE-96A9-11D2-B40F-00A0C9851B52}')

    def Remove(self, Subscript=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(2, LCID, 1, (11, 0), ((12, 0),),Subscript
            )

    @returns(PackageRev)
    def item(self, Index=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(0, LCID, 1, (9, 0), ((16396, 0),),Index
            )
        if ret is not None:
            ret = Dispatch(ret, 'item', None, UnicodeToString=0)
        return ret

    _prop_map_get_ = {
        "Count": (1, 2, (3, 0), (), "Count", None),
    }
    _prop_map_put_ = {
        "Count" : ((1, LCID, 4, 0),()),
        "_NewEnum" : ((-4, LCID, 4, 0),()),
    }
    # Default method for this class is 'item'
    @returns(PackageRev)
    def __call__(self, Index=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(0, LCID, 1, (9, 0), ((16396, 0),),Index
            )
        if ret is not None:
            ret = Dispatch(ret, '__call__', None, UnicodeToString=0)
        return ret

    # str(ob) and int(ob) will use __call__
    def __unicode__(self, *args):
        try:
            return unicode(self.__call__(*args))
        except pythoncom.com_error:
            return repr(self)
    def __str__(self, *args):
        return str(self.__unicode__(*args))
    def __int__(self, *args):
        return int(self.__call__(*args))
    @returns(CQIterator(PackageRev))
    def __iter__(self):
        "Return a Python iterator for this object"
        ob = self._oleobj_.InvokeTypes(-4,LCID,3,(13, 10),())
        return win32com.client.util.Iterator(ob)
    def _NewEnum(self):
        "Create an enumerator from this object"
        return win32com.client.util.WrapEnum(self._oleobj_.InvokeTypes(-4,LCID,3,(13, 10),()),None)
    @returns(PackageRev)
    def __getitem__(self, index):
        "Allow this class to be accessed as a collection"
        if not self.__dict__.has_key('_enum_'):
            self.__dict__['_enum_'] = self._NewEnum()
        return self._enum_.__getitem__(index)
    #This class has Count() property - allow len(ob) to provide this
    def __len__(self):
        return self._ApplyTypes_(*(1, 2, (3, 0), (), "Count", None))
    #This class has a __len__ - this is needed so 'if object:' always returns TRUE.
    def __nonzero__(self):
        return True

class Permission(CQObject):
    CLSID = IID('{A39B63C9-9798-401C-BD7B-7BBBF26485CF}')
    coclass_clsid = IID('{A39B63CA-9798-401C-BD7B-7BBBF26485CF}')

    def AllowsRead(self):
        return self._oleobj_.InvokeTypes(10, LCID, 1, (11, 0), (),)

    def AllowsWrite(self):
        return self._oleobj_.InvokeTypes(11, LCID, 1, (11, 0), (),)

    def GetFolder(self):
        ret = self._oleobj_.InvokeTypes(1, LCID, 1, (9, 0), (),)
        if ret is not None:
            ret = Dispatch(ret, 'GetFolder', None, UnicodeToString=0)
        return ret

    def GetGroup(self, extend_option=defaultNamedNotOptArg):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(7, LCID, 1, (8, 0), ((3, 0),),extend_option
            )

    def GetKind(self):
        return self._oleobj_.InvokeTypes(5, LCID, 1, (3, 0), (),)

    def GetKindName(self):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(4, LCID, 1, (8, 0), (),)

    def GetKindNameOf(self, kind=defaultNamedNotOptArg):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(2, LCID, 1, (8, 0), ((3, 0),),kind
            )

    def GetObjectDbId(self):
        return self._oleobj_.InvokeTypes(9, LCID, 1, (3, 0), (),)

    def IsSamePermission(self, Permission=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(3, LCID, 1, (11, 0), ((9, 0),),Permission
            )

    def SetGroup(self, GroupName=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(8, LCID, 1, (24, 0), ((8, 0),),GroupName
            )

    def SetKind(self, kind=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(6, LCID, 1, (24, 0), ((3, 0),),kind
            )

    _prop_map_get_ = {
    }
    _prop_map_put_ = {
    }

class Permissions(CQObject):
    CLSID = IID('{62975AFC-FD86-4E7A-A256-2D366AF15D54}')
    coclass_clsid = IID('{B93A6649-FD66-45AB-8F44-12C4897D33E1}')

    def AddItem(self, Permission=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(2, LCID, 1, (24, 0), ((9, 0),),Permission
            )

    def Has(self, Permission=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(4, LCID, 1, (11, 0), ((9, 0),),Permission
            )

    def IsACL(self):
        return self._oleobj_.InvokeTypes(5, LCID, 1, (11, 0), (),)

    def RemoveItem(self, Permission=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(3, LCID, 1, (24, 0), ((9, 0),),Permission
            )

    @returns(Permission)
    def item(self, Index=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(0, LCID, 1, (9, 0), ((16396, 0),),Index
            )
        if ret is not None:
            ret = Dispatch(ret, 'item', None, UnicodeToString=0)
        return ret

    _prop_map_get_ = {
        "Count": (1, 2, (3, 0), (), "Count", None),
    }
    _prop_map_put_ = {
        "Count" : ((1, LCID, 4, 0),()),
    }
    # Default method for this class is 'item'
    @returns(Permission)
    def __call__(self, Index=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(0, LCID, 1, (9, 0), ((16396, 0),),Index
            )
        if ret is not None:
            ret = Dispatch(ret, '__call__', None, UnicodeToString=0)
        return ret

    # str(ob) and int(ob) will use __call__
    def __unicode__(self, *args):
        try:
            return unicode(self.__call__(*args))
        except pythoncom.com_error:
            return repr(self)
    def __str__(self, *args):
        return str(self.__unicode__(*args))
    def __int__(self, *args):
        return int(self.__call__(*args))
    #This class has Count() property - allow len(ob) to provide this
    def __len__(self):
        return self._ApplyTypes_(*(1, 2, (3, 0), (), "Count", None))
    #This class has a __len__ - this is needed so 'if object:' always returns TRUE.
    def __nonzero__(self):
        return True

class QueryDef(CQWorkspaceItem):
    CLSID = IID('{14BE7431-785A-11D0-A431-00A024DED613}')
    coclass_clsid = IID('{14BE7432-785A-11D0-A431-00A024DED613}')

    def BuildField(self, field_path=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(9, LCID, 1, (24, 0), ((8, 0),),field_path
            )

    def BuildFilterOperator(self, bool_op=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(10, LCID, 1, (9, 0), ((3, 0),),bool_op
            )
        if ret is not None:
            ret = Dispatch(ret, 'BuildFilterOperator', None, UnicodeToString=0)
        return ret

    def BuildUniqueKeyField(self):
        ret = self._oleobj_.InvokeTypes(11, LCID, 1, (9, 0), (),)
        if ret is not None:
            ret = Dispatch(ret, 'BuildUniqueKeyField', None, UnicodeToString=0)
        return ret

    def BuildUniqueKeyFilter(self, parent=defaultNamedNotOptArg, op=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(12, LCID, 1, (9, 0), ((9, 0), (2, 0)),parent
            , op)
        if ret is not None:
            ret = Dispatch(ret, 'BuildUniqueKeyFilter', None, UnicodeToString=0)
        return ret

    def CreateTopNode(self, bool_op=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(19, LCID, 1, (9, 0), ((3, 0),),bool_op
            )
        if ret is not None:
            ret = Dispatch(ret, 'CreateTopNode', None, UnicodeToString=0)
        return ret

    def GetFieldByPosition(self, position=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(13, LCID, 1, (9, 0), ((2, 0),),position
            )
        if ret is not None:
            ret = Dispatch(ret, 'GetFieldByPosition', None, UnicodeToString=0)
        return ret

    def GetPrimaryEntityDefName(self):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(17, LCID, 1, (8, 0), (),)

    def IsFieldLegalForFilter(self, fieldname=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(16, LCID, 1, (11, 0), ((8, 0),),fieldname
            )

    def IsFieldLegalForQuery(self, fieldname=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(15, LCID, 1, (11, 0), ((8, 0),),fieldname
            )

    def Save(self, filename=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(8, LCID, 1, (11, 0), ((8, 0),),filename
            )

    _prop_map_get_ = {
        "IsAggregated": (6, 2, (11, 0), (), "IsAggregated", None),
        "IsDirty": (3, 2, (11, 0), (), "IsDirty", None),
        "IsMultiType": (14, 2, (11, 0), (), "IsMultiType", None),
        "IsSQLGenerated": (18, 2, (11, 0), (), "IsSQLGenerated", None),
        "Name": (7, 2, (8, 0), (), "Name", None),
        "QueryFieldDefs": (5, 2, (9, 0), (), "QueryFieldDefs", None),
        "QueryFilter": (4, 2, (9, 0), (), "QueryFilter", None),
        "QueryType": (1, 2, (3, 0), (), "QueryType", None),
        "SQL": (2, 2, (8, 0), (), "SQL", None),
    }
    _prop_map_put_ = {
        "IsAggregated" : ((6, LCID, 4, 0),()),
        "IsDirty" : ((3, LCID, 4, 0),()),
        "IsMultiType" : ((14, LCID, 4, 0),()),
        "IsSQLGenerated" : ((18, LCID, 4, 0),()),
        "Name" : ((7, LCID, 4, 0),()),
        "QueryFieldDefs" : ((5, LCID, 4, 0),()),
        "QueryFilter" : ((4, LCID, 4, 0),()),
        "QueryType" : ((1, LCID, 4, 0),()),
        "SQL" : ((2, LCID, 4, 0),()),
    }
    
class QueryDefs(CQObject):
    CLSID = IID('{24A57442-3F6C-11D1-B2C0-00A0C9851B52}')
    coclass_clsid = IID('{24A57450-3F6C-11D1-B2C0-00A0C9851B52}')

    def Add(self, PrimaryEntityDefName=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(2, LCID, 1, (9, 0), ((8, 0),),PrimaryEntityDefName
            )
        if ret is not None:
            ret = Dispatch(ret, 'Add', None, UnicodeToString=0)
        return ret

    def Load(self, filename=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(3, LCID, 1, (9, 0), ((8, 0),),filename
            )
        if ret is not None:
            ret = Dispatch(ret, 'Load', None, UnicodeToString=0)
        return ret

    def Remove(self, Subscript=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(4, LCID, 1, (11, 0), ((12, 0),),Subscript
            )

    @returns(QueryDef)
    def item(self, Index=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(0, LCID, 1, (9, 0), ((16396, 0),),Index
            )
        if ret is not None:
            ret = Dispatch(ret, 'item', None, UnicodeToString=0)
        return ret

    _prop_map_get_ = {
        "Count": (1, 2, (3, 0), (), "Count", None),
    }
    _prop_map_put_ = {
        "Count" : ((1, LCID, 4, 0),()),
        "_NewEnum" : ((-4, LCID, 4, 0),()),
    }
    # Default method for this class is 'item'
    @returns(QueryDef)
    def __call__(self, Index=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(0, LCID, 1, (9, 0), ((16396, 0),),Index
            )
        if ret is not None:
            ret = Dispatch(ret, '__call__', None, UnicodeToString=0)
        return ret

    # str(ob) and int(ob) will use __call__
    def __unicode__(self, *args):
        try:
            return unicode(self.__call__(*args))
        except pythoncom.com_error:
            return repr(self)
    def __str__(self, *args):
        return str(self.__unicode__(*args))
    def __int__(self, *args):
        return int(self.__call__(*args))
    @returns(CQIterator(QueryDef))
    def __iter__(self):
        "Return a Python iterator for this object"
        ob = self._oleobj_.InvokeTypes(-4,LCID,3,(13, 10),())
        return win32com.client.util.Iterator(ob)
    def _NewEnum(self):
        "Create an enumerator from this object"
        return win32com.client.util.WrapEnum(self._oleobj_.InvokeTypes(-4,LCID,3,(13, 10),()),None)
    @returns(QueryDef)
    def __getitem__(self, index):
        "Allow this class to be accessed as a collection"
        if not self.__dict__.has_key('_enum_'):
            self.__dict__['_enum_'] = self._NewEnum()
        return self._enum_.__getitem__(index)
    #This class has Count() property - allow len(ob) to provide this
    def __len__(self):
        return self._ApplyTypes_(*(1, 2, (3, 0), (), "Count", None))
    #This class has a __len__ - this is needed so 'if object:' always returns TRUE.
    def __nonzero__(self):
        return True

class QueryFieldDef(CQObject):
    CLSID = IID('{14BE7437-785A-11D0-A431-00A024DED613}')
    coclass_clsid = IID('{14BE7438-785A-11D0-A431-00A024DED613}')

    _prop_map_get_ = {
        "AggregateFunction": (5, 2, (3, 0), (), "AggregateFunction", None),
        "DataType": (2, 2, (3, 0), (), "DataType", None),
        "Description": (13, 2, (8, 0), (), "Description", None),
        "FieldPathName": (1, 2, (8, 0), (), "FieldPathName", None),
        "FieldType": (3, 2, (3, 0), (), "FieldType", None),
        "Function": (4, 2, (3, 0), (), "Function", None),
        "IsGroupBy": (10, 2, (11, 0), (), "IsGroupBy", None),
        "IsLegalForFilter": (12, 2, (11, 0), (), "IsLegalForFilter", None),
        "IsShown": (6, 2, (11, 0), (), "IsShown", None),
        "Label": (7, 2, (8, 0), (), "Label", None),
        "SortOrder": (9, 2, (3, 0), (), "SortOrder", None),
        "SortType": (8, 2, (3, 0), (), "SortType", None),
        "choiceList": (11, 2, (12, 0), (), "choiceList", None),
    }
    _prop_map_put_ = {
        "AggregateFunction" : ((5, LCID, 4, 0),()),
        "DataType" : ((2, LCID, 4, 0),()),
        "Description" : ((13, LCID, 4, 0),()),
        "FieldPathName" : ((1, LCID, 4, 0),()),
        "FieldType" : ((3, LCID, 4, 0),()),
        "Function" : ((4, LCID, 4, 0),()),
        "IsGroupBy" : ((10, LCID, 4, 0),()),
        "IsLegalForFilter" : ((12, LCID, 4, 0),()),
        "IsShown" : ((6, LCID, 4, 0),()),
        "Label" : ((7, LCID, 4, 0),()),
        "SortOrder" : ((9, LCID, 4, 0),()),
        "SortType" : ((8, LCID, 4, 0),()),
        "choiceList" : ((11, LCID, 4, 0),()),
    }

class QueryFieldDefs(CQObject):
    CLSID = IID('{24A57433-3F6C-11D1-B2C0-00A0C9851B52}')
    coclass_clsid = IID('{24A57441-3F6C-11D1-B2C0-00A0C9851B52}')

    def Add(self, item=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(2, LCID, 1, (9, 0), ((12, 0),),item
            )
        if ret is not None:
            ret = Dispatch(ret, 'Add', None, UnicodeToString=0)
        return ret

    def AddUniqueKey(self):
        ret = self._oleobj_.InvokeTypes(3, LCID, 1, (9, 0), (),)
        if ret is not None:
            ret = Dispatch(ret, 'AddUniqueKey', None, UnicodeToString=0)
        return ret

    def Remove(self, Subscript=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(4, LCID, 1, (11, 0), ((12, 0),),Subscript
            )

    @returns(QueryFieldDef)
    def item(self, Index=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(0, LCID, 1, (9, 0), ((16396, 0),),Index
            )
        if ret is not None:
            ret = Dispatch(ret, 'item', None, UnicodeToString=0)
        return ret

    _prop_map_get_ = {
        "Count": (1, 2, (3, 0), (), "Count", None),
    }
    _prop_map_put_ = {
        "Count" : ((1, LCID, 4, 0),()),
        "_NewEnum" : ((-4, LCID, 4, 0),()),
    }
    # Default method for this class is 'item'
    @returns(QueryFieldDef)
    def __call__(self, Index=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(0, LCID, 1, (9, 0), ((16396, 0),),Index
            )
        if ret is not None:
            ret = Dispatch(ret, '__call__', None, UnicodeToString=0)
        return ret

    # str(ob) and int(ob) will use __call__
    def __unicode__(self, *args):
        try:
            return unicode(self.__call__(*args))
        except pythoncom.com_error:
            return repr(self)
    def __str__(self, *args):
        return str(self.__unicode__(*args))
    def __int__(self, *args):
        return int(self.__call__(*args))
    @returns(CQIterator(QueryFieldDef))
    def __iter__(self):
        "Return a Python iterator for this object"
        ob = self._oleobj_.InvokeTypes(-4,LCID,3,(13, 10),())
        return win32com.client.util.Iterator(ob)
    def _NewEnum(self):
        "Create an enumerator from this object"
        return win32com.client.util.WrapEnum(self._oleobj_.InvokeTypes(-4,LCID,3,(13, 10),()),None)
    @returns(QueryFieldDef)
    def __getitem__(self, index):
        "Allow this class to be accessed as a collection"
        if not self.__dict__.has_key('_enum_'):
            self.__dict__['_enum_'] = self._NewEnum()
        return self._enum_.__getitem__(index)
    #This class has Count() property - allow len(ob) to provide this
    def __len__(self):
        return self._ApplyTypes_(*(1, 2, (3, 0), (), "Count", None))
    #This class has a __len__ - this is needed so 'if object:' always returns TRUE.
    def __nonzero__(self):
        return True

class QueryFilterNode(CQObject):
    CLSID = IID('{3A8CCF40-4F1B-11D1-B2DD-00A0C9851B52}')
    coclass_clsid = IID('{3A8CCF50-4F1B-11D1-B2DD-00A0C9851B52}')

    def BuildFilter(self, FieldPath=defaultNamedNotOptArg, comp_op=defaultNamedNotOptArg, value=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(2, LCID, 1, (24, 0), ((8, 0), (3, 0), (12, 0)),FieldPath
            , comp_op, value)

    def BuildFilterOperator(self, bool_op=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(1, LCID, 1, (9, 0), ((3, 0),),bool_op
            )
        if ret is not None:
            ret = Dispatch(ret, 'BuildFilterOperator', None, UnicodeToString=0)
        return ret

    _prop_map_get_ = {
    }
    _prop_map_put_ = {
    }

class ReportDef(CQObject):
    CLSID = IID('{7C2FB010-4D54-11D4-B501-0004AC96D6BA}')
    coclass_clsid = IID('{7C2FB011-4D54-11D4-B501-0004AC96D6BA}')

    def GetQueryDefId(self):
        return self._oleobj_.InvokeTypes(12, LCID, 1, (3, 0), (),)

    def GetQueryDefPath(self):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(10, LCID, 1, (8, 0), (),)

    def GetReportFormatId(self):
        return self._oleobj_.InvokeTypes(8, LCID, 1, (3, 0), (),)

    def GetReportFormatPath(self):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(6, LCID, 1, (8, 0), (),)

    def Save(self, filename=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(14, LCID, 1, (11, 0), ((8, 0),),filename
            )

    def SetQueryDefId(self, id=defaultNamedNotOptArg, forceEntity=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(13, LCID, 1, (24, 0), ((3, 0), (11, 0)),id
            , forceEntity)

    def SetQueryDefPath(self, entityDefName=defaultNamedNotOptArg, path=defaultNamedNotOptArg, forceEntity=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(11, LCID, 1, (24, 0), ((8, 0), (8, 0), (11, 0)),entityDefName
            , path, forceEntity)

    def SetReportFormatId(self, id=defaultNamedNotOptArg, forceEntity=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(9, LCID, 1, (24, 0), ((3, 0), (11, 0)),id
            , forceEntity)

    def SetReportFormatPath(self, entityDefName=defaultNamedNotOptArg, path=defaultNamedNotOptArg, forceEntity=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(7, LCID, 1, (24, 0), ((8, 0), (8, 0), (11, 0)),entityDefName
            , path, forceEntity)

    _prop_map_get_ = {
        "IsDirty": (1, 2, (11, 0), (), "IsDirty", None),
        "IsValid": (5, 2, (11, 0), (), "IsValid", None),
        "Name": (2, 2, (8, 0), (), "Name", None),
        "ReportDefId": (4, 2, (3, 0), (), "ReportDefId", None),
        "entityDefName": (3, 2, (8, 0), (), "entityDefName", None),
    }
    _prop_map_put_ = {
        "IsDirty" : ((1, LCID, 4, 0),()),
        "IsValid" : ((5, LCID, 4, 0),()),
        "Name" : ((2, LCID, 4, 0),()),
        "ReportDefId" : ((4, LCID, 4, 0),()),
        "entityDefName" : ((3, LCID, 4, 0),()),
    }

class ResultSet(CQObject):
    CLSID = IID('{14BE7434-785A-11D0-A431-00A024DED613}')
    coclass_clsid = IID('{14BE7435-785A-11D0-A431-00A024DED613}')

    def AddParamValue(self, param_number=defaultNamedNotOptArg, value=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(12, LCID, 1, (24, 0), ((3, 0), (12, 0)),param_number
            , value)

    def ClearParamValues(self, param_number=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(13, LCID, 1, (24, 0), ((3, 0),),param_number
            )

    def EnableRecordCount(self):
        return self._oleobj_.InvokeTypes(22, LCID, 1, (24, 0), (),)

    def Execute(self):
        return self._oleobj_.InvokeTypes(6, LCID, 1, (24, 0), (),)

    def ExecuteAndCountRecords(self):
        return self._oleobj_.InvokeTypes(19, LCID, 1, (3, 0), (),)

    def GetAllColumnValues(self, bMoveNext=defaultNamedNotOptArg):
        return self._ApplyTypes_(26, 1, (12, 0), ((11, 0),), 'GetAllColumnValues', None,bMoveNext
            )

    def GetColumnLabel(self, ordinal_column_number=defaultNamedNotOptArg):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(2, LCID, 1, (8, 0), ((3, 0),),ordinal_column_number
            )

    def GetColumnType(self, ordinal_column_number=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(1, LCID, 1, (3, 0), ((3, 0),),ordinal_column_number
            )

    def GetColumnValue(self, ordinal_column_number=defaultNamedNotOptArg):
        return self._ApplyTypes_(4, 1, (12, 0), ((3, 0),), 'GetColumnValue', None,ordinal_column_number
            )

    def GetNumberOfColumns(self):
        return self._oleobj_.InvokeTypes(3, LCID, 1, (3, 0), (),)

    def GetNumberOfParams(self):
        return self._oleobj_.InvokeTypes(7, LCID, 1, (3, 0), (),)

    def GetParamChoiceList(self, param_number=defaultNamedNotOptArg):
        return self._ApplyTypes_(11, 1, (12, 0), ((3, 0),), 'GetParamChoiceList', None,param_number
            )

    def GetParamComparisonOperator(self, param_number=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(14, LCID, 1, (3, 0), ((3, 0),),param_number
            )

    def GetParamFieldType(self, param_number=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(9, LCID, 1, (3, 0), ((3, 0),),param_number
            )

    def GetParamLabel(self, param_number=defaultNamedNotOptArg):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(10, LCID, 1, (8, 0), ((3, 0),),param_number
            )

    def GetParamPrompt(self, param_number=defaultNamedNotOptArg):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(8, LCID, 1, (8, 0), ((3, 0),),param_number
            )

    def GetRowEntityDefName(self):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(21, LCID, 1, (8, 0), (),)

    def GetSQL(self):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(15, LCID, 1, (8, 0), (),)

    def LookupPrimaryEntityDefName(self):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(16, LCID, 1, (8, 0), (),)

    def MoveAbsolute(self, row=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(18, LCID, 1, (3, 0), ((3, 0),),row
            )

    def MoveNext(self):
        return self._oleobj_.InvokeTypes(5, LCID, 1, (3, 0), (),)

    def SetParamComparisonOperator(self, param_number=defaultNamedNotOptArg, param=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(23, LCID, 1, (24, 0), ((3, 0), (3, 0)),param_number
            , param)

    _prop_map_get_ = {
        "BufferSize": (24, 2, (3, 0), (), "BufferSize", None),
        "MaxMultiLineTextLength": (25, 2, (3, 0), (), "MaxMultiLineTextLength", None),
        "MaxRowsInMemory": (17, 2, (3, 0), (), "MaxRowsInMemory", None),
        "RecordCount": (20, 2, (3, 0), (), "RecordCount", None),
    }
    _prop_map_put_ = {
        "BufferSize" : ((24, LCID, 4, 0),()),
        "MaxMultiLineTextLength" : ((25, LCID, 4, 0),()),
        "MaxRowsInMemory": ((17, LCID, 4, 0),()),
    }

class Schema(CQObject):
    CLSID = IID('{E79F83D3-D096-11D1-B37A-00A0C9851B52}')
    coclass_clsid = IID('{E79F83D5-D096-11D1-B37A-00A0C9851B52}')

    _prop_map_get_ = {
        "Name": (1, 2, (8, 0), (), "Name", None),
        "SchemaRevs": (2, 2, (9, 0), (), "SchemaRevs", None),
    }
    _prop_map_put_ = {
        "Name" : ((1, LCID, 4, 0),()),
        "SchemaRevs" : ((2, LCID, 4, 0),()),
    }
    
    def getRevision(self, revision):
        """
        @param revision: L{string} representing the revision number to retrieve.
        @return: L{SchemaRev} object for the given revision.
        """
        id = int(revision)
        revs = self.SchemaRevs
        rev = None
        found = False
        try:
            rev = revs[id-1]
            if rev.RevID != id:
                raise IndexError
            else:
                found = True
        except IndexError:
            i = 0
            count = revs.Count
            while i < count:
                rev = revs[i]
                if rev.RevID == id:
                    found = True
                    break
                i += 1
        finally:
            if not found:
                raise ValueError, "revision '%s' does not exist in schema '%s'"\
                                  % (revision, self.Name)
            else:
                return rev

class SchemaRev(CQObject):
    CLSID = IID('{E79F83D9-D096-11D1-B37A-00A0C9851B52}')
    coclass_clsid = IID('{E79F83DB-D096-11D1-B37A-00A0C9851B52}')

    @returns(EntityDefs)
    def GetEnabledEntityDefs(self, package=defaultNamedNotOptArg, rev=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(4, LCID, 1, (9, 0), ((8, 0), (8, 0)),package
            , rev)
        if ret is not None:
            ret = Dispatch(ret, 'GetEnabledEntityDefs', None, UnicodeToString=0)
        return ret

    @returns(PackageRevs)
    def GetEnabledPackageRevs(self):
        ret = self._oleobj_.InvokeTypes(5, LCID, 1, (9, 0), (),)
        if ret is not None:
            ret = Dispatch(ret, 'GetEnabledPackageRevs', None, UnicodeToString=0)
        return ret

    _prop_map_get_ = {
        "Description": (2, 2, (8, 0), (), "Description", None),
        "RevID": (1, 2, (3, 0), (), "RevID", None),
        "Schema": (3, 2, (9, 0), (), "Schema", None),
    }
    _prop_map_put_ = {
        "Description" : ((2, LCID, 4, 0),()),
        "RevID" : ((1, LCID, 4, 0),()),
        "Schema" : ((3, LCID, 4, 0),()),
    }

class SchemaRevs(CQObject):
    CLSID = IID('{E79F83DC-D096-11D1-B37A-00A0C9851B52}')
    coclass_clsid = IID('{E79F83DE-D096-11D1-B37A-00A0C9851B52}')

    @returns(SchemaRev)
    def item(self, Index=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(0, LCID, 1, (9, 0), ((16396, 0),),Index
            )
        if ret is not None:
            ret = Dispatch(ret, 'item', None, UnicodeToString=0)
        return ret

    _prop_map_get_ = {
        "Count": (1, 2, (3, 0), (), "Count", None),
    }
    _prop_map_put_ = {
        "Count" : ((1, LCID, 4, 0),()),
        "_NewEnum" : ((-4, LCID, 4, 0),()),
    }
    # Default method for this class is 'item'
    @returns(SchemaRev)
    def __call__(self, Index=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(0, LCID, 1, (9, 0), ((16396, 0),),Index
            )
        if ret is not None:
            ret = Dispatch(ret, '__call__', None, UnicodeToString=0)
        return ret

    # str(ob) and int(ob) will use __call__
    def __unicode__(self, *args):
        try:
            return unicode(self.__call__(*args))
        except pythoncom.com_error:
            return repr(self)
    def __str__(self, *args):
        return str(self.__unicode__(*args))
    def __int__(self, *args):
        return int(self.__call__(*args))
    @returns(CQIterator(SchemaRev))
    def __iter__(self):
        "Return a Python iterator for this object"
        ob = self._oleobj_.InvokeTypes(-4,LCID,3,(13, 10),())
        return win32com.client.util.Iterator(ob)
    def _NewEnum(self):
        "Create an enumerator from this object"
        return win32com.client.util.WrapEnum(self._oleobj_.InvokeTypes(-4,LCID,3,(13, 10),()),None)
    @returns(SchemaRev)
    def __getitem__(self, index):
        "Allow this class to be accessed as a collection"
        if not self.__dict__.has_key('_enum_'):
            self.__dict__['_enum_'] = self._NewEnum()
        return self._enum_.__getitem__(index)
    #This class has Count() property - allow len(ob) to provide this
    def __len__(self):
        return self._ApplyTypes_(*(1, 2, (3, 0), (), "Count", None))
    #This class has a __len__ - this is needed so 'if object:' always returns TRUE.
    def __nonzero__(self):
        return True

class Schemas(CQObject):
    CLSID = IID('{E79F83D6-D096-11D1-B37A-00A0C9851B52}')
    coclass_clsid = IID('{E79F83D8-D096-11D1-B37A-00A0C9851B52}')

    @returns(Schema)
    def item(self, Index=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(0, LCID, 1, (9, 0), ((16396, 0),),Index
            )
        if ret is not None:
            ret = Dispatch(ret, 'item', None, UnicodeToString=0)
        return ret

    _prop_map_get_ = {
        "Count": (1, 2, (3, 0), (), "Count", None),
    }
    _prop_map_put_ = {
        "Count" : ((1, LCID, 4, 0),()),
        "_NewEnum" : ((-4, LCID, 4, 0),()),
    }
    # Default method for this class is 'item'
    @returns(Schema)
    def __call__(self, Index=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(0, LCID, 1, (9, 0), ((16396, 0),),Index
            )
        if ret is not None:
            ret = Dispatch(ret, '__call__', None, UnicodeToString=0)
        return ret

    # str(ob) and int(ob) will use __call__
    def __unicode__(self, *args):
        try:
            return unicode(self.__call__(*args))
        except pythoncom.com_error:
            return repr(self)
    def __str__(self, *args):
        return str(self.__unicode__(*args))
    def __int__(self, *args):
        return int(self.__call__(*args))
    @returns(CQIterator(Schema))
    def __iter__(self):
        "Return a Python iterator for this object"
        ob = self._oleobj_.InvokeTypes(-4,LCID,3,(13, 10),())
        return win32com.client.util.Iterator(ob)
    def _NewEnum(self):
        "Create an enumerator from this object"
        return win32com.client.util.WrapEnum(self._oleobj_.InvokeTypes(-4,LCID,3,(13, 10),()),None)
    @returns(Schema)
    def __getitem__(self, index):
        "Allow this class to be accessed as a collection"
        if not self.__dict__.has_key('_enum_'):
            self.__dict__['_enum_'] = self._NewEnum()
        return self._enum_.__getitem__(index)
    #This class has Count() property - allow len(ob) to provide this
    def __len__(self):
        return self._ApplyTypes_(*(1, 2, (3, 0), (), "Count", None))
    #This class has a __len__ - this is needed so 'if object:' always returns TRUE.
    def __nonzero__(self):
        return True

class Session(CQObject):
    CLSID = IID('{94773111-72E8-11D0-A42E-00A024DED613}')
    coclass_clsid = IID('{94773112-72E8-11D0-A42E-00A024DED613}')
    
    def __init__(self, *args):
        self.__dict__['session'] = self
        CQObject.__init__(self, *args)
        self.__dict__['entityDefs'] = dict()

    def AddListMember(self, ListName=defaultNamedNotOptArg, Member=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(38, LCID, 1, (24, 0), ((8, 0), (8, 0)),ListName
            , Member)

    @returns(Entity)
    def BuildEntity(self, entity_def_name=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(8, LCID, 1, (9, 0), ((8, 0),),entity_def_name
            )
        if ret is not None:
            ret = Dispatch(ret, 'BuildEntity', None, UnicodeToString=0)
        return ret

    def BuildPermission(self):
        ret = self._oleobj_.InvokeTypes(121, LCID, 1, (9, 0), (),)
        if ret is not None:
            ret = Dispatch(ret, 'BuildPermission', None, UnicodeToString=0)
        return ret

    def BuildPermissions(self):
        ret = self._oleobj_.InvokeTypes(122, LCID, 1, (9, 0), (),)
        if ret is not None:
            ret = Dispatch(ret, 'BuildPermissions', None, UnicodeToString=0)
        return ret

    @returns(QueryDef)
    def BuildQuery(self, primary_entitydef_name=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(30, LCID, 1, (9, 0), ((8, 0),),primary_entitydef_name
            )
        if ret is not None:
            ret = Dispatch(ret, 'BuildQuery', None, UnicodeToString=0)
        return ret

    @returns(ResultSet)
    def BuildResultSet(self, query_def=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(10, LCID, 1, (9, 0), ((9, 0),),query_def
            )
        if ret is not None:
            ret = Dispatch(ret, 'BuildResultSet', None, UnicodeToString=0)
        return ret

    @returns('ResultSet')
    def BuildSQLQuery(self, sql_string=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(29, LCID, 1, (9, 0), ((8, 0),),sql_string
            )
        if ret is not None:
            ret = Dispatch(ret, 'BuildSQLQuery', None, UnicodeToString=0)
        return ret

    def CQDataCodePageIsSet(self):
        return self._oleobj_.InvokeTypes(90, LCID, 1, (11, 0), (),)

    def CanSubmit(self, entDefName=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(97, LCID, 1, (11, 0), ((8, 0),),entDefName
            )

    def CheckHeartbeat(self):
        return self._oleobj_.InvokeTypes(59, LCID, 1, (11, 0), (),)

    def ClearMessages(self):
        return self._oleobj_.InvokeTypes(58, LCID, 1, (24, 0), (),)

    def ClearNameValues(self):
        return self._oleobj_.InvokeTypes(44, LCID, 1, (24, 0), (),)

    def DbIdToStringId(self, db_id=defaultNamedNotOptArg):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(88, LCID, 1, (8, 0), ((8, 0),),db_id
            )

    def DeleteEntity(self, entity=defaultNamedNotOptArg, deleteActionName=defaultNamedNotOptArg):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(41, LCID, 1, (8, 0), ((9, 0), (8, 0)),entity
            , deleteActionName)

    def DeleteListMember(self, ListName=defaultNamedNotOptArg, Member=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(39, LCID, 1, (24, 0), ((8, 0), (8, 0)),ListName
            , Member)

    def EchoString(self, toEcho=defaultNamedNotOptArg):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(104, LCID, 1, (8, 0), ((8, 0),),toEcho
            )

    def EditEntity(self, entity=defaultNamedNotOptArg, edit_action_name=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(9, LCID, 1, (24, 0), ((9, 0), (8, 0)),entity
            , edit_action_name)

    def EmitMessage(self, message=defaultNamedNotOptArg, kind=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(55, LCID, 1, (24, 0), ((8, 0), (3, 0)),message
            , kind)

    def EntityExists(self, entityDefName=defaultNamedNotOptArg, displayName=defaultNamedNotOptArg):
        # The COM API version of this call doesn't seem to work; if you pass it
        # a valid EntityDef name, it always returns true, regardless of whether
        # or not there's actually an entity matching the provided display name.
        # So, we provide our own implementation that actually works.
        return bool(self.lookupEntityDbIdByDisplayName(entityDefName, displayName))
        
        # Originally:
        #return self._oleobj_.InvokeTypes(83, LCID, 1, (11, 0), ((8, 0), (8, 0)),entity_def_name
        #    , display_name)

    def EntityExistsByDbId(self, entityDefName=defaultNamedNotOptArg, dbid=defaultNamedNotOptArg):
        return bool(self.lookupEntityDisplayNameByDbId(entityDefName, dbid))
        
        # Originally:
        #return self._oleobj_.InvokeTypes(82, LCID, 1, (11, 0), ((8, 0), (3, 0)),entity_def_name
        #    , db_id)

    def FireRecordScriptAlias(self, entity=defaultNamedNotOptArg, editActionName=defaultNamedNotOptArg):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(45, LCID, 1, (8, 0), ((9, 0), (8, 0)),entity
            , editActionName)

    @returns(DatabaseDesc)
    def GetAccessibleDatabases(self, master_db_name=defaultNamedNotOptArg, user_login_name=defaultNamedNotOptArg, db_set_name=defaultNamedNotOptArg):
        return self._ApplyTypes_(28, 1, (12, 0), ((8, 0), (8, 0), (8, 0)), 'GetAccessibleDatabases', None,master_db_name
            , user_login_name, db_set_name)

    def GetAllGroups(self, extend_option=defaultNamedNotOptArg):
        return self._ApplyTypes_(124, 1, (12, 0), ((3, 0),), 'GetAllGroups', None,extend_option
            )

    def GetAllUsers(self, extend_option=defaultNamedNotOptArg):
        return self._ApplyTypes_(125, 1, (12, 0), ((3, 0),), 'GetAllUsers', None,extend_option
            )

    def GetAuthenticationLoginName(self):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(100, LCID, 1, (8, 0), (),)

    def GetAuxEntityDefNames(self):
        return self._ApplyTypes_(3, 1, (12, 0), (), 'GetAuxEntityDefNames', None,)

    def GetBasicReturnStringMode(self):
        return self._oleobj_.InvokeTypes(102, LCID, 1, (3, 0), (),)

    def GetBuildNumber(self):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(114, LCID, 1, (8, 0), (),)

    def GetCQDataCodePage(self):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(93, LCID, 1, (8, 0), (),)

    def GetClearQuestAPIVersionMajor(self):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(116, LCID, 1, (8, 0), (),)

    def GetClearQuestAPIVersionMinor(self):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(117, LCID, 1, (8, 0), (),)

    def GetClientCodePage(self):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(94, LCID, 1, (8, 0), (),)

    def GetCompanyEmailAddress(self):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(112, LCID, 1, (8, 0), (),)

    def GetCompanyFullName(self):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(111, LCID, 1, (8, 0), (),)

    def GetCompanyName(self):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(110, LCID, 1, (8, 0), (),)

    def GetCompanyWebAddress(self):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(113, LCID, 1, (8, 0), (),)

    def GetDefaultDbSetName(self):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(115, LCID, 1, (8, 0), (),)

    @returns(EntityDef)
    def GetDefaultEntityDef(self):
        ret = self._oleobj_.InvokeTypes(33, LCID, 1, (9, 0), (),)
        if ret is not None:
            ret = Dispatch(ret, 'GetDefaultEntityDef', None, UnicodeToString=0)
        return ret

    def GetDisplayNamesNeedingSiteExtension(self, edefname=defaultNamedNotOptArg):
        return self._ApplyTypes_(71, 1, (12, 0), ((8, 0),), 'GetDisplayNamesNeedingSiteExtension', None,edefname
            )

    @returns(EntityDef)
    def GetEnabledEntityDefs(self, package=defaultNamedNotOptArg, rev=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(53, LCID, 1, (9, 0), ((8, 0), (8, 0)),package
            , rev)
        if ret is not None:
            ret = Dispatch(ret, 'GetEnabledEntityDefs', None, UnicodeToString=0)
        return ret

    @returns(PackageRevs)
    def GetEnabledPackageRevs(self):
        ret = self._oleobj_.InvokeTypes(52, LCID, 1, (9, 0), (),)
        if ret is not None:
            ret = Dispatch(ret, 'GetEnabledPackageRevs', None, UnicodeToString=0)
        return ret

    @returns(Entity)
    def GetEntity(self, entity_def_name=defaultNamedNotOptArg, display_name=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(12, LCID, 1, (9, 0), ((8, 0), (8, 0)),entity_def_name
            , display_name)
        if ret is not None:
            ret = Dispatch(ret, 'GetEntity', None, UnicodeToString=0)
        return ret

    @returns(Entity)
    def GetEntityByDbId(self, entity_def_name=defaultNamedNotOptArg, db_id=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(13, LCID, 1, (9, 0), ((8, 0), (3, 0)),entity_def_name
            , db_id)
        if ret is not None:
            ret = Dispatch(ret, 'GetEntityByDbId', None, UnicodeToString=0)
        return ret

    @cache
    def GetEntityDef(self, entityDefName=defaultNamedNotOptArg): pass
            
    @returns(EntityDef)
    def _GetEntityDef(self, entity_def_name=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(15, LCID, 1, (9, 0), ((8, 0),),entity_def_name
            )
        if ret is not None:
            ret = Dispatch(ret, 'GetEntityDef', None, UnicodeToString=0)
        return ret

    @returns(EntityDef)
    def GetEntityDefFamily(self, familyName=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(48, LCID, 1, (9, 0), ((8, 0),),familyName
            )
        if ret is not None:
            ret = Dispatch(ret, 'GetEntityDefFamily', None, UnicodeToString=0)
        return ret

    def GetEntityDefFamilyNames(self):
        return self._ApplyTypes_(47, 1, (12, 0), (), 'GetEntityDefFamilyNames', None,)

    def GetEntityDefNames(self):
        return self._ApplyTypes_(5, 1, (12, 0), (), 'GetEntityDefNames', None,)

    def GetEntityDefNamesForSubmit(self):
        return self._ApplyTypes_(98, 1, (12, 0), (), 'GetEntityDefNamesForSubmit', None,)

    @returns(EntityDef)
    def GetEntityDefOfDbId(self, dbid=defaultNamedNotOptArg, entDefNames=defaultNamedNotOptArg, entityDefType=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(120, LCID, 1, (9, 0), ((8, 0), (12, 0), (3, 0)),dbid
            , entDefNames, entityDefType)
        if ret is not None:
            ret = Dispatch(ret, 'GetEntityDefOfDbId', None, UnicodeToString=0)
        return ret

    @returns(EntityDef)
    def GetEntityDefOfName(self, DisplayName=defaultNamedNotOptArg, entDefNames=defaultNamedNotOptArg, entityDefType=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(119, LCID, 1, (9, 0), ((8, 0), (12, 0), (3, 0)),DisplayName
            , entDefNames, entityDefType)
        if ret is not None:
            ret = Dispatch(ret, 'GetEntityDefOfName', None, UnicodeToString=0)
        return ret

    @returns(EntityDef)
    def GetEntityDefOrFamily(self, familyName=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(49, LCID, 1, (9, 0), ((8, 0),),familyName
            )
        if ret is not None:
            ret = Dispatch(ret, 'GetEntityDefOrFamily', None, UnicodeToString=0)
        return ret

    def GetEveryoneGroupName(self):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(123, LCID, 1, (8, 0), (),)

    def GetFullProductVersion(self):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(105, LCID, 1, (8, 0), (),)

    def GetInstalledMasters(self, DbSets=defaultNamedNotOptArg, MasterDbs=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(32, LCID, 1, (24, 0), ((16396, 0), (16396, 0)),DbSets
            , MasterDbs)

    def GetLicenseFeature(self):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(108, LCID, 1, (8, 0), (),)

    def GetLicenseVersion(self):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(107, LCID, 1, (8, 0), (),)

    def GetListDefNames(self):
        return self._ApplyTypes_(35, 1, (12, 0), (), 'GetListDefNames', None,)

    def GetListMembers(self, ListName=defaultNamedNotOptArg):
        return self._ApplyTypes_(36, 1, (12, 0), ((8, 0),), 'GetListMembers', None,ListName
            )

    def GetLocalReplica(self):
        ret = self._oleobj_.InvokeTypes(65, LCID, 1, (9, 0), (),)
        if ret is not None:
            ret = Dispatch(ret, 'GetLocalReplica', None, UnicodeToString=0)
        return ret

    def GetMaxCompatibleFeatureLevel(self):
        return self._oleobj_.InvokeTypes(74, LCID, 1, (3, 0), (),)

    def GetMessageCount(self):
        return self._oleobj_.InvokeTypes(57, LCID, 1, (3, 0), (),)

    def GetMinCompatibleFeatureLevel(self):
        return self._oleobj_.InvokeTypes(73, LCID, 1, (3, 0), (),)

    def GetNextEmission(self):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(62, LCID, 1, (8, 0), (),)

    def GetNextMessage(self, message=pythoncom.Missing, kind=pythoncom.Missing):
        return self._ApplyTypes_(56, 1, (11, 0), ((16392, 2), (16387, 2)), 'GetNextMessage', None,message
            , kind)

    def GetPatchVersion(self):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(106, LCID, 1, (8, 0), (),)

    def GetProductVersion(self):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(79, LCID, 1, (8, 0), (),)

    def GetQueryEntityDefFamilyNames(self):
        return self._ApplyTypes_(50, 1, (12, 0), (), 'GetQueryEntityDefFamilyNames', None,)

    def GetQueryEntityDefNames(self):
        return self._ApplyTypes_(7, 1, (12, 0), (), 'GetQueryEntityDefNames', None,)

    def GetReqEntityDefNames(self):
        return self._ApplyTypes_(4, 1, (12, 0), (), 'GetReqEntityDefNames', None,)

    def GetServerInfo(self):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(18, LCID, 1, (8, 0), (),)

    @returns(DatabaseDesc)
    def GetSessionDatabase(self):
        ret = self._oleobj_.InvokeTypes(31, LCID, 1, (9, 0), (),)
        if ret is not None:
            ret = Dispatch(ret, 'GetSessionDatabase', None, UnicodeToString=0)
        return ret

    def GetSessionFeatureLevel(self):
        return self._oleobj_.InvokeTypes(72, LCID, 1, (3, 0), (),)

    def GetSiteExtendedNames(self, lpszEDefName=defaultNamedNotOptArg, lpszDisplayName=defaultNamedNotOptArg):
        return self._ApplyTypes_(66, 1, (12, 0), ((8, 0), (8, 0)), 'GetSiteExtendedNames', None,lpszEDefName
            , lpszDisplayName)

    def GetSiteExtension(self, Name=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(70, LCID, 1, (3, 0), ((8, 0),),Name
            )

    def GetStageLabel(self):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(81, LCID, 1, (8, 0), (),)

    def GetSubmitEntityDefNames(self):
        return self._ApplyTypes_(6, 1, (12, 0), (), 'GetSubmitEntityDefNames', None,)

    def GetSuiteBuildId(self):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(118, LCID, 1, (8, 0), (),)

    def GetSuiteProductVersion(self):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(96, LCID, 1, (8, 0), (),)

    def GetSuiteVersion(self):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(80, LCID, 1, (8, 0), (),)

    def GetUnextendedName(self, Name=defaultNamedNotOptArg):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(69, LCID, 1, (8, 0), ((8, 0),),Name
            )

    def GetUserAuthenticationMode(self):
        return self._oleobj_.InvokeTypes(101, LCID, 1, (3, 0), (),)

    def GetUserEmail(self):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(24, LCID, 1, (8, 0), (),)

    def GetUserEncryptedPassword(self):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(40, LCID, 1, (8, 0), (),)

    def GetUserFullName(self):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(23, LCID, 1, (8, 0), (),)

    def GetUserGroups(self):
        return self._ApplyTypes_(27, 1, (12, 0), (), 'GetUserGroups', None,)

    def GetUserLoginName(self):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(22, LCID, 1, (8, 0), (),)

    def GetUserMiscInfo(self):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(26, LCID, 1, (8, 0), (),)

    def GetUserPhone(self):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(25, LCID, 1, (8, 0), (),)

    def GetWebLicenseVersion(self):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(109, LCID, 1, (8, 0), (),)

    @returns('Workspace')
    def GetWorkSpace(self):
        ret = self._oleobj_.InvokeTypes(43, LCID, 1, (9, 0), (),)
        if ret is not None:
            ret = Dispatch(ret, 'GetWorkSpace', None, UnicodeToString=0)
        return ret

    def HasUserPrivilege(self, priv_mask=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(75, LCID, 1, (11, 0), ((3, 0),),priv_mask
            )

    def HasValue(self, Name=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(34, LCID, 1, (11, 0), ((8, 0),),Name
            )

    def IsClientCodePageCompatibleWithCQDataCodePage(self):
        return self._oleobj_.InvokeTypes(92, LCID, 1, (11, 0), (),)

    def IsEmailEnabled(self):
        return self._oleobj_.InvokeTypes(51, LCID, 1, (11, 0), (),)

    def IsMetadataReadonly(self):
        return self._oleobj_.InvokeTypes(2, LCID, 1, (11, 0), (),)

    def IsMultisiteActivated(self):
        return self._oleobj_.InvokeTypes(84, LCID, 1, (11, 0), (),)

    def IsPackageUpgradeNeeded(self, package_name=defaultNamedNotOptArg, current_rev=defaultNamedNotOptArg, highest_rev=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(86, LCID, 1, (11, 0), ((8, 0), (16396, 0), (16396, 0)),package_name
            , current_rev, highest_rev)

    def IsReplicated(self):
        return self._oleobj_.InvokeTypes(78, LCID, 1, (11, 0), (),)

    def IsRestrictedUser(self):
        return self._oleobj_.InvokeTypes(61, LCID, 1, (11, 0), (),)

    def IsSiteExtendedName(self, Name=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(67, LCID, 1, (11, 0), ((8, 0),),Name
            )

    def IsStringInCQDataCodePage(self, string=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(89, LCID, 1, (11, 0), ((8, 0),),string
            )

    def IsUnsupportedClientCodePage(self):
        return self._oleobj_.InvokeTypes(91, LCID, 1, (11, 0), (),)

    def IsUserAppBuilder(self):
        return self._oleobj_.InvokeTypes(63, LCID, 1, (11, 0), (),)

    def IsUserSuperUser(self):
        return self._oleobj_.InvokeTypes(64, LCID, 1, (11, 0), (),)

    @returns(Entity)
    def LoadEntity(self, entity_def_name=defaultNamedNotOptArg, display_name=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(76, LCID, 1, (9, 0), ((8, 0), (8, 0)),entity_def_name
            , display_name)
        if ret is not None:
            ret = Dispatch(ret, 'LoadEntity', None, UnicodeToString=0)
        return ret

    @returns(Entity)
    def LoadEntityByDbId(self, entity_def_name=defaultNamedNotOptArg, db_id=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(77, LCID, 1, (9, 0), ((8, 0), (3, 0)),entity_def_name
            , db_id)
        if ret is not None:
            ret = Dispatch(ret, 'LoadEntityByDbId', None, UnicodeToString=0)
        return ret

    def MarkEntityAsDuplicate(self, entity_to_mark=defaultNamedNotOptArg, entity_it_duplicates=defaultNamedNotOptArg, duplicate_action_name=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(16, LCID, 1, (24, 0), ((9, 0), (9, 0), (8, 0)),entity_to_mark
            , entity_it_duplicates, duplicate_action_name)

    # The method NameValue is actually a property, but must be used as a method to correctly pass the arguments
    def NameValue(self, Name=defaultNamedNotOptArg):
        return self._ApplyTypes_(42, 2, (12, 0), ((8, 0),), 'NameValue', None,Name
            )

    @returns(QueryDef)
    def OpenQueryDef(self, filename=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(11, LCID, 1, (9, 0), ((8, 0),),filename
            )
        if ret is not None:
            ret = Dispatch(ret, 'OpenQueryDef', None, UnicodeToString=0)
        return ret

    def OutputDebugString(self, the_string=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(19, LCID, 1, (24, 0), ((8, 0),),the_string
            )

    def OutputTextMessage(self, the_message=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(20, LCID, 1, (24, 0), ((8, 0),),the_message
            )

    def ParseSiteExtendedName(self, Name=defaultNamedNotOptArg, display_name=defaultNamedNotOptArg, replica_dbid=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(68, LCID, 1, (11, 0), ((8, 0), (16396, 0), (16396, 0)),Name
            , display_name, replica_dbid)

    def RegisterSchemaRepoFromFile(self, filePath=defaultNamedNotOptArg):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(46, LCID, 1, (8, 0), ((8, 0),),filePath
            )

    def RegisterSchemaRepoFromFileByDbSet(self, dbset=defaultNamedNotOptArg, filePath=defaultNamedNotOptArg):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(85, LCID, 1, (8, 0), ((8, 0), (8, 0)),dbset
            , filePath)

    def SetBasicReturnStringMode(self, mode=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(103, LCID, 1, (24, 0), ((3, 0),),mode
            )

    def SetListMembers(self, ListName=defaultNamedNotOptArg, members=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(37, LCID, 1, (24, 0), ((8, 0), (12, 0)),ListName
            , members)

    # The method SetNameValue is actually a property, but must be used as a method to correctly pass the arguments
    def SetNameValue(self, Name=defaultNamedNotOptArg, arg1=defaultUnnamedArg):
        return self._oleobj_.InvokeTypes(42, LCID, 4, (24, 0), ((8, 0), (12, 0)),Name
            , arg1)

    def SetRestrictedUser(self):
        return self._oleobj_.InvokeTypes(60, LCID, 1, (11, 0), (),)

    def SignOff(self):
        return self._oleobj_.InvokeTypes(54, LCID, 1, (11, 0), (),)

    def StringIdToDbId(self, string_id=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(87, LCID, 1, (3, 0), ((8, 0),),string_id
            )

    def TestingThrowException(self, exception_code=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(14, LCID, 1, (24, 0), ((3, 0),),exception_code
            )

    def UnmarkEntityAsDuplicate(self, entity=defaultNamedNotOptArg, unduplicate_action_name=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(17, LCID, 1, (24, 0), ((9, 0), (8, 0)),entity
            , unduplicate_action_name)

    def UserLogon(self, login_name=defaultNamedNotOptArg, password=defaultNamedNotOptArg, database_name=defaultNamedNotOptArg, session_type=defaultNamedNotOptArg
            , database_set=defaultNamedNotOptArg):
        self.__dict__['_loginName'] = login_name
        self.__dict__['_password'] = password
        self.__dict__['_databaseName'] = database_name
        self.__dict__['_databaseSet'] = database_set
        self.__dict__['_sessionType'] = session_type
        # Clear any previously cached AdminSession object.
        try:
            del self.__dict__['_cache_getAdminSession']['(),{}']
        except:
            pass
        return self._oleobj_.InvokeTypes(21, LCID, 1, (24, 0), ((8, 0), (8, 0), (8, 0), (3, 0), (8, 0)),login_name
            , password, database_name, session_type, database_set)

    def ValidateStringInCQDataCodePage(self, string=defaultNamedNotOptArg):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(95, LCID, 1, (8, 0), ((8, 0),),string
            )

    def ValidateUserCredentials(self, login=defaultNamedNotOptArg, pw=defaultNamedNotOptArg):
        # Result is a Unicode object - return as-is for this version of Python
        return self._oleobj_.InvokeTypes(99, LCID, 1, (8, 0), ((8, 0), (8, 0)),login
            , pw)

    _prop_map_get_ = {
        "QueryDefs": (1, 2, (9, 0), (), "QueryDefs", None),
    }
    _prop_map_put_ = {
        "QueryDefs" : ((1, LCID, 4, 0),()),
    }
    
    @xml()
    def buildEntityFromXml(self, xmlText): pass
    
    @cache
    def connectString(self):
        return self.GetSessionDatabase().GetDatabaseConnectString()
    
    @cache
    def connectStringToMap(self):
        return connectStringToMap(self.connectString())

    @cache
    def db(self):
        return db.Connection(self)
    
    

    def lookupEntityDisplayNameByDbId(self, entityDefName, dbid):
        return self.GetEntityDef(entityDefName) \
                   .lookupDisplayNameByDbId(dbid)
                   
    def lookupEntityDbIdByDisplayName(self, entityDefName, displayName):
        return self.GetEntityDef(entityDefName) \
                   .lookupDbIdByDisplayName(displayName)
    
    def create(self, entityDefName, changes=dict()):
        return DeferredWriteEntityProxy(self.BuildEntity(entityDefName),
                                        changes=changes)
    
    def get(self, entityDefName, displayName, changes=dict()):
        return DeferredWriteEntityProxy(self.GetEntity(entityDefName,
                                                       displayName),
                                        changes=changes)
    
    def createOrUpdateEntity(self, entityDefName, displayName, changes=dict()):
        """
        Gets a reference to an entity of type @param entityDefName with the
        display name @param displayName.  If the entity exists, a reference to
        that entity will be returned; otherwise, the entity will be created via
        BuildEntity.
        @param entityDefName: entitydef's name
        @param destDisplayName: entity's display name
        @returns: instance of an api.DeferredWriteEntityProxy for the entity
        identified by @param displayName. If no existing entity can be found
        matching the display name, then a new one is created via BuildEntity.
        Note: for stateless entities with complex unique keys (more than one
        field), if the entity doesn't already exist and has to be created with 
        BuildEntity, this method will make a crude attempt to 'prime' the new
        entity's display name (that is, set each individual field) with the
        relevant values.  This can only be done if each field in the unique key
        doesn't contain a space, given that ClearQuest uses spaces to separate
        each fields.  So, the number of spaces found in the display name must
        be one less than the number of fields in the entity's unique key.
        If this isn't the case, a ValueError will be raised.  
        """
        entityDef = self.GetEntityDef(entityDefName)
        
        fields = [ f[0] for f in entityDef.getUniqueKey().fields() ]
        if len(fields) == 1:
            parts = (displayName,)
        else:
            parts = displayName.split(' ')
            
        if len(parts) != len(fields):
            raise ValueError, "could not discern unique key parts (%s) " \
                              "for entity '%s' from display name '%s'" % \
                              (", ".join(fields), entityDefName, displayName)
        else:
            changes = dict([(f, v) for f, v in zip(fields, parts)])
        
        args = (entityDefName, displayName)
        dbid = self.lookupEntityDbIdByDisplayName(*args)
        if dbid:
            entity = self.GetEntityByDbId(entityDefName, dbid)
        else:
            entity = self.BuildEntity(entityDefName)
        
        return DeferredWriteEntityProxy(entity, changes=changes)
        
    
    def getDynamicList(self, name):
        return loadDynamicList(name, self)
    
    def getDynamicLists(self):
        return loadDynamicLists(self)
    
    def setDynamicList(self, dynamicList):
        """
        For the list identified by dynamicList.Name, mirror its values for the
        dynamic list with the same name in this session object.  Values are 
        added and deleted as necessary.
        @param dynamicList: C{DynamicList}
        @returns: the affected C{DynamicList} of this session object.
        """
        name = dynamicList.Name
        old = self.GetListMembers(name) or tuple()
        new = tuple([ unicode(v) for v in dynamicList.values ])
        
        for value in [ n for n in new if not n in old ]:
            self.AddListMember(name, value)
        
        for value in [ o for o in old if not o in new ]:
            self.DeleteListMember(name, value)
        
        return self.getDynamicList(name)
    
    def mergeDynamicList(self, dynamicList):
        """
        For the list identified by dynamicList.Name, add all the values that 
        aren't already present to the dynamic list with the same name in this
        session object.  Does not delete any values.
        @param dynamicList: C{DynamicList}
        @returns: the affected C{DynamicList} of this session object. 
        """
        name = dynamicList.Name
        old = self.GetListMembers(name) or tuple()
        new = tuple([ unicode(v) for v in dynamicList.values ])
        
        for value in [ n for n in new if not n in old ]:
            self.AddListMember(name, value)
        
        return self.getDynamicList(name)
 
    def setDynamicLists(self, dynamicLists):
        return [ self.setDynamicList(dl) for dl in dynamicLists ]
    
    def mergeDynamicLists(self, dynamicLists):
        return [ self.mergeDynamicList(dl) for dl in dynamicLists ]
    
    def executeQuery(self, sql):
        r = self.BuildSQLQuery(sql)
        r.Execute()
        cols = range(1, r.GetNumberOfColumns()+1)
        rows = list()
        while r.MoveNext() == FetchStatus.Success:
            rows.append([ r.GetColumnValue(i) for i in cols ])
        return rows

    @cache
    @selectSingle
    def getReplicaId(self): pass
    
    @cache
    def getAllEntityDefs(self):
        return [ self.GetEntityDef(n) for n in self.GetEntityDefNames() ]
    
    @cache
    def getStatefulEntityDefs(self):
        return [
            entityDef for entityDef in self.getAllEntityDefs()
                if entityDef.GetType() == EntityType.Stateful
        ]
        
    @cache
    def getStatelessEntityDefs(self):
        return [
            entityDef for entityDef in self.getAllEntityDefs()
                if entityDef.GetType() == EntityType.Stateless
        ]

    def disableAllEntityIndexes(self):
        dummy = [ e.disableAllIndexes() for e in self.getAllEntityDefs() ]
        
    def enableAllEntityIndexes(self):
        dummy = [ e.enableAllIndexes() for e in self.getAllEntityDefs() ]
        
    @cache
    def getAdminSession(self):
        adminSession = AdminSession()
        adminSession.Logon(self._loginName, self._password, self._databaseSet)
        return adminSession
    
    @cache
    def getTablePrefix(self):
        adminSession = self.getAdminSession()
        return adminSession.getTablePrefix(self._databaseName)

    @cache
    def getPhysicalDatabaseName(self):
        return connectStringToMap(self.connectString())['DB']
    
    @cache
    def getDatabaseVendorName(self):
        connectString = self.connectString()
        driver = re.findall('DRIVER=\{([^\}]+)\}.*$', connectString,
                            re.IGNORECASE)[0].replace(' ', '')
        for vendor in DatabaseVendor.values():
            if vendor in driver:
                return vendor
        
        raise DatabaseVendorNotDiscernableFromConnectString, connectString
    
    @cache
    def getDatabaseVendor(self):
        return getattr(DatabaseVendor, self.getDatabaseVendorName())
    
    @cache
    @selectSingle
    def getCollation(self):
        return { 'databaseName' : self.getPhysicalDatabaseName() }
    
    
    @cache
    def schemaName(self):
        return self.db().selectSingle('SELECT schema_name FROM dbglobal')
    
    @cache
    def schemaRevision(self):
        return self.db().selectSingle('SELECT schema_rev FROM dbglobal')
    
    @cache
    def schemaRevisionVersion(self):
        return self.db().selectSingle('SELECT schemarev_version FROM dbglobal')
    
    
class User(CQObject):
    CLSID = IID('{B48005E4-CF24-11D1-B37A-00A0C9851B52}')
    coclass_clsid = IID('{B48005E6-CF24-11D1-B37A-00A0C9851B52}')

    def GetAuthenticationMode(self):
        return self._oleobj_.InvokeTypes(23, LCID, 1, (3, 0), (),)

    def GetUserPrivilege(self, priv=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(25, LCID, 1, (11, 0), ((3, 0),),priv
            )

    def IsSubscribedToAllDatabases(self):
        return self._oleobj_.InvokeTypes(16, LCID, 1, (11, 0), (),)

    def SetCQAuthentication(self, newPW=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(21, LCID, 1, (24, 0), ((8, 0),),newPW
            )

    def SetLDAPAuthentication(self, LDAP_Login_name=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(22, LCID, 1, (24, 0), ((8, 0),),LDAP_Login_name
            )

    def SetLoginName(self, new_name=defaultNamedNotOptArg, new_password=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(18, LCID, 1, (24, 0), ((8, 0), (8, 0)),new_name
            , new_password)

    def SetSubscribedToAllDatabases(self, bIsSubAll=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(17, LCID, 1, (24, 0), ((11, 0),),bIsSubAll
            )

    def SetUserPrivilege(self, priv=defaultNamedNotOptArg, bNewValue=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(24, LCID, 1, (24, 0), ((3, 0), (11, 0)),priv
            , bNewValue)

    def SiteHasMastership(self):
        return self._oleobj_.InvokeTypes(19, LCID, 1, (11, 0), (),)

    def SubscribeDatabase(self, database=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(13, LCID, 1, (24, 0), ((9, 0),),database
            )

    def UnsubscribeAllDatabases(self):
        return self._oleobj_.InvokeTypes(15, LCID, 1, (24, 0), (),)

    def UnsubscribeDatabase(self, database=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(14, LCID, 1, (24, 0), ((9, 0),),database
            )

    def UpgradeInfo(self):
        return self._ApplyTypes_(20, 1, (12, 0), (), 'UpgradeInfo', None,)

    _prop_map_get_ = {
        "Active": (10, 2, (11, 0), (), "Active", None),
        "AppBuilder": (8, 2, (11, 0), (), "AppBuilder", None),
        "EMail": (2, 2, (8, 0), (), "EMail", None),
        "FullName": (3, 2, (8, 0), (), "FullName", None),
        "Groups": (11, 2, (9, 0), (), "Groups", None),
        "MiscInfo": (5, 2, (8, 0), (), "MiscInfo", None),
        "Name": (1, 2, (8, 0), (), "Name", None),
        "Phone": (4, 2, (8, 0), (), "Phone", None),
        "SubscribedDatabases": (12, 2, (9, 0), (), "SubscribedDatabases", None),
        "SuperUser": (7, 2, (11, 0), (), "SuperUser", None),
        "UserMaintainer": (9, 2, (11, 0), (), "UserMaintainer", None),
        "Password": (6, 2, (8, 0), (), "password", None),
    }
    _prop_map_put_ = {
        "Active" : ((10, LCID, 4, 0),()),
        "AppBuilder" : ((8, LCID, 4, 0),()),
        "EMail" : ((2, LCID, 4, 0),()),
        "FullName" : ((3, LCID, 4, 0),()),
        "Groups" : ((11, LCID, 4, 0),()),
        "MiscInfo" : ((5, LCID, 4, 0),()),
        "Name" : ((1, LCID, 4, 0),()),
        "Phone" : ((4, LCID, 4, 0),()),
        "SubscribedDatabases" : ((12, LCID, 4, 0),()),
        "SuperUser" : ((7, LCID, 4, 0),()),
        "UserMaintainer" : ((9, LCID, 4, 0),()),
        "Password" : ((6, LCID, 4, 0),()),
    }
    
    def _setAuthenticationMode(self, mode, ldapLoginNameOrCQPassword):
        if mode == AuthenticationMode.LDAP:
            self.SetLDAPAuthentication(ldapLoginNameOrCQPassword)
        elif mode == AuthenticationMode.CQ:
            self.SetCQAuthentication(ldapLoginNameOrCQPassword)
    
    _prop_map_put_ex_ = {
                          
        # Name, Groups, SubscribedDatabases and SiteHasMastership are read-only.
        'Name' : lambda *args: None,
        'Groups' : lambda *args: None,
        'SubscribedDatabases' : lambda *args: None,
        'SiteHasMastership' : lambda *args: None,
        
        # Password can only be set indirectly via SetLoginName(login, password).
        'Password': lambda u, *args: u.SetLoginName(u.Name, args[1]),
        
        # Disable authentication mode for now.
        'AuthenticationMode' : lambda u, *args: None,
        
        # Remaining pseudo-properties that map to user privileges.
        'AllUsersVisible'   : lambda u, *args: u.SetUserPrivilege(5, args[1]),
        'DynamicListAdmin'  : lambda u, *args: u.SetUserPrivilege(1, args[1]),
        'MultiSiteAdmin'    : lambda u, *args: u.SetUserPrivilege(6, args[1]),
        'PublicFolderAdmin' : lambda u, *args: u.SetUserPrivilege(2, args[1]),
        'RawSQLWriter'      : lambda u, *args: u.SetUserPrivilege(4, args[1]),
        'SecurityAdmin'     : lambda u, *args: u.SetUserPrivilege(3, args[1]),
        'UserAdmin'         : lambda u, *args: u.SetUserPrivilege(9, args[1]),
        
        # Finalisation
        '_finalise' : lambda u, *args: u.UpgradeInfo(),
    }
    
    _prop_map_get_ex_ = {
        'IsSubscribedToAllDatabases' : lambda u: u.IsSuscribedToAllDatabases(),
                         
        'AllUsersVisible'   : lambda u: u.GetUserPrivilege(5),
        'DynamicListAdmin'  : lambda u: u.GetUserPrivilege(1),
        'MultiSiteAdmin'    : lambda u: u.GetUserPrivilege(6),
        'PublicFolderAdmin' : lambda u: u.GetUserPrivilege(2),
        'RawSQLWriter'      : lambda u: u.GetUserPrivilege(4),
        'SecurityAdmin'     : lambda u: u.GetUserPrivilege(3),
        'UserAdmin'         : lambda u: u.GetUserPrivilege(9),
    }
    
    def commit(self):
        self.UpgradeInfo()

class Users(CQCollection):
    CLSID = IID('{B48005E7-CF24-11D1-B37A-00A0C9851B52}')
    coclass_clsid = IID('{B48005E9-CF24-11D1-B37A-00A0C9851B52}')

    @returns(User)
    def item(self, Index=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(0, LCID, 1, (9, 0), ((16396, 0),),Index
            )
        if ret is not None:
            ret = Dispatch(ret, 'item', None, UnicodeToString=0)
        return ret

    _prop_map_get_ = {
        "Count": (1, 2, (3, 0), (), "Count", None),
    }
    _prop_map_put_ = {
        "Count" : ((1, LCID, 4, 0),()),
        "_NewEnum" : ((-4, LCID, 4, 0),()),
    }
    # Default method for this class is 'item'
    @returns(User)
    def __call__(self, Index=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(0, LCID, 1, (9, 0), ((16396, 0),),Index
            )
        if ret is not None:
            ret = Dispatch(ret, '__call__', None, UnicodeToString=0)
        return ret

    # str(ob) and int(ob) will use __call__
    def __unicode__(self, *args):
        try:
            return unicode(self.__call__(*args))
        except pythoncom.com_error:
            return repr(self)
    def __str__(self, *args):
        return str(self.__unicode__(*args))
    def __int__(self, *args):
        return int(self.__call__(*args))
    @returns(CQIterator(User))
    def __iter__(self):
        "Return a Python iterator for this object"
        ob = self._oleobj_.InvokeTypes(-4,LCID,3,(13, 10),())
        return win32com.client.util.Iterator(ob)
    def _NewEnum(self):
        "Create an enumerator from this object"
        return win32com.client.util.WrapEnum(self._oleobj_.InvokeTypes(-4,LCID,3,(13, 10),()),None)
    @returns(User)
    def __getitem__(self, index):
        "Allow this class to be accessed as a collection"
        if not self.__dict__.has_key('_enum_'):
            self.__dict__['_enum_'] = self._NewEnum()
        return self._enum_.__getitem__(index)
    #This class has Count() property - allow len(ob) to provide this
    def __len__(self):
        return self._ApplyTypes_(*(1, 2, (3, 0), (), "Count", None))
    #This class has a __len__ - this is needed so 'if object:' always returns TRUE.
    def __nonzero__(self):
        return True
    
    def __contains__(self, userName):
        if not 'Names' in self.__dict__:
            self.__dict__['Names'] = [ user.Name for user in self ]
        return userName in self.__dict__['Names']
    

class ReportMgr(CQObject):
    CLSID = IID('{3ACE8EF0-52FB-11D1-8C59-00A0C92337E5}')
    coclass_clsid = IID('{3ACE8EF3-52FB-11D1-8C59-00A0C92337E5}')

    def ExecuteReport(self):
        return self._oleobj_.InvokeTypes(3, LCID, 1, (24, 0), (),)

    @returns(QueryDef)
    def GetQueryDef(self):
        ret = self._oleobj_.InvokeTypes(1, LCID, 1, (9, 0), (),)
        if ret is not None:
            ret = Dispatch(ret, 'GetQueryDef', None, UnicodeToString=0)
        return ret

    def GetReportPrintJobStatus(self):
        return self._oleobj_.InvokeTypes(4, LCID, 1, (3, 0), (),)

    def SetFormat(self, format=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(5, LCID, 1, (24, 0), ((3, 0),),format
            )

    def SetHTMLFileName(self, HTMLPath=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(2, LCID, 1, (24, 0), ((8, 0),),HTMLPath
            )

    _prop_map_get_ = {
    }
    _prop_map_put_ = {
    }

class ReportMgr8(CQObject):
    CLSID = IID('{FC4DA50E-50B2-4E50-A779-D2F57EA3CC5D}')
    coclass_clsid = IID('{A0FADB3D-03D2-421C-82F3-32F6A0DD3184}')

    def ExecuteReport(self):
        return self._oleobj_.InvokeTypes(2, LCID, 1, (24, 0), (),)

    @returns(QueryDef)
    def GetQueryDef(self):
        ret = self._oleobj_.InvokeTypes(1, LCID, 1, (9, 0), (),)
        if ret is not None:
            ret = Dispatch(ret, 'GetQueryDef', None, UnicodeToString=0)
        return ret

    def GetReportPrintJobStatus(self):
        return self._oleobj_.InvokeTypes(3, LCID, 1, (3, 0), (),)

    def SetHTMLFileName(self, HTMLPath=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(4, LCID, 1, (24, 0), ((8, 0),),HTMLPath
            )

    _prop_map_get_ = {
    }
    _prop_map_put_ = {
    }

class Workspace(CQObject):
    CLSID = IID('{C5330130-ECA3-11D0-82B3-00A0C911F0B7}')
    coclass_clsid = IID('{C5330131-ECA3-11D0-82B3-00A0C911F0B7}')
    
    def __init__(self, *args, **kwds):
        self.__dict__['workspace'] = self
        CQObject.__init__(self, *args, **kwds)

    def AddStartUpQuery(self, QueryPathName=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(21, LCID, 1, (24, 0), ((8, 0),),QueryPathName
            )

    def BuildReportDef(self):
        ret = self._oleobj_.InvokeTypes(26, LCID, 1, (9, 0), (),)
        if ret is not None:
            ret = Dispatch(ret, 'BuildReportDef', None, UnicodeToString=0)
        return ret

    def CreateWorkspaceFolder(self, user_id=defaultNamedNotOptArg, folder_type=defaultNamedNotOptArg, new_name=defaultNamedNotOptArg, parent_dbid=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(57, LCID, 1, (3, 0), ((3, 0), (3, 0), (8, 0), (3, 0)),user_id
            , folder_type, new_name, parent_dbid)

    def DeleteQueryDef(self, Name=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(17, LCID, 1, (11, 0), ((8, 0),),Name
            )

    def DeleteReportDef(self, Name=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(31, LCID, 1, (11, 0), ((8, 0),),Name
            )

    def DeleteWorkspaceItemByDbId(self, dbid=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(45, LCID, 1, (11, 0), ((3, 0),),dbid
            )

    def GetAllQueriesList(self):
        return self._ApplyTypes_(14, 1, (12, 0), (), 'GetAllQueriesList', None,)

    def GetChartDbIdList(self, QuerySelector=defaultNamedNotOptArg):
        return self._ApplyTypes_(59, 1, (12, 0), ((2, 0),), 'GetChartDbIdList', None,QuerySelector
            )

    @returns(QueryDef)
    def GetChartDef(self, Name=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(6, LCID, 1, (9, 0), ((8, 0),),Name
            )
        if ret is not None:
            ret = Dispatch(ret, 'GetChartDef', None, UnicodeToString=0)
        return ret

    @returns(QueryDef, dbid=1)
    def GetChartDefByDbId(self, dbid=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(49, LCID, 1, (9, 0), ((3, 0),),dbid
            )
        if ret is not None:
            ret = Dispatch(ret, 'GetChartDefByDbId', None, UnicodeToString=0)
        return ret

    def GetChartList(self, ChartSelector=defaultNamedNotOptArg):
        return self._ApplyTypes_(5, 1, (12, 0), ((2, 0),), 'GetChartList', None,ChartSelector
            )

    @returns(ChartMgr)
    def GetChartMgr(self):
        ret = self._oleobj_.InvokeTypes(7, LCID, 1, (9, 0), (),)
        if ret is not None:
            ret = Dispatch(ret, 'GetChartMgr', None, UnicodeToString=0)
        return ret

    @returns(Folder)
    def GetFolder(self, pathname=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(71, LCID, 1, (9, 0), ((8, 0),),pathname
            )
        if ret is not None:
            ret = Dispatch(ret, 'GetFolder', None, UnicodeToString=0)
        return ret

    @returns(Folder, dbid=1)
    def GetFolderByDbId(self, dbid=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(72, LCID, 1, (9, 0), ((3, 0),),dbid
            )
        if ret is not None:
            ret = Dispatch(ret, 'GetFolderByDbId', None, UnicodeToString=0)
        return ret

    @returns(Folder)
    def GetPersonalFolder(self):
        ret = self._oleobj_.InvokeTypes(69, LCID, 1, (9, 0), (),)
        if ret is not None:
            ret = Dispatch(ret, 'GetPersonalFolder', None, UnicodeToString=0)
        return ret

    @returns(Folder)
    def GetPersonalFolderForUser(self, username=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(70, LCID, 1, (9, 0), ((8, 0),),username
            )
        if ret is not None:
            ret = Dispatch(ret, 'GetPersonalFolderForUser', None, UnicodeToString=0)
        return ret

    def GetPersonalFolderName(self):
        return self._ApplyTypes_(37, 1, (12, 0), (), 'GetPersonalFolderName', None,)

    def GetPersonalWebFolderName(self):
        return self._ApplyTypes_(64, 1, (12, 0), (), 'GetPersonalWebFolderName', None,)

    @returns(Folder)
    def GetPublicFolder(self):
        ret = self._oleobj_.InvokeTypes(68, LCID, 1, (9, 0), (),)
        if ret is not None:
            ret = Dispatch(ret, 'GetPublicFolder', None, UnicodeToString=0)
        return ret

    def GetPublicFolderName(self):
        return self._ApplyTypes_(36, 1, (12, 0), (), 'GetPublicFolderName', None,)

    def GetQueryDbIdList(self, QuerySelector=defaultNamedNotOptArg):
        return self._ApplyTypes_(58, 1, (12, 0), ((2, 0),), 'GetQueryDbIdList', None,QuerySelector
            )

    @returns(QueryDef, Name=1)
    def GetQueryDef(self, Name=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(3, LCID, 1, (9, 0), ((8, 0),),Name
            )
        if ret is not None:
            ret = Dispatch(ret, 'GetQueryDef', None, UnicodeToString=0)
        return ret

    @returns(QueryDef, dbid=1)
    def GetQueryDefByDbId(self, dbid=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(46, LCID, 1, (9, 0), ((3, 0),),dbid
            )
        if ret is not None:
            ret = Dispatch(ret, 'GetQueryDefByDbId', None, UnicodeToString=0)
        return ret

    def GetQueryList(self, QuerySelector=defaultNamedNotOptArg):
        return self._ApplyTypes_(2, 1, (12, 0), ((2, 0),), 'GetQueryList', None,QuerySelector
            )

    def GetReportDbIdList(self, ReportSelector=defaultNamedNotOptArg):
        return self._ApplyTypes_(60, 1, (12, 0), ((2, 0),), 'GetReportDbIdList', None,ReportSelector
            )

    @returns(ReportDef, Name=1)
    def GetReportDef(self, ReportDefPathName=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(27, LCID, 1, (9, 0), ((8, 0),),ReportDefPathName
            )
        if ret is not None:
            ret = Dispatch(ret, 'GetReportDef', None, UnicodeToString=0)
        return ret

    @returns(ReportDef, dbid=1)
    def GetReportDefByDbId(self, dbid=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(54, LCID, 1, (9, 0), ((3, 0),),dbid
            )
        if ret is not None:
            ret = Dispatch(ret, 'GetReportDefByDbId', None, UnicodeToString=0)
        return ret

    def GetReportFormatDbIdList(self):
        return self._ApplyTypes_(61, 1, (12, 0), (), 'GetReportFormatDbIdList', None,)

    def GetReportFormatList(self):
        return self._ApplyTypes_(24, 1, (12, 0), (), 'GetReportFormatList', None,)

    def GetReportFormatQueryDbIdList(self, entdef_name=defaultNamedNotOptArg):
        return self._ApplyTypes_(53, 1, (12, 0), ((8, 0),), 'GetReportFormatQueryDbIdList', None,entdef_name
            )

    def GetReportFormatQueryList(self):
        return self._ApplyTypes_(25, 1, (12, 0), (), 'GetReportFormatQueryList', None,)

    def GetReportList(self, ReportSelector=defaultNamedNotOptArg):
        return self._ApplyTypes_(8, 1, (12, 0), ((2, 0),), 'GetReportList', None,ReportSelector
            )

    @returns(ReportMgr)
    def GetReportMgr(self, Name=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(9, LCID, 1, (9, 0), ((8, 0),),Name
            )
        if ret is not None:
            ret = Dispatch(ret, 'GetReportMgr', None, UnicodeToString=0)
        return ret

    @returns(ReportMgr8)
    def GetReportMgr8(self, Name=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(63, LCID, 1, (9, 0), ((8, 0),),Name
            )
        if ret is not None:
            ret = Dispatch(ret, 'GetReportMgr8', None, UnicodeToString=0)
        return ret

    @returns(ReportMgr)
    def GetReportMgrByReportDbId(self, report_dbid=defaultNamedNotOptArg):
        ret = self._oleobj_.InvokeTypes(52, LCID, 1, (9, 0), ((3, 0),),report_dbid
            )
        if ret is not None:
            ret = Dispatch(ret, 'GetReportMgrByReportDbId', None, UnicodeToString=0)
        return ret

    def GetSiteExtendedNames(self, bucketPath=defaultNamedNotOptArg):
        return self._ApplyTypes_(34, 1, (12, 0), ((8, 0),), 'GetSiteExtendedNames', None,bucketPath
            )

    def GetStartUpQueries(self):
        return self._ApplyTypes_(20, 1, (12, 0), (), 'GetStartUpQueries', None,)

    def GetStartUpQueryType(self, QueryPathName=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(23, LCID, 1, (2, 0), ((8, 0),),QueryPathName
            )

    def GetUneditedQueries(self, QuerySelector=defaultNamedNotOptArg):
        return self._ApplyTypes_(65, 1, (12, 0), ((2, 0),), 'GetUneditedQueries', None,QuerySelector
            )

    def GetUserPreferenceBucket(self, key=defaultNamedNotOptArg, subKey=defaultNamedNotOptArg):
        return self._ApplyTypes_(15, 1, (12, 0), ((3, 0), (3, 0)), 'GetUserPreferenceBucket', None,key
            , subKey)

    def GetWorkspaceItemDbIdList(self, query_selector=defaultNamedNotOptArg, item_type=defaultNamedNotOptArg, parent_dbid=defaultNamedNotOptArg, entdef_name=defaultNamedNotOptArg):
        return self._ApplyTypes_(38, 1, (12, 0), ((3, 0), (3, 0), (3, 0), (8, 0)), 'GetWorkspaceItemDbIdList', None,query_selector
            , item_type, parent_dbid, entdef_name)

    def GetWorkspaceItemMasterReplicaName(self, dbid=defaultNamedNotOptArg):
        return self._ApplyTypes_(66, 1, (12, 0), ((3, 0),), 'GetWorkspaceItemMasterReplicaName', None,dbid
            )

    def GetWorkspaceItemName(self, dbid=defaultNamedNotOptArg, extended_option=defaultNamedNotOptArg):
        return self._ApplyTypes_(40, 1, (12, 0), ((3, 0), (3, 0)), 'GetWorkspaceItemName', None,dbid
            , extended_option)

    def GetWorkspaceItemParentDbId(self, dbid=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(62, LCID, 1, (3, 0), ((3, 0),),dbid
            )

    def GetWorkspaceItemPathName(self, dbid=defaultNamedNotOptArg, extended_option=defaultNamedNotOptArg):
        return self._ApplyTypes_(42, 1, (12, 0), ((3, 0), (3, 0)), 'GetWorkspaceItemPathName', None,dbid
            , extended_option)

    def GetWorkspaceItemSiteExtendedName(self, dbid=defaultNamedNotOptArg):
        return self._ApplyTypes_(41, 1, (12, 0), ((3, 0),), 'GetWorkspaceItemSiteExtendedName', None,dbid
            )

    def GetWorkspaceItemType(self, dbid=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(43, LCID, 1, (3, 0), ((3, 0),),dbid
            )

    def InsertNewChartDef(self, new_bare_name=defaultNamedNotOptArg, parent_dbid=defaultNamedNotOptArg, pOaqdef=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(50, LCID, 1, (3, 0), ((8, 0), (3, 0), (9, 0)),new_bare_name
            , parent_dbid, pOaqdef)

    def InsertNewQueryDef(self, newName=defaultNamedNotOptArg, parent_dbid=defaultNamedNotOptArg, pOaqdef=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(47, LCID, 1, (3, 0), ((8, 0), (3, 0), (9, 0)),newName
            , parent_dbid, pOaqdef)

    def InsertNewReportDef(self, newName=defaultNamedNotOptArg, parent_dbid=defaultNamedNotOptArg, pOareportDef=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(55, LCID, 1, (3, 0), ((8, 0), (3, 0), (9, 0)),newName
            , parent_dbid, pOareportDef)

    def NormalizeDateTimeString(self, DTStr=defaultNamedNotOptArg):
        return self._ApplyTypes_(10, 1, (12, 0), ((8, 0),), 'NormalizeDateTimeString', None,DTStr
            )

    def Refresh(self):
        return self._oleobj_.InvokeTypes(73, LCID, 1, (24, 0), (),)

    def RemoveStartUpQuery(self, QueryPathName=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(22, LCID, 1, (24, 0), ((8, 0),),QueryPathName
            )

    def RenameQueryDef(self, oldName=defaultNamedNotOptArg, newName=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(18, LCID, 1, (11, 0), ((8, 0), (8, 0)),oldName
            , newName)

    def RenameReportDef(self, oldName=defaultNamedNotOptArg, newName=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(30, LCID, 1, (11, 0), ((8, 0), (8, 0)),oldName
            , newName)

    def RenameWorkspaceItem(self, oldPath=defaultNamedNotOptArg, newName=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(35, LCID, 1, (11, 0), ((8, 0), (8, 0)),oldPath
            , newName)

    def RenameWorkspaceItemByDbId(self, dbid=defaultNamedNotOptArg, newName=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(44, LCID, 1, (11, 0), ((3, 0), (8, 0)),dbid
            , newName)

    def SaveQueryDef(self, qdefName=defaultNamedNotOptArg, qdefPath=defaultNamedNotOptArg, pOaqdef=defaultNamedNotOptArg, overwrite=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(13, LCID, 1, (24, 0), ((8, 0), (8, 0), (9, 0), (11, 0)),qdefName
            , qdefPath, pOaqdef, overwrite)

    def SaveQueryDef2(self, qdefName=defaultNamedNotOptArg, qdefPath=defaultNamedNotOptArg, pOaqdef=defaultNamedNotOptArg, overwrite=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(32, LCID, 1, (24, 0), ((8, 0), (8, 0), (9, 0), (11, 0)),qdefName
            , qdefPath, pOaqdef, overwrite)

    def SaveReportDef(self, rdefName=defaultNamedNotOptArg, rdefPath=defaultNamedNotOptArg, pOardef=defaultNamedNotOptArg, overwrite=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(28, LCID, 1, (24, 0), ((8, 0), (8, 0), (9, 0), (11, 0)),rdefName
            , rdefPath, pOardef, overwrite)

    def SetDateTimeFmtString(self, DTFmtStr=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(11, LCID, 1, (24, 0), ((8, 0),),DTFmtStr
            )

    def SetSession(self, SessionPtr=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(1, LCID, 1, (11, 0), ((9, 0),),SessionPtr
            )

    def SetUserName(self, username=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(4, LCID, 1, (24, 0), ((8, 0),),username
            )

    def SetUserPreferenceBucket(self, key=defaultNamedNotOptArg, subKey=defaultNamedNotOptArg, data=defaultNamedNotOptArg):
        return self._ApplyTypes_(16, 1, (12, 0), ((3, 0), (3, 0), (8, 0)), 'SetUserPreferenceBucket', None,key
            , subKey, data)

    def SetWorkspaceItemMasterReplica(self, replicaName=defaultNamedNotOptArg, dbid=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(67, LCID, 1, (24, 0), ((8, 0), (3, 0)),replicaName
            , dbid)

    def SiteExtendedNameRequired(self, dbid=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(39, LCID, 1, (11, 0), ((3, 0),),dbid
            )

    def SiteHasMastership(self, bucketPath=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(33, LCID, 1, (11, 0), ((8, 0),),bucketPath
            )

    def UpdateChartDef(self, dbid=defaultNamedNotOptArg, pOaqdef=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(51, LCID, 1, (24, 0), ((3, 0), (9, 0)),dbid
            , pOaqdef)

    def UpdateQueryDef(self, dbid=defaultNamedNotOptArg, pOaqdef=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(48, LCID, 1, (24, 0), ((3, 0), (9, 0)),dbid
            , pOaqdef)

    def UpdateReportDef(self, dbid=defaultNamedNotOptArg, pOareportDef=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(56, LCID, 1, (24, 0), ((3, 0), (9, 0)),dbid
            , pOareportDef)

    def ValidateQueryDefName(self, qdefName=defaultNamedNotOptArg, qdefPath=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(12, LCID, 1, (24, 0), ((8, 0), (8, 0)),qdefName
            , qdefPath)

    def ValidateReportDefName(self, rdefName=defaultNamedNotOptArg, rdefPath=defaultNamedNotOptArg):
        return self._oleobj_.InvokeTypes(29, LCID, 1, (24, 0), ((8, 0), (8, 0)),rdefName
            , rdefPath)

    _prop_map_get_ = {
        "IsRefreshOnGet": (19, 2, (11, 0), (), "IsRefreshOnGet", None),
    }
    _prop_map_put_ = {
        "IsRefreshOnGet" : ((19, LCID, 4, 0),()),
    }

RecordMap = {
}

CLSIDToClassMap = {
    '{24A57421-3F6C-11D1-B2C0-00A0C9851B52}' : FilterNode,
    '{A39B63C9-9798-401C-BD7B-7BBBF26485CF}' : Permission,
    '{754F0160-B0EF-11D0-A475-00A024DED613}' : Field,
    '{24A57433-3F6C-11D1-B2C0-00A0C9851B52}' : QueryFieldDefs,
    '{24A57442-3F6C-11D1-B2C0-00A0C9851B52}' : QueryDefs,
    '{5ED34A11-D4B3-11D1-B37D-00A0C9851B52}' : EventObject,
    '{14BE7431-785A-11D0-A431-00A024DED613}' : QueryDef,
    '{14BE7434-785A-11D0-A431-00A024DED613}' : ResultSet,
    '{14BE7437-785A-11D0-A431-00A024DED613}' : QueryFieldDef,
    '{D267C190-245F-11D1-A4ED-00A0C9243B7B}' : DatabaseDesc,
    '{754F0160-B0EF-11D0-A475-10A024DED613}' : FieldHookEvents,
    '{E9F82951-73A9-11D0-A42E-10A024DED613}' : EntityActionHookEvents,
    '{62975AFC-FD86-4E7A-A256-2D366AF15D54}' : Permissions,
    '{94773111-72E8-11D0-A42E-00A024DED613}' : Session,
    '{E79F83D3-D096-11D1-B37A-00A0C9851B52}' : Schema,
    '{E79F83D6-D096-11D1-B37A-00A0C9851B52}' : Schemas,
    '{E79F83D9-D096-11D1-B37A-00A0C9851B52}' : SchemaRev,
    '{E79F83DC-D096-11D1-B37A-00A0C9851B52}' : SchemaRevs,
    '{CE573C21-3B54-11D1-B2BF-00A0C9851B52}' : AttachmentFields,
    '{CE573C23-3B54-11D1-B2BF-00A0C9851B52}' : AttachmentField,
    '{CE573C25-3B54-11D1-B2BF-00A0C9851B52}' : Attachments,
    '{CE573C27-3B54-11D1-B2BF-00A0C9851B52}' : Attachment,
    '{04A2C910-C552-11D0-A47F-00A024DED613}' : EntityDef,
    '{B9F132E4-96A9-11D2-B40F-00A0C9851B52}' : Item,
    '{B9F132E9-96A9-11D2-B40F-00A0C9851B52}' : Items,
    '{B9F132EB-96A9-11D2-B40F-00A0C9851B52}' : EntityDefs,
    '{B9F132ED-96A9-11D2-B40F-00A0C9851B52}' : PackageRevs,
    '{B9F132EF-96A9-11D2-B40F-00A0C9851B52}' : PackageRev,
    '{B48005E4-CF24-11D1-B37A-00A0C9851B52}' : User,
    '{C5330130-ECA3-11D0-82B3-00A0C911F0B7}' : Workspace,
    '{1F632611-D0B1-11D1-B37A-00A0C9851B52}' : Databases,
    '{3ACE8EF3-52FB-11D1-8C59-00A0C92337E5}' : ReportMgr,
    '{4C183050-FF8F-11D0-A051-00A0C9233DE1}' : ChartMgr,
    '{950B1875-3E96-481B-8C26-84E0B4CB54A7}' : Folders,
    '{CE573C89-3B54-11D1-B2BF-00A0C9851B52}' : HistoryField,
    '{FC4DA50E-50B2-4E50-A779-D2F57EA3CC5D}' : ReportMgr8,
    '{CE573C98-3B54-11D1-B2BF-00A0C9851B52}' : Histories,
    '{9EC2BB70-1892-11D1-A4E4-00A0C9243B7B}' : Link,
    '{CE573CA7-3B54-11D1-B2BF-00A0C9851B52}' : History,
    '{3ACE8EF0-52FB-11D1-8C59-00A0C92337E5}' : ReportMgr,
    '{B48005E7-CF24-11D1-B37A-00A0C9851B52}' : Users,
    '{B48005EA-CF24-11D1-B37A-00A0C9851B52}' : Group,
    '{60A7B420-B5A3-11D0-A477-00A024DED613}' : HookChoices,
    '{B48005ED-CF24-11D1-B37A-00A0C9851B52}' : Groups,
    '{21E00E8C-3996-11D1-A4F4-00A0C9243B7B}' : FieldInfo,
    '{B48005F0-CF24-11D1-B37A-00A0C9851B52}' : Database,
    '{B48005F5-CF24-11D1-B37A-00A0C9851B52}' : AdminSession,
    '{CE573C7A-3B54-11D1-B2BF-00A0C9851B52}' : HistoryFields,
    '{E9F82951-73A9-11D0-A42E-00A024DED613}' : Entity,
    '{7C2FB010-4D54-11D4-B501-0004AC96D6BA}' : ReportDef,
    '{3A8CCF40-4F1B-11D1-B2DD-00A0C9851B52}' : QueryFilterNode,
    '{98720365-0491-4910-82A5-93266CFC84B2}' : Folder,
    '{24A57401-3F6C-11D1-B2C0-00A0C9851B52}' : FieldFilter,
    '{24A57412-3F6C-11D1-B2C0-00A0C9851B52}' : FieldFilters,
}
CLSIDToPackageMap = {}
win32com.client.CLSIDToClass.RegisterCLSIDsFromDict( CLSIDToClassMap )
VTablesToPackageMap = {}
VTablesToClassMap = {
}


NamesToIIDMap = {
    'Workspace' : '{C5330130-ECA3-11D0-82B3-00A0C911F0B7}',
    'QueryFilterNode' : '{3A8CCF40-4F1B-11D1-B2DD-00A0C9851B52}',
    'Schema' : '{E79F83D3-D096-11D1-B37A-00A0C9851B52}',
    'ReportMgr' : '{3ACE8EF0-52FB-11D1-8C59-00A0C92337E5}',
    'Link' : '{9EC2BB70-1892-11D1-A4E4-00A0C9243B7B}',
    'EventObject' : '{5ED34A11-D4B3-11D1-B37D-00A0C9851B52}',
    'SchemaRevs' : '{E79F83DC-D096-11D1-B37A-00A0C9851B52}',
    'HookChoices' : '{60A7B420-B5A3-11D0-A477-00A024DED613}',
    'History' : '{CE573CA7-3B54-11D1-B2BF-00A0C9851B52}',
    'Entity' : '{E9F82951-73A9-11D0-A42E-00A024DED613}',
    'FilterNode' : '{24A57421-3F6C-11D1-B2C0-00A0C9851B52}',
    'Items' : '{B9F132E9-96A9-11D2-B40F-00A0C9851B52}',
    'QueryFieldDefs' : '{24A57433-3F6C-11D1-B2C0-00A0C9851B52}',
    'EntityDef' : '{04A2C910-C552-11D0-A47F-00A024DED613}',
    'SchemaRev' : '{E79F83D9-D096-11D1-B37A-00A0C9851B52}',
    'QueryDefs' : '{24A57442-3F6C-11D1-B2C0-00A0C9851B52}',
    'PackageRev' : '{B9F132EF-96A9-11D2-B40F-00A0C9851B52}',
    'Folder' : '{98720365-0491-4910-82A5-93266CFC84B2}',
    'Groups' : '{B48005ED-CF24-11D1-B37A-00A0C9851B52}',
    'ResultSet' : '{14BE7434-785A-11D0-A431-00A024DED613}',
    'AttachmentFields' : '{CE573C21-3B54-11D1-B2BF-00A0C9851B52}',
    'QueryFieldDef' : '{14BE7437-785A-11D0-A431-00A024DED613}',
    'Attachment' : '{CE573C27-3B54-11D1-B2BF-00A0C9851B52}',
    'Permission' : '{A39B63C9-9798-401C-BD7B-7BBBF26485CF}',
    'FieldFilter' : '{24A57401-3F6C-11D1-B2C0-00A0C9851B52}',
    'Histories' : '{CE573C98-3B54-11D1-B2BF-00A0C9851B52}',
    'QueryDef' : '{14BE7431-785A-11D0-A431-00A024DED613}',
    'EntityActionHookEvents' : '{E9F82951-73A9-11D0-A42E-10A024DED613}',
    'Group' : '{B48005EA-CF24-11D1-B37A-00A0C9851B52}',
    'HistoryField' : '{CE573C89-3B54-11D1-B2BF-00A0C9851B52}',
    'FieldFilters' : '{24A57412-3F6C-11D1-B2C0-00A0C9851B52}',
    'FieldInfo' : '{21E00E8C-3996-11D1-A4F4-00A0C9243B7B}',
    'Folders' : '{950B1875-3E96-481B-8C26-84E0B4CB54A7}',
    'Schemas' : '{E79F83D6-D096-11D1-B37A-00A0C9851B52}',
    'FieldHookEvents' : '{754F0160-B0EF-11D0-A475-10A024DED613}',
    'ChartMgr' : '{4C183050-FF8F-11D0-A051-00A0C9233DE1}',
    'DatabaseDesc' : '{D267C190-245F-11D1-A4ED-00A0C9243B7B}',
    'Field' : '{754F0160-B0EF-11D0-A475-00A024DED613}',
    'User' : '{B48005E4-CF24-11D1-B37A-00A0C9851B52}',
    'ReportMgr8' : '{FC4DA50E-50B2-4E50-A779-D2F57EA3CC5D}',
    'ReportDef' : '{7C2FB010-4D54-11D4-B501-0004AC96D6BA}',
    'Attachments' : '{CE573C25-3B54-11D1-B2BF-00A0C9851B52}',
    'Database' : '{B48005F0-CF24-11D1-B37A-00A0C9851B52}',
    'Session' : '{94773111-72E8-11D0-A42E-00A024DED613}',
    'AttachmentField' : '{CE573C23-3B54-11D1-B2BF-00A0C9851B52}',
    'Permissions' : '{62975AFC-FD86-4E7A-A256-2D366AF15D54}',
    'Users' : '{B48005E7-CF24-11D1-B37A-00A0C9851B52}',
    'AdminSession' : '{B48005F5-CF24-11D1-B37A-00A0C9851B52}',
    'EntityDefs' : '{B9F132EB-96A9-11D2-B40F-00A0C9851B52}',
    'PackageRevs' : '{B9F132ED-96A9-11D2-B40F-00A0C9851B52}',
    'Databases' : '{1F632611-D0B1-11D1-B37A-00A0C9851B52}',
    'Item' : '{B9F132E4-96A9-11D2-B40F-00A0C9851B52}',
    'HistoryFields' : '{CE573C7A-3B54-11D1-B2BF-00A0C9851B52}',
}

SessionClassTypeMap = {
    SessionClassType.User  : Session,
    SessionClassType.Admin : AdminSession,
}

SessionClassTypeLogonMethod = {
    SessionClassType.User  : Session.UserLogon,
    SessionClassType.Admin : AdminSession.Logon,
}


class constants:
    OLEWKSPC_E_CANTCREATEREPORTMGR=0x2f6      # from enum OLEWKSPCERROR
    OLEWKSPC_E_CANTCREATESESSION  =0x2e6      # from enum OLEWKSPCERROR
    OLEWKSPC_E_CANTCREATEWORKSPACE=0x2e7      # from enum OLEWKSPCERROR
    OLEWKSPC_E_CHARTDEFBUCKETGETCHARTDEFFAILURE=0x2f3      # from enum OLEWKSPCERROR
    OLEWKSPC_E_CHARTDEFGETBUCKETFAILURE=0x2f2      # from enum OLEWKSPCERROR
    OLEWKSPC_E_CHARTDEFNOTFOUND   =0x2f0      # from enum OLEWKSPCERROR
    OLEWKSPC_E_CHARTLISTFAILURE   =0x2ee      # from enum OLEWKSPCERROR
    OLEWKSPC_E_CHARTLISTSAFEARRAYFAILURE=0x2ef      # from enum OLEWKSPCERROR
    OLEWKSPC_E_GETCHARTDEFFAILURE =0x2f1      # from enum OLEWKSPCERROR
    OLEWKSPC_E_GETQUERYDEFFAILURE =0x2eb      # from enum OLEWKSPCERROR
    OLEWKSPC_E_GETREPORTMGRFAILURE=0x2f8      # from enum OLEWKSPCERROR
    OLEWKSPC_E_INVALIDQUERYNAME   =0x30a      # from enum OLEWKSPCERROR
    OLEWKSPC_E_NORMALIZEDATETIME_EXCEPTION_FAIL=0x308      # from enum OLEWKSPCERROR
    OLEWKSPC_E_NORMALIZEDATETIME_FAIL=0x304      # from enum OLEWKSPCERROR
    OLEWKSPC_E_NORMALIZEDATETIME_FORMAT_FAIL=0x307      # from enum OLEWKSPCERROR
    OLEWKSPC_E_NORMALIZEDATETIME_NULL_INPUT_FAIL=0x305      # from enum OLEWKSPCERROR
    OLEWKSPC_E_NORMALIZEDATETIME_PARSE_FAIL=0x306      # from enum OLEWKSPCERROR
    OLEWKSPC_E_NOSESSIONSET       =0x2e4      # from enum OLEWKSPCERROR
    OLEWKSPC_E_QUERYDEFBUCKETGETQUERYDEFFAILURE=0x2ed      # from enum OLEWKSPCERROR
    OLEWKSPC_E_QUERYDEFGETBUCKETFAILURE=0x2ec      # from enum OLEWKSPCERROR
    OLEWKSPC_E_QUERYDEFNOTFOUND   =0x2ea      # from enum OLEWKSPCERROR
    OLEWKSPC_E_QUERYDEFSAVEBUCKETFAILURE=0x30b      # from enum OLEWKSPCERROR
    OLEWKSPC_E_QUERYLISTFAILURE   =0x2e8      # from enum OLEWKSPCERROR
    OLEWKSPC_E_QUERYLISTSAFEARRAYFAILURE=0x2e9      # from enum OLEWKSPCERROR
    OLEWKSPC_E_QUERYNAMEEXISTS    =0x309      # from enum OLEWKSPCERROR
    OLEWKSPC_E_REPORTLISTFAILURE  =0x2f4      # from enum OLEWKSPCERROR
    OLEWKSPC_E_REPORTLISTSAFEARRAYFAILURE=0x2f5      # from enum OLEWKSPCERROR
    OLEWKSPC_E_REPORTMGRBUCKETGETREPORTFAILURE=0x2fa      # from enum OLEWKSPCERROR
    OLEWKSPC_E_REPORTMGRGETBUCKETFAILURE=0x2f9      # from enum OLEWKSPCERROR
    OLEWKSPC_E_REPORTMGRNOTFOUND  =0x2f7      # from enum OLEWKSPCERROR
    OLEWKSPC_E_REPORTMGR_EXEC_ATTACH_RS_FAILURE=0x300      # from enum OLEWKSPCERROR
    OLEWKSPC_E_REPORTMGR_EXEC_CADORS_CREATE_FAILURE=0x2ff      # from enum OLEWKSPCERROR
    OLEWKSPC_E_REPORTMGR_EXEC_CAUGHT_EXCEPTION_FAILURE=0x303      # from enum OLEWKSPCERROR
    OLEWKSPC_E_REPORTMGR_EXEC_CHECK_FILEPATH_FAILURE=0x301      # from enum OLEWKSPCERROR
    OLEWKSPC_E_REPORTMGR_EXEC_EMPTYHTMLFILENAME=0x2fb      # from enum OLEWKSPCERROR
    OLEWKSPC_E_REPORTMGR_EXEC_ENGINE_FAILURE=0x302      # from enum OLEWKSPCERROR
    OLEWKSPC_E_REPORTMGR_EXEC_RPTENGINEINUSE=0x2fc      # from enum OLEWKSPCERROR
    OLEWKSPC_E_REPORTMGR_EXEC_RPT_ENGINE_SET_REPORT=0x2fe      # from enum OLEWKSPCERROR
    OLEWKSPC_E_REPORTMGR_EXEC_RPT_EXTRACT_FAILURE=0x2fd      # from enum OLEWKSPCERROR
    OLEWKSPC_E_SESSIONALREADYSET  =0x2e5      # from enum OLEWKSPCERROR
    OLEWKSPCBOTHQUERIES           =0x3        # from enum OLEWKSPCQUERYTYPE
    OLEWKSPCQUERIESNONE           =0x0        # from enum OLEWKSPCQUERYTYPE
    OLEWKSPCSYSTEMQUERIES         =0x1        # from enum OLEWKSPCQUERYTYPE
    OLEWKSPCUSERQUERIES           =0x2        # from enum OLEWKSPCQUERYTYPE
    OLEWKSPCBOTHREPORTS           =0x3        # from enum OLEWKSPCREPORTTYPE
    OLEWKSPCREPORTSNONE           =0x0        # from enum OLEWKSPCREPORTTYPE
    OLEWKSPCSYSTEMREPORTS         =0x1        # from enum OLEWKSPCREPORTTYPE
    OLEWKSPCUSERREPORTS           =0x2        # from enum OLEWKSPCREPORTTYPE

win32com.client.constants.__dicts__.append(constants.__dict__)
