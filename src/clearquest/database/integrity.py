"""
clearquest.database.integrity: various methods that can be used to check the
integrity of ClearQuest databases.
"""
#===============================================================================
# Imports
#===============================================================================

import os
import sys
import itertools

from itertools import chain, repeat

from clearquest.db import Connection
from clearquest.api import EntityDef, Session
from clearquest.util import renderTextTable
from clearquest.callback import Callback, ConsoleCallback
from clearquest.constants import CQConstant, FieldType, EntityType

#===============================================================================
# Globals
#===============================================================================
__rcsid__ = '$Id$'
__rcsurl__ = '$URL$'
__copyright__ = 'Copyright 2008 OnResolve Ltd'

#===============================================================================
# Constants
#===============================================================================
class _IntegrityScope(CQConstant):
    Fix    = 1
    Check  = 2
IntegrityScope = _IntegrityScope()

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

def __processEntity(session, entityDefName):
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

class DatabaseIntegrity(object):
    def __init__(self, session, scope, output=sys.stdout):
        self.session = session
        self.scope = scope
        self.output = output
        self.valid = False
        self.db = Connection(session)
        self.tablePrefix = session.getTablePrefix()
        
        self._processEntities()
        
    def _processEntities(self):
        
        self.entities = dict()
        
        tablePrefix = self.session.getTablePrefix()
        select = 'SELECT %(select)s FROM %(from)s WHERE %(where)s'
        update = 'UPDATE %(from)s SET %(update)s WHERE %(where)s'
        wheres = [
            '%(fieldDbName)s IS NULL',
            '%(fieldDbName)s NOT IN ' \
            '(SELECT DISTINCT dbid FROM %(tablePrefix)s.%(refEntityDefDbName)s)'
        ]
        
        valid = True
        
        for entityDef in self.session.getAllEntityDefs():
            entityDefName = entityDef.GetName()
            
            if entityDefName in ('history', 'ratl_replicas'):
                continue
            
            entityDefDbName = entityDef.GetDbName()
            entityDefTable = '%s.%s' % (self.tablePrefix, entityDefDbName)
            uniqueKey = entityDef.getUniqueKey()
            ourInfo = uniqueKey._info()
            
            for fieldName in entityDef.GetFieldDefNames():
                fieldType = entityDef.GetFieldDefType(fieldName)
                fieldDbName = entityDef.getFieldDbName(fieldName)
                
                if fieldType != FieldType.Reference:
                    continue
                
                refEntityDef = entityDef.GetFieldReferenceEntityDef(fieldName)
                refEntityDefDbName = refEntityDef.GetDbName() 
                refUniqueKey = refEntityDef.getUniqueKey()
                refInfo = refUniqueKey._info()
                
                nullSql = select % {
                    'select': 'COUNT(*)',
                    'from'  : entityDefTable,
                    'where' : wheres[0] % locals()
                }
                invalidSql = select % {
                    'select': 'COUNT(*)',
                    'from'  : entityDefTable,
                    'where' : wheres[1] % locals()
                }
                nullCount = self.db.selectSingle(nullSql)
                invalidCount = self.db.selectSingle(invalidSql)
                
                assert nullCount >= 0 and invalidCount >= 0
                
                if nullCount > 0 or invalidCount > 0:
                    results = {
                        'null'    : nullCount,
                        'invalid' : invalidCount,
                    }
                    # Note that we delay entering anything into the entities map
                    # until we reach this point, when we can be certain we've
                    # found a discrepancy.
                    self.entities.setdefault(entityDefName, dict()) \
                                 .setdefault(fieldName, dict())     \
                                 .update(results)
                
                    if self.scope == IntegrityScope.Fix:
                        where = [ w % locals() for w in wheres ]
                        k = {
                            'from'   : entityDefTable,
                            'update' : '%s = 0' % fieldDbName,
                            'where'  : ' OR '.join(where)
                        }
                        sql = update % k
                        self.db.execute(sql)
                    else:
                        valid = False
                        
        self.valid = valid
        if self.entities:
            
            fixed = 'Yes' if self.scope == IntegrityScope.Fix else 'No'
            
            header = ('Entity', 'Field', 'Null', 'Invalid', 'Fixed?')
            cols = len(header)
            rows = [ 
                header,
                ('',) * cols,
            ]
            
            for (entity, fields) in self.entities.items():
                count = itertools.count(0)
                for (field, r) in fields.items():
                    # Only print out the entity name for the first row.
                    name = '' if count.next() else entity
                    rows.append((name, field, r['null'], r['invalid'], fixed))
                    
            header = (
                '[%s Database]' % self.session._databaseName,
                'Entity Integrity Report'
            )
            renderTextTable(header, rows, output=self.output)
            
    def _processHistory(self):
        pass
    
    def _processUsersAndGroups(self):
        pass
    
    def _processParentChildLinks(self):
        pass
    
        
def checkDatabase(session, output=sys.stdout):
    return DatabaseIntegrity(session, IntegrityScope.Check, output=output)

def fixDatabase(session, output=sys.stdout):
    return DatabaseIntegrity(session, IntegrityScope.Fix, output=output)

    