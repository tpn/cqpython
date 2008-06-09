"""
clearquest.merge: module for merging ClearQuest databases
"""

#===============================================================================
# Imports
#===============================================================================

import os
import sys
import time
import itertools
from itertools import chain, repeat
import cStringIO as StringIO

from pywintypes import com_error
from pprint import pprint
from subprocess import Popen, PIPE

from clearquest import api, db
from clearquest.task import Task, TaskManagerConfig, MultiSessionTaskManager
from clearquest.util import connectStringToMap, joinPath, listToMap, unzip
from clearquest.tools import exportQueries, updateQueries
from clearquest.constants import EntityType, FieldType, SessionClassType

#===============================================================================
# Globals
#===============================================================================
__rcsid__ = '$Id$'
__rcsurl__ = '$URL$'
__copyright__ = 'Copyright 2008 OnResolve Ltd'

__mergeDbField   = 'merge_orig_db'
__mergeIdField   = 'merge_orig_id'
__mergeDbIdField = 'merge_orig_dbid'

__statelessDbIdMapTableName = 'merge_aux_map'
__statelessDbIdMapMaxUniqueKeyLength = 250

__userBucketMapTableName = 'merge_bucket_usage'

__useClusteredIndexes = False

__defaultFillFactor = 85

Stateful  = api.EntityType.Stateful
Stateless = api.EntityType.Stateless
SQLServer = api.DatabaseVendor.SQLServer
Oracle    = api.DatabaseVendor.Oracle

#===============================================================================
# Decorators
#===============================================================================

#===============================================================================
# Source-code Completion Helpers
#===============================================================================
if 0:
    entityDef = session = destSession = sourceSession = None
    assert isinstance(entityDef, api.EntityDef)
    assert isinstance(session, api.Session)
    assert isinstance(destSession, api.Session)
    assert isinstance(sourceSession, api.Session)

#===============================================================================
# Helper Methods
#===============================================================================
    
def findSql(name, *args, **kwds):
    try:
        session = kwds['session']
        del kwds['session']
    except:
        try:
            session = sys._getframe().f_back.f_locals['session']
        except:
            session = sys._getframe().f_back.f_locals['destSession']
    sql = db._findSql(session, 'merge', name, *args, **kwds)
    if sql.endswith('\n'):
        return sql[:-1]
    else:
        return sql

def _innerJoin(*args):
    return __getJoinSql('INNER JOIN', args)

def _rightOuterJoin(*args):
    return __getJoinSql('RIGHT OUTER JOIN', args)
        
def __getJoinSql(joinType, targets, indent=0):
    _indent = lambda i: ' ' * (4 * (indent+i))
    for (table, predicate) in targets:
        yield '%s%s\n%s%s ON\n%s%s' % (
            _indent(0),
            joinType,
            _indent(1),
            table,
            _indent(2),
            predicate
        )

def _getStatelessMapKwds(dbidOffsets, destSession, *args):
    
    return {
        'dbidOffsets' : dbidOffsets,
        'statelessDbIdMapMaxUniqueKeyLength' : \
            __statelessDbIdMapMaxUniqueKeyLength,
        'statelessDbIdMapTableName' : '%s.%s' % (   
            destSession.getTablePrefix(),
            __statelessDbIdMapTableName
        )
    }
def _getUserBucketMapKwds(dbidOffsets, destSession, *args):
    k = { 
        'shortName' : __userBucketMapTableName,
        'userBucketMapTableName' : '%s.%s' % (
            destSession.getTablePrefix(),
            __userBucketMapTableName,
        )
    }
    k.update(_getStatelessMapKwds(dbidOffsets, destSession))
    return k

def _getOffsetDecoder(session):
    vendor = session.getDatabaseVendor()
    if vendor == SQLServer:
        f = lambda c, o: \
            '(CASE WHEN %s = 0 THEN 0 ELSE %s + %d END)' % (c, c, o)
    elif vendor == Oracle:
        f = lambda c, o: \
          '({fn DECODE(%s, 0, 0, %s + %d)})' % (c, c, o)
    else:
        raise NotImplementedError
    return lambda c, o: f(c, o) if o != 0 else c

def _getIdUpdater(session):
    vendor = session.getDatabaseVendor()
    if vendor == SQLServer:
        return lambda n, d: \
                  "'%s' + REPLICATE(0,8-LEN(CAST((%s-33554432) AS VARCHAR)))+" \
                  "CAST((%s-33554432) AS VARCHAR)" % (n, d, d)
    else:
        raise NotImplementedError
    return f
@api.cache
def _getDbIdColumn(session):
    return '%s_dbid' % session._databaseName.lower()

@api.cache
def _chainedSessions(destSession, sourceSessions):
    if getMaxStatefulEntityDbIds((destSession,)).next() != 0:
        return chain((destSession,), sourceSessions)
    else:
        return sourceSessions
    
def _createStatelessDbIdMap(destSession, sourceSessions, dbidOffsets):
    
    args = destSession, sourceSessions
    k = dict(_getStatelessMapKwds(dbidOffsets, *args))
    
    sql = [ _createStatelessDbIdMapTable(*args, **k) ] + \
          [ i for i in _insertIntoStatelessDbIdMap(*args, **k) ] + \
          [ u for u in _updateStatelessDbIdMap(*args, **k) ] + \
          [ _createStatelessDbIdMapIndexes(*args, **k) ] 
    
    return '\nGO\n'.join(sql)
    
def _updateStatelessDbIdMap(destSession, sourceSessions, **kwds):
    args = (destSession, sourceSessions, findSql('updateStatelessDbIdMap'))
    return __constructStatelessDbIdSql(*args, **kwds)

def _insertIntoStatelessDbIdMap(destSession, sourceSessions, **kwds):
    args = (destSession, sourceSessions, findSql('insertIntoStatelessDbIdMap'))
    return __constructStatelessDbIdSql(*args, **kwds)
    
def _createStatelessDbIdMapTable(destSession, sourceSessions, **kwds):
    sessions = _chainedSessions(destSession, sourceSessions)
    k = {
        'replicaIds'     : [ api.Session.getReplicaId(s) for s in sessions ],
        'dstTablePrefix' : destSession.getTablePrefix(),
        'dboTablePrefix' : destSession.db().getDboTablePrefix(),
        'dbDbIdColumns'  : [ _getDbIdColumn(s) for s in sessions ],
    }
    k.update(kwds)
    k['shortName'] = k['statelessDbIdMapTableName'].split('.')[-1]
    return findSql('createStatelessDbIdMap', **k) % k

