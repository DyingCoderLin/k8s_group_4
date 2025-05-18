import os

class GlobalConfig:
    """
    Global configuration class for the application.
    """
    # 计算并缓存项目根目录路径
    @classmethod
    def get_project_root(cls):
        if not hasattr(cls, '_PROJECT_ROOT'):
            # 从配置文件位置推导项目根目录
            config_file = os.path.abspath(__file__)
            config_dir = os.path.dirname(config_file)
            pkg_dir = os.path.dirname(config_dir)
            cls._PROJECT_ROOT = os.path.dirname(pkg_dir)
        return cls._PROJECT_ROOT
    
    @classmethod
    def get_docker_yml_path(cls):
        return os.path.join(cls.get_project_root(), 'docker_ymls')
    
    @classmethod
    def get_test_file_path(cls):
        return os.path.join(cls.get_project_root(), 'testFile')
    
    @classmethod
    def get_config_path(cls):
        return os.path.join(cls.get_project_root(), 'pkg', 'config')
    
    # 向后兼容的属性
    @property
    def PROJECT_ROOT(self):
        return self.get_project_root()
    
    @property
    def DOCKER_YML_FILE_PATH(self):
        return self.get_docker_yml_path()
    
    @property
    def TEST_FILE_PATH(self):
        return self.get_test_file_path()
    
    @property
    def CONFIG_PATH(self):
        return self.get_config_path()