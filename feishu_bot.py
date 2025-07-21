#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Feishu GymBot: 适配飞书的健身与身体数据记录机器人。
"""
import os
import re
import urllib.parse
import logging
from collections import defaultdict
from functools import wraps
from datetime import datetime
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from feishu import FeishuBot, EventDispatcher
import database as db

# --- 初始化 ---
load_dotenv()
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

FEISHU_APP_ID = os.getenv("FEISHU_APP_ID")
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET")
FEISHU_VERIFICATION_TOKEN = os.getenv("FEISHU_VERIFICATION_TOKEN")
FEISHU_ENCRYPT_KEY = os.getenv("FEISHU_ENCRYPT_KEY")
ADMIN_USER_IDS_STR = os.getenv("ADMIN_USER_IDS")
if not ADMIN_USER_IDS_STR:
    ADMIN_USER_IDS = []
    logger.warning("ADMIN_USER_IDS environment variable not set. Admin commands will not be available.")
else:
    try:
        ADMIN_USER_IDS = [uid.strip() for uid in ADMIN_USER_IDS_STR.split(',')]
    except ValueError:
        raise ValueError("ADMIN_USER_IDS environment variable must be a comma-separated list of strings.")

# --- 状态与正则 ---
user_states = defaultdict(lambda: defaultdict(dict))
TRAINING_PATTERN = re.compile(r"""^\s*(?:(.+?)\s+)?(-?\d+\.?\d*)\s*kg\s+(\d+)\s*$""", re.IGNORECASE)
REPS_ONLY_PATTERN = re.compile(r"""^\s*(\d+)\s*$""")
BODY_DATA_PATTERN = re.compile(r"""^\s*([\u4e00-\u9fa5a-zA-Z]+)\s+(-?\d+\.?\d*)\s*([a-zA-Z%]*)\s*$""")

# --- Flask & FeishuBot ---
app = Flask(__name__)
bot = FeishuBot(app_id=FEISHU_APP_ID, app_secret=FEISHU_APP_SECRET)
dispatcher = EventDispatcher(bot, verification_token=FEISHU_VERIFICATION_TOKEN, encrypt_key=FEISHU_ENCRYPT_KEY)

# --- 装饰器 ---
def admin_only(func):
    @wraps(func)
    def wrapped(event, *args, **kwargs):
        user_id = event.get('sender', {}).get('sender_id', {}).get('open_id')
        if user_id not in ADMIN_USER_IDS:
            bot.reply_text(event, "抱歉,只有管理员才能使用此命令.")
            return
        return func(event, *args, **kwargs)
    return wrapped

# --- 处理消息 ---
@dispatcher.on_message
def handle_message(event):
    content = event.get('text', '').strip()
    user_id = event['sender']['sender_id']['open_id']
    chat_id = event['chat_id']
    state = user_states[chat_id][user_id]

    # 训练数据
    training_match = TRAINING_PATTERN.match(content)
    reps_only_match = REPS_ONLY_PATTERN.match(content)
    exercise_name, weight_kg, reps = None, None, None
    if training_match:
        exercise_name = training_match.group(1).strip() if training_match.group(1) else state.get('exercise')
        weight_kg = float(training_match.group(2))
        reps = int(training_match.group(3))
        if not exercise_name:
            bot.reply_text(event, "请先发送一条包含项目名称的完整记录.")
            return
        state['exercise'] = exercise_name
        state['weight'] = weight_kg
    elif reps_only_match:
        if 'exercise' not in state or 'weight' not in state:
            bot.reply_text(event, "请先发送一条包含项目和重量的完整记录.")
            return
        exercise_name = state['exercise']
        weight_kg = state['weight']
        reps = int(reps_only_match.group(1))
    if exercise_name and weight_kg is not None and reps is not None:
        previous_pr = db.get_personal_record(user_id, exercise_name)
        if previous_pr is None or weight_kg > previous_pr:
            pr_message = f"🎉 新纪录诞生! {exercise_name} 达到新的巅峰: {weight_kg}kg!"
            bot.reply_text(event, pr_message)
        log_id = db.add_training_log(user_id, chat_id, exercise_name, weight_kg, reps)
        state['last_log_id'] = log_id
        bot.reply_text(event, f"记录成功: {exercise_name} {weight_kg}kg {reps}次.")
        return
    # 身体数据
    body_data_match = BODY_DATA_PATTERN.match(content)
    if body_data_match:
        metric_type = body_data_match.group(1)
        value = float(body_data_match.group(2))
        valid_metrics = db.get_valid_body_metrics()
        if metric_type in valid_metrics:
            unit = valid_metrics[metric_type]
            db.add_body_data_log(user_id, metric_type, value, unit)
            bot.reply_text(event, f"身体数据记录成功: {metric_type} = {value} {unit}.")
            return
    # 帮助
    if content in ["/start", "/help", "帮助"]:
        help_text = (
            "*GymBot 使用指南*\n\n"
            "*记录训练*\n"
            "- 项目 重量kg 次数 (如: 卧推 80kg 10)\n"
            "- 重量kg 次数 (沿用上一条的项目)\n"
            "- 次数 (沿用上一条的项目和重量)\n\n"
            "*记录身体数据*\n"
            "- 指标 数值 (如: 体重 75, 体脂率 15%)\n\n"
            "*通用指令*\n"
            "- /help - 显示此帮助信息\n"
            "- /summary [day|week|month] - 查看训练总结 (默认本周)\n"
            "- /my_stats [项目名] - 查询指定项目的训练历史图表\n"
            "- /my_body_stats [指标名] - 查询指定身体指标的历史图表\n"
            "- /delete_last - 删除您发送的上一条训练记录\n\n"
            "*管理员指令*\n"
            "- /add_metric 名称 单位 - 添加新的身体指标 (如: /add_metric 臂围 cm)\n"
            "- /list_metrics - 查看所有可记录的身体指标\n"
            "- /delete_metric 名称 - 删除一个身体指标"
        )
        bot.reply_text(event, help_text)
        return
    logger.info(f"Message from {user_id} did not match any format: {content}")

# --- 其他命令（略，结构同上，可参考 bot.py 逐步迁移）---
# 你可以继续补充 /summary, /my_stats, /my_body_stats, /add_metric, /delete_metric, /list_metrics 等命令，
# 只需将 bot.reply_text(event, ...) 替换为对应的飞书消息回复即可。

# --- 启动 ---
if __name__ == '__main__':
    db.init_db()
    app.route('/feishu/webhook', methods=['POST'])(dispatcher.dispatch)
    app.run(host='0.0.0.0', port=8000) 