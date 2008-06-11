import os
import sys
import dbi
import pyodbc as odbc
from subprocess import Popen, PIPE
from functools import wraps
from inspect import ismethod, isfunction
from os.path import dirname, isfile
from win32api import RegCloseKey, RegOpenKeyEx, RegQueryValueEx
from win32con import HKEY_LOCAL_MACHINE, KEY_QUERY_VALUE
from genshi.template import TemplateLoader, TextTemplate
from clearquest.util import listToMap, joinPath, cache, Dict, readRegKey
from clearquest.constants import DatabaseVendor

#===============================================================================
# Exceptions 
#===============================================================================

class DatabaseVendorNotSupported(Exception): pass            
class DatabaseVendorNotDiscernableFromSQL_DBMS_NAME(Exception): pass

class DatabaseError(Exception):
    """
    Helper class for wrapping any DBI error we may encounter in a single class.
    """
    def __init__(self, details, sql):
        self.args = (details, "Offending SQL:\n%s" % sql)
        
#===============================================================================
# Globals
#===============================================================================

_SqlTemplateDir = joinPath(dirname(__file__), 'sql')
_SqlLoader = TemplateLoader(_SqlTemplateDir, 
                            default_class=TextTemplate,
                            variable_lookup='strict',
                            auto_reload=True)

#===============================================================================
# Decorators
#===============================================================================

def sql(mf):
    @wraps(mf)
    def decorator(f):
        fname = f.func_name
        @wraps(f)
        def newf(*_args, **_kwds):
            this = _args[0]
            prefixes = (this.__class__.__name__,
                        f.__module__.replace('clearquest.', ''))
            try:
                db = this.db()
            except AttributeError:
                db = this.session.db()
            
            args = list(_args)
            kwds = dict(_kwds)
                
            m = f(*args, **kwds)
            if isinstance(m, dict):
                kwds.update(m)
            elif isinstance(m, (list, tuple)):
                args += m
            elif m is not None:
                args += (m,)
                        
            kwds['this'] = this
            sql = db.findSql(prefixes, fname, *args, **kwds)
            return getattr(db, mf.func_name)(sql, *args[1:])
        return newf
    return decorator

@sql
def select(f): pass

@sql
def selectSingle(f): pass

@sql
def selectAll(f): pass

@sql
def execute(f): pass

@sql
def getSql(f): pass

#===============================================================================
# Helper Methods
#===============================================================================

def getConnectOptionsFromRegistry(dbset, db):
    """
    @param dbset: L{str} database set name (e.g. 'Classics')
    @param db:    L{str} database name (e.g. 'CLSIC')
    @return: L{str} a string representing the connect options for the given
             database set and database (or an empty string if none are present)
    """
    # Get the 'CurrentVersion' of ClearQuest from the registry.
    path = 'Software\\Rational Software\\ClearQuest'
    try:
        key = RegOpenKeyEx(HKEY_LOCAL_MACHINE, path, 0, KEY_QUERY_VALUE)
    except:
        raise
    else:
        try:
            ver, dummy = RegQueryValueEx(key, 'CurrentVersion')
        except:
            raise
        else:
            if not ver:
                raise RuntimeError, 'No value for HKLM\\%s\\%s' % \
                                    (path, 'CurrentVersion')
        finally:
            RegCloseKey(key)
    
    # Now get the 'ConnectOptions' string.
    path = '%s\\%s\\Core\\Databases\\%s\\%s' % (path, ver, dbset, db) 
    try:
        key = RegOpenKeyEx(HKEY_LOCAL_MACHINE, path, 0, KEY_QUERY_VALUE)
    except:
        raise
    else:
        try:
            connectOptions, dummy = RegQueryValueEx(key, 'ConnectOptions')
        except:
            raise
        finally:
            RegCloseKey(key)        
    
    return connectOptions

#===============================================================================
# Private Methods
#===============================================================================

def _findSql(session, classOrModuleName, methodName, *args, **kwds):
    vendor = session.getDatabaseVendorName()
    fileName = '%s.%s.%s.sql' % (classOrModuleName, methodName, vendor)
    if not isfile(joinPath(_SqlTemplateDir, fileName)):
        fileName = '%s.%s.sql' % (classOrModuleName, methodName)
    
    return _SqlLoader.load(fileName) \
                     .generate(args=args, **kwds) \
                     .render('text')

def _getSqlCmdExe():
    p = 'Software/Microsoft/Microsoft SQL Server/90/Tools/ClientSetup/Path'
    exe = joinPath(readRegKey(p), 'sqlcmd.exe')
    if not os.path.isfile(exe):
        raise RuntimeError("sqlcmd.exe does not exist at: %s" % exe)
    return exe

def _sqlcmd(session, sql, stdout=PIPE, stderr=PIPE):
    conf = Dict(session.connectStringToMap())
    f = open(r'c:\temp\foo.sql', 'w').write(sql)
    args = (
        _getSqlCmdExe(),
        '-U',   conf.UID,
        '-P',   conf.PWD,
        '-S',   conf.SERVER,
        '-d',   conf.DB,
        '-r', '1', # Redirect everything to stderr
        '-b',      # Return immediately when an error occurs
        '-i', r'C:\temp\foo.sql',
    )
    print 'running:\n%s' % ' '.join(args)
    return
    p = Popen(args, stdout=PIPE, stderr=PIPE)
    p.wait()
    return p
    

