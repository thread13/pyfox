#!/usr/bin/python3
# -*- coding: utf-8 -*-

"""
    Here we can add a number of "permanent" SQL query filters for history queries,
    which will be added as additional "NOT LIKE" conditions -- e.g. "twitter.com"
    will result in a clause "AND url NOT LIKE '%twitter.com%'" --
    -- i.e. tokens without '%' in them would be treated 
    as if they were wrapped by '%'-symbols ( a globbing character for SQL LIKE predicates ).
"""

# any urls that match these filters would be _omitted_ from the results
HISTORY_SQL_URL_FILTERS = ( '%google.com%' 
                          # , '%gmail.com%' 
                          , '%facebook.com%' 
                          # , '%amazon.com%' 
                          , '%127.0.0.1%' 
                          , '%duckduckgo.com%'
                          # , '%change.org%' 
                          , '%twitter.com%' 
                          # , '%google.co.in%' 
                          )

