"""snowflakes.py  -- data collection, identification, & indexing services

Lion's Mission #44, trigger2 Project #007G
"""

NAME = "NAME"
DEFAULT = "DEFAULT"
POLICY = "POLICY"
NEXT = "NEXT"

SESSION = "SESSION"  # POLICY: session-only value
EXPORTED = "EXPORTED"  # POLICY: imported and exported value


db = []  # {NAME: "...", DEFAULT: 0, POLICY: SESSION/EXPORTED, NEXT: 34}

byname = {}


def defined(name):
    return any((D[NAME] == name for D in db))

def define(snowflake_spec):
    """Define a snowflake specification.
    
    NAME: "..." (unique name of the snowflake sequence)
    DEFAULT: 0  (first value to be handed out; int)
    POLICY: SESSION/EXPORTED  (if EXPORTED, included in exports, imports)
    """
    entry = dict(snowflake_spec)  # copy; shallow is fine -- it shouldn't be complex, ever
    db.append(entry)
    byname[entry[NAME]] = entry


def export_to_jsondict():
    """Return Python JSON Object representing the current snowflake counts."""
    R = {}
    for D in db:
        if D[POLICY] == EXPORTED:
            R[D[NAME]] = D.get(NEXT, D[DEFAULT])
    return R

def import_from_jsondict(json_D):
    """Reset counts from Python JSON Object representing snowflake counts.
    
    If there's no snowflake value in the json_D, it's ignored.
    If there's a snowflake value defined in json_D, but it's not
      defined in this session, it's ignored.
    WARNING: ignored values will NOT be exported -- and quite likely LOST!
    """
    for D in db:
        if D[POLICY] == EXPORTED and D[NAME] in json_D:
            D[NEXT] = json_D[D[NAME]]


def next(name):
    D = byname[name]
    n = D.get(NEXT, D[DEFAULT])
    D[NEXT] = n+1
    return n

def reset(name, val=None):
    """Reset a snowflake count's next.
    
    By default, resets it to the snowflake counter's DEFAULT.
    Alternatively, you can specify a specific value to set as NEXT.
    """
    D = byname[name]
    if val is None:
        D[NEXT] = D[DEFAULT]
    else:
        D[NEXT] = val

