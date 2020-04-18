SELECT url, title, last_visit_date,rev_host
    FROM moz_historyvisits 
    NATURAL JOIN moz_places 
    WHERE last_visit_date IS NOT NULL 
        AND url LIKE 'http%' 
        AND title IS NOT NULL ;
        /* use 'pyfox_filters.py' instead */
        -- AND url NOT LIKE '%google.com%' 
        -- AND url NOT LIKE '%gmail.com%' 
        -- AND url NOT LIKE '%facebook.com%' 
        -- AND url NOT LIKE '%amazon.com%' 
        -- AND url NOT LIKE '%127.0.0.1%' 
        -- AND url NOT LIKE '%duckduckgo.com%'
        -- AND url NOT LIKE '%change.org%' 
        -- AND url NOT LIKE '%twitter.com%' 
        -- AND url NOT LIKE '%google.co.in%' ;
