# -*- coding: utf-8 -*-
"""
教务系统爬虫模板。

现状：用户学校的教务系统厂商（正方/金智等）和登录方式还未确定，
因此这里只提供"怎么适配"的模板。确认厂商和登录页地址后，
把下面的占位内容替换成实际接口即可（全程只改这一个文件）。

适配步骤：
1. 浏览器打开学校教务系统登录页，把网址填到 LOGIN_PAGE_URL
2. 用浏览器 F12 → 网络，观察登录请求发出什么参数，照着填 LOGIN_FORM_FIELDS
3. 找到成绩/考试查询接口的返回结构，在 fetch_deadlines 里解析
"""

from crawler.base import BaseCrawler

# 登录页地址（现场适配：填你学校教务系统的登录页）
LOGIN_PAGE_URL = "https://your-school-jwxt.example.com/login"


class JwxtCrawler(BaseCrawler):
    """教务系统爬虫模板（默认关闭，未实现）"""

    name = "jwxt"
    label = "教务系统（模板）"

    def __init__(self):
        # TODO: 用 requests.Session() 保持登录状态
        pass

    def login(self, username, password):
        raise NotImplementedError(
            "教务系统爬虫还是模板：需要你提供学校教务系统登录页地址，"
            "由开发者现场适配（只需要改 jwxt.py 一个文件）。"
        )

    def fetch_deadlines(self):
        raise NotImplementedError("教务系统爬虫尚未实现。")
