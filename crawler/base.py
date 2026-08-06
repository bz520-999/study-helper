# -*- coding: utf-8 -*-
"""
爬虫基类：所有爬虫的公共"接口约定"。
新增一个学校系统 = 新建一个类继承 BaseCrawler，实现下面三个方法。
"""


class BaseCrawler:
    """爬虫基类。login 和 fetch_deadlines 必须由子类实现。"""

    name = "base"          # 标识，写入日志用
    label = "通用爬虫"      # 给人看的名字

    def login(self, username, password):
        """登录学校系统。失败抛异常（异常信息会写入日志并展示给用户）。"""
        raise NotImplementedError("子类必须实现 login")

    def fetch_deadlines(self):
        """
        抓取作业/考试截止日期。
        返回 [{"title": 任务名, "due_at": "YYYY-MM-DD HH:MM", "course": 课程名}, ...]
        """
        raise NotImplementedError("子类必须实现 fetch_deadlines")

    def close(self):
        """收尾（关闭会话等）。没有特殊需要就不用管。"""
        pass
