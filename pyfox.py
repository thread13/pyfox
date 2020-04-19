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
from configparser import SafeConfigParser
import re

# debugging 
from pprint import pprint as pp

# trying to load additional url filters for history sql queries
HISTORY_SQL_URL_FILTERS = [] # an empty sequence
try:
    from pyfox_filters import HISTORY_SQL_URL_FILTERS
except ImportError:
    print( "! Failed to import additional SQL filters from 'pyfox_filters.py'"
         , file=sys.stderr )


# -----------------------------------------------------------------------------------
# cwd finder

def resolve_symlink( pathname, _level = 0, _maxlevel = 8 ):
    """  """

    result = pathname # default

    if _level > _maxlevel :
        _msg = "resolve_symlink({0!r}): too many indirection levels ({1})".format( pathname, _level )
        raise RuntimeError( _msg )
    # else ..

    # nb: islink() returns False for non-existent paths
    if os.path.islink( pathname ):
        path = os.path.dirname( pathname )
        link = os.readlink( pathname )
        
        newpath = os.path.join( path, link )
        if _dbg:
            print( "resolving: {0!r} -> {1!r}".format( pathname, newpath ) )

        result = resolve_symlink( newpath, _level = _level + 1 )

    return result


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
## PROGDIR = os.path.dirname( sys.argv[0] )
PROGDIR = os.path.dirname( resolve_symlink( sys.argv[0] ) )
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

#
# accessory constants
#

# strip '-- ... end-of-line' sql comments
RE_SQL_COMMENT_1 = re.compile(r'--.*$', re.MULTILINE)
# strip C-like comments ( sadly would also work inside sql strings )
RE_SQL_COMMENT_2 = re.compile(r'/[*].*?[*]/', re.DOTALL)

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


def sql_quick_strip_comments( sql_code
                            , _re_strip_1 = RE_SQL_COMMENT_1
                            , _re_strip_2 = RE_SQL_COMMENT_2
                            ):
    """ a quick hack using regexps """

    result = _re_strip_1.sub('', sql_code)
    result = _re_strip_2.sub('', result)

    return result


def history_add_sql_url_filters( stripped_sql
                               , decorated_like_tokens
                               ):

    fragments = []
    for t in decorated_like_tokens:
        fragments.append( "AND url NOT LIKE '{}'".format( t ) )

    append_text = '\n'.join( fragments )
    result = stripped_sql + '\n' + append_text + '\n'

    return result


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


def _parse_date( datestr ):
    """ 
        - "2020-02-20" -> datetime(2020, 2, 20, 0, 0) 
        - "2020-02"    -> datetime(2020, 2,  0, 0, 0) 
        - "2020"       -> datetime(2020, 0,  0, 0, 0) 
    """

    result = None

    n_parts = datestr.count('-')

    if 0 == n_parts :
        result = datetime.strptime(datestr, '%Y')
    elif 1 == n_parts :
        result = datetime.strptime(datestr, '%Y-%m')
    else : 
        assert 2 == n_parts
        result = datetime.strptime(datestr, '%Y-%m-%d')

    return result


def _parse_date_spec( date_expr ):
    """ returns a tuple (start_date, end_date), 
        where each part can be None ;
        
        date spec by example : 
         - '2020-02-02..2020-02-20'
         - '2020..2030'
         - '2020-02-02..' 
           # ^^^ '..' are important 
           #     since they denote start or end of the interval
         - '..2020-02-20' # probably less useful, but also correct
    """

    parts = date_expr.split('.')

    # there shall always be three parts :
    ## '2020-02-02..2020-02-20'.split('.')
    ##  =>
    ## ['2020-02-02', '', '2020-02-20']
    ##
    ## '2020-02-02..'.split('.')
    ##  =>
    ## ['2020-02-02', '', '']

    assert len(parts) == 3

    start_expr = parts[0]
    end_expr = parts[-1]

    start_date = None
    if start_expr != '' :
        start_date = _parse_date( start_expr )

    end_date = None
    if end_expr != '' :
        end_date = _parse_date( end_expr )

    result = ( start_date, end_date )
    return result


def _date_within( some_date, start_date, end_date ):
    """ 
        check if start_date <= some_date <= end_date ,
        considering inequality to be true if either 
        start_date or end_date is None
    """

    result = True # start with a truth assumption
    if start_date is not None:
        result = result and ( start_date <= some_date )

    if end_date is not None:
        result = result and ( some_date <= end_date  )

    return result