def _createStatelessDbIdMapIndexes(destSession, sourceSessions, **kwds):
    sessions = _chainedSessions(destSession, sourceSessions)
    k = { 'dbDbIdColumns' : [ _getDbIdColumn(s) for s in sessions ] }
    k.update(kwds)
    return findSql('createStatelessDbIdMapIndexes', **k) % k

    
def __constructStatelessDbIdSql(destSession, sourceSessions, sql, **kwds):
    
    defaultCollation = destSession.getCollation()
    SQLServer = api.DatabaseVendor.SQLServer
    sessions = _chainedSessions(destSession, sourceSessions)
    k = dict(kwds)
    dbidOffsets = iter(k['dbidOffsets'])
    
    for session in sessions:
        dbidOffset = dbidOffsets.next()
        vendor = session.getDatabaseVendor()
        collationCast = None
        if vendor == SQLServer and session.getCollation() != defaultCollation:
            collationCast = ' COLLATE %s' % defaultCollation
            
        dbName = session._databaseName
        k['dbName'] = dbName
        k['dbDbIdColumn'] = _getDbIdColumn(session)

        p = session.getTablePrefix()
        if session is not destSession:
            p = api.getLinkedServerAwareTablePrefix(session, (destSession,))
        
        for entityDef in session.getStatelessEntityDefs():
            if entityDef.name in ('attachments', 'history', 'ratl_replicas'):
                continue
            
            k['entityDefId'] = entityDef.id
            
            uniqueKey = entityDef.getUniqueKey()
            displayNameSql = uniqueKey._getDisplayNameSql()
            if uniqueKey.hasTextColumnsInKey() and collationCast:
                displayNameSql += collationCast
            k['uniqueKeyDisplayNameSql'] = \
                '{fn CONVERT((%s), SQL_VARCHAR)}' % displayNameSql
            
            if dbidOffset == 0:
                k['targetDbId'] = 't1.dbid'
            else:
                k['targetDbId'] = '(t1.dbid + %d)' % dbidOffset 
                
            info = uniqueKey._info()
            joins = [ '%s.%s' % (p, j[j.rfind('.')+1:]) for j in info['joins'] ]
            k['from'] = ', '.join(joins)
            
            k['where'] = 't1.dbid <> 0 AND '
            where = info['where']
            if where:
                k['where'] += ' AND '.join(where) + ' AND '
            
            yield sql % k
            
def _createUserBucketMap(destSession, sourceSessions, dbidOffsets):
    
    args = destSession, sourceSessions
    k = dict(_getUserBucketMapKwds(dbidOffsets, *args))
    
    sql = [ _createUserBucketMapTable(*args, **k) ] + \
          [ i for i in _insertIntoUserBucketMap(*args, **k) ] + \
          [ u for u in _updateUserBucketMap(*args, **k) ] + \
          [ _createUserBucketMapIndexes(*args, **k) ] 
    
    return '\nGO\n'.join(sql)
    
def _updateUserBucketMap(destSession, sourceSessions, **kwds):
    args = (destSession, sourceSessions, findSql('updateUserBucketMap'))
    return __constructUserBucketSql(*args, **kwds)

def _insertIntoUserBucketMap(destSession, sourceSessions, **kwds):
    args = (destSession, sourceSessions, findSql('insertIntoUserBucketMap'))
    return __constructUserBucketSql(*args, **kwds)
    
def _createUserBucketMapTable(destSession, sourceSessions, **kwds):
    sessions = _chainedSessions(destSession, sourceSessions)
    k = { 'dboTablePrefix' : destSession.db().getDboTablePrefix() }
    k.update(kwds)
    return findSql('createUserBucketMap') % k

def _createUserBucketMapIndexes(destSession, sourceSessions, **kwds):
    sessions = _chainedSessions(destSession, sourceSessions)
    return findSql('createUserBucketMapIndexes') % kwds
    
def __constructUserBucketSql(destSession, sourceSessions, sql, **kwds):
    
    sessions = _chainedSessions(destSession, sourceSessions)
    k = dict(kwds)
    k['dstPrefix'] = destSession.getTablePrefix()
    
    for session in sessions:
        p = session.getTablePrefix()
        if session is not destSession:
            p = api.getLinkedServerAwareTablePrefix(session, (destSession,))
        k['srcPrefix'] = p
        k['dbDbIdColumn'] = _getDbIdColumn(session)
            
        yield sql % k            
        
