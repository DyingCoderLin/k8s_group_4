from pkg.apiObject.job import STATUS

class JobConfig:
    def __init__(self, form):
        self.name = form.get('metadata').get('name')
        self.status = STATUS.PENDING