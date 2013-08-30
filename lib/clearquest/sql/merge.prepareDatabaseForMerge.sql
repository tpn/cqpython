DELETE FROM ${dstPrefix}.list_member 
DELETE FROM ${dstPrefix}.parent_child_links
DELETE FROM ${dstPrefix}.users WHERE dbid <> 0
DELETE FROM ${dstPrefix}.groups WHERE dbid <> 0
DELETE FROM ${dstPrefix}.bucket WHERE dbid <> 0
DELETE FROM ${dstPrefix}.user_blob WHERE dbid <> 0
UPDATE
    ${dstPrefix}.dbglobal
SET
    next_request_id = 1,
    next_aux_id = 1