#===============================================================================
# Classes
#===============================================================================

class Connection(object):
    def __init__(self, connectString):
        self._connectString = connectString
        self._con = odbc.connect(self._connectString, autocommit=True)
    
    def _execute(self, sql, *args):
        try:
            return self._con.cursor().execute(sql, *args)
        except (odbc.DatabaseError,
                odbc.DataError,
                odbc.Error,
                odbc.IntegrityError,
                odbc.InterfaceError,
                odbc.InternalError,
                odbc.NotSupportedError,
                odbc.OperationalError,
                odbc.ProgrammingError), details:
            raise DatabaseError(details, sql)
    
    def select(self, sql, *args):
        cursor = self._execute(sql, *args)
        single = len(cursor.description) == 1
        for row in iter(lambda: cursor.fetchone(), None):
            yield row[0] if single else row
        
    def selectAsDict(self, sql, *args):
        cursor = self._execute(sql, *args)
        description = [ d[0] for d in cursor.description ]
        for row in iter(lambda: cursor.fetchone(), None):
            yield dict(zip(description, row))
    
    def selectAll(self, sql, *args):
        cursor = self._execute(sql, *args)
        single = len(cursor.description) == 1
        results = cursor.fetchall()
        return results if not single else [ row[0] for row in results ]
    
    def selectAllAsDict(self, sql, *args):
        cursor = self._execute(sql, *args)
        description = [ d[0] for d in cursor.description ]
        results = cursor.fetchall()
        return [ dict(zip(description, row)) for row in results ]
    
    def selectSingle(self, sql, *args):
        cursor = self._execute(sql, *args)
        try:
            return cursor.fetchone()[0]
        except TypeError:
            return None
    
    def execute(self, sql, *args):
        return self._execute(sql, *args)
    
    def getSql(self, sql, *args):
        return sql, args
    
    @cache
    def getDatabaseVendor(self):
        """
        @return: L{constants.DatabaseVendor}
        """
        vendor = self.getinfo(odbc.SQL_DBMS_NAME)
        if vendor == 'ACCESS':
            return DatabaseVendor.Access
        elif vendor == 'Oracle':
            return DatabaseVendor.Oracle
        elif vendor == 'Microsoft SQL Server':
            return DatabaseVendor.SQLServer
        elif 'DB2' in vendor:
            return DatabaseVendor.DB2
        else:
            raise DatabaseVendorNotDiscernableFromSQL_DBMS_NAME, vendor
    
    def findSql(self, prefixes, name, *args, **kwds):
        vendor = DatabaseVendor[self.getDatabaseVendor()]
        # Ugh, this is ugly.
        for prefix in prefixes:
            fileName = '%s.%s.%s.sql' % (prefix, name, vendor)
            if isfile(joinPath(_SqlTemplateDir, fileName)):
                break
            fileName = '%s.%s.sql' % (prefix, name)
            if isfile(joinPath(_SqlTemplateDir, fileName)):
                break
    
        return _SqlLoader.load(fileName) \
                         .generate(args=args, **kwds) \
                         .render('text')

    def getTablePrefix(self):
        return self._parent.getTablePrefix()
    
    def getDboTablePrefix(self):
        if self.getDatabaseVendor() != DatabaseVendor.SQLServer:
            raise NotImplementedError
        else:
            return '%s.%s'.lower() % (self.catalog(), 'dbo')
            
    def columns(self, tableName):
        return [ 
            (c[3].lower(),) + c[4:]
                for c in self.cursor()
                             .columns(schema=self.schema(),
                                      catalog=self.catalog(),
                                      table=tableName.upper()).fetchall()
        ]
    
    def tables(self):
        return [
            t[2] for t in
                self.cursor().tables(schema=self.schema(),
                                     catalog=self.catalog()).fetchall()
        ]
    
    def indexes(self, table):
        return listToMap([
            i[5] for i in self.cursor()
                              .statistics(table,
                                          schema=self.schema(),
                                          catalog=self.catalog()).fetchall()
                                              if i[5] is not None
        ]).keys()

    @cache
    def catalog(self):
        p = self.getTablePrefix()
        return p.split('.')[0].upper() if '.' in p else ''
    
    @cache
    def schema(self):
        p = self.getTablePrefix()
        return p.split('.')[1].upper() if '.' in p else p
        
    def __getattr__(self, attr):
        return getattr(self._con, attr)
    
    def dropAllConstraints(self):
        if self.getDatabaseVendor() == DatabaseVendor.SQLServer:
            sql = "SELECT o.name, fk.name FROM sys.foreign_keys fk, "       \
                  "sys.objects o WHERE fk.parent_object_id = o.object_id "  \
                  "AND o.type = 'U'"
            drop = "ALTER TABLE %s DROP CONSTRAINT %s"
            for (key, table) in self.selectAll(sql):
                self.execute(drop % (key, table))
            self.commit()
                             
        else:
            raise NotImplementedError    


class CQDbConnection(Connection):
    def __init__(self, parent):
        self._parent = parent
        try:
            self._databaseSet = parent._databaseSet
            self._databaseName = parent._databaseName
            connectString = parent.connectString()
        
        except AttributeError:
            raise TypeError, "Unsupported parameter type for parent argument: "\
                             "'%s'.  Supported types: api.Session, " \
                             "api.AdminSession" % repr(parent)

        Connection.__init__(self, connectString)
        
    