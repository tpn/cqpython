# -*- coding: mbcs -*-
# Created by makepy.py version 0.4.95
# By python version 2.5.1 (r251:54863, May  1 2007, 17:47:05) [MSC v.1310 32 bit (Intel)]
# From type library 'CQCom.dll'
# On Fri Apr 11 15:39:28 2008
"""CQCom 1.0 Type Library"""
makepy_version = '0.4.95'
python_version = 0x20501f0

from clearquest.util import CQBaseObject

import win32com.client.CLSIDToClass, pythoncom
import win32com.client.util
from pywintypes import IID
from win32com.client import Dispatch

# The following 3 lines may need tweaking for the particular server
# Candidates are pythoncom.Missing, .Empty and .ArgNotFound
defaultNamedOptArg=pythoncom.Empty
defaultNamedNotOptArg=pythoncom.Empty
defaultUnnamedArg=pythoncom.Empty

CLSID = IID('{9523D70A-417C-11D4-94FF-00105A179237}')
MajorVersion = 1
MinorVersion = 0
LibraryFlags = 8
LCID = 0x0

TopLevelObjects = ('Designer', 'DatabaseSetup', 'DatabaseAccess')

class Designer(CQBaseObject):
    CLSID = IID('{9523D717-417C-11D4-94FF-00105A179237}')
    coclass_clsid = IID('{9523D718-417C-11D4-94FF-00105A179237}')

    def CanUpgradeDatabase(self, bsDbName=defaultNamedNotOptArg):
        """method CanUpgradeDatabase"""
        return self._oleobj_.InvokeTypes(17, LCID, 1, (24, 0), ((8, 0),),bsDbName
            )

    def CheckinSchema(self, bsComment=defaultNamedNotOptArg):
        """method CheckinSchema"""
        return self._oleobj_.InvokeTypes(7, LCID, 1, (24, 0), ((8, 0),),bsComment
            )

    def CheckoutSchema(self, bsSchema=defaultNamedNotOptArg, bsComment=defaultNamedNotOptArg):
        """method CheckoutSchema"""
        return self._oleobj_.InvokeTypes(6, LCID, 1, (24, 0), ((8, 0), (8, 0)),bsSchema
            , bsComment)

    def ClearUniqueKey(self, bsTableName=defaultNamedNotOptArg):
        """method ClearUniqueKey"""
        return self._oleobj_.InvokeTypes(14, LCID, 1, (24, 0), ((8, 0),),bsTableName
            )

    def CreateEntityDef(self, bsTableName=defaultNamedNotOptArg):
        """method CreateEntityDef"""
        return self._oleobj_.InvokeTypes(2, LCID, 1, (24, 0), ((8, 0),),bsTableName
            )

    def CreateHookDef(self, bsTableName=defaultNamedNotOptArg, bsHookName=defaultNamedNotOptArg, iLanguage=defaultNamedNotOptArg, bsBody=defaultNamedNotOptArg):
        """method CreateHookDef"""
        return self._oleobj_.InvokeTypes(15, LCID, 1, (24, 0), ((8, 0), (8, 0), (3, 0), (8, 0)),bsTableName
            , bsHookName, iLanguage, bsBody)

    def CreateModifyAndDeleteActions(self, bsTableName=defaultNamedNotOptArg):
        """method CreateModifyAndDeleteActions"""
        return self._oleobj_.InvokeTypes(24, LCID, 1, (24, 0), ((8, 0),),bsTableName
            )

    def DeleteEntityDef(self, bsTableName=defaultNamedNotOptArg):
        """method DeleteEntityDef"""
        return self._oleobj_.InvokeTypes(9, LCID, 1, (24, 0), ((8, 0),),bsEntityDefName
            )

    def DeleteFieldDef(self, bsTableName=defaultNamedNotOptArg, bsFieldName=defaultNamedNotOptArg):
        """method DeleteFieldDef"""
        return self._oleobj_.InvokeTypes(10, LCID, 1, (24, 0), ((8, 0), (8, 0)),bsTableName
            , bsFieldName)

    def DeleteHookDef(self, bsTableName=defaultNamedNotOptArg, bsHookName=defaultNamedNotOptArg):
        """method DeleteHookDef"""
        return self._oleobj_.InvokeTypes(16, LCID, 1, (24, 0), ((8, 0), (8, 0)),bsTableName
            , bsHookName)

    def GetHookProperties(self, bsTableName=defaultNamedNotOptArg, bsHookName=defaultNamedNotOptArg, iLanguage=defaultNamedNotOptArg, Prologue=defaultNamedNotOptArg
            , Body=defaultNamedNotOptArg, Epilogue=defaultNamedNotOptArg):
        """method GetHookProperties"""
        return self._oleobj_.InvokeTypes(20, LCID, 1, (24, 0), ((8, 0), (8, 0), (3, 0), (16396, 0), (16396, 0), (16396, 0)),bsTableName
            , bsHookName, iLanguage, Prologue, Body, Epilogue
            )

    def GetHookTemplate(self, bsTableName=defaultNamedNotOptArg, bsHookName=defaultNamedNotOptArg, iLanguage=defaultNamedNotOptArg, Prologue=defaultNamedNotOptArg
            , Body=defaultNamedNotOptArg, Epilogue=defaultNamedNotOptArg):
        """method GetHookTemplate"""
        return self._ApplyTypes_(19, 1, (24, 0), ((8, 0), (8, 0), (3, 0), (16396, 3), (16396, 3), (16396, 3)), 'GetHookTemplate', None,bsTableName
            , bsHookName, iLanguage, Prologue, Body, Epilogue
            )

    def GetPlatformScriptLanguage(self, iPlatform=defaultNamedNotOptArg):
        """method GetPlatformScriptLanguage"""
        return self._oleobj_.InvokeTypes(22, LCID, 1, (3, 0), ((3, 0),),iPlatform
            )

    def IsOKToCheckOutSchema(self, bsSchema=defaultNamedNotOptArg):
        """method IsOKToCheckOutSchema"""
        return self._oleobj_.InvokeTypes(11, LCID, 1, (24, 0), ((8, 0),),bsSchema
            )

    def IsSchemaCheckedOut(self, bsSchema=defaultNamedNotOptArg):
        """method IsSchemaCheckedOut"""
        return self._oleobj_.InvokeTypes(13, LCID, 1, (24, 0), ((8, 0),),bsSchema
            )

    def Login(self, bsDbName=defaultNamedNotOptArg, bsUserName=defaultNamedNotOptArg, bsPassword=defaultNamedNotOptArg, bsDBSetName=defaultNamedNotOptArg):
        """method Login"""
        return self._oleobj_.InvokeTypes(1, LCID, 1, (24, 0), ((8, 0), (8, 0), (8, 0), (8, 0)),bsDbName
            , bsUserName, bsPassword, bsDBSetName)

    def Logoff(self):
        """method Logoff"""
        return self._oleobj_.InvokeTypes(5, LCID, 1, (24, 0), (),)

    def SetPlatformScriptLanguage(self, iPlatform=defaultNamedNotOptArg, iLanguage=defaultNamedNotOptArg):
        """method SetPlatformScriptLanguage"""
        return self._oleobj_.InvokeTypes(23, LCID, 1, (24, 0), ((3, 0), (3, 0)),iPlatform
            , iLanguage)

    def SetUniqueKey(self, bsTableName=defaultNamedNotOptArg, bsUniqueKey=defaultNamedNotOptArg, iSequence=defaultNamedNotOptArg):
        """method SetUniqueKey"""
        return self._oleobj_.InvokeTypes(12, LCID, 1, (24, 0), ((8, 0), (8, 0), (3, 0)),bsTableName
            , bsUniqueKey, iSequence)

    def UnCheckoutSchema(self):
        """method UnCheckoutSchema"""
        return self._oleobj_.InvokeTypes(8, LCID, 1, (24, 0), (),)

    def UpgradeDatabase(self, bsDbName=defaultNamedNotOptArg):
        """method UpgradeDatabase"""
        return self._oleobj_.InvokeTypes(4, LCID, 1, (24, 0), ((8, 0),),bsDbName
            )

    def UpgradeFieldDef(self, bsTableName=defaultNamedNotOptArg, bsFieldName=defaultNamedNotOptArg, iFieldType=defaultNamedNotOptArg, bsRelatedTable=defaultNamedNotOptArg):
        """method UpgradeFieldDef"""
        return self._oleobj_.InvokeTypes(3, LCID, 1, (24, 0), ((8, 0), (8, 0), (3, 0), (8, 0)),bsTableName
            , bsFieldName, iFieldType, bsRelatedTable)

    def ValidateSchema(self):
        """method ValidateSchema"""
        return self._oleobj_.InvokeTypes(18, LCID, 1, (24, 0), (),)

    _prop_map_get_ = {
    }
    _prop_map_put_ = {
    }

