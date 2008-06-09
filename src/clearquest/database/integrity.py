"""
clearquest.database.integrity: various methods that can be used to check the
integrity of ClearQuest databases.
"""
#===============================================================================
# Imports
#===============================================================================

import os
import sys

from clearquest.api import EntityDef, Session
from clearquest.callback import Callback, ConsoleCallback
from clearquest.constants import FieldType

#===============================================================================
# Globals
#===============================================================================
__rcsid__ = '$Id$'
__rcsurl__ = '$URL$'
__copyright__ = 'Copyright 2008 OnResolve Ltd'

#===============================================================================
# Methods
#===============================================================================

def _checkUsersOrGroups(session, entityDefName):
    assert entityDefName in ('users', 'groups')

def _checkHistory(session, entityDefName):
    assert entityDefName == 'history'

def _checkRatlReplicas(session, entityDefName):
    assert entityDefName == 'ratl_replicas'
    
def _checkParentChildLinks(session):
    pass

def _checkEntity(session, entityDefName):
    """
    Checks that every dbid value is valid.
    """
    if entityDefName in ('history', 'users', 'groups', 'ratl_replicas'):
        raise ValueError("unsupported entity: %s" % entityDefName)
    
    tablePrefix = session.getTablePrefix()
    entityDef = session.GetEntityDef(entityDefName)
    entityDefDbName = entityDef.GetDbName()
    uniqueKey = entityDef.getUniqueKey()
    ourInfo = uniqueKey._info()
    stmt = 'SELECT DISTINCT\n'  \
           '    %(select)s\n'   \
           'FROM\n'             \
           '    %(from)s\n'     \
           'WHERE\n'            \
           '    %(where)s'
    
    where = [
        't1.%(fieldDbName)s IS NULL',
        't1.%(fieldDbName)s NOT IN\n   ' \
        '    (SELECT DISTINCT dbid FROM %(tablePrefix)s.%(refEntityDefDbName)s)'
    ]
    
    for fieldName in entityDef.GetFieldDefNames():
        fieldType = entityDef.GetFieldDefType(fieldName)
        fieldDbName = entityDef.getFieldDbName(fieldName)
        
        if fieldType != FieldType.Reference:
            continue
        
        refEntityDef = entityDef.GetFieldReferenceEntityDef(fieldName)
        refEntityDefDbName = refEntityDef.GetDbName() 
        refUniqueKey = refEntityDef.getUniqueKey()
        refInfo = refUniqueKey._info()
                
        select = list()
        select = [
            ("'%s'" % entityDefName, 'entity_name'),
            ('t1.dbid', 'dbid'),
            ("'%s'" % fieldName, 'field_name'),
            ('t1.%s' % fieldDbName, 'invalid_value')
        ]
        
        yield stmt % {
            'select' : ',\n    '.join([ '%s "%s"' % s for s in select]),
            'from'   : '%s.%s t1' % (tablePrefix, entityDefDbName),
            'where'  : ' OR\n    '.join([ w % locals() for w in where ])
        }
        
__entityDefNameToIntegrityCheckMethod = {
    'history'       : _checkHistory,
    'ratl_replicas' : _checkRatlReplicas,
    'users'         : _checkUsersOrGroups,
    'groups'        : _checkUsersOrGroups,
}

def checkEntity(session, entityDefName):
    
    from twisted.internet import threads, defer, reactor
    
    
    
    
    pass
 