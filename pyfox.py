#!/usr/bin/python3
# -*- coding: utf-8 -*-

'''
author: @thewhitetulip

A small python script to extract browsing history and bookmarks from  various
browsers, currently supports firefox and chromium (partially)

'''

import sqlite3
import os
from datetime import datetime
import sys
import argparse
import webbrowser
import tempfile
import fnmatch
import shutil


# -----------------------------------------------------------------------------------
# constants

# "dev mode" with full tracebacks
_dbg = True # change this in production
if _dbg:
    import cgitb
    cgitb.enable(format='text')

# Firefox history database name, see
# [ https://developer.mozilla.org/en-US/docs/Mozilla/Tech/Places/Database ]
DBNAME = 'places.sqlite'

# moving SQL code to external files makes it easier to test with sqlite3 utility, e.g. :
#   "echo '.read test_query.sql | sqlite3 places.sqlite"
FF_QUERY_BOOKMARKS = 'bookmarks_query.sql'
FF_QUERY_HISTORY   = 'history_query.sql'
# this can be wrapped with some function/class and invoked from __main__,
# however, for a small utility it shall just do
PROGDIR = os.path.dirname( sys.argv[0] )
## print( f"PROGDIR: {PROGDIR!r}" )

# converting to paths relative to sys.argv[0]
FF_QUERY_BOOKMARKS = os.path.join( PROGDIR, FF_QUERY_BOOKMARKS )
FF_QUERY_HISTORY   = os.path.join( PROGDIR, FF_QUERY_HISTORY )

# attaching js table filtering code, see [  ]
JQ_MIN_PATH = 'jquery.min.js'
JQ_FT_PATH  = 'jquery.filtertable.min.js'

# -----------------------------------------------------------------------------------

def execute_query(cursor, query):
    ''' Takes the cursor object and the query, executes it '''
    try:
        cursor.execute(query)
    except Exception as error:
        if not _dbg:
            print(str(error) + "\n " + query)
        else:
            raise


# an external wrapper
def run_query_wrapper( dbname, query ):
    """ a generator ; opens an sqlite database, runs a query, 
        yields rows, closes the connection """

    if _dbg:
        print( dbname )
        print( query )

    try:
        for row in run_query( dbname, query ):
            yield row

    except Exception as error:
        if _dbg:
            raise
        else:
            print(str(error) + "\n " + query)
            ## sys.exit(2)


# next-level wrapper: tries to open an existing database, 
# and reopens a temporary if that fails ;
# calls an internal function to actually run a query )
def run_query( dbname, query ):
    """ a generator ; opens an sqlite database, runs a query, 
        yields rows, closes the connection """


    reopen = False

    try:
        
        for row in run_query_internal( dbname, query ):
            yield row
                
    except sqlite3.OperationalError as e:
        ## print( (e, e.args, vars(e)) )
        if 'database is locked' in e.args :
            reopen = True
        else:
            raise
    else:
        reopen = False

    if reopen:
        # try to open the same as a temporary file
        # // not ideal, but shall do for home use
        tmp = tempfile.NamedTemporaryFile(delete=False, prefix='pyfox', suffix='.sqlite')
        tmpname = tmp.name
        if _dbg: 
            print( tmpname )
        shutil.copyfile( dbname, tmpname )
        tmp.close()

        for row in run_query_internal( tmpname, query ):
            yield row

        ## if not _dbg: 
        if 1:
            os.unlink( tmpname )



# implementation ; may reopne a copy for a locked database file
def run_query_internal( dbname, query, _print_max = 30 ):
    """ a generator ; opens an sqlite database, runs a query, 
        yields rows, closes the connection """

    with sqlite3.connect(dbname) as conn:
    
        c = conn.cursor()
        for n, row in enumerate(c.execute( query )):

            if _dbg:
                if n < _print_max:
                    print(row)
                elif n == _print_max:
                    print('...')

            yield row



def open_browser(url):
    '''Opens the default browswer'''
    webbrowser.open(url, autoraise=True)


def convert_moz_time( moz_time_entry ):
    """ Convert Mozilla timestamp-alike data entries to an ISO 8601-ish representation """

    # [ https://developer.mozilla.org/en-US/docs/Mozilla/Projects/NSPR/Reference/PRTime ]
    result = datetime.fromtimestamp( moz_time_entry/1000000 ).strftime('%Y-%m-%d %H:%M:%S')

    return result


def make_temp_filename( query_type = 'bookmarks' ):
    """ let us have a constant rewritable path for query results, 
        ideally in a temporary folder
    """

    tmpdir = tempfile.gettempdir()

    # copy js accessory code if missing
    for js_filename in ( JQ_MIN_PATH, JQ_FT_PATH ):
        js_orig = os.path.join( PROGDIR, js_filename )
        js_dest = os.path.join( tmpdir, js_filename )
        if not os.path.exists( js_dest ):
            shutil.copyfile( js_orig, js_dest )

    if query_type == 'bookmarks' :
        result = os.path.join( tmpdir, 'pyfox-bookmarks.html' )
    else: # assume a 'history' query
        result = os.path.join( tmpdir, 'pyfox-history.html' )

    return result


