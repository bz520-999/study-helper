# -*- coding: utf-8 -*-
"""
自动标签：根据文件名猜课程和标签。
规则在 config.py 里，改规则不用动代码。
"""

import config


def suggest_course(filename):
    """按规则猜课程，猜不到返回空字符串"""
    for keyword, course in config.FILENAME_COURSE_RULES:
        if keyword in filename:
            return course
    return ""


def suggest_tags(filename):
    """按规则猜标签，返回文件名里命中的标签列表"""
    return [kw for kw in config.FILENAME_TAG_RULES if kw in filename]
