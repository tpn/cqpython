SELECT DISTINCT  
    'UPDATE ' || e.db_name || ' ' ||   
    'SET id = ''' || db.site_name || ''' || SUBSTR(id, -8, 8) ' ||   
    'WHERE dbid <> 0 AND ' ||   
    'SUBSTR(id, 0, ' || TO_CHAR(LENGTH(db.site_name)) ||    
    ') <> '''|| db.site_name || ''''        
FROM  
    entitydef e   
INNER JOIN  
    history h ON  
        h.entitydef_id = e.id   
INNER JOIN  
    dbglobal db ON  
        db.site_name IS NOT NULL  
WHERE  
    e.type = 1   