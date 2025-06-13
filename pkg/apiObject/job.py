import docker
import os
import platform
import shutil

def exists_in_dir(file, dir):
    tgt_path = os.path.join(dir, file)
    return os.path.isfile(tgt_path)

class STATUS:
    PENDING = "PENDING"
    FAILED = "FAILED"
    FINISHED = "FINISHED"

class Job():
    def __init__(self, config, serverless_config, uri_config, file):
        # 这个类就是负责构建一个镜像罢了，生成一个起Pod的参数罢了
        # 我*了，写k8s真给我写应激了
        self.config = config
        self.serverless_config = serverless_config
        self.uri_config = uri_config
        self.file = file

        if platform.system() == "Windows":
            self.client = docker.DockerClient(
                base_url="npipe:////./pipe/docker_engine", version="1.25", timeout=60
            )
        else:
            self.client = docker.DockerClient(
                base_url="unix://var/run/docker.sock", version="1.25", timeout=5
            )

    def slurm_template(self, command, job_name = 'default', num_gpus = 1, mail_user = 'nyte_plus@sjtu.edu.cn'):
        return f"""
#!/bin/bash

#SBATCH --job-name={job_name}
#SBATCH --partition=dgx2
#SBATCH -N 1
#SBATCH --ntasks-per-node=4
#SBATCH --gres=gpu:{num_gpus}
#SBATCH --mail-type=end
#SBATCH --mail-user={mail_user}
#SBATCH --output=%j.out
#SBATCH --error=%j.err

{command}
"""

    def download_code(self):
        code_dir = self.serverless_config.JOB_PATH.format(name=self.config.name)
        if os.path.exists(code_dir):
            # 删除该目录
            try:
                shutil.rmtree(code_dir)  # 递归删除目录及其所有内容
                print(f"[INFO]Overwrite {code_dir}")
            except Exception as e:
                print(f"[INFO]{code_dir} already exists and cannot overwrite: {e}")

        os.makedirs(code_dir, exist_ok=False)

        # 存储代码文件
        if os.path.splitext(self.file.filename)[0] != self.config.name:
            print(f'[WARNING]Python file name {self.file.filename} does not equal to function name {self.config.name}. Renaming to {self.config.name}.py')
        self.file.save(os.path.join(code_dir, self.config.name + '.zip'))

        # 复制一份uploader.py
        shutil.copy(self.serverless_config.UPLOADER_PATH, os.path.join(code_dir, 'uploader.py'))
        # 写入执行脚本
        slurm_path = os.path.join(code_dir, f"{self.config.name}.slurm")
        slurm_content = self.slurm_template(self.config.command, self.config.name)
        with open(slurm_path, 'w') as f:
            f.write(slurm_content)

    def docker_file_template(self, apiserver_url, apiserver_port):
        return f"""
FROM python:3.9-slim
MAINTAINER Minik8s <nyte_plus@sjtu.edu.cn>

ENV APISERVER_URL={apiserver_url} APISERVER_PORT={apiserver_port} JOB_NAME={self.config.name}

RUN DEBIAN_FRONTEND=noninteractive apt-get -y update
RUN DEBIAN_FRONTEND=noninteractive apt-get -y install python3 python3-pip

ADD ./uploader.py uploader.py
ADD ./{self.config.name}.slurm {self.config.name}.slurm
ADD ./{self.config.name}.zip {self.config.name}.zip
COPY ./ .

# install python requirements 
RUN pip install --no-cache-dir --break-system-packages paramiko requests

CMD ["python3","./uploader.py"]
"""

    def build_image(self):
        job_path = self.serverless_config.JOB_PATH.format(name=self.config.name)
        dockerfile_path = os.path.join(job_path, 'Dockerfile')

        dockerfile_content = self.docker_file_template(self.uri_config.HOST, self.uri_config.PORT)
        with open(dockerfile_path, 'w') as f:
            f.write(dockerfile_content)

        try:
            image_name = f"{self.config.name.lower()}:latest"
            build_output = self.client.images.build(
                path=job_path,
                dockerfile=dockerfile_path,
                tag=image_name,
                rm=True
            )
            self.image_name = image_name
            print(f"[INFO]镜像构建成功")
        except docker.errors.BuildError as e:
            print(f"[ERROR]构建失败: {e.msg}")
            raise
        except docker.errors.APIError as e:
            print(f"[ERROR]Docker API 错误: {e}")
            raise

    def push_image(self):
        if self.image_name is None:
            raise ValueError('Image is not built yet. You should call "build_image" before "push_image".')
        try:
            target_image = f"{self.serverless_config.REGISTRY_URL}/{self.image_name}"
            image = self.client.images.get(self.image_name)
            image.tag(target_image)
            resp = self.client.api.push(
                repository=target_image,
                stream=True,
                decode=True,
                auth_config={
                    'username': self.serverless_config.REGISTRY_USER,
                    'password': self.serverless_config.REGISTRY_PASSWORD
                }
            )
            for line in resp:
                if 'error' in line:
                    err_msg = line['errorDetail']['message']
                    raise ValueError(err_msg)
            print(f'[INFO]镜像上传registry成功')
            self.target_image = target_image
            return target_image
        except Exception as e:
            print(f'[EEROR]镜像上传失败: {str(e)}')
            raise

    def run(self):
        self.client.containers.run(image=self.target_image, name=f'Job-{self.config.name}', detach=True)

    def delete(self):
        containers = self.client.containers.list(all=True, filters={"name": self.config.name})
        if len(containers) > 0:
            for container in containers: container.remove(force=True)

if __name__ == '__main__':
    import yaml
    import requests
    from pkg.config.globalConfig import GlobalConfig
    from pkg.config.uriConfig import URIConfig
    config = GlobalConfig()

    job = 'CUDA_mm'
    yaml_path = os.path.join(config.TEST_FILE_PATH, f'job-1.yaml')
    with open(yaml_path, "r", encoding="utf-8") as file:
        data = yaml.safe_load(file)
    
    file_path = os.path.join(config.TEST_FILE_PATH, f'job/CUDA_mm.zip')
    with open(file_path, 'rb') as f:
        file_data = f.read()

    form = {
        "name": data.get('metadata').get('name'),
        "command": data.get('args').get('command'),
    }

    # post
    files = {'file': (os.path.basename(file_path), file_data)}
    
    url = URIConfig.PREFIX + URIConfig.JOB_SPEC_URL.format(name=job)
    response = requests.post(url, files=files, data=form)
    print(response.json())

    # get
    url = URIConfig.PREFIX + URIConfig.JOB_SPEC_URL.format(name=job)
    response = requests.get(url, files=files, data=form)
    print(response.json())

    input('Press Enter to continue.')
    url = URIConfig.PREFIX + URIConfig.JOB_SPEC_URL.format(name=job)
    response = requests.get(url, files=files, data=form)
    print(response.json())