

class ChassisException(Exception): pass


class BrokenPromise(ChassisException): pass

class WasLocked(BrokenPromise): pass

class WasNotLocked(BrokenPromise): pass

class BadState(BrokenPromise): pass

