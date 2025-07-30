# 使用一个轻量级的 Python 官方镜像作为基础
FROM python:3.11-slim

# 设置容器内的工作目录
WORKDIR /app

# 将依赖文件复制到工作目录中
COPY requirements.txt .

# 安装项目依赖
RUN pip install --no-cache-dir -r requirements.txt

# 将项目代码复制到工作目录中
COPY . .

# 设置容器启动时要执行的命令
CMD ["python", "bot.py"]
