import paramiko
import os
from io import BytesIO
import requests
from time import sleep

def upload(ssh_client, zip_path, script_path, remote_dir):
    """
    上传zip文件和脚本文件到SSH服务器

    参数:
        ssh_client: paramiko.SSHClient实例
        zip_path: 本地zip文件路径
        script_path: 本地脚本文件路径
        remote_dir: 远程服务器目标目录
    """
    sftp = ssh_client.open_sftp()

    try:
        # 上传zip文件
        remote_zip_path = os.path.join(remote_dir, os.path.basename(zip_path))
        sftp.put(zip_path, remote_zip_path)
        print(f"上传 {zip_path} 到 {remote_zip_path} 成功")

        # 上传脚本文件
        remote_script_path = os.path.join(remote_dir, os.path.basename(script_path))
        sftp.put(script_path, remote_script_path)
        print(f"上传 {script_path} 到 {remote_script_path} 成功")

        return remote_zip_path, remote_script_path
    finally:
        sftp.close()


def unzip(ssh_client, remote_zip_path, remote_dir):
    """
    在远程服务器上解压zip文件

    参数:
        ssh_client: paramiko.SSHClient实例
        remote_zip_path: 远程zip文件路径
        remote_dir: 解压到的目录
    """
    # 确保unzip命令可用
    command = f"unzip -o {remote_zip_path} -d {remote_dir}"

    stdin, stdout, stderr = ssh_client.exec_command(command)
    exit_status = stdout.channel.recv_exit_status()

    if exit_status == 0:
        print(f"解压 {remote_zip_path} 成功")
    else:
        error = stderr.read().decode()
        raise Exception(f"解压失败: {error}")


def exec(ssh_client, command):
    """
    在远程服务器上执行命令

    参数:
        ssh_client: paramiko.SSHClient实例
        command: 要执行的命令
    """
    stdin, stdout, stderr = ssh_client.exec_command(command)
    exit_status = stdout.channel.recv_exit_status()

    output = stdout.read().decode()
    error = stderr.read().decode()

    print(f"执行命令: {command}")
    print(f"输出:\n{output}")

    if exit_status != 0:
        raise Exception(f"命令执行失败 (状态码 {exit_status}): {error}")

    return output


def check_slurm_output_files(ssh, job_id):
    """检查作业的 .err 和 .out 文件是否存在，并返回文件内容

    Args:
        ssh: paramiko.SSHClient 连接对象
        job_id: SLURM 作业ID

    Returns:
        tuple: (stdout_content, stderr_content) 如果文件存在
        None: 如果任一文件不存在
    """
    # 检查并读取 stdout 文件
    stdout_file = f"{job_id}.out"
    stdin, stdout, stderr = ssh.exec_command(f"cat ~/{stdout_file} 2>/dev/null")
    stdout_content = stdout.read().decode().strip()

    # 检查并读取 stderr 文件
    stderr_file = f"{job_id}.err"
    stdin, stdout, stderr = ssh.exec_command(f"cat ~/{stderr_file} 2>/dev/null")
    stderr_content = stdout.read().decode().strip()

    # 如果两个文件都有内容或至少存在
    if stdout_content or stderr_content:
        return True, stdout_content, stderr_content
    else:
        return False, '', ''


if __name__ == "__main__":
    job_name = os.getenv('JOB_NAME', 'DEFAULT')
    ip = os.getenv('APISERVER_URL', '10.115.191.182')
    port = os.getenv('APISERVER_PORT', 5050)

    file_server = "data.hpc.sjtu.edu.cn"
    compute_server = "pilogin.hpc.sjtu.edu.cn"
    port = 22
    username = "stu1151"
    password = "1135540486ppt"

    # --- 使用文件服务器上传文件 ---
    # 文件路径
    local_zip_path = f"{job_name}.zip"
    local_slurm_path = f"{job_name}.slurm"
    remote_directory = "~/"

    # 创建SSH客户端
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        # 连接到文件服务器
        ssh.connect(file_server, port, username, password)

        # 上传文件
        remote_zip, remote_script = upload(ssh, local_zip_path, local_slurm_path, remote_directory)

        # 解压文件
        unzip(ssh, remote_zip, remote_directory)
    except Exception as e:
        print(f"发生错误: {str(e)}")
    finally:
        ssh.close()
        print("SSH连接已关闭")

    # --- 使用计算服务器上传任务 ---
    command_to_execute = f"sbatch {job_name}.slurm"
    try:
        # 连接到计算服务器
        ssh.connect(compute_server, port, username, password)

        # 执行命令并捕获输出
        stdin, stdout, stderr = ssh.exec_command(command_to_execute)

        # 读取输出
        output = stdout.read().decode().strip()
        error = stderr.read().decode().strip()

        # 检查作业是否提交成功（Slurm 返回格式示例：Submitted batch job 12345）
        if "Submitted batch job" in output:
            job_id = output.split()[-1]  # 提取作业ID
            print(f"作业提交成功，ID: {job_id}")
        else:
            print("作业提交失败")

        while True:
            sleep(30.0)
            print('检查作业完成情况')
            flag, out, err = check_slurm_output_files(ssh, job_id)
            if flag:
                json = {
                    'err': err,
                    'out': out
                }
                requests.put(f'http://{ip}:{port}/apis/v1/jobs/{job_name}', json=json)
                break
    except Exception as e:
        print(f"发生错误: {str(e)}")
    finally:
        ssh.close()
        print("SSH连接已关闭")