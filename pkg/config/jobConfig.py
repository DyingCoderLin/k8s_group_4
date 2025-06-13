from pkg.apiObject.job import STATUS

class JobConfig:
    def __init__(self, form):
        self.name = form.get('name')
        self.command = form.get('command', None)
        self.status = STATUS.PENDING
        self.out = None
        self.err = None

    def setOutput(self, out, err, status):
        self.out = out
        self.err = err
        self.status = status

    def to_dict(self):
        return {
            "name": self.name,
            "status": self.status,
            "out": self.out,
            "err": self.err,
        }