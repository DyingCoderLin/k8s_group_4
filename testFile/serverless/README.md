# Minik8s Serverless 规范

---
## Function

### Function定义规范
- 只支持**python**语言
- 两种函数上传方式
  - **1. 通过单个python文件上传**：适用于不依赖于其它文件，并且不需要安装依赖的简单程序
  - **2. 通过zip压缩包上传**：适用于项目，可以提供requirments文件，从而进行依赖下载
- 文件定义规范
  - **1. 对于单个python文件**：python文件名必须和声明的函数名一致，文件内有且仅有一个`handler`函数作为入口。
  - **2. 对于zip项目**：zip包解压后应该是一个目录，进入目录下至少包含一个与函数名一致的python文件，python文件内部有且仅有一个`handler`函数签名。目录下可以存在`requirements.txt`，会自动添加依赖
- 函数签名规范
  - 入口函数为`<function名>.py`文件中的`handler`函数，它的输入类型为两个`dict`，输出类型为`dict`。输出的含义由用户自己决定，但需要能够序列化。
  - ```
    def handler(event: dict, context: dict) -> dict:
    ```
    
### Example