def _mergeEntity(destSession, sourceSession, entityDefName, dbidOffset):
    """
    Generates SQL necessary to merge all entities of type @param entityDefName
    from @param sourceSession into @param destSession.  For stateless entities,
    the generated SQL ensures each entity will only be brought over if there's
    no corresponding entity with the same unique ID present in the database.
    
    @param dbidOffset is an integer that is added to references.
    
    Note that the generated SQL only brings over fields that are actual columns
    on the underlying entity table.  i.e. attachments and parent/child links 
    aren't brought over by this method.
    """
    srcDbName = sourceSession._databaseName
    dstDbName = destSession._databaseName
    dstReplicaId = str(destSession.getReplicaId())
    entityDef = destSession.GetEntityDef(entityDefName)
    entityDbName = entityDef.db_name
    entityDefType = entityDef.GetType()
    uniqueKey = entityDef.getUniqueKey()
    requiresCollation = False
    destCollation = destSession.getCollation()
    sourceCollation = sourceSession.getCollation()
    if destCollation != sourceCollation:
        requiresCollation = bool(uniqueKey._info()['text'])
    
    # Fields of the following types can be copied over directly.  They require
    # no translation, unlike id/dbid fields.
    straightCopyFieldTypes = (
        FieldType.ShortString,
        FieldType.MultilineString,
        FieldType.Integer,
        FieldType.DateTime,
        FieldType.State,
    )
    
    args = (sourceSession, (destSession,))
    dstTablePrefix = destSession.getTablePrefix()
    srcTablePrefix = api.getLinkedServerAwareTablePrefix(*args)
    
    dbName = destSession._databaseName.lower()
    auxMapTable = '%s.%s' % (dstTablePrefix, __statelessDbIdMapTableName) 
    
    _decodeOffset = _getOffsetDecoder(destSession)
    _updateId = _getIdUpdater(destSession)
    
    c = itertools.count(1)
    
    joins = list()
    srcColumns = list()
    dstColumns = list()
    
    dbColumns = entityDef.getFieldNameToDbColumnMap()
    
    for fieldName in entityDef.GetFieldDefNames():
        
        fieldType = entityDef.GetFieldDefType(fieldName)
        
        dst = dbColumns.get(fieldName)
        src = None
        
        if fieldName == __mergeDbField:
            src = "'%s'" % srcDbName
            
        elif fieldName == __mergeIdField:
            src = 'src.id'
        
        elif fieldName == __mergeDbIdField:
            src = 'src.dbid'
        
        elif fieldName in ('ratl_mastership', 'ratl_keysite'):
            src = dstReplicaId
            
        elif fieldType in straightCopyFieldTypes:
            src = 'src.%s' % dst
            
        elif fieldType == FieldType.Id:
            if dbidOffset:
                dbid = '(src.dbid + %d)' % dbidOffset
            else:
                dbid = 'src.dbid'
                
            src = _updateId(dstDbName, dbid)
            
        elif fieldType == FieldType.DbId:
            if dbidOffset:
                src = '(src.dbid + %d)' % dbidOffset
            else:
                src = 'src.dbid'
                
        elif fieldType == FieldType.Reference:
            if entityDef.isReferenceField(fieldName):
                refEntityDef = entityDef.GetFieldReferenceEntityDef(fieldName)
                refEntityDefType = refEntityDef.GetType()
                if refEntityDefType == Stateful:
                    if dbidOffset:
                        src = _decodeOffset('src.%s' % dst, dbidOffset)
                    else:
                        src = 'src.%s' % dst
                else:
                    alias = 'm%d' % c.next()
                    src = '%s.dbid' % alias
                    joins.append((alias, (dst, refEntityDef.id)))
                    
            else:
                print "skipping field %s: field type is reference but " \
                      "isReferenceField() returned false"
        
        if src:
            dstColumns.append(dst)
            srcColumns.append(src)
    
    
    where = list()
    srcDbId = _getDbIdColumn(sourceSession)
    srcTables = list()
    srcTables.append('%s.%s src' % (srcTablePrefix, entityDbName))
    for (alias, (column, eid)) in joins:
        srcTables.append('%s %s' % (auxMapTable, alias))
        where.append('%s.%s = src.%s AND %s.entitydef_id = %d' % \
                     (alias, srcDbId, column, alias, eid))
        
    where.append('src.dbid <> 0')
    if entityDefType == EntityType.Stateless:
        # Make sure we only insert stateless entities where we're listed as the
        # owner for in the merged dbid map.
        alias = 'm%d' % c.next()
        srcTables.append('%s %s' % (auxMapTable, alias))
        if dbidOffset:
            src = '(src.dbid + %d)' % dbidOffset
        else:
            src = 'src.dbid'
        where.append('%s.ratl_mastership = src.ratl_mastership AND '           \
                     '%s.%s = src.dbid AND %s.dbid = %s AND '                  \
                     '%s.entitydef_id = %d' %                                  \
                     (alias, alias, srcDbId, alias, src, alias, entityDef.id))
        
    kwds = {
        'where'      : ' AND\n    '.join(where),
        'dstTable'   : '%s.%s' % (dstTablePrefix, entityDbName),
        'orderBy'    : 'src.dbid ASC',
        'srcTables'  : ',\n    '.join(srcTables),
        'dstColumns' : ',\n    '.join(dstColumns),
        'srcColumns' : ',\n    '.join(srcColumns),
    }
    
    return findSql('mergeEntity') % kwds

def _mergeHistory(destSession, sourceSessions, dbidOffsets):
    """
    """
    offsets = iter(dbidOffsets)
    dstReplicaId = destSession.getReplicaId()
    dstPrefix = destSession.getTablePrefix()
    auxMapTable = '%s.%s' % (dstPrefix, __statelessDbIdMapTableName)
    
    defaultColumns = (
        ('old_state', 'src.old_state'),
        ('new_state', 'src.new_state'),
        ('action_name', 'src.action_name'),
        ('ratl_keysite', str(dstReplicaId)),
        ('entitydef_id', 'src.entitydef_id'),
        ('entitydef_name', 'src.entitydef_name'),
        ('ratl_mastership', str(dstReplicaId)),
        ('action_timestamp', 'src.action_timestamp'),
        ('expired_timestamp', 'src.expired_timestamp'),
    )
    
    user = "{fn CONCAT({fn LEFT(src.user_name, %d)}, ' (%s)')}"
    
    for session in sourceSessions:
        
        dbidOffset = offsets.next()
        srcDbName = session._databaseName
        srcDbId = _getDbIdColumn(session)
        srcPrefix = api.getLinkedServerAwareTablePrefix(session, (destSession,))
        
        entityTypes = {
            Stateless : ('m1.dbid', True),
            Stateful  : ('(src.entity_dbid + %d)' % dbidOffset, False),
        }
        
        for (entityType, (column, joinAuxMap)) in entityTypes.items():
            columns = list(defaultColumns)
            columns.append(('user_name', user % (27-len(srcDbName),srcDbName)))
            
            columns.append(('dbid', '(src.dbid + %d)' % dbidOffset))
            columns.append(('entity_dbid', column))
            
            where = list()
            where.append('src.entitydef_id = e1.id')
            where.append('e1.type = %d AND e1.is_family = 0' % entityType)
            
            srcTables = list()
            srcTables.append('%s.history src' % srcPrefix)
            srcTables.append('%s.entitydef e1' % dstPrefix)
            if joinAuxMap:
                srcTables.append('%s m1' % auxMapTable)
                where.append('m1.%s = src.entity_dbid ' % srcDbId)
                where.append('m1.entitydef_id = src.entitydef_id')
            
            (dstColumns, srcColumns) = unzip(columns)
            
            kwds = {
                'where'      : ' AND\n    '.join(where),
                'orderBy'    : 'src.dbid ASC',
                'dstTable'   : '%s.history' % dstPrefix,
                'srcTables'  : ',\n    '.join(srcTables),
                'dstColumns' : ',\n    '.join(dstColumns),
                'srcColumns' : ',\n    '.join(srcColumns),
            }
            
            yield findSql('mergeEntity') % kwds

