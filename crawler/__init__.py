# -*- coding: utf-8 -*-
"""
爬虫模块统一入口。

当前实现：学习通（超星）全自动同步
  - 登录：手机扫码（不用密码，绕开 RSA 加密和验证码）→ 登录态存本地约 7 天
  - 抓取：Playwright 无头浏览器打开课程列表 → 逐门课点"作业/考试"标签 → 解析 DDL
  - 交互：设置页显示二维码 → 扫码 → 前端每 2 秒轮询状态 → 预览勾选导入 DDL 清单

设计原则（评审重点）：
  - 后台线程执行，不卡页面（登录/同步状态由前端轮询）
  - 失败隔离：任何异常只写 crawl_logs 日志 + 状态提示，绝不向外抛
  - 只新增不覆盖：抓到的 DDL 标记 source=crawler，可人工删改
  - 不影响核心功能：爬虫不开，其他功能照常
"""

import models
from crawler import chaoxing


def is_enabled():
    """爬虫总开关（settings 表里 crawl_enabled，默认关闭）"""
    return models.get_setting("crawl_enabled") == "1"


# 把学习通模块的常用函数直接暴露给 app.py 使用
# —— start_qr_login / start_sync / login_status / sync_status / is_logged_in / logout
start_qr_login = chaoxing.start_qr_login
start_sync = chaoxing.start_sync
login_status = chaoxing.login_status
sync_status = chaoxing.sync_status
is_logged_in = chaoxing.is_logged_in
logout = chaoxing.logout

