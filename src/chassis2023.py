"""chassis2023 -- general chassis for program executions"""

import sys
import time
import json
import importlib
import inspect
import argparse
import pathlib

from . import snowflakes

from .exceptions import ChassisException, BadPackageFile, BadPackageFileValue
from .exceptions import BrokenPromise, WasLocked, WasNotLocked, BadState



# --[ globals ]---------------------------------------------------------

g = {}  # call reset_g() before use

config = {}  # config populated from CLI

def reset():
    """completely reset for execution"""
    config.clear()
    reset_g()
    setup_execution_types()

def reset_g():
    g["PACKAGE_NAME"] = None  # core package (string name of package)
    g["PACKAGE_JSON_DATA"] = None  # package.json content loaded from package
    g["EXECINFO"] = None  # matching entry in execution_types_L
    g["STAGE"] = None  # presently active stage (str, options)
    g["HOST"] = None  # for specific execution modes (str, IP addr)
    g["PORT"] = None  # for specific execution modes (int, TCP port)


# --[ execution types ]-------------------------------------------------

execution_types_L = []
execution_types = {}  # NAME -> dict

# flags: "H" -- collects a HOST/PORT pair

def setup_execution_types():
    execution_types_L[:] = [
        {"NAME": "CLITOOL",
         "FLAGS": "",
         "EXECFN": None},
        
        {"NAME": "JSONWEBSERVICE",
         "FLAGS": "H",
         "EXECFN": execute_jsonwebservice},
        
        {"NAME": "TCPSERVICE",
         "FLAGS": "H",
         "EXECFN": None},

        {"NAME": "FILETALKSERVER",
         "FLAGS": "",
         "EXECFN": None},
        
        {"NAME": "TKINTERGUI",
         "FLAGS": "",
         "EXECFN": None},
        
        {"NAME": "INTERACTIVEMENU",
         "FLAGS": "",
         "EXECFN": None}
    ]
    
    execution_types.clear()
    
    for D in execution_types_L:
        execution_types[D[NAME]] = D


# --[ security ]--------------------------------------------------------

locks = set()


def lock(key):
    if key in locks:
        raise WasLocked(key)
    locks.add(key)

def unlock(key):
    try:
        locks.remove(key)
    except KeyError:
        raise WasNotLocked(key)

def req(key):
    if key not in locks:
        raise WasNotLocked(key)

def forbid(key):
    if key in locks:
        raise WasLocked(key)


# --[ logging ]---------------------------------------------------------

logs = []  # running log of NOTE, DBG, WARN, ERR notes
ringlogs = []  # like log, but finite in length
noticed = set()  # set of symbols, things noticed in execution
notice_text = {}  # notice symbol -> human readable string

def log(type_, code, title, msg):
    """Add a note to the record.
    
    type_  -- (sym) should be one of:
              NOTE, DBG, WARN, ERR
    
      NOTE  -- general catch-all
      DBG   -- not an error or a warning,
               but info perhaps relevant to debugging
      WARN  -- something developer should be aware of
      ERR   -- a note about an error that occured
    
    code -- (sym) a code representing the record
    title  -- (str) human readable title string for the record
    msg  -- (str) human readable details string for the record
    """
    if type_ not in [NOTE, DBG, WARN, ERR]:
        raise ValueError(type_)
    logs.append({TIME: time.time(),
                 SRC: inspect.stack(),
                 TYPE: type_,
                 CODE: code,
                 TITLE: title,
                 MSG: msg})

def ringlog(type_, code, title, msg):
    """Add a note to the ring log.
   
    Takes care of rotating the log.
    See log(...) docstring, for argument description.
    """
    log(type_, code, title, msg)
    ringlogs.append(logs.pop())
    try:
        if len(ringlogs) > g[PROGRAMDATA][LOGRINGLEN]:
            del ringlogs[0]
    except KeyError:
        g[PROGRAMDATA]  # raise a different error if not resolving
        log(ERR,
            BADPROGRAMDATA,
            "LOGRINGLEN not defined",
            "ringlog(...) called, but LOGRIGNLEN was not defined in the program data")

def print_log(D):
    print("* time:", time.strftime("%#I:%M:%S%p", time.localtime(D[TIME])).replace("AM", "a"))
    print("  source:", D[SRC][1].filename, D[SRC][1].lineno, D[SRC][1].function)
    print("  type:", D[TYPE])
    print("  code:", D[CODE])
    print("  title:", D[TITLE])
    print("  message:", D[MSG])

def print_logs():
    print("log:")
    for D in logs:
        print_log(D)
        print()

def print_noticed():
    print("noticed flags:")
    for k in noticed:
        print(f"  - {k}: {notice_text[k]}")
    if not noticed:
        print("  - (nothing)")

def print_ringlogs():
    print("ringlog:")
    for D in ringlogs:
        print_log(D)
        print()


# --[ run_package execution ]-------------------------------------------
#
# In the case of beginning with run_package(package_name), the package
# runs the program like so:
#
# -- __main__.py -------------------------
# import chassis2023
#
# chassis2023.run_package(__package__)
# ----------------------------------------
#
# The value of __package__ will be a string.  It will not end in ".py"
# or anything like that.
#
# The package will have a file databytes.py, that will contain the file
# data with the package.json contents within it, that it was created
# with.
#
# It will be JSON decoded, and then the EXECUTIONTYPE key will be looked
# up:
#
# {
#   "CHASSIS2023": {
#     "EXECUTIONTYPE": "WEBSERVER" (or what not)
#   }
# }
#
# 

def package_module(module_name):
    """Return the entry module for a named Python package.

    It can include "." as separators.
    
    Assumptions: -- "if package_module() is called, the following is true..."
    * PACKAGE_NAME has been set, and points to an actual package.
    """
    module_path = g["PACKAGE_NAME"] + "." + module_name
    return importlib.import_module(module_path)

