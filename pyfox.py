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

# debugging 
from pprint import pprint as pp

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

HTML_TEMPLATE_BOOKMARKS = 'template_bookmarks.html'
HTML_TEMPLATE_HISTORY   = 'template_history.html'

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

HTML_TEMPLATE_BOOKMARKS = os.path.join( PROGDIR, HTML_TEMPLATE_BOOKMARKS )
HTML_TEMPLATE_HISTORY   = os.path.join( PROGDIR, HTML_TEMPLATE_HISTORY )

# attaching js table filtering code, 
# see [ https://github.com/sunnywalker/jQuery.FilterTable ]
JQ_MIN_PATH = 'jquery.min.js'
JQ_FT_PATH  = 'jquery.filtertable.min.js'

# -----------------------------------------------------------------------------------

if 0:
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


def copy_js_files( pathname ):
    """
        copy accessory javascript files to the given location if they are missing
    """

    for js_filename in ( JQ_MIN_PATH, JQ_FT_PATH ):
        js_orig = os.path.join( PROGDIR, js_filename )
        js_dest = os.path.join( pathname, js_filename )
        if not os.path.exists( js_dest ):
            shutil.copyfile( js_orig, js_dest )


def make_temp_filename( query_type = 'bookmarks' ):
    """ let us have a constant rewritable path for query results, 
        ideally in a temporary folder
    """

    tmpdir = tempfile.gettempdir()

    # copy js accessory code if missing
    copy_js_files( pathname = tmpdir )

    if query_type == 'bookmarks' :
        result = os.path.join( tmpdir, 'pyfox-bookmarks.html' )
    else: # assume a 'history' query
        result = os.path.join( tmpdir, 'pyfox-history.html' )

    return result


## def history(cursor, pattern=None, src=""):
## def history(dbname, pattern=None, src=""):
## def history(dbname, options, src="" ):
def history(dbnames, options, src="" ):
    ''' Function which extracts history from the sqlite file '''
    
    with open( HTML_TEMPLATE_HISTORY, 'r') as t:
        html = t.read()

    if src == 'firefox':
        
        with open( FF_QUERY_HISTORY ) as f:
            ff_sql = f.read().rstrip().rstrip(';')
        
        if options.pattern is not None:
            ff_sql += " AND url LIKE '%"+pattern+"%' "
        ff_sql += " ORDER BY last_visit_date DESC;"

        for dbname in dbnames:
            for row in run_query_wrapper( dbname, ff_sql ):

                last_visit = convert_moz_time( row[2] )

                link = row[0]
                show_link = link[:100]
                title = row[1][:100]

                trow = "<tr><td><a href='{link}'>{title}</a></td><td>{last_visit}</td><td>{show_link}</td></tr>\n".format( **locals() )
                html += trow


    # turning off chrome 'branch' -- anyone interested feel free to reopen it and handle like FF code above )
    if 0:
        if src == 'chrome':
            sql = "SELECT urls.url, urls.title, urls.visit_count, \
            urls.typed_count, datetime(urls.last_visit_time/1000000-11644473600,'unixepoch','localtime'), urls.hidden,\
            visits.visit_time, visits.from_visit, visits.transition FROM urls, visits\
             WHERE  urls.id = visits.url and urls.title is not null order by last_visit_time desc "

            execute_query(cursor, sql)
            for row in cursor:
                print("%s %s"%(row[0], row[4]))


    html += "</tbody>\n</table>\n</body>\n</html>"
    
    if options.output_filename is None:
        filename = make_temp_filename( 'history' )
    else:
        filename = options.output_filename
        copy_js_files( os.path.dirname( filename ) )
        
    html_file = open( filename, 'w' )

    html_file.write(html)
    html_file.close()
    
    open_browser( filename )


## def bookmarks(cursor, pattern=None):
## def bookmarks(dbname, pattern=None, _max_dbg_lines = 20):
def bookmarks(dbnames, options, _max_dbg_lines = 20):
    ''' Function to extract bookmark related information '''

    with open( FF_QUERY_BOOKMARKS ) as f:
        ff_query = f.read()


    with open( HTML_TEMPLATE_BOOKMARKS, 'r') as t:
        html = t.read()

    if options.output_filename is None:
        filename = make_temp_filename( 'bookmarks' )
    else:
        filename = options.output_filename
        copy_js_files( os.path.dirname( filename ) )
    
    html_file = open( filename, 'wb' )

    for dbname in dbnames:
        for n, row in enumerate(run_query_wrapper( dbname, ff_query )):

            link = row[0]
            show_link = link[:100]
            title = row[1]

            date = convert_moz_time( row[2] )

            folder = row[3]

            html += "<tr><td><a href='{link}'>{title}</a></td><td>{date}</td><td>{folder}</td><td>{show_link}</td></tr>\n".format( **locals() )
            
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


