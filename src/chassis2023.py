"""chassis2023 -- general chassis for program executions"""

import sys
import time
import json
import importlib
import inspect

import snowflakes


# --[ core symbols ]----------------------------------------------------

kSYMBOLS = """
PROGRAMDATA
APPID
  GUID TAGURI NAME TITLE TAGS DESC
PROGRAM
  EXECUTIONTYPE CLITOOL WEBSERVER FILETALKSERVER
                TKINTERGUI INTERACTIVEMENU
  LOGRINGLEN
MODULES
  NAMES FILES DIRS
RESOURCES

SYMBOLS IMPORTSYMBOLS CONFIG MODULES RESOURCES SNOWFLAKES

MODULES NRUNMODULES

NAME FILE DIR

MI_SRC
STAGE
RUNMODULE

INIT SETUP LOAD POSTLOAD INTERLINK
RUNSTART RUNSTOP
PRECLOSE SAVE POSTSAVE TEARDOWN

NOTE DBG WARN ERR
  BADPROGRAMDATA TOOMANYRUNMODULES NORUNMODULE
TIME SRC TYPE CODE TITLE MSG
"""

symbols_from_module = {}  # module name -> symbols

def intern_symbols(s):
    """Split a string and intern each part of it."""
    return [sys.intern(sym) for sym in s.split()]

def inject_symbols(module, L):
    """Inject each symbol in L into module.
    
    BE SURE that the elements of L have already been interned;
    That is NOT taken care of by this routine.
    """
    for sym in L:
        setattr(module, sym, sym)

def setup_symbols():
    symbols = intern_symbols(kSYMBOLS)
    symbols_from_module["chassis2023"] = symbols
    me = sys.modules[__name__]
    inject_symbols(me, symbols_from_module["chassis2023"])


# --[ globals ]---------------------------------------------------------

g = {}

class ChassisException(Exception): pass


def setup_g():
    g.update({
        PROGRAMDATA: None,
        MI_SRC: None,
        RUNMODULE: None,
        STAGE: None
    })

# --[ execution types ]-------------------------------------------------

execution_types_L = []
execution_types = {}  # NAME -> dict

def setup_execution_types():
    execution_types_L[:] = [
        {NAME: CLITOOL,
         MODULES: {},
         NRUNMODULES: 1},
        
        {NAME: WEBSERVER,
         MODULES: {},
         NRUNMODULES: 0},
        
        {NAME: FILETALKSERVER,
         MODULES: {},
         NRUNMODULES: 0},
        
        {NAME: TKINTERGUI,
         MODULES: {NAMES: ["tk23top", "tk23symbols", "tk23util", "tk23builder", "tk23base"]},
         NRUNMODULES: 0},
        
        {NAME: INTERACTIVEMENU,
         MODULES: {},
         NRUNMODULES: 0}
    ]
    
    for D in execution_types_L:
        execution_types[D[NAME]] = D


# --[ utility ]---------------------------------------------------------

def timestamp():
    "Return a UTC ISO-8601 timestamp as a string."
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())


# --[ security ]--------------------------------------------------------

class BrokenPromise(Exception): pass

class WasLocked(BrokenPromise): pass

class WasNotLocked(BrokenPromise): pass


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


# --[ programdata.json ]------------------------------------------------

kPROGRAMDATA_FILENAME = "programdata.json"

def load_programdata():
    f = open(kPROGRAMDATA_FILENAME, "r", encoding="utf-8")
    g[PROGRAMDATA] = json.loads(f.read())

def save_programdata():
    """rarely called"""
    f = open(kPROGRAMDATA_FILENAME, "w", encoding="utf-8")
    f.write(json.dumps(g[PROGRAMDATA]))

def execution_type_D():
    """assumption: PROGRAMDATA loaded, EXECUTIONTYPE properly configured
    
    intended for internal use only
    """
    exectype = g[PROGRAMDATA][PROGRAM][EXECUTIONTYPE]
    return execution_types[exectype]


# --[ modules ]---------------------------------------------------------

kMODULE_INFO = "kMODULE_INFO"  # varname for module info

modules = []  # all modules known about
pulsers = []  # optimization: modules found to have a pulse() fn