def convert_moz_time( moz_time_entry ):
    """ Convert Mozilla timestamp-alike data entries to an ISO 8601-ish representation """

    # [ https://developer.mozilla.org/en-US/docs/Mozilla/Projects/NSPR/Reference/PRTime ]
    ## result = datetime.fromtimestamp( moz_time_entry/1000000 ).strftime('%Y-%m-%d %H:%M:%S')
    result = datetime.fromtimestamp( moz_time_entry/1000000 )

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


def _pass_filters( title, link
                 , parsed_query, parsed_filter
                 , _n_lines_max = 20
                 , _counter = [0]
                 ):
    """
        check if url and title: 
          (a) match 'parsed_query' and 
          (b) do not match 'parsed_filter'
          
        returns True for (a) and (b) and only when so        
    """

    # a quick workaround ( for former NULL-s, I guess )
    if title is None:
        title = ''
    if link is None:
        link = ''

    query_matched = True # passed by default
    if parsed_query:
        _link_matched  = fnmatch_pass( link, parsed_query )
        _title_matched = fnmatch_pass( title, parsed_query )
        
        query_matched = _link_matched or _title_matched

    if not query_matched:
        if _dbg:
            if _counter[0] < _n_lines_max:
                print(f"# {title} / {link!r} : no match!")
                _counter[0] = _counter[0] + 1
        # skip this row
        return False

    query_filtered = False # passed by default
    if parsed_filter:
        _link_filtered  = fnmatch_pass( link, parsed_filter )
        _title_filtered = fnmatch_pass( title, parsed_filter )
        
        query_filtered = _link_filtered or _title_filtered

    if query_filtered:
        if _dbg:
            if _counter[0] < _n_lines_max:
                print(f"# {title} / {link!r} : filtered!")
                _counter[0] = _counter[0] + 1
        # skip this row
        return False

    # else ...
    return True


