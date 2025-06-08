import zipfile
import docker

class Function:
    def __init__(self, config):
        self.config = config

    def build_image(self, file, output_dir):

    def docker_file_template(self, has_req):
        ubuntu_lines =
        """
        FROM ubuntu
MAINTAINER Minik8s <nyte_plus@sjtu.edu.cn>

RUN DEBIAN_FRONTEND=noninteractive apt-get -y update

RUN DEBIAN_FRONTEND=noninteractive apt-get -y install python3 python3-pip
        """

        if has_req:
            pip_lines =
            """
            RUN pip install -r requirements.txt

# install python requirements
RUN pip install flask
            """
        else:
            pip_lines = "RUN pip install flask"

        copy_lines = f"COPY {self.config.file_dir} ."

        run_lines = 'CMD ["python3","/serverlessServer.py"]'

        return ubuntu_lines + pip_lines + copy_lines + run_lines

if __name__ == '__main__':
    from pkg.config.functionConfig import FunctionConfig
    c = FunctionConfig('default', , code_dir)
    f = Function()