# --[ module intake ]---------------------------------------------------
#
# This code, prefixed with mi_, is entirelty internal, and for the purpose
# of gathering all of the modules that will be used by the program during
# execution.  This is a one time process.  None of this should be called
# by any other code; it's an entirely self-contained chunk of code.
# The entry is: "gather_modules", and it is called once.

mi_toprocess = []  # (mi_kind, mi_addr)  mi_kind:NAME,FILE,DIR mi_addr:name or path
mi_processed = []

mi_recently_processed = []  # modules, to be mined for cascading
mi_processing_sources = {}  # (kind,addr) -> source description string

# mi_processing_sources is purely for debugging, tracability

class ChassisModuleNotFoundError(ChassisException): pass

def mi_register_module(module):
    """Add a module to modules list."""
    if module not in modules:  # safeguard: no double-imports
        modules.append(module)
        mi_recently_processed.append(module)

def mi_import_module_from_name(module_name):
    try:
        module = importlib.import_module(module_name)
        mi_register_module(module)
    except ModuleNotFoundError:
        src = mi_processing_sources[(NAME, module_name)]
        raise ChassisModuleNotFoundError(module_name, src)


def mi_import_module_from_path(module_path):
    # Extract the module name from the filepath
    module_name = os.path.splitext(os.path.basename(module_path))[0]
    
    # Load the module from the filepath
    try:
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        mi_register_module(module)
    except ModuleNotFoundError:
        src = mi_processing_sources.get((FILE, module_path))
        if src is None:
            src = mi_processing_sources.get((DIR, module_path))
        raise ChassisModuleNotFoundError(module_path, src)

def mi_import_modules_from_dir(dir_path):
    # Iterate over the files in the directory
    for filename in os.listdir(dir_path):
        # Check if the file is a .py or .pyc module
        if filename.endswith('.py') or filename.endswith('.pyc'):
            # Load the module from the filepath
            module_path = os.path.join(dir_path, filename)
            mi_import_module_from_path(module_path)


def gather_modules():
    # This has to be called once, and only once.
    # The modules list is assembled once, and is never modified after.
    lock("CALLED:chassis2023.gather_modules")
    mi_seed_from_programdata()
    mi_seed_from_executiontype()
    mi_cascade_processing()

def mi_seed_from_programdata():
    lock("CALLED:chassis2023.mi_seed_from_programdata")
    mi_register_to_process(g[PROGRAMDATA][MODULES], "programdata.json")

def mi_seed_from_executiontype():
    lock("CALLED:chassis2023.mi_seed_from_executiontype")
    mi_register_to_process(execution_type_D()[MODULES],
                           "execution type: "+execution_type_D()[NAME])

def mi_cascade_processing():
    lock("CALLED:chassis2023.mi_cascade_processing")
    while mi_processing_remains():
        (kind, s) = mi_next_toprocess()
        mi_dispatch_processing(kind, s)
        mi_rollover_toprocess()  # move to process->processed
        for mod in mi_recently_processed:
            spec = getattr(mod, kMODULE_INFO, {}).get(MODULES, {})
            mi_register_to_process(spec, mod)
        mi_recently_processed[:] = []


def mi_register_to_process(spec, source_desc):
    g[MI_SRC] = source_desc
    for p in spec.get(DIRS, []):
        mi_register_one(DIR, p)
    for p in spec.get(FILES, []):
        mi_register_one(FILE, p)
    for name in spec.get(NAMES, []):
        mi_register_one(NAME, name)

def mi_register_one(kind, s):
    tup = (kind, s)
    if tup in mi_toprocess: return
    if tup in mi_processed: return
    mi_toprocess.append(tup)
    mi_processing_sources[tup] = g[MI_SRC]

def mi_processing_remains():
    return len(mi_toprocess) > 0

def mi_next_toprocess():
    return mi_toprocess[-1]

def mi_dispatch_processing(kind, s):
    if kind == NAME:
        mi_import_module_from_name(s)
    elif kind == FILE:
        mi_import_module_from_path(s)
    elif kind == DIR:
        mi_import_modules_from_dir(s)

def mi_rollover_toprocess():
    mi_processed.append(mi_toprocess.pop())


