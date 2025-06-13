import paramiko
import os
from io import BytesIO
from time import sleep

def upload_file(ssh_client, localpath, remotepath):
    try:
        localpath = localpath.rstrip('\\').rstrip('/')
        localpath = localpath.replace('\t', '/t').replace('\n', '/n').replace('\r', '/r').replace('\b', '/b')  # 转换特殊字符
        localpath = localpath.replace('\f', '/f')
        localpath = os.path.abspath(localpath)
        print('转换后的本地文件路径为：%s' % localpath)

        remotepath = remotepath.rstrip('\\').rstrip('/')
        head, tail = os.path.split(localpath)
        if not tail:
            print('上传文件：%s 到远程：%s失败，本地文件名不能为空' % (localpath, remotepath))
            return [False, '上传文件：%s 到远程：%s失败，本地文件名不能为空' % (localpath, remotepath)]
        if not os.path.exists(head):
            print('上传文件：%s 到远程：%s失败，父路径不存在' % (localpath, remotepath, head))
            return [False, '上传文件：%s 到远程：%s失败，父路径不存在' % (localpath, remotepath, head)]

        if not (remotepath.startswith('/') or remotepath.startswith('.')):
            print('上传文件：%s 到远程：%s失败，远程路径填写不规范%s' % (localpath, remotepath, remotepath))
            return [False, '上传文件：%s 到远程：%s失败，远程路径填写不规范%s' % (localpath, remotepath, remotepath)]
        sftp_client = ssh_client.open_sftp()
        head, tail = os.path.split(remotepath)

        head = sftp_client.normalize(head)  # 规范化路径
        remotepath = head + '/' + tail
        print('规范化后的远程目标路径：', remotepath)

        print('正在上传文件：%s 到远程：%s' % (localpath, remotepath))
        sftp_client.put(localpath, remotepath)
        sftp_client.close()
        return [True, '']
    except Exception as e:
        print('上传文件：%s 到远程：%s 出错:%s' % (localpath, remotepath, e))
        return [False, '上传文件：%s 到远程：%s 出错:%s' % (localpath, remotepath, e)]

def upload(ssh_client, zip_path, script_path, remote_dir):
    """
    上传zip文件和脚本文件到SSH服务器

    参数:
        ssh_client: paramiko.SSHClient实例
        zip_path: 本地zip文件路径
        script_path: 本地脚本文件路径
        remote_dir: 远程服务器目标目录
    """
    # 上传zip文件
    remote_zip_path = os.path.join(remote_dir, os.path.basename(zip_path))
    this_path = os.path.dirname(os.path.abspath(__file__)).replace('\t', '/t').replace('\n', '/n').replace('\r', '/r').replace('\b', '/b').replace('\f', '/f')
    upload_file(ssh_client, os.path.join(this_path, zip_path), remote_zip_path)

    # 上传脚本文件
    remote_script_path = os.path.join(remote_dir, os.path.basename(script_path))
    upload_file(ssh_client, script_path, remote_script_path)

    return remote_zip_path, remote_script_path


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
    """检查作业的 .err 和 .out 文件是否存在"""
    stdout_files = ssh.exec_command(f"ls ~/ | grep '{job_id}.out'")[1].read().decode().strip()
    stderr_files = ssh.exec_command(f"ls ~/ | grep '{job_id}.err'")[1].read().decode().strip()

    if stdout_files and stderr_files:
        return True


if __name__ == "__main__":
    job_name = os.getenv('JOB_NAME', 'CUDA_mm')
    file_server = "data.hpc.sjtu.edu.cn"
    compute_server = "pilogin.hpc.sjtu.edu.cn"
    port = 22
    username = "stu1151"
    password = "1135540486ppt"

    # --- 使用文件服务器上传文件 ---
    # 文件路径
    local_zip_path = f"{job_name}.zip"
    local_slurm_path = f"{job_name}.slurm"
    remote_directory = "./"

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
        raise e
    finally:
        ssh.close()
        print("SSH连接已关闭")

    # --- 使用计算服务器上传任务 ---
    convert_commad = f'dos2unix {job_name}.slurm'
    command_to_execute = f"sbatch {job_name}.slurm"
    try:
        # 连接到计算服务器
        ssh.connect(compute_server, port, username, password)

        # 执行命令并捕获输出
        _, _, _ = ssh.exec_command(convert_commad)
        stdin, stdout, stderr = ssh.exec_command(command_to_execute)

        # 读取输出
        output = stdout.read().decode().strip()
        error = stderr.read().decode().strip()

        print(output, error)
        # 检查作业是否提交成功（Slurm 返回格式示例：Submitted batch job 12345）
        if "Submitted batch job" in output:
            job_id = output.split()[-1]  # 提取作业ID
            print(f"作业提交成功，ID: {job_id}")
        else:
            print("作业提交失败")

        while True:
            sleep(60.0)
            if check_slurm_output_files(ssh, job_id):
                break
    except Exception as e:
        print(f"发生错误: {str(e)}")
    finally:
        ssh.close()
        print("SSH连接已关闭")