## def history(cursor, pattern=None, src=""):
## def history(dbname, pattern=None, src=""):
## def history(dbname, options, src="" ):
## def history(dbnames, options, profiles={}, src="", _max_dbg_lines = 20 ):
def history(dbnames, options, sql_filters, profiles={}, src="", _max_dbg_lines = 20 ):
    ''' Function which extracts history from the sqlite file '''

    with open( HTML_TEMPLATE_HISTORY, 'r') as t:
        html_chunks = [ t.read() ]

    parsed_query = None
    if options.query is not None:
        parsed_query = parse_query( options.query )
    parsed_filter = None
    if options.filter is not None:
        parsed_filter = parse_query( options.filter )

    date_cond = None ;  start_date, end_date = ( None, None )
    if options.date_cond is not None:
        start_date, end_date = _parse_date_spec( options.date_cond )
        date_cond = ( start_date, end_date )

    if src == 'firefox':

        with open( FF_QUERY_HISTORY ) as f:

            sql_code = f.read()
            no_comments = sql_quick_strip_comments( sql_code )
            ff_sql = no_comments.rstrip().rstrip(';')

        # '--history' loses an optional "pattern" argument --
        #  -- use '--query' and '--filter' options instead
        if 0:
            pattern = options.history
            ## if options.pattern is not None:
            if pattern is not None:
                ff_sql += " AND url LIKE '%"+pattern+"%' "

        ff_sql = history_add_sql_url_filters( ff_sql, sql_filters )

        ff_sql += " ORDER BY last_visit_date DESC;"

        for dbname in dbnames:

            profile_name = get_profile_name( dbname, profiles )

            _n_dbg = 0
            for row in run_query_wrapper( dbname, ff_sql ):

                last_visit = convert_moz_time( row[2] )

                link = row[0]
                show_link = link[:100]
                title = row[1][:100]


                if not _pass_filters( title = title
                                    , link = link
                                    , parsed_query = parsed_query
                                    , parsed_filter = parsed_filter
                                    , _n_lines_max = _max_dbg_lines
                                    ):
                    # no match or filtered by the filter expression --
                    # -- skip this one
                    continue

                if date_cond is not None:
                    if not _date_within( last_visit, start_date, end_date ):
                        if _dbg:
                            if _n_dbg < _max_dbg_lines:
                                _n_dbg += 1
                                print (f"# > {show_link!r} filtered by date: !({start_date} < {last_visit} < {end_date})"
                                      , file = sys.stderr )
                        continue

                last_visit = last_visit.strftime('%Y-%m-%d %H:%M:%S')

                # else ...

                _parts = [ "<tr>"
                         , "<td><a href='{link}'>{title}</a></td>"
                         , "<td>{last_visit}</td>"
                         , "<td>{show_link}</td>"
                         , "<td>{profile_name}</td>"
                         , "</tr>\n" 
                         ]

                ## trow = "<tr><td><a href='{link}'>{title}</a></td><td>{last_visit}</td><td>{show_link}</td></tr>\n".format( **locals() )
                trow = ''.join(_parts).format( **locals() )
                html_chunks.append( trow )


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


    html_chunks.append( "</tbody>\n</table>\n</body>\n</html>" )
    html = ''.join( html_chunks )
    
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
def bookmarks(dbnames, options, profiles={}, _max_dbg_lines = 20):
    ''' Function to extract bookmark related information '''

    with open( FF_QUERY_BOOKMARKS ) as f:
        ff_query = f.read()

    parsed_query = None
    if options.query is not None:
        parsed_query = parse_query( options.query )
    parsed_filter = None
    if options.filter is not None:
        parsed_filter = parse_query( options.filter )

    with open( HTML_TEMPLATE_BOOKMARKS, 'r') as t:
        ## html = t.read()
        html_chunks = [ t.read() ]

    if options.output_filename is None:
        filename = make_temp_filename( 'bookmarks' )
    else:
        filename = options.output_filename
        copy_js_files( os.path.dirname( filename ) )
    
    html_file = open( filename, 'wb' )

    for dbname in dbnames:
        
        profile_name = get_profile_name( dbname, profiles )
        if _dbg:
            print( f"profile: {profile_name!r}" )

        for n, row in enumerate(run_query_wrapper( dbname, ff_query )):

            link = row[0]
            show_link = link[:100]
            title = row[1]

            if not _pass_filters( title = title
                                , link = link
                                , parsed_query = parsed_query
                                , parsed_filter = parsed_filter
                                , _n_lines_max = _max_dbg_lines
                                ):
                # no match or filtered by the filter expression --
                # -- skip this one
                continue

            # else ...

            date = convert_moz_time( row[2] ) # datetime object
            date = date.strftime('%Y-%m-%d %H:%M:%S') # a string

            folder = row[3]

            _parts = [ "<tr>"
                     , "<td><a href='{link}'>{title}</a></td>"
                     , "<td>{date}</td>"
                     , "<td>{folder}</td>"
                     , "<td>{show_link}</td>"
                     , "<td>{profile_name}</td>"
                     , "</tr>\n"
                     ]
            ## html += "<tr><td><a href='{link}'>{title}</a></td><td>{date}</td><td>{folder}</td><td>{show_link}</td></tr>\n".format( **locals() )
            line = ''.join(_parts).format( **locals() )
            html_chunks.append( line )

            if n < _max_dbg_lines:
                print( "%s %s" % (link, title) )

    html_chunks.append( "</tbody>\n</table>\n</body>\n</html>" )

    html = ''.join( html_chunks )

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


def list_profiles( base_dir ):
    """ enumerates profile names and related filenames """

    # dicts are ordered since 3.7 (since 3.6 for CPython) ;
    # till then, we would sacrifice profile order for pretty-printing )
    result = {}

    inifile = os.path.join(base_dir, 'profiles.ini')
    if os.path.exists( inifile ):
        
        cp = SafeConfigParser()
        cp.read( inifile )
        
        for section in cp.sections():
            if cp.has_option(section, 'path'):
                if cp.has_option( section, 'name' ):
                   
                    p = cp.get(section, 'path', raw = True)
                    n = cp.get(section, 'name', raw = True)
                    
                    fullpath = os.path.join( base_dir, p )
                    
                    result[ fullpath ] = n
                    
    return result


def get_profile_name( places_pathname, profile_dict ):
    """ check the name in 'profiles.ini' and return the filename if not found """

    where = os.path.dirname( places_pathname )
    std_name = profile_dict.get( where, None )

    shortname = os.path.basename( where )

    if std_name is not None:
        result = "{0} ({1!r})".format( std_name, shortname )
    else:
        result = "{}".format( shortname )

    return result


def sql_like_decorate( pattern ):
    """ wrap the given string with '%' if it is not already there """

    if '%' not in pattern:
        pattern = '%' + pattern + '%'

    return pattern


def fnmatch_decorate( pattern ):
    """ wrap the given string with '*' if there are no other glob symbols in it """

    if '*' not in pattern:
        if '?' not in pattern:
            pattern = '*' + pattern + '*'
            
    return pattern


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
        p = fnmatch_decorate( p )

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


