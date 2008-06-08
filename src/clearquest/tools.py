"""
clearquest.tools: collection of miscellaneous ClearQuest-oriented utilities.
"""

#===============================================================================
# Imports
#===============================================================================

import os
import sys
import itertools

from glob import iglob
from tempfile import mkdtemp
from subprocess import Popen, PIPE

from clearquest.constants import CQConstant
from clearquest.util import joinPath, findFileInCQDir

#===============================================================================
# Globals
#===============================================================================

__rcsid__ = '$Id$'
__rcsurl__ = '$URL$'
__copyright__ = 'Copyright 2008 OnResolve Ltd'

#===============================================================================
# Bucket Tool (bkt_tool.exe) Methods
#===============================================================================

class _BucketStorageType(CQConstant):
    File      = '-st'
    Directory = '-di'
BucketStorageType = _BucketStorageType()

class _BucketToolOperation(CQConstant):
    Export    = '-e'
    Import    = '-i'
    Update    = '-u'
BucketToolOperation = _BucketToolOperation()

def getBucketToolExe():
    return findFileInCQDir('bkt_tool.exe')

def runBucketTool(session, storagePath, storageType, operation):
    args = (
        getBucketToolExe(),
        operation,
        '-us',  session._loginName,
        '-p',   session._password,
        '-db',  session._databaseName,
        '-dbs', session._databaseSet,
        storageType, storagePath,
    )
    stdout = StringIO.StringIO()
    stderr = StringIO.StringIO()
    p = Popen(args, stdout=PIPE, stderr=PIPE)
    p.wait()
    if p.returncode != 0:
        raise RuntimeError("bkt_tool.exe failed with error code %d: %s" % \
                           (p.returncode, p.stderr.read()))
    return

def exportQueries(session, storagePath, storageType=BucketStorageType.File):
    return runBucketTool(session,
                         storagePath,
                         storageType,
                         BucketToolOperation.Export)

def importQueries(session, storagePath, storageType=BucketStorageType.File):
    return runBucketTool(session,
                         storagePath,
                         storageType,
                         BucketToolOperation.Import)

def updateQueries(session, storagePath, storageType=BucketStorageType.File):
    return runBucketTool(session,
                         storagePath,
                         storageType,
                         BucketToolOperation.Update)

#===============================================================================
# CQLoad (cqload.exe) Methods
#===============================================================================

class _CQLoadOperation(CQConstant):
    ExportSchema         = 'exportschema'
    ExportIntegration    = 'exportintegration'
    ImportSchema         = 'importschema'
    ImportIntegration    = 'importintegration'
CQLoadOperation = _CQLoadOperation()

def getCQLoadExe():
    return findFileInCQDir('cqload.exe')

def runCQLoad(session, operation, getCmdLineOnly, *args):
    exe = getCQLoadExe()
    args = (
        exe,
        operation,
        '-dbset',
        session._databaseSet,
        session._loginName,
        session._password
    ) + args
    
    if getCmdLineOnly:
        return ' '.join([ '"%s"' % a or '' for a in args ])
    p = Popen(args, stdout=PIPE)
    p.wait()
    if p.returncode != 0:
        # cqload.exe prints errors to stdout
        raise RuntimeError("%s failed with error code %d:\n%s" % \
                           (exe, p.returncode, p.stdout.read()))
    return

def exportIntegration(session, schemaName, beginRevision, endRevision=0,
                      outputDir=os.getcwd(), recordTypeToRename='',
                      getCmdLineOnly=False):
    """
    Export an integration of @param C{str} schemaName to @param C{str}
    outputDir, starting at @param C{int} beginRevision and ending at @param
    C{int} endRevision.  If endRevision is ommitted or 0, it will be set to the
    value of beginRevision, which results in a single schema version being 
    exported.
    
    If @param C{bool} getCmdLineOnly is set to True, cqload.exe will not be run
    directly.  Instead, a string will be returned that represents the command
    line arguments necessary to run cqload.exe manually.

        Usage: cqload exportintegration
                 [-dbset dbset_name]
                 clearquest_login
                 clearquest_password
                 schema_name
                 begin_rev
                 end_rev
                 record_type_to_rename
                 schema_pathname    
    """
    if not endRevision:
        endRevision = beginRevision
        rev = str(beginRevision)
    else:
        rev = '%d-%d' % (beginRevision, endRevision)
        
    file = '%s-%s-v%s.txt' % (session._databaseSet, schemaName, rev)
    schemaPathName = joinPath(outputDir, file)
        
    return runCQLoad(session,
                     CQLoadOperation.ExportIntegration,
                     getCmdLineOnly,
                     schemaName,
                     str(beginRevision),
                     str(endRevision),
                     recordTypeToRename,
                     schemaPathName)

