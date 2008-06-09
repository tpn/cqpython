"""
clearquest.database: module for database related methods/classes.
"""

#===============================================================================
# Imports
#===============================================================================

import os
import sys

from os.path import abspath, dirname

from genshi.template import TemplateLoader, TextTemplate

from twisted.enterprise import adbapi

#===============================================================================
# Globals
#===============================================================================
__rcsid__ = '$Id$'
__rcsurl__ = '$URL$'
__copyright__ = 'Copyright 2008 OnResolve Ltd'

#===============================================================================
# Methods
#===============================================================================

def getSqlPaths():
    if 'clearquest' not in sys.modules:
        import clearquest
        
    paths = list()
    basedir = dirname(abspath(sys.modules['clearquest'].__file__))
    for root, dirs, files in os.walk(basedir):
        if root.endswith('sql'):
            paths.append(root)
            
    return paths

#===============================================================================
# Classes
#===============================================================================

#class SqlFactory(object):
    #PATHS = getSqlPaths()
    #def __init__(self, session):
        #self.session = session
        #self.paths = getSqlPaths()
        #self.vendor = session.getDatabaseVendorName()
        #self.loader = TemplateLoader(search_path=None,
                                     #default_class=TextTemplate,
                                     #variable_lookup='strict',
                                     #auto_reload=True)
    
    #def findFile(self, name):
        #moduleName = ''
        #parts = name.split('.')
        #parts.pop
        #(moduleName, classOrMethodName, sqlName) = name.split('.')

#class Connection(adbapi.Connection):
    #pass

#class Transaction(adbapi.Transaction):
    #pass

#class ConnectionPool(adbapi.ConnectionPool):
    #def __init__(self, parent):
        #self._parent = parent
        #try:
            #self._databaseSet = parent._databaseSet
            #self._databaseName = parent._databaseName
            #self._connectString = parent.connectString()
        
        #except AttributeError:
            #raise TypeError, "Unsupported parameter type for parent argument: "\
                             #"'%s'.  Supported types: api.Session, " \
                             #"api.AdminSession" % repr(parent)
                            
        #self._con = odbc.connect(self._connectString, autocommit=True)
    
    #def _execute(self, sql, *args):
        #try:
            #return self._con.cursor().execute(sql, *args)
        #except (odbc.DatabaseError,
                #odbc.DataError,
                #odbc.Error,
                #odbc.IntegrityError,
                #odbc.InterfaceError,
                #odbc.InternalError,
                #odbc.NotSupportedError,
                #odbc.OperationalError,
                #odbc.ProgrammingError), details:
            #raise DatabaseError(details, sql)
    
    #def select(self, sql, *args):
        #cursor = self._execute(sql, *args)
        #single = len(cursor.description) == 1
        #for row in iter(lambda: cursor.fetchone(), None):
            #yield row[0] if single else row
        
    #def selectAsDict(self, sql, *args):
        #cursor = self._execute(sql, *args)
        #description = [ d[0] for d in cursor.description ]
        #for row in iter(lambda: cursor.fetchone(), None):
            #yield dict(zip(description, row))
    
    #def selectAll(self, sql, *args):
        #cursor = self._execute(sql, *args)
        #single = len(cursor.description) == 1
        #results = cursor.fetchall()
        #return results if not single else [ row[0] for row in results ]
    
    #def selectAllAsDict(self, sql, *args):
        #cursor = self._execute(sql, *args)
        #description = [ d[0] for d in cursor.description ]
        #results = cursor.fetchall()
        #return [ dict(zip(description, row)) for row in results ]
    
    #def selectSingle(self, sql, *args):
        #cursor = self._execute(sql, *args)
        #try:
            #return cursor.fetchone()[0]
        #except TypeError:
            #return None
    
    #def execute(self, sql, *args):
        #return self._execute(sql, *args)
    
    #def getSql(self, sql, *args):
        #return sql, args
    
    #@cache
    #def getDatabaseVendor(self):
        #"""
        #@return: L{constants.DatabaseVendor}
        #"""
        #vendor = self.getinfo(odbc.SQL_DBMS_NAME)
        #if vendor == 'ACCESS':
            #return DatabaseVendor.Access
        #elif vendor == 'Oracle':
            #return DatabaseVendor.Oracle
        #elif vendor == 'Microsoft SQL Server':
            #return DatabaseVendor.SQLServer
        #elif 'DB2' in vendor:
            #return DatabaseVendor.DB2
        #else:
            #raise DatabaseVendorNotDiscernableFromSQL_DBMS_NAME, vendor
    
    #def findSql(self, prefixes, name, *args, **kwds):
        #vendor = DatabaseVendor[self.getDatabaseVendor()]
        ## Ugh, this is ugly.
        #for prefix in prefixes:
            #fileName = '%s.%s.%s.sql' % (prefix, name, vendor)
            #if isfile(joinPath(_SqlTemplateDir, fileName)):
                #break
            #fileName = '%s.%s.sql' % (prefix, name)
            #if isfile(joinPath(_SqlTemplateDir, fileName)):
                #break
    
        #return _SqlLoader.load(fileName) \
                         #.generate(args=args, **kwds) \
                         #.render('text')

    #def getTablePrefix(self):
        #return self._parent.getTablePrefix()
    
    #def getDboTablePrefix(self):
        #if self.getDatabaseVendor() != DatabaseVendor.SQLServer:
            #raise NotImplementedError
        #else:
            #return '%s.%s'.lower() % (self.catalog(), 'dbo')
            
    #def columns(self, tableName):
        #return [ 
            #(c[3].lower(),) + c[4:]
                #for c in self.cursor()
                             #.columns(schema=self.schema(),
                                      #catalog=self.catalog(),
                                      #table=tableName.upper()).fetchall()
        #]
    
    #def tables(self):
        #return [
            #t[2] for t in
                #self.cursor().tables(schema=self.schema(),
                                     #catalog=self.catalog()).fetchall()
        #]
    
    #def indexes(self, table):
        #return listToMap([
            #i[5] for i in self.cursor()
                              #.statistics(table,
                                          #schema=self.schema(),
                                          #catalog=self.catalog()).fetchall()
                                              #if i[5] is not None
        #]).keys()

    #@cache
    #def catalog(self):
        #p = self.getTablePrefix()
        #return p.split('.')[0].upper() if '.' in p else ''
    
    #@cache
    #def schema(self):
        #p = self.getTablePrefix()
        #return p.split('.')[1].upper() if '.' in p else p
        
    #def __getattr__(self, attr):
        #return getattr(self._con, attr)
        
        
        
        