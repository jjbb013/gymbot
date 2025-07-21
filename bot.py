#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
GymBot: A Telegram bot to track fitness and body data, with advanced features.
"""

import logging
import re
import urllib.parse
import os # Import os module to access environment variables
from collections import defaultdict
from functools import wraps
from datetime import datetime
from dotenv import load_dotenv # Import load_dotenv

load_dotenv()  # 先加载 .env 文件

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

import database as db

# --- Configuration ---
# IMPORTANT: Get your bot token from environment variable
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN environment variable not set.")

# IMPORTANT: Get admin user IDs from environment variable
ADMIN_USER_IDS_STR = os.getenv("ADMIN_USER_IDS")
if not ADMIN_USER_IDS_STR:
    ADMIN_USER_IDS = []
    logger.warning("ADMIN_USER_IDS environment variable not set. Admin commands will not be available.")
else:
    try:
        ADMIN_USER_IDS = [int(uid.strip()) for uid in ADMIN_USER_IDS_STR.split(',')]
    except ValueError:
        raise ValueError("ADMIN_USER_IDS environment variable must be a comma-separated list of integers.")

# --- State & Patterns ---
user_states = defaultdict(lambda: defaultdict(dict)) # {chat_id: {user_id: {exercise, weight, last_log_id}}}

# Combined regex for efficiency
TRAINING_PATTERN = re.compile(
    r"""^\s*(?:(.+?)\s+)?(-?\d+\.?\d*)\s*kg\s+(\d+)\s*""",
    re.IGNORECASE
)
REPS_ONLY_PATTERN = re.compile(r"""^\s*(\d+)\s*"""
)
BODY_DATA_PATTERN = re.compile(r"""^\s*([\u4e00-\u9fa5a-zA-Z]+)\s+(-?\d+\.?\d*)\s*([a-zA-Z%]*)\s*"""
)

# --- Decorators for Auth ---
def admin_only(func):
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id not in ADMIN_USER_IDS:
            await update.message.reply_text("抱歉,只有管理员才能使用此命令.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapped

# --- Command Handlers ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("欢迎使用 GymBot! 我会帮助您追踪训练和身体数据. 发送 /help 查看所有指令.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = (
        "*GymBot 使用指南*\n\n"
        "*记录训练*\n"
        "- `项目 重量kg 次数` (例如: `卧推 80kg 10`)\n"
        "- `重量kg 次数` (沿用上一条的项目)\n"
        "- `次数` (沿用上一条的项目和重量)\n\n"
        "*记录身体数据*\n"
        "- `指标 数值` (例如: `体重 75`, `体脂率 15%`)\n\n"
        "*通用指令*\n"
        "- `/help` - 显示此帮助信息\n"
        "- `/summary [day|week|month]` - 查看训练总结 (默认本周)\n"
        "- `/my_stats [项目名]` - 查询指定项目的训练历史图表\n"
        "- `/my_body_stats [指标名]` - 查询指定身体指标的历史图表\n"
        "- `/delete_last` - 删除您发送的上一条训练记录\n\n"
        "*管理员指令*\n"
        "- `/add_metric 名称 单位` - 添加新的身体指标 (例如: `/add_metric 臂围 cm`)\n"
        "- `/list_metrics` - 查看所有可记录的身体指标\n"
        "- `/delete_metric 名称` - 删除一个身体指标"
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def summary_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, chat_id = update.effective_user, update.effective_chat.id
    period = context.args[0].lower() if context.args and context.args[0].lower() in ['day', 'week', 'month'] else 'week'
    summary_data = db.get_training_summary(user.id, chat_id, period)

    if not summary_data:
        await update.message.reply_text(f"您在指定时间范围内没有任何训练记录.")
        return

    period_map = {'day': '今日', 'week': '本周', 'month': '本月'}
    response_text = f"💪 *{user.first_name} 的{period_map[period]}训练总结*:\n\n"
    total_volume = sum(item['total_volume'] for item in summary_data)

    for item in summary_data:
        response_text += f"🏋️ *{item['exercise_name']}*\n"
        response_text += f"  - 组数: {item['sets']}, 总次数: {item['total_reps']}\n"
        response_text += f"  - 巅峰重量: {item['max_weight']} kg, 总容量: {item['total_volume']} kg\n\n"
    
    response_text += f"🔥 *总计训练容量*: {total_volume} kg"
    await update.message.reply_text(response_text, parse_mode='Markdown')

async def delete_last_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    state = user_states[chat_id][user_id]

    if 'last_log_id' not in state:
        await update.message.reply_text("我没有找到您上一条可以删除的训练记录.")
        return

    if db.delete_last_log(state['last_log_id'], user_id):
        await update.message.reply_text("👌 已成功删除您的上一条训练记录.")
        del state['last_log_id']
    else:
        await update.message.reply_text("删除失败,可能记录已被删除或不存在.")

# --- Charting Commands ---

async def my_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("请提供要查询的训练项目, 例如: `/my_stats 卧推`")
        return
    
    exercise_name = " ".join(context.args)
    history = db.get_exercise_history(update.effective_user.id, exercise_name)

    if not history:
        await update.message.reply_text(f"找不到关于“{exercise_name}”的训练记录.")
        return

    dates = [datetime.strptime(row['timestamp'], '%Y-%m-%d %H:%M:%S').strftime('%m-%d') for row in reversed(history)]
    weights = [row['weight_kg'] for row in reversed(history)]

    chart_config = {
        'type': 'line',
        'data': {
            'labels': dates,
            'datasets': [{'label': '负重 (kg)', 'data': weights, 'fill': False, 'borderColor': '#4e73df'}]
        },
        'options': {'title': {'display': True, 'text': f'{exercise_name} 负重趋势'}}
    }
    chart_url = "https://quickchart.io/chart?c=" + urllib.parse.quote(str(chart_config))
    await update.message.reply_photo(photo=chart_url, caption=f"这是您最近的 *{exercise_name}* 训练趋势图.", parse_mode='Markdown')

async def my_body_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("请提供要查询的身体指标, 例如: `/my_body_stats 体重`")
        return

    metric_name = " ".join(context.args)
    history = db.get_body_data_history(update.effective_user.id, metric_name)

    if not history:
        await update.message.reply_text(f"找不到关于“{metric_name}”的身体数据记录.")
        return

    dates = [datetime.strptime(row['timestamp'], '%Y-%m-%d %H:%M:%S').strftime('%m-%d') for row in reversed(history)]
    values = [row['value'] for row in reversed(history)]

    chart_config = {
        'type': 'line',
        'data': {
            'labels': dates,
            'datasets': [{'label': metric_name, 'data': values, 'fill': False, 'borderColor': '#1cc88a'}]
        },
        'options': {'title': {'display': True, 'text': f'{metric_name} 变化趋势'}}
    }
    chart_url = "https://quickchart.io/chart?c=" + urllib.parse.quote(str(chart_config))
    await update.message.reply_photo(photo=chart_url, caption=f"这是您最近的 *{metric_name}* 数据趋势图.", parse_mode='Markdown')

# --- Admin Commands ---

@admin_only
async def add_metric_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) != 2:
        await update.message.reply_text("格式错误. 请使用: `/add_metric <名称> <单位>`")
        return
    
    metric_name, unit = context.args[0], context.args[1]
    if db.add_body_metric_config(metric_name, unit):
        await update.message.reply_text(f"✅ 已成功添加新的身体指标: {metric_name} ({unit})")
    else:
        await update.message.reply_text(f"添加失败, 指标“{metric_name}”可能已存在.")

@admin_only
async def delete_metric_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("格式错误. 请使用: `/delete_metric <名称>`")
        return

    metric_name = context.args[0]
    if db.delete_body_metric_config(metric_name):
        await update.message.reply_text(f"🗑️ 已成功删除指标: {metric_name}")
    else:
        await update.message.reply_text(f"删除失败, 找不到指标“{metric_name}”.")

@admin_only
async def list_metrics_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    metrics = db.get_valid_body_metrics()
    if not metrics:
        await update.message.reply_text("当前没有配置任何身体指标.")
        return
    
    response = "*当前可记录的身体指标*:\n"
    for name, unit in metrics.items():
        response += f"- {name} ({unit})\n"
    await update.message.reply_text(response, parse_mode='Markdown')

# --- Main Message Handler ---

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_message = update.message.text
    user, chat_id = update.effective_user, update.effective_chat.id
    state = user_states[chat_id][user.id]

    # Try to parse as training data first
    training_match = TRAINING_PATTERN.match(user_message)
    reps_only_match = REPS_ONLY_PATTERN.match(user_message)

    exercise_name, weight_kg, reps = None, None, None

    if training_match:
        exercise_name = training_match.group(1).strip() if training_match.group(1) else state.get('exercise')
        weight_kg = float(training_match.group(2))
        reps = int(training_match.group(3))
        if not exercise_name:
            await update.message.reply_text("请先发送一条包含项目名称的完整记录.")
            return
        state['exercise'] = exercise_name
        state['weight'] = weight_kg

    elif reps_only_match:
        if 'exercise' not in state or 'weight' not in state:
            await update.message.reply_text("请先发送一条包含项目和重量的完整记录.")
            return
        exercise_name = state['exercise']
        weight_kg = state['weight']
        reps = int(reps_only_match.group(1))

    if exercise_name and weight_kg is not None and reps is not None:
        # Check for PR
        previous_pr = db.get_personal_record(user.id, exercise_name)
        if previous_pr is None or weight_kg > previous_pr:
            pr_message = f"🎉 *新纪录诞生!* {exercise_name} 达到新的巅峰: {weight_kg}kg!"
            await context.bot.send_message(chat_id, pr_message, parse_mode='Markdown')
        
        log_id = db.add_training_log(user.id, chat_id, exercise_name, weight_kg, reps)
        state['last_log_id'] = log_id
        await update.message.reply_text(f"记录成功: {exercise_name} {weight_kg}kg {reps}次.")
        return

    # Try to parse as body data
    body_data_match = BODY_DATA_PATTERN.match(user_message)
    if body_data_match:
        metric_type = body_data_match.group(1)
        value = float(body_data_match.group(2))
        valid_metrics = db.get_valid_body_metrics()
        
        if metric_type in valid_metrics:
            unit = valid_metrics[metric_type]
            db.add_body_data_log(user.id, metric_type, value, unit)
            await update.message.reply_text(f"身体数据记录成功: {metric_type} = {value} {unit}.")
            return

    logger.info(f"Message from {user.first_name} did not match any format: {user_message}")


def main() -> None:
    """Start the bot."""
    db.init_db()
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("summary", summary_command))
    application.add_handler(CommandHandler("delete_last", delete_last_command))
    application.add_handler(CommandHandler("my_stats", my_stats_command))
    application.add_handler(CommandHandler("my_body_stats", my_body_stats_command))
    application.add_handler(CommandHandler("add_metric", add_metric_command))
    application.add_handler(CommandHandler("delete_metric", delete_metric_command))
    application.add_handler(CommandHandler("list_metrics", list_metrics_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot is starting...")
    application.run_polling()

if __name__ == '__main__':
    main()