## def history(cursor, pattern=None, src=""):
def history(dbname, pattern=None, src=""):
    ''' Function which extracts history from the sqlite file '''
    
    with open("template.html", 'r') as t:
        html = t.read()

    if src == 'firefox':
        
        with open( FF_QUERY_HISTORY ) as f:
            ff_sql = f.read().rstrip().rstrip(';')
        
        if pattern is not None:
            ff_sql += " AND url LIKE '%"+pattern+"%' "
        ff_sql += " ORDER BY last_visit_date DESC;"


        ## execute_query(cursor, ff_sql)
        ## for row in cursor:
        for row in run_query_wrapper( dbname, ff_sql ):

            last_visit = convert_moz_time( row[2] )

            link = row[0]
            show_link = link[:100]
            title = row[1][:100]

            trow = "<tr><td><a href='{link}'>{title}</a></td><td>{last_visit}</td><td>{show_link}</td></tr>\n".format( **locals() )
            html += trow


    if src == 'chrome':
        sql = "SELECT urls.url, urls.title, urls.visit_count, \
        urls.typed_count, datetime(urls.last_visit_time/1000000-11644473600,'unixepoch','localtime'), urls.hidden,\
        visits.visit_time, visits.from_visit, visits.transition FROM urls, visits\
         WHERE  urls.id = visits.url and urls.title is not null order by last_visit_time desc "

        execute_query(cursor, sql)
        for row in cursor:
            print("%s %s"%(row[0], row[4]))

    html += "</tbody>\n</table>\n</body>\n</html>"
    
    filename = make_temp_filename( 'history' )
    html_file = open( filename, 'w' )

    html_file.write(html)
    html_file.close()
    
    open_browser( filename )


## def bookmarks(cursor, pattern=None):
## def bookmarks( cursor ):
def bookmarks(dbname, pattern=None, _max_dbg_lines = 30):
    ''' Function to extract bookmark related information '''

    with open( FF_QUERY_BOOKMARKS ) as f:
        ff_query = f.read()

    ## execute_query(cursor, ff_query)

    with open("template.html", 'r') as t:
        html = t.read()

    filename = make_temp_filename( 'bookmarks' )
    html_file = open( filename, 'wb' )

    ## for row in cursor:
    for n, row in enumerate(run_query_wrapper( dbname, ff_query )):

        link = row[0]
        show_link = link[:100]
        title = row[1]

        date = convert_moz_time( row[4] )

        html += "<tr><td><a href='{link}'>{title}</a></td><td>{date}</td><td>{show_link}</td></tr>\n".format( **locals() )
        
        if n < _max_dbg_lines:
            print( "%s %s" % (link, title) )

    html += "</tbody>\n</table>\n</body>\n</html>"

    # TODO: handle possible encoding issues if bookmarks aren't in utf-8 
    #       ( could they be? what the docs say? )
    #       // possibly use locale.getpreferredencoding()
    #       // sys.getfilesystemencoding() could be a second guess, I suppose
    html_file.write(html.encode('utf8'))
    if 0:
        try:
            html_file.write(html.encode('utf8'))
        except:
            if not _dbg:
                html_file.write(html)
            else:
                raise
    html_file.close()
    
    ## open_browser("bookmarks.html")
    open_browser( filename )


def get_path(browser):
    '''Gets the path where the sqlite3 database file is present'''
    if browser == 'firefox':
        if sys.platform.startswith('win') == True:
            path = '\\AppData\\Roaming\\Mozilla\\Firefox\\Profiles\\'
        elif sys.platform.startswith('linux') == True:
            path = "/.mozilla/firefox/"
        elif sys.platform.startswith('darwin') == True:
            path = '/Library/Application Support/Firefox/Profiles/'

    #elif browser == 'chrome':
    #    if sys.platform.startswith('win') == True:
    #        path = ''
    #    elif sys.platform.startswith('linux') == True:
    #        path =  "/.config/chromium/Default/History"
    #    elif sys.platform.startswith('darwin') == True:
    #        path = ''

    return path


def parse_options():
    """ handle command-line arguments """

    DESC_PYFOX = "Extract records for Firefox history and/or bookmarks"
    
    parser = argparse.ArgumentParser(description=DESC_PYFOX)
    
    parser.add_argument('--bookmarks', '--bm', '-b', action='store_true', default=None)
    parser.add_argument('--history', '-y', nargs='?', default=None, const='' )
    
    args = parser.parse_args()

    return args


# -----------------------------------------------------------------------------------
# main

if __name__ == "__main__":

    options = parse_options()

    try:
        firefox_path = get_path('firefox')
        home_dir = os.environ['HOME']
        firefox_path = home_dir + firefox_path; print(firefox_path)
        profiles = [i for i in os.listdir(firefox_path) if i.endswith('.default')]
        ## sqlite_path = firefox_path+ profiles[0]+'/places.sqlite'
        sqlite_path = os.path.join(firefox_path, profiles[0], DBNAME )

        print(sqlite_path)
        if 0:
            if os.path.exists(sqlite_path):
                firefox_connection = sqlite3.connect(sqlite_path)

        #chrome_sqlite_path = '/home/thewhitetulip/.config/chromium/Default/History'
        #chrome_sqlite_path = get_path('chrome')
        #if os.path.exists(chrome_sqlite_path):
        #    chrome_connection = sqlite3.connect(chrome_sqlite_path)
    except Exception as error:
        if not _dbg:
            print("_main_")
            print(str(error))
            exit(1)
        else:
            raise

    ## cursor = firefox_connection.cursor()
    #CHROME_CURSOR = chrome_connection.cursor()

    if options.bookmarks is not None:
        ## bookmarks(cursor, pattern=options.bm)
        ## bookmarks(cursor)
        bookmarks(sqlite_path, pattern=options.bookmarks) 

    if options.history is not None:
        print("From firefox")
        ## history(cursor, pattern=options.history, src="firefox")
        history(sqlite_path, pattern=options.history, src="firefox")
        #print("From chrome")
        #history(CHROME_CURSOR, src="chrome")

    ## cursor.close()
    #CHROME_CURSOR.close()