def _mergeParentChildLinks(destSession, sourceSessions, dbidOffsets):
    """
    """
    offsets = iter(dbidOffsets)
    prefixes = ('parent', 'child')
    
    # We need to discern between stateful/stateless and User/Group for our final
    # iteration, so use some meaningful aliases such that the code in the loop
    # below looks a little less obtuse.
    User = -Stateless
    Group = -Stateless
    linkTypes = (
        (Stateful, Stateful),
        (Stateful, Stateless),
        (Stateless, Stateful),
        (Stateless, Stateless),
        (User, Group),
    )    
   
    _decodeOffset = _getOffsetDecoder(destSession)
    
    for sourceSession in sourceSessions:
        
        dbidOffset = offsets.next()
        srcDbId = '%s_dbid' % sourceSession._databaseName.lower()
        
        for linkType in linkTypes:
    
            joins = list()
            where = list()
            dstColumns = list()
            srcColumns = list()
            m = itertools.count(1)
            e = itertools.count(1)
            exclude = { 'exclude' : True }
            
            for (prefix, link) in zip(prefixes, linkType):
                dst = '%s_dbid' % prefix
                alias = 'e%d' % e.next()
                joins.append((alias, 'entitydef')) 
                
                if prefix == 'child' and link == Group:
                    where.append("%s.name = 'groups'" % alias)
                else:
                    where += [
                        '%s.id = src.%s_entitydef_id' % (alias,prefix),
                        '%s.type = %d AND %s.is_family = 0' % \
                            (alias, abs(link), alias)
                    ]
                
                entityDefAlias = alias
                
                if link == Stateful:
                    if dbidOffset:
                        src = _decodeOffset('src.%s_dbid' % prefix, dbidOffset)
                    else:
                        src = 'src.%s_dbid' % prefix
                else:
                    alias = 'm%d' % m.next()
                    src = '%s.dbid' % alias
                    joins.append((alias, __statelessDbIdMapTableName))
                    where.append('%s.%s = src.%s_dbid' % \
                                 (alias, srcDbId, prefix))                    if link != Group:
                        where.append('%s.entitydef_id = src.%s_entitydef_id' % \
                                     (alias, prefix))
                    else:
                        where.append('%s.entitydef_id = %s.id' % \
                                     (alias, entityDefAlias))
                
                dstColumns.append(dst)
                srcColumns.append(src)
                
                for other in ('_entitydef_id', '_fielddef_id'):
                    dstColumns.append('%s%s'     % (prefix, other))
                    srcColumns.append('src.%s%s' % (prefix, other))
                
                exclude[prefix] = src
            
            dstColumns.append('link_type_enum')
            srcColumns.append('1')
            
            if linkType not in ((Stateless, Stateless), (User, Group)):
                exclude['exclude'] = False
                
            args = (sourceSession, (destSession,))
            srcTablePrefix = api.getLinkedServerAwareTablePrefix(*args)
            dstTablePrefix = destSession.getTablePrefix()
            
            srcTables = list()
            srcTables.append('%s.parent_child_links src' % srcTablePrefix)
            
            for (alias, table) in joins:
                srcTables.append('%s.%s %s' % (dstTablePrefix, table, alias))
            
            kwds = {
                'where'      : ' AND\n    '.join(where),
                'dstTable'   : '%s.parent_child_links' % dstTablePrefix,
                'srcTables'  : ',\n    '.join(srcTables),
                'dstColumns' : ',\n    '.join(dstColumns),
                'srcColumns' : ',\n    '.join(srcColumns),
            }
            
            yield findSql('mergeParentChildLinks', **exclude) % kwds

def _mergeEntities(destSession, sourceSessions, dbidOffsets):
    
    offsets = iter(dbidOffsets)
    for sourceSession in sourceSessions:
        offset = offsets.next()
        for entityDef in destSession.getAllEntityDefs():
            entityDefName = entityDef.GetName()
            if entityDefName in ('history', 'ratl_replicas'):
                continue
            yield _mergeEntity(destSession, sourceSession, entityDefName,offset)
    
def _mergeAttachments(destSession, sourceSessions, dbidOffsets):
    offsets = iter(dbidOffsets)
    dstPrefix = destSession.getTablePrefix()
    auxMapTable = '%s.%s' % (dstPrefix, __statelessDbIdMapTableName)    
    
    defaultColumns = (
        ('filename', 'src.filename'),
        ('filesize', 'src.filesize'),
        ('description', 'src.description'),
        ('entity_fielddef_id', 'src.entity_fielddef_id'),
    )
    
    defaultBlobColumns = (
        ('data', 'src.data'),
        ('entity_dbid', 'a1.entity_dbid'),
        ('attachments_dbid', 'a1.dbid'),
        ('entity_fielddef_id', 'a1.entity_fielddef_id'),
    )
    
    (dstBlobColumns, srcBlobColumns) = unzip(defaultBlobColumns)
    
    for session in sourceSessions:
        
        dbidOffset = offsets.next()
        srcDbName = session._databaseName
        srcDbId = _getDbIdColumn(session)
        srcPrefix = api.getLinkedServerAwareTablePrefix(session, (destSession,))
        
        entityTypes = {
            Stateless : ('m1.dbid', True),
            Stateful  : ('(src.entity_dbid + %d)' % dbidOffset, False),
        }
        
        for (entityType, (column, joinAuxMap)) in entityTypes.items():
            columns = list(defaultColumns)
            
            columns.append(('dbid', '(src.dbid + %d)' % dbidOffset))
            columns.append(('entity_dbid', column))
            
            where = list()
            where.append('f1.id = src.entity_fielddef_id')
            where.append('e1.id = f1.entitydef_id')
            where.append('e1.type = %d AND e1.is_family = 0' % entityType)
            
            srcTables = list()
            srcTables.append('%s.attachments src' % srcPrefix)
            srcTables.append('%s.fielddef f1' % dstPrefix)
            srcTables.append('%s.entitydef e1' % dstPrefix)
            if joinAuxMap:
                srcTables.append('%s m1' % auxMapTable)
                where.append('m1.%s = src.entity_dbid ' % srcDbId)
                where.append('m1.entitydef_id = e1.id')
                
            (dstColumns, srcColumns) = unzip(columns)

            kwds = {
                'where'      : ' AND\n    '.join(where),
                'orderBy'    : 'src.dbid ASC',
                'dstTable'   : '%s.attachments' % dstPrefix,
                'srcTables'  : ',\n    '.join(srcTables),
                'dstColumns' : ',\n    '.join(dstColumns),
                'srcColumns' : ',\n    '.join(srcColumns),
            }
            
            yield findSql('mergeEntity') % kwds
        
        # Merging attachments_blob only requires one SQL statement per source
        # session, as opposed to one per entity type as above, because we join
        # on the newly populated attachments table directly.
        srcTables = list()
        srcTables.append('%s.attachments_blob src' % srcPrefix)
        srcTables.append('%s.attachments a1' % dstPrefix)
        
        where = list()
        where.append('a1.dbid = (src.attachments_dbid + %d)' % dbidOffset)
        where.append('src.entity_fielddef_id = a1.entity_fielddef_id')
        
        kwds = {
            'where'      : ' AND\n    '.join(where),
            'orderBy'    : 'a1.dbid ASC',
            'dstTable'   : '%s.attachments_blob' % dstPrefix,
            'srcTables'  : ',\n    '.join(srcTables),
            'dstColumns' : ',\n    '.join(dstBlobColumns),
            'srcColumns' : ',\n    '.join(srcBlobColumns),
        }
        
        yield findSql('mergeEntity') % kwds