class DatabaseAccess(CQBaseObject):
    """ICQDBAccess Interface"""
    CLSID = IID('{071EC961-640D-11D4-950A-00105A179237}')
    coclass_clsid = IID('{5872B192-640C-11D4-950A-00105A179237}')

    def AllocateDbid(self, iCount=defaultNamedNotOptArg):
        """method AllocateDbid"""
        return self._oleobj_.InvokeTypes(5, LCID, 1, (3, 0), ((3, 0),),iCount
            )

    def CloseConnection(self):
        """method CloseConnection"""
        return self._oleobj_.InvokeTypes(3, LCID, 1, (24, 0), (),)

    def Execute(self, bsSQL=defaultNamedNotOptArg):
        """method Execute"""
        return self._oleobj_.InvokeTypes(2, LCID, 1, (3, 0), ((8, 0),),bsSQL
            )

    def FetchLong(self, bsSQL=defaultNamedNotOptArg):
        """method FetchLong"""
        return self._oleobj_.InvokeTypes(4, LCID, 1, (3, 0), ((8, 0),),bsSQL
            )

    def Initialize(self, bsDbName=defaultNamedNotOptArg, bsDBSetName=defaultNamedNotOptArg):
        """method Initialize"""
        return self._oleobj_.InvokeTypes(1, LCID, 1, (24, 0), ((8, 0), (8, 0)),bsDbName
            , bsDBSetName)

    _prop_map_get_ = {
    }
    _prop_map_put_ = {
    }

