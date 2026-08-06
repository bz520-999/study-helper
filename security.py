# -*- coding: utf-8 -*-
"""
安全模块：用 Fernet 对称加密保存账号密码。
原理：一把"密钥钥匙"（key.key 文件）只存在本机，用它加密/解密。
即使数据库文件被拷走，没有这把钥匙也读不出明文密码。
安全边界：防"数据库文件被拷贝后读出明文"；不宣称能防本机木马。
"""

import os

from cryptography.fernet import Fernet

import config

# 密钥文件路径（首次使用时自动生成）
KEY_FILE = os.path.join(config.DATA_DIR, "key.key")


def _get_key():
    """读取密钥；不存在则生成并保存（只生成一次，之后一直用它）"""
    os.makedirs(config.DATA_DIR, exist_ok=True)
    if not os.path.exists(KEY_FILE):
        key = Fernet.generate_key()
        with open(KEY_FILE, "wb") as f:
            f.write(key)
    with open(KEY_FILE, "rb") as f:
        return f.read()


def encrypt_text(plain):
    """明文 → 密文（存数据库前调用）"""
    if not plain:
        return ""
    return Fernet(_get_key()).encrypt(plain.encode("utf-8")).decode("utf-8")


def decrypt_text(cipher):
    """密文 → 明文（用时才解密，用完即弃）"""
    if not cipher:
        return ""
    return Fernet(_get_key()).decrypt(cipher.encode("utf-8")).decode("utf-8")