def parse_query( query_expr ):
    """
         'http://* google OR https://* twitter' 
        =>
         [ 'http://* google ',  'https://* twitter']
        =>
         [ ('http://*', '*google*'), ('https://*', '*twitter*') ]
    """

    result = []
    or_parts = re.split('OR', query_expr)
    
    for part in or_parts :
        tokens = part.split()
        # nb: we also convert them to lower-case (shall "just work" in Py3 ))
        tokens = [ fnmatch_decorate(t.lower()) for t in tokens ]

        result.append( tokens )

    return result


def fnmatch_pass( text, parsed_query ):
    """
        check if text matches any group of filters as defined by parse_query()
    """

    text = text.lower()

    passed = False # default, empty query -> "no pass"
    for or_group in parsed_query:
        passed = True # changing default ; "no filters" -> pass
        for expr in or_group :
            if not fnmatch.fnmatch( text, expr ):
                passed = False
                break
        
    # at this stage, any "well-defined" (no empty clauses) query 
    # will match when and only when there's at least one group
    # where all filters match

    return passed



def parse_options():
    """ handle command-line arguments """

    DESC_PYFOX = "Extract records for Firefox history and/or bookmarks"

    parser = argparse.ArgumentParser(description=DESC_PYFOX)

    parser.add_argument('--bookmarks', '--bm', '-b', action='store_true', default=None)
    ## parser.add_argument('--history', '-y', nargs='?', default=None, const='' )
    parser.add_argument('--history', '-y', '-H',    action='store_true', default=None)

    parser.add_argument('--profile-pattern', '-p', action='append', default=[], dest='profile_filters'
                       , help="a shell-alike pattern to filter profile paths; we'll take the first one")

    _MAX_PROFILES_DEFAULT = 1
    parser.add_argument('--max-profiles', '-m', dest='max_profiles', nargs='?', default=None, const=_MAX_PROFILES_DEFAULT, type=int
                       , help = "use first max_profiles found (default {} if set, none if unset)".format( _MAX_PROFILES_DEFAULT ) )

    parser.add_argument('--list-profiles', '-L', dest='list_profiles', action='store_true', default=None
                       , help = "list existing profiles and their paths" )

    # this will have priority compared to --profile-pattern ( as a more low-level thing ) )
    parser.add_argument('--use-places', '--db', dest='places_sqlite', default = None
                       , help="direct path to a 'places.sqlite' database ; takes priority when used along with '--profile-pattern'")


    parser.add_argument('--output-file', '-o', dest='output_filename', default = None
                       , help="dump bookmarks / history to a given location")


    parser.add_argument('--dates', '-d', dest='date_cond', default = None
                       , help="filter history urls by (last-visited) date: '2020-02-02..2020-02-20', or ''2020-02-02..', or just ''..2020'")
    

    parser.add_argument('--query', '-q', dest='query', default = None
                       , help="apply a filter to pass matching links/titles ; an example: 'http://* google OR https://* twitter' : OR splits groups, within each group all tokens are AND-ed")
    parser.add_argument('--filter', '-f', dest='filter', default = None
                       , help="apply a filter to drop matching links/titles ; basically it is a 'not --query ...' and is AND-ed with the --query filter, if any ")

    args = parser.parse_args()

    return args


# -----------------------------------------------------------------------------------
# main

if __name__ == "__main__":

    options = parse_options()

    # wrap imported filter fragments, if any, with sql 'like' globbing characters ('%')
    HISTORY_SQL_URL_FILTERS = [ sql_like_decorate(f) for f in HISTORY_SQL_URL_FILTERS ]

    try:
        firefox_path = get_path('firefox')
        home_dir = os.environ['HOME']
        firefox_path = home_dir + firefox_path; print(firefox_path)

        profile_dict = list_profiles( firefox_path )

        if options.list_profiles:
            _swapped = [ (n, p) for (p, n) in profile_dict.items() ]
            
            # probably some better formatting (and/or sorting) would be appropriate
            pp( _swapped )

            sys.exit(0)

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
        bookmarks(sqlite_paths, options = options, profiles = profile_dict ) 

    if options.history is not None:
        print("From firefox")
        ## history(cursor, pattern=options.history, src="firefox")
        ## history(sqlite_path, pattern=options.history, src="firefox")
        ## history(sqlite_paths, options = options, profiles = profile_dict, src="firefox")
        history( sqlite_paths
               , options = options
               , sql_filters = HISTORY_SQL_URL_FILTERS
               , profiles = profile_dict
               , src="firefox")

        #print("From chrome")
        #history(CHROME_CURSOR, src="chrome")

    ## cursor.close()
    #CHROME_CURSOR.close()

