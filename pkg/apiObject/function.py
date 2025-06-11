import zipfile
import os
import docker
import yaml
import shutil
import platform
from pathlib import Path

def exists_in_dir(file, dir):
    tgt_path = os.path.join(dir, file)
    return os.path.isfile(tgt_path)

class Function:
    def __init__(self, config, serverless_config, file):
        self.config = config
        self.file = file
        self.serverless_config = serverless_config
        self.image_name = None

        if platform.system() == "Windows":
            self.client = docker.DockerClient(
                base_url="npipe:////./pipe/docker_engine", version="1.25", timeout=60
            )
        else:
            self.client = docker.DockerClient(
                base_url="unix://var/run/docker.sock", version="1.25", timeout=5
            )

    def download_unzip_code(self):
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

    def build_image(self):
        code_dir = self.config.code_dir
        dockerfile_path = os.path.join(code_dir, 'Dockerfile')

        has_req = exists_in_dir('requirements.txt', code_dir)
        dockerfile_content = self.docker_file_template(has_req)
        with open(dockerfile_path, 'w') as f:
            f.write(dockerfile_content)

        try:
            image_name = f"{self.config.namespace}-{self.config.name}:latest"
            build_output = self.client.images.build(
                path = code_dir,
                dockerfile = dockerfile_path,
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

    def docker_file_template(self, has_req):
        pip_lines = "RUN pip install --no-cache-dir --break-system-packages -r requirements.txt" if has_req else ""

        return f"""
FROM python:3.9-slim
MAINTAINER Minik8s <nyte_plus@sjtu.edu.cn>

RUN DEBIAN_FRONTEND=noninteractive apt-get -y update
RUN DEBIAN_FRONTEND=noninteractive apt-get -y install python3 python3-pip

ADD ./serverlessServer.py serverlessServer.py
COPY ./ .

# install python requirements 
{pip_lines} -i https://pypi.tuna.tsinghua.edu.cn/simple
RUN pip install --break-system-packages flask

CMD ["python3","/serverlessServer.py"]
"""

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

    def pod_yaml_template(self, namespace, name):
        return f"""
apiVersion: v1
kind: Pod
metadata:
  name: {name}
  namespace: {namespace}
spec:
  containers:
  - name: {name}-server
    image: {self.config.target_image}
    ports:
    - containerPort: {self.serverless_config.POD_PORT}
      protocol: TCP
        """

    def pod_info(self, id):
        pod_name = self.serverless_config.POD_NAME.format(name = self.config.name, id = str(id))
        pod_namespace = self.serverless_config.POD_NAMESPACE.format(namespace = self.config.namespace)
        pod_yaml = yaml.safe_load(self.pod_yaml_template(pod_namespace, pod_name))

        return pod_namespace, pod_name, pod_yaml

if __name__ == '__main__':
    import requests
    import os
    from pkg.config.uriConfig import URIConfig

    print('测试函数上传')
    yaml_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '../../testFile/function-1.yaml')
    with open(yaml_path, "r", encoding="utf-8") as file:
        data = yaml.safe_load(file)
    file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '../../testFile/serverless/zip-function/pkgs(文件在第一层).zip')
    with open(file_path, 'rb') as f:
        file_data = f.read()

    files = {'file': (os.path.basename(file_path), file_data)}
    url = URIConfig.PREFIX + URIConfig.FUNCTION_SPEC_URL.format(namespace='default', name='hello')
    response = requests.post(url, files=files, data=data)
    print(response.json())
    input('Press Enter To Continue.')

    print('测试函数调用')
    json = {
        'a': 1,
        'b': 0
    }
    response = requests.put(url, json=json)
    print(response.json())