def _mergeUserBuckets(destSession, sourceSessions, dbidOffsets):
    dstPrefix = destSession.getTablePrefix()
    dstReplicaId = str(destSession.getReplicaId())
    dstCollation = destSession.getCollation()
    auxMapTable = '%s.%s' % (dstPrefix, __statelessDbIdMapTableName)
    bucketMapTable = '%s.%s' % (dstPrefix, __userBucketMapTableName)
    
    defaultColumns = (
        ('type', 'src.type'),
        ('user_id', 'm1.dbid'),
        ('subtype', 'src.subtype'),
        ('data_length', 'src.data_length'),
        ('ratl_keysite', dstReplicaId),
        ('entitydef_id', 'src.entitydef_id'),
        ('ratl_mastership', dstReplicaId),
        ('package_ownership', 'src.package_ownership'),
    )
    
    decodeNameForPrimaries = findSql('decodeNameForPrimaryUserBuckets')
    decodeNameForSecondaries = findSql('decodeNameForSecondaryUserBuckets')
    decodeParentForSecondaries = findSql('decodeParentForSecondaryUserBuckets')
    
    # Merging user buckets is a two part process.  We create a 'bucket usage
    # map' earlier on in the merge process that records which database the
    # user has the most buckets in (i.e. queries, preferences etc).  This
    # database is treated as their primary database and all buckets from it
    # are imported. The first bit of SQL generation logic below handles this
    # task.  The second part of the process is bringing over queries that
    # were associated with them in their non-primary database.  A folder is
    # created under their 'Personal Queries' folder named 'Merged <dbname>
    # Queries', which contains their queries from the other databases.

    offsets = iter(dbidOffsets)
    for session in sourceSessions:
        srcPrefix = api.getLinkedServerAwareTablePrefix(session, (destSession,))
        dbidOffset = offsets.next()
        decodeOffset = _getOffsetDecoder(session)
        dbDbIdColumn = _getDbIdColumn(session)
        srcReplicaId = session.getReplicaId()
        collationCast = ''
        if session.getCollation() != dstCollation:
            collationCast = ' COLLATE %s' % dstCollation
        
        expand = lambda s: (s, decodeOffset('src.%s' % s, dbidOffset))
        columns = list(defaultColumns)
        columns += [
            expand('dbid'),
            expand('data_id'),
            expand('query_bucket_id'),
            expand('parent_bucket_id'),
            ('name', decodeNameForPrimaries % (dstPrefix, collationCast)),
        ]
        (dstColumns, srcColumns) = unzip(columns)
        
        srcTables = (
            '%s m1' % auxMapTable, 
            '%s b1' % bucketMapTable, 
            '%s.bucket src' % srcPrefix,
        )
               
        where = (
            'b1.dbid = m1.dbid',
            'm1.%s = src.user_id' % dbDbIdColumn,
            'b1.ratl_mastership = src.ratl_mastership',
        )            
        
        kwds = {
            'where'      : ' AND\n    '.join(where),
            'orderBy'    : 'src.dbid ASC',
            'dstTable'   : '%s.bucket' % dstPrefix,
            'srcTables'  : ',\n    '.join(srcTables),
            'dstColumns' : ',\n    '.join(dstColumns),
            'srcColumns' : ',\n    '.join(srcColumns),
        }
        
        yield findSql('mergeEntity') % kwds
        
    # Now for part two: importing queries present in the user's non-primary
    # database, but making sure they live under a new folder names 'Merged
    # <dbname> Queries' (which we also ensure lives under the root 'Personal
    # Queries' folder for the user in the merged database).
    offsets = iter(dbidOffsets)
    for session in sourceSessions:
        dbName = session._databaseName
        srcPrefix = api.getLinkedServerAwareTablePrefix(session, (destSession,))
        dbidOffset = offsets.next()
        decodeOffset = _getOffsetDecoder(session)
        dbDbIdColumn = _getDbIdColumn(session)
        srcReplicaId = session.getReplicaId()
        
        expand = lambda s: (s, decodeOffset('src.%s' % s, dbidOffset))
        
        decodeName = decodeNameForSecondaries % dbName
        decodeParent = decodeParentForSecondaries % \
            (dstPrefix, 'src.parent_bucket_id + %d' % dbidOffset)
        
        columns = list(defaultColumns)
        columns += [
            expand('dbid'),
            expand('data_id'),
            expand('query_bucket_id'),
            ('name', decodeName),
            ('parent_bucket_id', decodeParent),
        ]
        (dstColumns, srcColumns) = unzip(columns)
        
        srcTables = (
            '%s m1' % auxMapTable, 
            '%s b1' % bucketMapTable, 
            '%s.bucket src' % srcPrefix,
        )
        
        # We only copy the following types of buckets from secondary databases:
        #   1:   queries
        #   2:   charts
        #   4:   folders
        #   256: report
        #   512: report format
        where = (
            'src.type IN (1, 2, 4, 256, 512)',
            'b1.ratl_mastership <> src.ratl_mastership',
            'm1.%s = src.user_id' % dbDbIdColumn,
            'b1.dbid = m1.dbid'
        )
        
        kwds = {
            'where'      : ' AND\n    '.join(where),
            'orderBy'    : 'src.dbid ASC',
            'dstTable'   : '%s.bucket' % dstPrefix,
            'srcTables'  : ',\n    '.join(srcTables),
            'dstColumns' : ',\n    '.join(dstColumns),
            'srcColumns' : ',\n    '.join(srcColumns),
        }
        
        yield findSql('mergeEntity') % kwds
        
    # And finally, generate SQL statements to copy the user_blob data over for
    # the final set of merged queries.
    offsets = iter(dbidOffsets)
    for session in sourceSessions:
        srcPrefix = api.getLinkedServerAwareTablePrefix(session, (destSession,))
        dbidOffset = offsets.next()
        
        offset = '(src.dbid + %d)' % dbidOffset
        columns = (
            ('data', 'src.data'),
            ('dbid', offset),
        )
        (dstColumns, srcColumns) = unzip(columns)
        
        srcTables = (
            '%s.bucket b1' % dstPrefix,
            '%s.user_blob src' % srcPrefix,
        )
        
        kwds = {
            'where'      : 'b1.data_id = %s' % offset,
            'orderBy'    : 'src.dbid ASC',
            'dstTable'   : '%s.user_blob' % dstPrefix,
            'srcTables'  : ',\n    '.join(srcTables),
            'dstColumns' : ',\n    '.join(dstColumns),
            'srcColumns' : ',\n    '.join(srcColumns),
        }
        
        yield findSql('mergeEntity') % kwds        
                
