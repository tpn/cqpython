
class CQConstant(dict):
    def __init__(self):
        items = self.__class__.__dict__.items()
        for (key, value) in filter(lambda t: t[0][:2] != '__', items):
            try:
                self[value] = key
            except:
                pass
    def __getattr__(self, name):
        return self.__getitem__(name)
    def __setattr__(self, name, value):
        return self.__setitem__(name, value)            
    
class _ActionType(CQConstant):
    Submit      = 1
    Modify      = 2
    ChangeState = 3
    Duplicate   = 4
    Unduplicate = 5
    Import      = 6
    Delete      = 7
    Base        = 8
    RecordScriptAlias = 9
ActionType = _ActionType()

class _AuthenticationAlgorithm(CQConstant):
    CQFirst = 2
    CQOnly  = 3
AuthenticationAlgorithm = _AuthenticationAlgorithm()

class _AuthenticationMode(CQConstant):
    LDAP = 1
    CQ   = 2
AuthenticationMode = _AuthenticationMode()

class _Behavior(CQConstant):
    Mandatory   = 1
    Optional    = 2
    ReadOnly    = 3
    UseHook     = 4
Behavior = _Behavior()

class _BoolOp(CQConstant):
    And = 1
    Or  = 2
BoolOp = _BoolOp()

class _ChoiceType(CQConstant):
    Closed  = 1
    Open    = 2
ChoiceType = _ChoiceType()

class _DatabaseVendor(CQConstant):
    SQLServer   = 1
    Access      = 2
    SQLAnywhere = 3
    Oracle      = 4
    DB2         = 5
DatabaseVendor = _DatabaseVendor()
UppercaseDatabases = (
    DatabaseVendor.Oracle,
    DatabaseVendor.DB2
)

class _DbAggregate(CQConstant):
    Count   = 1
    Sum     = 2
    Average = 3
    Min     = 4
    Max     = 5
DbAggregate = _DbAggregate()

class _DbFunction(CQConstant):
    Day     = 1
    Week    = 2
    Month   = 3
    Year    = 4
DbFunction = _DbFunction()

class _EntityStatus(CQConstant):
    NotFound    = 1
    Visible     = 2
    Hidden      = 3
EntityStatus = _EntityStatus()

class _EntityType(CQConstant):
    Stateful    = 1
    Stateless   = 2
    Any         = 3
EntityType = _EntityType()

class _EventType(CQConstant):
    ButtonClick              = 1
    SubdialogButtonClick     = 2
    ItemSelection            = 3
    ItemDoubleClick          = 4
    ContextMenuItemSelection = 5
    ContextMenuItemCondition = 6
EventType = _EventType()

class _FetchStatus(CQConstant):
    Success         = 1
    NoDataFound     = 2
    MaxRowsExceeded = 3
FetchStatus = _FetchStatus()

class _FieldType(CQConstant):
    ShortString     = 1
    MultilineString = 2
    Integer         = 3
    DateTime        = 4
    Reference       = 5
    ReferenceList   = 6
    AttachmentList  = 7
    Id              = 8
    State           = 9
    Journal         = 10
    DbId            = 11
    StateType       = 12
    RecordType      = 13
FieldType = _FieldType()
FieldType.referenceTypes = (
    FieldType.Reference,
    FieldType.ReferenceList,
    FieldType.AttachmentList,
)
FieldType.listTypes = (
    FieldType.ReferenceList,
    FieldType.AttachmentList,
    FieldType.Journal, 
)
FieldType.readOnlyListTypes = (
    FieldType.Journal,                               
)
FieldType.writeableListTypes = (
    FieldType.ReferenceList,
    FieldType.AttachmentList,
)
FieldType.scalarTypes = (
    FieldType.ShortString,
    FieldType.MultilineString,
    FieldType.Integer,
    FieldType.DateTime,
    FieldType.Reference,
    FieldType.Id,
    FieldType.State,
    FieldType.DbId,
    FieldType.StateType,
    FieldType.RecordType,
)
FieldType.dbScalarTypes = (
    FieldType.ShortString,
    FieldType.MultilineString,
    FieldType.Integer,
    FieldType.DateTime,
    FieldType.Id,
    FieldType.State,
    FieldType.DbId,
)
FieldType.readOnlyScalarTypes = (
    FieldType.Id,
    FieldType.DbId,
    FieldType.State,
    FieldType.StateType,
    FieldType.RecordType,
)
FieldType.writeableScalarTypes = (
    FieldType.ShortString,
    FieldType.MultilineString,
    FieldType.Integer,
    FieldType.DateTime,
    FieldType.Reference,
)
FieldType.uniqueKeyTypes = (
    FieldType.ShortString,
    FieldType.Integer,
    FieldType.DateTime,
    FieldType.Reference,
    FieldType.DbId,
)
FieldType.textTypes = (
    FieldType.ShortString,
    FieldType.MultilineString,
)
class _QueryType(CQConstant):
    List    = 1
    Report  = 2
    Chart   = 3
QueryType = _QueryType()

class _ReturnString(CQConstant):
    Local   = 1
    Unicode = 2
ReturnString = _ReturnString()

class _SessionClassType(CQConstant):
    User    = 1
    Admin   = 2
SessionClassType = _SessionClassType()

class _SessionType(CQConstant):
    Shared          = 1
    Private         = 2
    Admin           = 3
    SharedMetadata  = 4
SessionType = _SessionType()

class _SortType(CQConstant):
    Ascending   = 1
    Descending  = 2
SortType = _SortType()

class _ValueStatus(CQConstant):
    HasNoValue          = 1
    HasValue            = 2
    ValueNotAvailable   = 3
ValueStatus = _ValueStatus()

class _WorkspaceFolderType(CQConstant):
    Public = 1
    Personal = 2
WorkspaceFolderType = _WorkspaceFolderType()

class _WorkspaceItemType(CQConstant):
    Query              = 1
    Chart              = 2
    Folder             = 3
    Favorites          = 5
    QueryParameters    = 6
    Preferences        = 7
    Report             = 9
    ReportFormat       = 10
    StartupBucketArray = 11    
WorkspaceItemType = _WorkspaceItemType()

WorkspaceItemTypeMap = {
    WorkspaceItemType.Query  : 'QueryDef',
    WorkspaceItemType.Chart  : 'QueryDef',
    WorkspaceItemType.Folder : 'Folder',
}

class _WorkspaceNameOption(CQConstant):
    NotExtended = 1
    Extended = 2
    ExtendedWhenNeeded = 3
WorkspaceNameOption = _WorkspaceNameOption()

class _UserPrivilegeMaskType(CQConstant):
    DynamicListAdmin    = 1
    PublicFolderAdmin   = 2
    SecurityAdmin       = 3
    RawSQLWriter        = 4
    AllUsersVisible     = 5
    MultiSiteAdmin      = 6
UserPrivilegeMaskType = _UserPrivilegeMaskType()

