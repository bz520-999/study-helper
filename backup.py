# -*- coding: utf-8 -*-
"""
备份模块：把数据库"复印"一份到 backups 文件夹。
  - 启动自动备份：距上次备份超过 BACKUP_INTERVAL_HOURS 小时就备份
  - 手动备份：设置页按钮随时触发
  - 保留策略：最多 BACKUP_KEEP 份，最旧的自动删除
用 SQLite 官方的 backup() API 复制，保证备份文件是一致的快照（不是裸拷贝文件）。
"""

import glob
import os
import sqlite3
import time
from datetime import datetime

import config
import db

# 备份文件夹
BACKUP_DIR = os.path.join(config.DATA_DIR, "backups")


def backup_now():
    """立即备份一次，返回备份文件路径（失败返回 None）"""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    try:
        name = f"study_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        path = os.path.join(BACKUP_DIR, name)
        src = db.get_conn()
        try:
            # 目标必须是一个【新文件】连接！
            # 注意：不能用 db.get_conn() 当目标——那会打开同一个 study.db（把自己备份给自己）
            dst = sqlite3.connect(path)
            try:
                src.backup(dst)   # SQLite 官方一致性备份
            finally:
                dst.close()
        finally:
            src.close()
        _cleanup_old()
        return path
    except Exception:
        return None


def last_backup_time():
    """最近一次备份的时间（没有则返回 None）"""
    files = _list_backups()
    if not files:
        return None
    return datetime.fromtimestamp(os.path.getmtime(files[0]))


def _list_backups():
    """备份文件列表（新的在前）"""
    files = glob.glob(os.path.join(BACKUP_DIR, "study_*.db"))
    files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return files


def _cleanup_old():
    """保留最近 BACKUP_KEEP 份，删掉更旧的"""
    files = _list_backups()
    for old in files[config.BACKUP_KEEP:]:
        try:
            os.remove(old)
        except OSError:
            pass


def maybe_auto_backup():
    """启动时调用：超过间隔时间才备份"""
    last = last_backup_time()
    if last is None:
        return backup_now()
    hours = (time.time() - last.timestamp()) / 3600
    if hours >= config.BACKUP_INTERVAL_HOURS:
        return backup_now()
    return None
