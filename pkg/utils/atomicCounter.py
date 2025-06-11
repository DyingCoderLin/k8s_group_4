import threading

class AtomicCounter:
    def __init__(self):
        self._dict = dict()
        self._lock = threading.Lock()

    def increment(self, key):
        with self._lock:
            if self._dict.get(key) is None:
                self._dict[key] = 0
            self._dict[key] += 1

    def get(self, key):
        with self._lock:
            if self._dict.get(key) is None:
                self._dict[key] = 0
            return self._dict[key]

    def reset(self, key):
        with self._lock:
            self._dict[key] = 0