# GymBot - 您的私人健身记录机器人

GymBot 是一个功能强大的 Telegram 机器人，旨在帮助您轻松记录和追踪您的健身数据，并通过图表直观地展示您的进步。

## ✨ 功能特性

- **便捷的训练记录**:
  - 支持记录训练项目、重量和次数 (`卧推 80kg 10`)。
  - 智能沿用上一条记录的项目和/或重量，简化输入 (`80kg 10` 或 `10`)。
- **身体数据追踪**:
  - 记录各项身体指标，如体重、体脂率等 (`体重 75`)。
  - 支持管理员自定义新的身体指标 (`/add_metric 臂围 cm`)。
- **数据可视化**:
  - 通过图表展示指定训练项目的历史负重趋势 (`/my_stats 卧推`)。
  - 通过图表展示指定身体指标的历史变化 (`/my_body_stats 体重`)。
- **即时反馈**:
  - **组数统计**: 每次记录后，自动提醒您当天该项目已完成的组数。
  - **个人纪录 (PR) 提醒**: 当您打破某项训练的个人最高负重纪录时，会收到祝贺消息。
- **灵活查询**:
  - 支持按日、周、月查看训练总结 (`/summary week`)。
  - 历史查询支持模糊匹配，无需输入完整的项目名称。
- **易于管理**:
  - 可随时删除上一条错误的训练记录 (`/delete_last`)。
  - 提供完整的管理员指令来管理身体指标。

## 🚀 部署指南

本项目使用 Docker 和 Docker Compose 进行部署，简单快捷。

### 1. 克隆仓库

```bash
git clone https://github.com/jjbb013/gymbot.git
cd gymbot
```

### 2. 创建环境配置文件

在项目根目录下，创建一个名为 `.env` 的文件。这是存放您个人密钥的地方。

复制以下内容到 `.env` 文件中，并替换为您自己的信息：

```env
# 您的 Telegram Bot Token
TELEGRAM_BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN

# 您的 Telegram User ID (作为管理员)。如果是多个，请用逗号隔开。
ADMIN_USER_IDS=YOUR_ADMIN_USER_ID
```

### 3. 配置数据库路径 (重要)

默认情况下，机器人会将数据库文件 `gym_bot.db` 创建在项目根目录。如果您想将数据库存放在其他位置，请修改 `docker-compose.yml` 文件中的 `volumes` 部分：

```yaml
volumes:
  # 将下面的路径 /path/to/your/db/gym_bot.db 替换为您的实际路径
  - /path/to/your/db/gym_bot.db:/app/gym_bot.db
```

### 4. 启动服务

完成以上配置后，执行以下命令来构建并启动机器人：

```bash
docker-compose up --build -d
```

服务将在后台启动。您可以随时使用 `docker logs gymbot_service` 来查看机器人的运行日志。

## 🤖 使用方法

直接在 Telegram 中向您的机器人发送以下命令或格式的消息：

### 记录训练
- `项目 重量kg 次数` (例如: `卧推 80kg 10`)
- `重量kg 次数` (沿用上一条的项目)
- `次数` (沿用上一条的项目和重量)

### 记录身体数据
- `指标 数值` (例如: `体重 75`, `体脂率 15%`)

### 通用指令
- `/help` - 显示帮助信息
- `/summary [day|week|month]` - 查看训练总结 (默认本周)
- `/my_stats [项目名]` - 查询指定项目的训练历史图表
- `/my_body_stats [指标名]` - 查询指定身体指标的历史图表
- `/delete_last` - 删除您发送的上一条训练记录

### 管理员指令
- `/add_metric 名称 单位` - 添加新的身体指标 (例如: `/add_metric 臂围 cm`)
- `/list_metrics` - 查看所有可记录的身体指标
- `/delete_metric 名称` - 删除一个身体指标