@api.cache
def __getAffectedIndexes(destSession):
    vendor = destSession.getDatabaseVendor()
    if vendor != SQLServer:
        return ()
    dstDb = destSession.db()
    prefix = destSession.getTablePrefix()
    
    return [
        (index, '%s.%s' % (prefix, table))
            for table in dstDb.tables()
                for index in dstDb.indexes(table)
                    if table != __statelessDbIdMapTableName and
                       not index.endswith('_cix')
    ]

@api.cache
def __getClusteredIndexes(destSession):
    vendor = destSession.getDatabaseVendor()
    if vendor != SQLServer:
        return ()
    dstDb = destSession.db()
    prefix = destSession.getTablePrefix()
    
    return [
        ('%s_cix' % e.db_name, '%s.%s' % (prefix, e.db_name))
            for e in destSession.getAllEntityDefs()
    ]
    
def _disableIndexes(destSession, *args):
    if destSession.getDatabaseVendor() == SQLServer:
        
        if __useClusteredIndexes:
            for i in __getClusteredIndexes(destSession):
                yield 'CREATE UNIQUE CLUSTERED INDEX %s ON %s (dbid) ' \
                      'WITH (DROP_EXISTING = ON, FILL_FACTOR = %d)' %  \
                        tuple(chain(i, (__defaultFillFactor,)))
            
        else:
            for i in __getAffectedIndexes(destSession):
                yield 'ALTER INDEX %s ON %s DISABLE' % i
        
def _rebuildIndexes(destSession, *args):
    if destSession.getDatabaseVendor() == SQLServer:
        
        if __useClusteredIndexes:
            indexes = chain(__getClusteredIndexes(destSession),
                            __getAffectedIndexes(destSession))
                            
            for i in indexes:
                yield 'ALTER INDEX %s ON %s REBUILD' % i
            
        else:
            for i in __getAffectedIndexes(destSession):
                yield 'ALTER INDEX %s ON %s REBUILD' % i

def _finaliseDbGlobal(destSession, sourceSessions, dbidOffsets):
    prefix = destSession.getTablePrefix()
    last = dbidOffsets[-1]
    sql = 'UPDATE %s.dbglobal SET next_request_id = %d, next_aux_id = %d'
    return sql % (prefix, last, last)
        
def _mergeDatabases(destSession, sourceSessions):
    
    dbidOffsets = getDbIdOffsets(destSession, sourceSessions)
    args = (destSession, sourceSessions, dbidOffsets)
    sql  = [
        _setPreMergeDatabaseOptions(*args),
        _prepareDatabaseForMerge(*args),
        _createStatelessDbIdMap(*args),
        _createUserBucketMap(*args),
    ]
    sql += [ s for s in _disableIndexes(*args) ]
    sql += [ s for s in _mergeEntities(*args) ]
    sql += [ s for s in _mergeParentChildLinks(*args) ]
    sql += [ s for s in _mergeHistory(*args) ]
    sql += [ s for s in _mergeAttachments(*args) ]
    sql += [ s for s in _mergeUserBuckets(*args) ]
    sql += [ s for s in _rebuildIndexes(*args) ]
    sql += [ 
        _finaliseDbGlobal(*args),
        _setPostMergeDatabaseOptions(*args),
    ]
    
    return '\nGO\n'.join(sql)

def verifyMerge(destSession, sourceSessions, output=sys.stdout):
    """
    Verifies the contents of a merged database by checking record counts and
    comparing the results to the expected record counts.  For stateful entities,
    the total record count in destSession for each entity is compared to the
    sum of all record counts for each source session.  For stateless entities,
    the merge map table is consulted.  The final count in destSession should
    equal the count of distinct rows for a given entitydef in the merge map.
    
    Once all the record count checks are done, a second level of checks are run.
    These checks attempt to find any entities in one of the source sessions that
    aren't in destSession when they should be.
    
    For stateful entities, this is simply achieved by selecting rows in the 
    source session for which the row's dbid does not exist in the distinct list
    of merge_orig_dbid values for a given entitydef.
    
    For stateless entities, rows from the source session that do not have a 
    corresponding row in the destSession are returned. This is done by querying
    against each stateless entity's unique ID.
    """
    
    targets = [ entityDef for entityDef in destSession.getAllEntityDefs() ] + \
              [ 'attachments', 'attachments_blob', 'parent_child_links' ]
    
    
    counts = dict()
    dstPrefix = destSession.getTablePrefix()
    simpleCountSql = 'SELECT COUNT(*) FROM %s.%s %s'
    statelessCountSql = findSql('selectStatelessEntityCounts')
    sessions = [ s for s in chain(sourceSessions, (destSession,)) ]
    
    for session in sessions:
        prefix = api.getLinkedServerAwareTablePrefix(session, (destSession,))
        dbName = session._databaseName
        dbc = session.db()
        assert isinstance(dbc, db.Connection)
        
        counts[dbName] = dict()
        
        for target in targets:
            simple = True
            where = ' WHERE dbid <> 0'
            if isinstance(target, api.EntityDef):
                targetName = target.GetName()
                targetDbName = target.GetDbName()
                if targetName != 'history' and          \
                   target.GetType() == Stateless and    \
                   session is not destSession:
                    simple = False
            else:
                if target in ('parent_child_links', 'attachments_blob'):
                    where = ''
                targetName = targetDbName = target
                
            if simple:
                sql = simpleCountSql % (prefix, targetDbName, where)
                counts[dbName][targetName] = dbc.selectSingle(sql)            
            else:
            
                otherDbIdColumns = [
                    'm1.%s IS NULL' % _getDbIdColumn(s)
                        for s in sessions
                            if s not in (session, destSession)
                ]
                
                sql = statelessCountSql % {
                    'dstPrefix'        : dstPrefix,
                    'entityDefId'      : target.id,
                    'dbDbIdColumn'     : _getDbIdColumn(session),
                    'otherDbIdColumns' : ' AND\n        '.join(otherDbIdColumns)
                }
                counts[dbName][targetName] = dbc.selectSingle(sql)
    
    rows = list()
    
    for target in [ t if type(t) is str else t.GetName() for t in targets ]:
        total = 0
        row = list()
        row.append(target)
        
        for session in sourceSessions:
            count = counts[session._databaseName][target]
            row.append(count)
            total += count 
        
        row.append(total)
        actual = counts[destSession._databaseName][target]
        row.append(actual)
        
        sign = ''
        diff = actual - total
        if diff < 0:
            sign = '-'
        elif diff > 0:
            sign = '+'
        
        row.append('%s%d' % (sign, diff))
        
        rows.append(row)
    
    columnCount = len([s for s in sourceSessions]) + 3
    paddings = [ p for p in chain((35,), repeat(11, columnCount)) ]
    adjust = [ a for a in chain((str.ljust,), repeat(str.rjust, columnCount)) ]
    
    header = [ 'Target' ] + \
             [ s._databaseName for s in sourceSessions ] + \
             [ 'Total', destSession._databaseName, 'Difference' ]
    rows.insert(0, header)
    rows.insert(1, ('',) * len(header))
    
    out = \
        '\n'.join([
            '|'.join([
                format(str(column), padding, fill)
                    for (column, format, padding) in zip(row, adjust, paddings)
            ]) for (row, fill) in zip(rows, chain((' ', '_'), repeat(' ')))
        ])
    return out
    
    
        
