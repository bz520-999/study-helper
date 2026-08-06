# -*- coding: utf-8 -*-
"""
检索模块：按关键词 / 课程 / 标签查找资料。
关键词优先走 FTS5 全文索引（jieba 分词，快且准）；
FTS 不可用（个别精简版 SQLite）时自动降级为"逐个比对"。
"""

import models


def search_materials(keyword="", course_id=None, tag_name=""):
    """
    按条件搜索资料，条件可以任意组合（不填的条件等于不限制）。
    返回：资料列表（每条带 course_name 和 tags）。
    """
    keyword = keyword.strip().lower()
    tag_name = tag_name.strip()

    # 全文索引预筛：拿到命中的 material_id 集合（FTS 不可用则为 None → 全部候选）
    fts_ids = models.fts_search(keyword) if keyword else None
    if fts_ids is not None and not fts_ids:
        return []  # 索引明确说没有命中

    result = []

    for m in models.list_materials():
        # 条件 0：FTS 预筛结果（非 None 时必须命中）
        if fts_ids is not None and m["id"] not in fts_ids:
            continue

        # 条件 1：关键词——FTS 不可用时用"逐个比对"兜底
        if keyword and fts_ids is None:
            blob = " ".join([
                m["title"] or "",
                m["file_name"] or "",
                m["notes"] or "",
                m["course_name"] or "",
            ]).lower()
            if keyword not in blob:
                continue
        # 条件 1：关键词——把能搜的字段拼成一段话，看里面有没有关键词
        if keyword:
            blob = " ".join([
                m["title"] or "",
                m["file_name"] or "",
                m["notes"] or "",
                m["course_name"] or "",
            ]).lower()
            if keyword not in blob:
                continue

        # 条件 2：课程（按课程 id 精确匹配）
        if course_id and m["course_id"] != course_id:
            continue

        # 条件 3：标签（看这份资料的标签列表里有没有）
        if tag_name and tag_name not in m["tags"]:
            continue

        result.append(m)
    return result
