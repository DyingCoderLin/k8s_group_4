import docker

class STATUS:
    PENDING = "PENDING"
    FAILED = "FAILED"
    FINISHED = "FINISHED"

class Job():
    def __init__(self, config, serverless_config, uri_config):
        # 这个类就是负责构建一个镜像罢了，生成一个起Pod的参数罢了
        # 我*了，写k8s真给我写应激了
        self.config = config
        self.serverless_config = serverless_config
        self.uri_config = uri_config

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
        code_dir = self.config.code_dir
        if os.path.exists(code_dir):
            # 删除该目录
            try:
                shutil.rmtree(code_dir)  # 递归删除目录及其所有内容
                print(f"[INFO]Overwrite {code_dir}")
            except Exception as e:
                print(f"[INFO]{code_dir} already exists and cannot overwrite: {e}")

        os.makedirs(code_dir, exist_ok=False)

        # 解压文件并存储代码文件
        if zipfile.is_zipfile(self.file):
            self.file.seek(0)
            with zipfile.ZipFile(self.file, "r") as zip_ref:
                zip_ref.extractall(code_dir)
            find_handler = False

            if exists_in_dir(f"{self.config.name}.py", code_dir):
                print(f'[INFO]Find {self.config.name}.py in the first layer.')
                find_handler = True
            else:
                print(f'[INFO]Cannot find {self.config.name}.py in the first layer.')
                sub_dirs = os.listdir(code_dir)
                if len(sub_dirs) == 1:
                    print(f'[INFO]Only one subdir. Finding in the subdir.')
                    sub_dir = os.path.join(code_dir, sub_dirs[0])
                    if exists_in_dir(f"{self.config.name}.py", sub_dir):
                        base_path, sub_path = Path(code_dir), Path(sub_dir)
                        temp_dir = base_path / "temp_migration"
                        temp_dir.mkdir(exist_ok=True)

                        try:
                            for item in Path(sub_path).iterdir():
                                shutil.move(str(item), str(temp_dir))
                            sub_path.rmdir()
                            for item in temp_dir.iterdir():
                                shutil.move(str(item), str(base_path))
                        finally:
                            if temp_dir.exists():
                                temp_dir.rmdir()
                        print(f'[INFO]Find {self.config.name}.py in the second layer.')
                        find_handler = True
                    else:
                        print(f'[INFO]Cannot find {self.config.name}.py in the second layer.')
                else:
                    print(f'[INFO]Multiple subdir. Stop finding.')

            if not find_handler:
                print(f'[INFO]Cannot find {self.config.name}.py in zip files.')
                raise ValueError(f"Cannot find {self.config.name}.py in zip files")

        elif self.file.filename[-3:] == '.py':
            if os.path.splitext(self.file.filename)[0] != self.config.name:
                print(f'[WARNING]Python file name {self.file.filename} does not equal to function name {self.config.name}. Renaming to {self.config.name}.py')
            self.file.save(os.path.join(code_dir, {self.config.name} + '.py'))
        else:
            raise ValueError(f"File type {os.path.splitext(self.file.filename)[1]} is not supported. You should upload an *.zip or *.py.")

        # 复制一份serverlessServer.py
        if exists_in_dir('serverlessServer.py', code_dir):
            raise ValueError(f'Your file should not contain named "serverlessServer.py".')
        shutil.copy(self.serverless_config.SERVER_PATH, os.path.join(code_dir, 'serverlessServer.py'))


    def docker_file_template(self, apiserver_url, apiserver_port):
        return f"""
FROM python:3.9-slim
MAINTAINER Minik8s <nyte_plus@sjtu.edu.cn>

ENV APISERVER_URL={apiserver_url} APISERVER_PORT={apiserver_port}

RUN DEBIAN_FRONTEND=noninteractive apt-get -y update
RUN DEBIAN_FRONTEND=noninteractive apt-get -y install python3 python3-pip

ADD ./uploader.py uploader.py
COPY ./ .

# install python requirements 
RUN pip install --no-cache-dir --break-system-packages paramiko requests

CMD ["python3","/uploader.py"]
"""

    def build_image(self):
        job_path = self.serverless_config.JOB_PATH.format(self.config.name)
        dockerfile_path = os.path.join(job_path, 'Dockerfile')

        dockerfile_content = self.docker_file_template(self.uri_config.HOST, self.uri_config.PORT)
        with open(dockerfile_path, 'w') as f:
            f.write(dockerfile_content)

        try:
            image_name = f"{self.config.name}:latest"
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
            for line in e.build_log:
                if "error" in line.lower():
                    print(line.get('stream', '').strip())
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
        except Exception as e:
            print(f'[EEROR]镜像上传失败: {str(e)}')
            raise
        finally:
            return target_image