def populate_PACKAGE_JSON_DATA():
    """only call from run_package
    
    Assumptions: -- "if populate_PACKAGE_JSON_DATA() is called, the following is true..."
    * PACKAGE_NAME has been set
    """
    g["PACKAGE_JSON_DATA"] = json.loads(package_module("databytes").files["package.json"])

def populate_EXECINFO():
    """only call from run_package
    
    Assumptions: -- "if populate_EXECINFO() is called, the following is true..."
    * PACKAGE_JSON_DATA has been loaded and populated
    * PACKAGE_JSON_DATA is well-formed; in particular, the EXECINFO type is valid
    * execution_types_L has been properly loaded and initialized
    """
    key = g["PACKAGE_JSON_DATA"]["CHASSIS2023"]["EXECUTIONTYPE"]
    for D in execution_types_L:
        if D["NAME"] == key:
            g["EXECINFO"] = D
            return
    raise BadState("bad EXECINFO values should have been caught before calling")

def run_package(package_name):
    """single entry port from a chassis2023 program"""
    setup()
    reset_g()

    # establish basic information
    g["PACKAGE_NAME"] = package_name
    populate_PACKAGE_JSON_DATA()   # PACKAGE_NAME must be set, before this is called
    populate_EXECINFO()

    # collect information from command line
    collect_cli_data()

    # if all required information is present, commence execution
    execute()

def execute():
    """only call from run_package(...) -- at least, for now
    
    Assumptions: -- "if execute() is called, the following is true..."
    * PACKAGE_NAME is valid,
    * PACKAGE_JSON_DATA is loaded,
    * the config dictionary has been populated
    * no stages have been executed yet
    * it is time to run the program
    """
    g["EXECINFO"]["EXECFN"]()


# --[ CHASSIS2023.EXECUTIONTYPE: JSONWEBSERVICE ]----------------------

class RequestHandler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length).decode('utf-8')
        data = json.loads(post_data)

        # TODO: wrap this in a try...except block, and handle a failure in a defined way
        response = package_module("handler").handle(data)
        
        # Respond with a success status code
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        
        self.wfile.write(json.dumps(response).encode('utf-8'))
        
    def log_message(self, format, *args):
        """Override log_message to suppress logging output."""
        pass


def execute_jsonwebservice():
    """Called ONLY by execute(), via EXECFN."""
    from http.server import BaseHTTPRequestHandler, HTTPServer
    
    server_address = (g["HOST"], g["PORT"])
    
    httpd = HTTPServer(server_address, RequestHandler)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("Server terminated by user.")


# --[ CLI processor ]---------------------------------------------------
# 2023-08-25

# 2023-08-25 -- this organizational information can be relocated
#
# Parts:
# - Command Line Processor   [ WRITTEN ]
#   - assembly
#   - collection from arguments
#
# - Global Config Dictionary
#   - storing values in it
#   - verifying requirements are met
#       req_package_json_data_loaded() => (None) [raise]
#       req_package_json_config_well_formatted() => (None) [raise]
#       options_match(supplied_str, specific_config_dict_w_options) => x [raise]
#
# - Alert/Err/Deprecation/Notice Logging System
#   - transfer the Factory system?
# - Context System


def options_match(option_str, conf_dict):
    """Match an option str, against a configuration dictionary's options."""
    for option_entry in conf_dict["OPTIONS"]:
        if str(option_entry) == option_str:
            return option_entry

def collect_cli_data():
    """Collect CLI data from the command line invocation.

    Assumptions: -- "if collect_cli_data() is called, the following is true..."
    * there WAS a CLI command line invocation
    * PACKAGE_JSON_DATA has been loaded -- that information is relied on
    * PACKAGE_JSON_DATA is well-formed
      NOTE: this assumption is NOT well-made, presently;
            I intend to write the code to ensure that PACKAGE_JSON_DATA is well-formed,
            I just haven't written it yet.
            But I don't want to clutter this code with checks and checking.
            THIS code should be written in the assumption that data is well-formed.
    
    Returns:
    * None -- success
    * exception -- something unexpected happened, likely a bug
    
    Requires from PACKAGE_JSON_DATA:
    * APPID.TITLE
    """
    pkg_data = g["PACKAGE_JSON_DATA"]  # shortcut
    
    # create and populate parser
    parser = argparse.ArgumentParser(description=pkg_data["APPID"]["TITLE"])
    
    # prompt execution-type dependent options
    if "H" in g["EXECINFO"]["FLAGS"]::
        parser.add_argument("--host", type=str, help="host address to run server on", default="127.0.0.1")
        parser.add_argument("--port", type=int, help="port to run srever on", default=80)
    
    # prompt package-specified options
    for D in pkg_data.get("CONFIG", []):
        type_fn = {"STR": str,
                   "INT": int,
                   "PATH": pathlib.Path,
                   "FLOAT": float,
                   "BOOL": bool,
                   "OPTION": lambda s: options_match(s, D)}[D["TYPE"]]  # /!\ options_match NOT IMPLEMENTED YET
        parser.add_argument(f"""--{D["NAME"]}""",
                            type=type_fn,
                            help=D["DESC"],
                            default=D["DEFAULT"])
    
    # parse arguments
    args = parser.parse_args()
    
    # place execution-type dependent options
    if "H" in g["EXECINFO"]["FLAGS"]:
        g["HOST"] = args.host
        g["PORT"] = args.port
    
    # place package-specified options
    for D in pkg_data.get("CONFIG", []):
        config[D["NAME"]] = getattr(args, D["NAME"])
    
    # return Success
    return True