def exportIntegrationRange(session, schemaName, beginRevision, endRevision,
                           outputDir, getCmdLineOnly=False):
    """
    For each revision in the range between beginRevision and endRevision, export
    a single integration of schemaName from session into outputDir.  The export
    will be named '<dbset>-<schemaName>-v<revision>.txt'.  (The value for dbset 
    is automatically derived from the session parameter.)  This method is 
    intended to be used with the importIntegrationRange() method.  It is useful
    if you want to keep the revision history of two schemas synchronised.
    
    In order to minimise the likelihood of picking up stray/unwanted schemas
    when running exportIntegrationRange() followed by importIntegrationRange(),
    a RuntimeError exception is raised if outputDir is not empty.
    """
    for dummy in iglob(joinPath(outputDir, '*')):
        raise RuntimeError("output directory not empty: %s" % outputDir)
    
    kwds = dict(outputDir=outputDir, getCmdLineOnly=getCmdLineOnly)
    revs = xrange(beginRevision, endRevision+1)
    
    if getCmdLineOnly:
        return [
            exportIntegration(session, schemaName, r, **kwds) for r in revs
        ]
    else:
        for r in revs:
            print "exporting revision %d of '%s' schema..." % \
                  (r, schemaName)
            exportIntegration(session, schemaName, r, **kwds)

def importIntegration(session, schemaName, schemaPathName, integrationName='',
                      integrationVersion=0, newRecordTypeName='', 
                      getCmdLineOnly=False, *formNames):
    """
    Import an integration of @param C{str} schemaName stored in the file @param
    C{str} schemaPathName.
    
        Usage: cqload importintegration
                 [-dbset dbset_name]
                 clearquest_login
                 clearquest_password
                 schema_name
                 new_record_type_name
                 integration_name
                 integration_version
                 schema_pathname
                 form_name
          Remaining arguments are names of forms defined for
          the primary entity to which the new tabs are to
          be added:
                 form_name_1
                 form_name_2
                 etc.    
    """
    if not integrationName:
        integrationName = 'cq.util: imported %s' % \
                          os.path.basename(schemaPathName)

    # Need to provide at least one form name, even if it's just an empty string.
    if not formNames:
        formNames = ('',)
        
    return runCQLoad(session,
                     CQLoadOperation.ImportIntegration,
                     getCmdLineOnly,
                     schemaName,
                     newRecordTypeName,
                     integrationName,
                     str(integrationVersion),
                     schemaPathName,
                     *formNames)

def importIntegrationRange(session, schemaName, outputDir,
                           getCmdLineOnly=False, beginRev=0, endRev=0):
    """
    Unless getCmdLineOnly is set to True, beginRev and endRev are ignored.
    """
    if getCmdLineOnly:
        return [
            importIntegration(session, schemaName, file, getCmdLineOnly=True)        
                for file in [
                    joinPath(outputDir, '%s-%s-v%d.txt' % \
                             (session._databaseSet, schemaName, rev))
                        for rev in xrange(beginRev, endRev+1)
                ]
        ]
    else:
        files = [ f for f in iglob(joinPath(outputDir, '*.txt')) ]
        files.sort()
        for file in files:
            print "importing %s..." % file
            importIntegration(session, schemaName, file, getCmdLineOnly)
            
            
class IdenticalSchemaRevisions(Exception): pass

def reorderSessionsByEldestSchemaRev(adminSessions, schemaName):
    """
    Given two admin sessions, return a tuple containing both sessions, but with
    the session that has the highest schema revision for schemaName first.
    """
    if len(adminSessions) != 2:
        raise ValueError("incorrect number of elements in adminSessions, " \
                         "expected 2, got %d" % len(adminSessions))
    
    a1 = adminSessions[0]
    s1 = a1.getSchema(schemaName)
    r1 = s1.SchemaRevs    
    m1 = r1[len(r1)-1].RevID
    
    a2 = adminSessions[1]
    s2 = a2.getSchema(schemaName)
    r2 = s2.SchemaRevs    
    m2 = r2[len(r2)-1].RevID
    
    if m1 < m2:
        return ((a2, m2), (a1, m1))
    elif m1 > m2:
        return ((a1, m1), (a2, m2))
    else:
        raise IdenticalSchemaRevisions()
    
def manuallySyncSchemaRevisions(adminSessions, schemaName, outputDir=None):
    """
    
    """
    removeOutputDir = False
    try:
        if not outputDir:
            outputDir = mkdtemp()
            removeOutputDir = True
            
        src, dst = reorderSessionsByEldestSchemaRev(adminSessions, schemaName)
        
        srcSession, endRev = src
        dstSession, beginRev = dst
        
        exports = exportIntegrationRange(srcSession, schemaName,
                                         beginRev, endRev, outputDir,
                                         getCmdLineOnly=True)
        
        exportBatchFile = open(joinPath(outputDir,
                                        'export-%s-%s-v%d-%d.bat' % \
                                        (srcSession._databaseSet,
                                         schemaName,
                                         beginRev,
                                         endRev)), 'w')
        
        exportBatchFile.write('\n'.join(exports))
        exportBatchFile.close()
        print "wrote %s" % exportBatchFile.name
        
        imports = importIntegrationRange(dstSession, schemaName, outputDir,
                                         getCmdLineOnly=True,
                                         beginRev=beginRev,
                                         endRev=endRev)
        
        importsBatchFile = open(joinPath(outputDir,
                                        'import-%s-%s-v%d-%d.bat' % \
                                        (dstSession._databaseSet,
                                         schemaName,
                                         beginRev,
                                         endRev)), 'w')
        
        importsBatchFile.write('\n'.join(imports))
        importsBatchFile.close()
        print "wrote %s" % importsBatchFile.name
        
    except Exception, e:
        if removeOutputDir:
            try:
                os.remove(outputDir)
            except:
                pass
        raise e
            


def syncSchemaRevisions(sourceAdminSession,
                        destAdminSession,
                        schemaName,
                        outputDir,
                        getCmdLineOnly):
    pass
    