def find_runmodule():
    lock("CALLED:chassis2023.find_runmodule()")
    too_many_found = False
    has_run = []
    for module in modules:
        if getattr(module, "run", None):
            has_run.append(module)
    need = execution_type_D()[NRUNMODULES]  # how many needed?
    if len(has_run) == need:
        if need == 1:
            g[RUNMODULE] = has_run[0]
    elif len(has_run) > need:
        register_error(TOOMANYRUNMODULES, MODULES=has_run)
    elif len(has_run) < need:
        register_error(NORUNMODULE)

def find_pulsers():
    lock("CALLED:chassis2023.find_pulsers()")
    for module in modules:
        if getattr(module, "pulse", None):
            pulsers.append(module.pulse)


def inject_module_symbols():
    for mod in modules:
        symbols = intern_symbols(getattr(mod, kMODULE_INFO, {}).get("SYMBOLS"))
        inject_symbols(mod, symbols)
        symbols_from_module[mod.__name__] = symbols
    for mod in modules:
        requests = getattr(mod, kMODULE_INFO, {}).get("IMPORTSYMBOLS", [])
        for req in requests:
            inject_symbols(mod, symbols_from_module[req])


def define_snowflakes():
    for mod in modules:
        definitions = getattr(mod, kMODULE_INFO, {}).get("SNOWFLAKES", [])
        for _def in definitions:
            snowflakes.define(_def)


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


# --[ internal error code ]---------------------------------------------

def register_error(code, **data):
    """Internal function -- register this error, per whatever mechanisms."""
    if code == TOOMANYRUNMODULES:
        ttl = "Too Many Run Modules"
        msg = "There should only be one module with run() defined in it,\n"
        msg += "But these modules all define run():\n"
        for module in data[MODULES]:
            msg += "  " + str(module) + "\n"
        log(ERR, code, ttl, msg)
    elif code == NORUNMODULE:
        ttl = "No Run Module"
        msg = "run() was not defined in any of the imported modules:\n"
        for module in modules:
            msg += "  " + str(module) + "\n"
        if not modules:
            msg += "  (no modules)\n"
        log(ERR, code, ttl, msg)
    else:
        raise ValueError(code)


# --[ program data ]----------------------------------------------------

kPROGRAMDATA_FILENAME = "programdata.json"

def load_programdata():
    f = open(kPROGRAMDATA_FILENAME, "r", encoding="utf-8")
    g[PROGRAMDATA] = json.loads(f.read())


def save_programdata():
    f = open(kPROGRAMDATA_FILENAME, "w", encoding="utf-8")
    f.write(json.dumps(g[PROGRAMDATA]))


# --[ primary execution ]-----------------------------------------------

def setup():
    setup_symbols()
    setup_execution_types()
    setup_g()

def run():
    perform_prep()
#    if errors:
#        print_errors_report()
#        return
    perform_setup()
    perform_run()
    perform_teardown()


def perform_prep():
    load_programdata()
    gather_modules()
    find_runmodule()
    find_pulsers()
    inject_module_symbols()
    define_snowflakes()

def perform_setup():
    perform_stage(INIT)
    if execution_type_D()[NAME] == TKINTERGUI:
        import tk23base
        tk23base.setup()
    perform_stage(SETUP)
    #resources.load()
    perform_stage(LOAD)
    perform_stage(POSTLOAD)
    perform_stage(INTERLINK)

def perform_run():
    perform_stage(RUNSTART)
    if g[RUNMODULE]:
        g[RUNMODULE].run()
    elif execution_type_D()[NAME] == TKINTERGUI:
        import tk23process
        tk23process.run()
    perform_stage(RUNSTOP)

def perform_teardown():
    perform_stage(PRECLOSE)
    perform_stage(SAVE)
    #resources.save()
    perform_stage(POSTSAVE)
    perform_stage(TEARDOWN)

def perform_stage(stage):
    g[STAGE] = stage
    for m in modules:
        fn = getattr(m, "stage", None)
        if fn:
            fn()

def pulse():
    for fn in pulsers:
        fn()


# NOTE:
#   there is NO if __name__ == "__main__" block here, on purpose;
#     if this was run directly,
#     then imports of chassis2023 would load another module
#     due to a strange vagary of Python's;
#     so write a go.py that imports chassis2023 and then
#     calls the run() routine
#