class DatabaseSetup(CQBaseObject):
    """ICQDBSetup Interface"""
    CLSID = IID('{725CFE51-8F38-11D4-9524-00105A179237}')
    coclass_clsid = IID('{F2EFF8B5-8E8E-11D4-9520-00105A179237}')

    def ApplyPackage(self, szDBSetName=defaultNamedNotOptArg, szLogin=defaultNamedNotOptArg, szPassword=defaultNamedNotOptArg, szSchemaName=defaultNamedNotOptArg
            , szPackageName=defaultNamedNotOptArg, szPackageRev=defaultNamedNotOptArg, bCheckin=defaultNamedNotOptArg):
        """method ApplyPackage"""
        return self._oleobj_.InvokeTypes(11, LCID, 1, (24, 0), ((8, 0), (8, 0), (8, 0), (8, 0), (8, 0), (8, 0), (3, 0)),szDBSetName
            , szLogin, szPassword, szSchemaName, szPackageName, szPackageRev
            , bCheckin)

    def ConnectToMaster(self, bsVendor=defaultNamedNotOptArg, bsServerName=defaultNamedNotOptArg, bsDbName=defaultNamedNotOptArg, bsDBMSUserName=defaultNamedNotOptArg
            , bsDBMSPassword=defaultNamedNotOptArg, bsLoginUserName=defaultNamedNotOptArg, bsLoginPassword=defaultNamedNotOptArg, bsConnectionOptions=defaultNamedNotOptArg):
        """method ConnectToMaster"""
        return self._oleobj_.InvokeTypes(2, LCID, 1, (24, 0), ((8, 0), (8, 0), (8, 0), (8, 0), (8, 0), (8, 0), (8, 0), (8, 0)),bsVendor
            , bsServerName, bsDbName, bsDBMSUserName, bsDBMSPassword, bsLoginUserName
            , bsLoginPassword, bsConnectionOptions)

    def GetDefaultConnectOptions(self, bsVendor=defaultNamedNotOptArg):
        """method GetDefaultConnectOptions"""
        return self._ApplyTypes_(12, 1, (12, 0), ((8, 0),), 'GetDefaultConnectOptions', None,bsVendor
            )

    def InstallPackage(self, szDBSetName=defaultNamedNotOptArg, szLogin=defaultNamedNotOptArg, szPassword=defaultNamedNotOptArg, szPackageName=defaultNamedNotOptArg
            , szPackageRev=defaultNamedNotOptArg, bCheckin=defaultNamedNotOptArg):
        """method InstallPackage"""
        return self._oleobj_.InvokeTypes(10, LCID, 1, (24, 0), ((8, 0), (8, 0), (8, 0), (8, 0), (8, 0), (3, 0)),szDBSetName
            , szLogin, szPassword, szPackageName, szPackageRev, bCheckin
            )

    def MoveMasterDb(self, bsCQAdminName=defaultNamedNotOptArg, bsCQAdminPass=defaultNamedNotOptArg, bsDBVendor=defaultNamedNotOptArg, bsDBServer=defaultNamedNotOptArg
            , bsDbName=defaultNamedNotOptArg, bsAdminName=defaultNamedNotOptArg, bsAdminPass=defaultNamedNotOptArg, bsRWUserName=defaultNamedNotOptArg, bsRWUserPass=defaultNamedNotOptArg
            , bsROUserName=defaultNamedNotOptArg, bsROUserPass=defaultNamedNotOptArg, bsConnectionOptions=defaultNamedNotOptArg, bsSqlProtocols=defaultNamedNotOptArg, bsSqaHostnames=defaultNamedNotOptArg):
        """method MoveMasterDb"""
        return self._oleobj_.InvokeTypes(3, LCID, 1, (24, 0), ((8, 0), (8, 0), (8, 0), (8, 0), (8, 0), (8, 0), (8, 0), (8, 0), (8, 0), (8, 0), (8, 0), (8, 0), (8, 0), (8, 0)),bsCQAdminName
            , bsCQAdminPass, bsDBVendor, bsDBServer, bsDbName, bsAdminName
            , bsAdminPass, bsRWUserName, bsRWUserPass, bsROUserName, bsROUserPass
            , bsConnectionOptions, bsSqlProtocols, bsSqaHostnames)

    def MoveUserDB(self, bsCQAdminName=defaultNamedNotOptArg, bsCQAdminPass=defaultNamedNotOptArg, bsUserDBName=defaultNamedNotOptArg, bsDBVendor=defaultNamedNotOptArg
            , bsDBServer=defaultNamedNotOptArg, bsDbName=defaultNamedNotOptArg, bsAdminName=defaultNamedNotOptArg, bsAdminPass=defaultNamedNotOptArg, bsRWUserName=defaultNamedNotOptArg
            , bsRWUserPass=defaultNamedNotOptArg, bsConnectionOptions=defaultNamedNotOptArg, bsSqlProtocols=defaultNamedNotOptArg, bsSqaHostnames=defaultNamedNotOptArg):
        """method MoveUserDB"""
        return self._oleobj_.InvokeTypes(6, LCID, 1, (24, 0), ((8, 0), (8, 0), (8, 0), (8, 0), (8, 0), (8, 0), (8, 0), (8, 0), (8, 0), (8, 0), (8, 0), (8, 0), (8, 0)),bsCQAdminName
            , bsCQAdminPass, bsUserDBName, bsDBVendor, bsDBServer, bsDbName
            , bsAdminName, bsAdminPass, bsRWUserName, bsRWUserPass, bsConnectionOptions
            , bsSqlProtocols, bsSqaHostnames)

    def RegisterPackage(self, szPackageName=defaultNamedNotOptArg, szPackageRev=defaultNamedNotOptArg, szPackageFolder=defaultNamedNotOptArg):
        """method RegisterPackage"""
        return self._oleobj_.InvokeTypes(9, LCID, 1, (24, 0), ((8, 0), (8, 0), (8, 0)),szPackageName
            , szPackageRev, szPackageFolder)

    def RelocateMasterDB(self, bsDBVendor=defaultNamedNotOptArg, bsDBServer=defaultNamedNotOptArg, bsDbName=defaultNamedNotOptArg, bsAdminName=defaultNamedNotOptArg
            , bsAdminPass=defaultNamedNotOptArg, bsRWUserName=defaultNamedNotOptArg, bsRWUserPass=defaultNamedNotOptArg, bsROUserName=defaultNamedNotOptArg, bsROUserPass=defaultNamedNotOptArg
            , bsConnectionOptions=defaultNamedNotOptArg, bsSqlProtocols=defaultNamedNotOptArg, bsSqaHostnames=defaultNamedNotOptArg):
        """method UpdateMasterLocation"""
        return self._oleobj_.InvokeTypes(4, LCID, 1, (24, 0), ((8, 0), (8, 0), (8, 0), (8, 0), (8, 0), (8, 0), (8, 0), (8, 0), (8, 0), (8, 0), (8, 0), (8, 0)),bsDBVendor
            , bsDBServer, bsDbName, bsAdminName, bsAdminPass, bsRWUserName
            , bsRWUserPass, bsROUserName, bsROUserPass, bsConnectionOptions, bsSqlProtocols
            , bsSqaHostnames)

    def RelocateUserDB(self, bsCQAdminName=defaultNamedNotOptArg, bsCQAdminPass=defaultNamedNotOptArg, bsUserDBName=defaultNamedNotOptArg, bsDBVendor=defaultNamedNotOptArg
            , bsDBServer=defaultNamedNotOptArg, bsDbName=defaultNamedNotOptArg, bsAdminName=defaultNamedNotOptArg, bsAdminPass=defaultNamedNotOptArg, bsRWUserName=defaultNamedNotOptArg
            , bsRWUserPass=defaultNamedNotOptArg, bsConnectionOptions=defaultNamedNotOptArg, bsSqlProtocols=defaultNamedNotOptArg, bsSqaHostnames=defaultNamedNotOptArg):
        """method RelocateUserDB"""
        return self._oleobj_.InvokeTypes(5, LCID, 1, (24, 0), ((8, 0), (8, 0), (8, 0), (8, 0), (8, 0), (8, 0), (8, 0), (8, 0), (8, 0), (8, 0), (8, 0), (8, 0), (8, 0)),bsCQAdminName
            , bsCQAdminPass, bsUserDBName, bsDBVendor, bsDBServer, bsDbName
            , bsAdminName, bsAdminPass, bsRWUserName, bsRWUserPass, bsConnectionOptions
            , bsSqlProtocols, bsSqaHostnames)

    def SetActiveDBSet(self, bsDBSet=defaultNamedNotOptArg):
        """method SetActiveDBSet"""
        return self._oleobj_.InvokeTypes(1, LCID, 1, (24, 0), ((8, 0),),bsDBSet
            )

    def UnlockMasterDB(self, bsVendor=defaultNamedNotOptArg, bsServerName=defaultNamedNotOptArg, bsDbName=defaultNamedNotOptArg, bsUserName=defaultNamedNotOptArg
            , bsPassword=defaultNamedNotOptArg, bsConnectionOptions=defaultNamedNotOptArg):
        """method UnlockMasterDB"""
        return self._oleobj_.InvokeTypes(7, LCID, 1, (24, 0), ((8, 0), (8, 0), (8, 0), (8, 0), (8, 0), (8, 0)),bsVendor
            , bsServerName, bsDbName, bsUserName, bsPassword, bsConnectionOptions
            )

    def UnlockUserDB(self, bsVendor=defaultNamedNotOptArg, bsServerName=defaultNamedNotOptArg, bsDbName=defaultNamedNotOptArg, bsUserName=defaultNamedNotOptArg
            , bsPassword=defaultNamedNotOptArg, bsConnectionOptions=defaultNamedNotOptArg):
        """method UnlockUserDB"""
        return self._oleobj_.InvokeTypes(8, LCID, 1, (24, 0), ((8, 0), (8, 0), (8, 0), (8, 0), (8, 0), (8, 0)),bsVendor
            , bsServerName, bsDbName, bsUserName, bsPassword, bsConnectionOptions
            )

    _prop_map_get_ = {
    }
    _prop_map_put_ = {
    }


RecordMap = {
}

CLSIDToClassMap = {
    '{9523D717-417C-11D4-94FF-00105A179237}' : Designer,
    '{725CFE51-8F38-11D4-9524-00105A179237}' : DatabaseSetup,
    '{071EC961-640D-11D4-950A-00105A179237}' : DatabaseAccess,
}
CLSIDToPackageMap = {}
win32com.client.CLSIDToClass.RegisterCLSIDsFromDict( CLSIDToClassMap )
VTablesToPackageMap = {}
VTablesToClassMap = {
    '{9523D717-417C-11D4-94FF-00105A179237}' : 'Designer',
    '{725CFE51-8F38-11D4-9524-00105A179237}' : 'DatabaseSetup',
    '{071EC961-640D-11D4-950A-00105A179237}' : 'DatabaseAccess',
}

NamesToIIDMap = {
    'Designer'          : '{9523D717-417C-11D4-94FF-00105A179237}',
    'DatabaseSetup'     : '{725CFE51-8F38-11D4-9524-00105A179237}',
    'DatabaseAccess'    : '{071EC961-640D-11D4-950A-00105A179237}',
}