def list_places(base_dir, filter_patterns = [], _default_filter = '*'):
    """find all profiles -- folders with 'places.sqlite' inside
       and return a list of 'places.sqlite' full paths
       
       args:
        - base_dir -- path for firefox settings ( get_path() -> )
        - filter_pattern -- an fnmatch/glob-style pattern to filter profile names
    """

    found = []

    if not filter_patterns:
        filter_patterns = [ _default_filter ]

    # correct supplied patterns wrapping them with '*' if needed )
    patterns = []
    for p in filter_patterns :
        # if there are no glob characters at all, append some
        if '*' not in p:
            if '?' not in p:
                p = '*' + p + '*'

        patterns.append(p)

    dirs = os.listdir( base_dir )
    
    # apply all patterns, collect anything matching
    for p in patterns:
        filtered = fnmatch.filter( dirs, p )

        for d in filtered:
            testpath = os.path.join( base_dir, d, DBNAME )
            if os.path.exists( testpath ):
                if _dbg:
                    _fmt = "found a matching profile: {0!r} /{1!r}/"
                    print( _fmt.format( testpath, p ) )
                found.append( testpath )

    return found


def parse_options():
    """ handle command-line arguments """

    DESC_PYFOX = "Extract records for Firefox history and/or bookmarks"

    parser = argparse.ArgumentParser(description=DESC_PYFOX)

    parser.add_argument('--bookmarks', '--bm', '-b', action='store_true', default=None)
    parser.add_argument('--history', '-y', nargs='?', default=None, const='' )

    parser.add_argument('--profile-pattern', '-p', action='append', default=[], dest='profile_filters'
                       , help="a shell-alike pattern to filter profile names; we'll take the first one")

    _MAX_PROFILES_DEFAULT = 1
    parser.add_argument('--max-profiles', '-m', dest='max_profiles', nargs='?', default=None, const=_MAX_PROFILES_DEFAULT, type=int
                       , help = "use first max_profiles found (default {})".format( _MAX_PROFILES_DEFAULT ) )

    # this will have priority compared to --profile-pattern ( as a more low-level thing ) )
    parser.add_argument('--use-places', '--db', dest='places_sqlite', default = None
                       , help="direct path to a 'places.sqlite' database ; takes priority when used along with '--profile-pattern'")


    parser.add_argument('--output-file', '-o', dest='output_filename', default = None
                       , help="dump bookmarks / history to a given location")

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
        
        sqlite_paths = [] # not set yet
        if options.places_sqlite is not None:
            if os.path.exists( options.places_sqlite ):
                sqlite_paths = [ options.places_sqlite ]
            else:
                print( "--db: path {0!r} does not exist!".format( options.places_sqlite )
                     , file=sys.stderr  
                     )

        # next try
        if not sqlite_paths :
        
            places = list_places( firefox_path, filter_patterns=options.profile_filters )
            if not places:
                print("no profile found") ; sys.exit(2)

            if options.max_profiles :
                places = places[:(options.max_profiles)]

            ## profiles = [i for i in os.listdir(firefox_path) if i.endswith('.default')]
            ## sqlite_path = firefox_path+ profiles[0]+'/places.sqlite'
            sqlite_paths = places
            if not sqlite_paths:
                print("no suitable profile found") ; sys.exit(2)

        pp( sqlite_paths )

        # ^^^ not sure why we need this additional check, 
        #     but let's preserve it just in case if it helps to debug something 
        if _dbg:
            assert os.path.exists( sqlite_paths[0] )


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
        bookmarks(sqlite_paths, options = options) 

    if options.history is not None:
        print("From firefox")
        ## history(cursor, pattern=options.history, src="firefox")
        ## history(sqlite_path, pattern=options.history, src="firefox")
        history(sqlite_paths, options = options, src="firefox")
        #print("From chrome")
        #history(CHROME_CURSOR, src="chrome")

    ## cursor.close()
    #CHROME_CURSOR.close()
