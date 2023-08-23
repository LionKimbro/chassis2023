

def timestamp():
    "Return a UTC ISO-8601 timestamp as a string."
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())