def _setPreMergeDatabaseOptions(destSession, *args):
    k = { 'dbName' : destSession.getPhysicalDatabaseName() }
    return str(findSql('setPreMergeDatabaseOptions') % k)

def _setPostMergeDatabaseOptions(destSession, *args):
    k = { 'dbName' : destSession.getPhysicalDatabaseName() }
    return (findSql('setPostMergeDatabaseOptions') % k)
    
def mergeDatabases(destSession, sourceSessions):
    dstDb = destSession.db()
    sql = _mergeDatabases(destSession, sourceSessions)
    
    destSession.mergeMultipleDynamicListValues([
        s.getDynamicLists() for s in sourceSessions
    ])
    
    mergePublicQueries(destSession, sourceSessions)
        
def mergePublicQueries(destSession, sourceSessions):
    cwd = os.getcwd()
    for session in sourceSessions:
        name = session._databaseName
        path = '%s-queries.bkt' % name
        if not os.path.isfile(joinPath(cwd, path)):
            exportQueries(session, path)
        updateQueries(destSession, path)
    
class DatabaseNotEmptyError(Exception): pass

def _prepareDatabaseForMerge(destSession, *args):
    """
    Deletes all rows (except for where dbid == 0) in the following tables:
    parent_child_links, users, groups, bucket, user_blob.
    """
    
    # This method should only be run against sessions for databases that have
    # been newly created from Designer, which we can verify by seeing if there
    # are any entities present.
    if getMaxStatefulEntityDbIds((destSession,)).next() != 0:
        raise DatabaseNotEmptyError()
    
    kwds = { 'dstPrefix' : destSession.getTablePrefix() }
    return findSql('prepareDatabaseForMerge', **kwds)
    

def addMergeFields(adminSession, destSession):
    """
    @param adminSession: instance of api.AdminSession() that's logged in to the
    schema database that the merge fields should be added to.
    @param destSession: instance of api.Session() for any database using the
    schema that is to be modified to add the merge fields.
    """
    adminSession.setVisible(False, destSession._databaseName)
    
    import clearquest.designer
    designer = clearquest.designer.Designer()
    designer.Login(adminSession._databaseName,
                   adminSession._loginName,
                   adminSession._password,
                   adminSession._databaseSet)
    
    schemaName = destSession.schemaName()
    designer.CheckoutSchema(schemaName, '')
    
    for entityDef in destSession.getAllEntityDefs():
        entityDefName = entityDef.GetName()
        fields = listToMap(entityDef.GetFieldDefNames()).keys()
        for (mergeField, mergeFieldType) in MergeFields.items():
            # Ugh, quick hack...
            if mergeField.endswith('_id') and \
               entityDef.GetType() == api.EntityType.Stateless:
                continue
            if mergeField not in fields:
                print "adding field '%s' of type '%s' to entity '%s'..." % (   \
                    mergeField,
                    FieldType[mergeFieldType],
                    entityDefName
                )
                designer.UpgradeFieldDef(entityDefName,
                                         mergeField,
                                         mergeFieldType,
                                         None)
            else:
                if entityDef.GetFieldDefType(mergeField) != mergeFieldType:
                    raise RuntimeError("entity '%s' already has a field named "
                                       "'%', but it is not a short string." %  \
                                       (entityDefName, mergeField))
                
            oldMergeField = '__%s' % mergeField
            if oldMergeField in fields:
                print "deleting old field '%s' from entity '%s'..." % ( \
                    oldMergeField,
                    entityDefName
                )
                designer.DeleteFieldDef(entityDefName, oldMergeField)
                
    print "validating schema..."
    designer.ValidateSchema()
    print "checking in schema..."
    designer.CheckinSchema('Added fields for database merge.')
    #print "upgrading database '%s'..." % destSession._databaseName
    #designer.UpgradeDatabase(destSession._databaseName)
    designer.Logoff()
    del designer
    
    adminSession.setVisible(True, destSession._databaseName)

def getRecommendedStatefulDbIdOffset(session):
    maximum = (0, '<entity def name will live here>')
    dbc = session.db()
    for entityDef in session.getStatefulEntityDefs():
        name = entityDef.GetDbName()
        m = dbc.selectSingle('SELECT MAX(dbid) FROM %s' % name)
        if m > maximum[0]:
            maximum = (m, name)
    
    # 0x2000000 = 33554432: starting dbid used by CQ databases.  The
    # offset gets added to each dbid, which, technically, could be as
    # low as the very minimum, so check that the dbidOffset provided is
    # sufficient.
    if maximum[0] == 0:
        return 0
    m = str(maximum[0] - 33554432)
    recommended = str(int(m[0])+1) + '0' * (len(m)-1)
    return int(recommended)

def getDbIdOffsets(destSession, sourceSessions):
    """
    Enumerates over the given list of sourceSessions and constructs a list of
    offsets that should be used when merging the contents of each session's
    database into the destSession's database.  The length of the list of offsets
    returned will be len(sourceSessions)+1.  This is because an extra offset is
    added to the end of the list that represents what dbglobal.next_request_id
    and dbglobal.next_aux_id should be set to in destSession when all source
    sessions have been merged in.
    
    @param destSession: L{api.Session} object.
    @param sourceSessions: enumerable container of L{api.Session} objects.
    @returns: L{list} of L{int}s.
    """
    offsets = list()
    
    # Is our destination session an empty database?  We detect this by whether
    # or not there are any stateful entities present.
    if getMaxStatefulEntityDbIds((destSession,)).next() == 0:
        offsets.append(0)
        sessions = sourceSessions
    else:
        sessions = chain((destSession,), sourceSessions)
        
    previous = 0
    count = itertools.count(1)
    for maximum in getMaxTableDbIds(sessions):
        if maximum == 0:
            offsets.append(0)
        else:
            m = str((maximum + previous) - 33554432)
            prefix = count.next()
            zeroes = len(m) if prefix == 1 else len(m)-1
            offset = int('%d%s' % (prefix, '0' * zeroes))
            offsets.append(offset)
            previous = offset
    
    return offsets

