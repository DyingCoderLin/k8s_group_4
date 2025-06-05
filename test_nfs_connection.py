#!/usr/bin/env python3
"""
测试NFS服务器连接和PV Controller的NFS存储创建功能
"""
import subprocess
import sys
import os

def test_nfs_connection():
    """测试SSH连接到NFS服务器"""
    print("=== 测试NFS服务器连接 ===")
    
    nfs_server = "10.119.15.190"
    nfs_user = "root"
    nfs_password = "Lin040430"
    
    # 构建SSH命令
    ssh_cmd = f"sshpass -p '{nfs_password}' ssh -o StrictHostKeyChecking=no {nfs_user}@{nfs_server}"
    
    # 测试基本连接
    test_cmd = f"{ssh_cmd} 'echo \"Connection successful\"'"
    print(f"执行命令: {test_cmd}")
    
    try:
        result = subprocess.run(test_cmd, shell=True, capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0:
            print("✅ SSH连接成功")
            print(f"输出: {result.stdout.strip()}")
        else:
            print("❌ SSH连接失败")
            print(f"错误: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        print("❌ SSH连接超时")
        return False
    except Exception as e:
        print(f"❌ SSH连接异常: {str(e)}")
        return False
    
    return True

def test_nfs_directory_operations():
    """测试NFS目录操作"""
    print("\n=== 测试NFS目录操作 ===")
    
    nfs_server = "10.119.15.190"
    nfs_user = "root"
    nfs_password = "Lin040430"
    
    ssh_cmd = f"sshpass -p '{nfs_password}' ssh -o StrictHostKeyChecking=no {nfs_user}@{nfs_server}"
    
    # 测试目录
    test_path = "/nfs/pv-storage/test-connection"
    
    # 1. 检查/nfs/pv-storage目录是否存在
    check_cmd = f"{ssh_cmd} 'ls -la /nfs/pv-storage'"
    print(f"检查/nfs/pv-storage目录: {check_cmd}")
    
    try:
        result = subprocess.run(check_cmd, shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ /nfs/pv-storage目录存在")
            print(f"目录内容:\n{result.stdout}")
        else:
            print("❌ /nfs/pv-storage目录不存在或无权限访问")
            print(f"错误: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ 检查目录失败: {str(e)}")
        return False
    
    # 2. 创建测试目录
    mkdir_cmd = f"{ssh_cmd} 'mkdir -p {test_path} && chmod 777 {test_path}'"
    print(f"创建测试目录: {mkdir_cmd}")
    
    try:
        result = subprocess.run(mkdir_cmd, shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ 测试目录创建成功")
        else:
            print("❌ 测试目录创建失败")
            print(f"错误: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ 创建目录失败: {str(e)}")
        return False
    
    # 3. 创建测试文件
    test_content = "This is a test file created by MiniK8s PV Controller test"
    create_file_cmd = f"{ssh_cmd} 'echo \"{test_content}\" > {test_path}/test.txt'"
    print(f"创建测试文件: {create_file_cmd}")
    
    try:
        result = subprocess.run(create_file_cmd, shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ 测试文件创建成功")
        else:
            print("❌ 测试文件创建失败")
            print(f"错误: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ 创建文件失败: {str(e)}")
        return False
    
    # 4. 验证文件内容
    read_file_cmd = f"{ssh_cmd} 'cat {test_path}/test.txt'"
    print(f"读取测试文件: {read_file_cmd}")
    
    try:
        result = subprocess.run(read_file_cmd, shell=True, capture_output=True, text=True)
        if result.returncode == 0 and test_content in result.stdout:
            print("✅ 测试文件内容验证成功")
            print(f"文件内容: {result.stdout.strip()}")
        else:
            print("❌ 测试文件内容验证失败")
            print(f"期望: {test_content}")
            print(f"实际: {result.stdout.strip()}")
            return False
    except Exception as e:
        print(f"❌ 读取文件失败: {str(e)}")
        return False
    
    # 5. 清理测试文件
    cleanup_cmd = f"{ssh_cmd} 'rm -rf {test_path}'"
    print(f"清理测试目录: {cleanup_cmd}")
    
    try:
        result = subprocess.run(cleanup_cmd, shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ 测试目录清理成功")
        else:
            print("⚠️ 测试目录清理失败，但不影响测试结果")
            print(f"错误: {result.stderr}")
    except Exception as e:
        print(f"⚠️ 清理失败: {str(e)}")
    
    return True

def test_nfs_exports():
    """测试NFS导出配置"""
    print("\n=== 测试NFS导出配置 ===")
    
    nfs_server = "10.119.15.190"
    nfs_user = "root"
    nfs_password = "Lin040430"
    
    ssh_cmd = f"sshpass -p '{nfs_password}' ssh -o StrictHostKeyChecking=no {nfs_user}@{nfs_server}"
    
    # 检查NFS导出
    check_exports_cmd = f"{ssh_cmd} 'showmount -e localhost'"
    print(f"检查NFS导出: {check_exports_cmd}")
    
    try:
        result = subprocess.run(check_exports_cmd, shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ NFS导出配置正常")
            print(f"导出列表:\n{result.stdout}")
            
            if "/nfs/pv-storage" in result.stdout:
                print("✅ /nfs/pv-storage已正确导出")
            else:
                print("⚠️ /nfs/pv-storage未在导出列表中找到")
        else:
            print("❌ 获取NFS导出失败")
            print(f"错误: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ 检查NFS导出失败: {str(e)}")
        return False
    
    return True

def main():
    """主测试函数"""
    print("NFS服务器连接测试开始...")
    print("=" * 50)
    
    # 检查sshpass是否安装
    try:
        result = subprocess.run("which sshpass", shell=True, capture_output=True, text=True)
        if result.returncode != 0:
            print("❌ sshpass未安装，请运行: brew install sshpass")
            sys.exit(1)
        else:
            print("✅ sshpass已安装")
    except Exception as e:
        print(f"❌ 检查sshpass失败: {str(e)}")
        sys.exit(1)
    
    # 运行测试
    tests = [
        test_nfs_connection,
        test_nfs_directory_operations,
        test_nfs_exports
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"❌ 测试异常: {str(e)}")
            results.append(False)
    
    # 总结
    print("\n" + "=" * 50)
    print("测试结果总结:")
    
    test_names = [
        "SSH连接测试",
        "目录操作测试", 
        "NFS导出测试"
    ]
    
    all_passed = True
    for i, (name, result) in enumerate(zip(test_names, results)):
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{i+1}. {name}: {status}")
        if not result:
            all_passed = False
    
    if all_passed:
        print("\n🎉 所有测试通过！NFS服务器连接正常，可以继续进行PV/PVC测试。")
        return 0
    else:
        print("\n⚠️ 部分测试失败，请检查NFS服务器配置。")
        return 1

if __name__ == "__main__":
    sys.exit(main())