def getMaxTableDbIds(sessions):
    tables = list()
    firstSession = True
    for session in sessions:
        maximum = 0
        dbc = session.db()
        if firstSession:
            # Get a list of all the tables, then reduce to those that have a
            # dbid column of type int.
            for table in dbc.tables():
                # ratl_replicas has a dbid column, but it references a master
                # dbid value in the schema, which we don't care about.
                if table in ('ratl_replicas', __statelessDbIdMapTableName):
                    continue
                for column in dbc.columns(table):
                    if column[0] == u'dbid' and column[2] == u'int':
                        tables.append(table)
                        break
            firstSession = False
            
        for table in tables:
            # XXX: MAKE SURE THIS EXCEPTION BLOCK GETS REMOVED!
            try:
                sql = 'SELECT MAX(dbid) FROM %s' % table
                mx = dbc.selectSingle(sql)
                if mx > maximum:
                    maximum = mx
            except:
                pass
        
        yield maximum

def _getMaxEntityDbIds(sessions, getEntityDefMethod):
    for session in sessions:
        maximum = 0
        dbc = session.db()
        for entityDef in getEntityDefMethod(session):
            table = entityDef.GetDbName()
            # ratl_replicas has a dbid column, but it references a master
            # dbid value in the schema, which we don't care about.
            if table == 'ratl_replicas':
                continue
            sql = 'SELECT MAX(dbid) FROM %s' % table
            mx = dbc.selectSingle(sql)
            if mx > maximum:
                maximum = mx
        
        yield maximum

def getMaxEntityDbIds(sessions):
    return _getMaxEntityDbIds(sessions, api.Session.getAllEntityDefs)

def getMaxStatefulEntityDbIds(sessions):
    return _getMaxEntityDbIds(sessions, api.Session.getStatefulEntityDefs)

def getMaxStatelessEntityDbIds(sessions):
    return _getMaxEntityDbIds(sessions, api.Session.getStatelessEntityDefs)

def isValidDbIdOffset(sessions, dbidOffset):
    maximum = getMaxDbId(sessions)
    return bool(dbidOffset > maximum)

def getMaxIdForField(session, table, column):
    db = session.db().selectSingle('SELECT MAX(%s) FROM %s' % (column, table))


#===============================================================================
# Classes
#=============================================================================== 

class MergeConfigOld(TaskManagerConfig):
    def __init__(self, manager):
        self.defaultConfigSection = manager.profile
        TaskManagerConfig.__init__(self, manager)
        print "file: %s" % self.file
        
    def getDefaultConfigSection(self):
        return self.defaultConfigSection
    
    def tasks(self):
        return [
            InitialisePhysicalDatabase,
            InitialiseLogicalDatabase,
            MergeDatabases,
            VerifyMerge,
        ]
        
class MergeManager(MultiSessionTaskManager):
    def __init__(self, profile='DEFAULT'):
        self.profile = profile
        MultiSessionTaskManager.__init__(self)
            
    def run(self):
        
        for task in self.tasks:
            t = task(self)
            t.run()
            # Keep a copy of the task so other tasks can access it.
            self.task[t.__class__.__name__] = t    
    
    def createConfig(self):
        return MergeConfig(self)
        

class MergeTask(Task):
    def __init__(self, manager):
        Task.__init__(self, manager)
        self.sourceSessions = manager.getSourceSessions()
    
    def getSessionClassType(self):
        return api.SessionClassType.User

class InitialisePhysicalDatabase(MergeTask):
    def run(self):
        print "Running InitialisePhysicalDatabase()..."
        pass

class InitialiseLogicalDatabase(MergeTask):
    def run(self):
        print "Running InitialiseLogicalDatabase()..."
        pass

class MergeDatabases(MergeTask):
    def run(self):
        print "Running MergeDatabases()..."
        pass

class VerifyMerge(MergeTask):
    def run(self):
        print "Running VerifyMerge()..."
        pass

class DisableEntityIndexesTask(MergeTask):
    def __init__(self, manager, entityDefName):
        MergeTask.__init__(self, manager)
    
    def run(self):
        s = self.destSession
        [ s.GetEntityDef(n).disableAllIndexes() for n in s.GetEntityDefNames() ]
        
class EnableEntityIndexesTask(MergeTask):
    def __init__(self, manager, entityDefName):
        MergeTask.__init__(self, manager)
    
    def run(self):
        s = self.destSession
        [ s.GetEntityDef(n).enableAllIndexes() for n in s.GetEntityDefNames() ]
        

class MergeEntityTask(MergeTask):
    def __init__(self, manager, entityDefName, start, end):
        MergeTask.__init__(self, manager)
        self.entityDefName = entityDefName
        self.entityDef = self.destSession.GetEntityDef(entityDefName)
        self.entityDbName = self.entityDef.GetDbName()
        self.start = start
        self.end = end
    
    def run(self):
        cb = self.cb
        sql = 'SELECT COUNT(*) FROM %s WHERE dbid <> 0' % self.entityDbName
        cb.expected = self.sourceSession.db().selectSingle(sql)

class BulkCopyTask(MergeTask):
    
    def getSourceSessions(self):
        raise NotImplementedError
    
    def run(self):
        sql = []
        destSession = self.destSession
        sourceSessions = self.getSourceSessions()
        sessionCounter = itertools.count(1)
        dbidOffsets = self.manager.conf.get('dbidOffsets').split(',')
        targets = [ e.GetName() for e in destSession.getAllEntityDefs() ] + \
                  [ 'attachments_blob', 'parent_child_links' ]
        
        for sourceSession in sourceSessions:
            sessionCount = sessionCounter.next()
            emptyDb = True if sessionCount == 1 else False
            if not emptyDb:
                dbidOffset = dbidOffsets.pop(0)
            for target in targets:
                sql.append(bulkCopy(destSession,
                                    sourceSession,
                                    target,
                                    emptyDb=emptyDb,
                                    dbidOffset=dbidOffset)[0])
