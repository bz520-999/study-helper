# -*- coding: utf-8 -*-
"""
教务系统（南京理工大学：强智教务）爬虫。

实现依据：《梨课程 v1.1.3 APK 逆向分析报告》（2026-08-07）+
 2026-08-07 实际抓包验证（梨课程同款直登方式）。

真实机制（实测确认）：
  - 教务数据接口在 http://202.119.81.112:9080/njlgdx/（课表/成绩/考试）
  - 登录走强智自己的 Verifyservlet：
      1) GET 数据页 → 建立会话并弹出强智登录页
      2) GET /verifycode.servlet 取验证码（ddddocr 识别或人工输入）
      3) POST /xk/Verifyservlet，字段 USERNAME/PASSWORD/RANDOMCODE（密码明文）
      4) 成功 → 302 跳转到认证服务器 202.119.81.113:9080 的 LoginToXk，
         跟随后就建立了教务会话（JSESSIONID）
  - ⚠️ 认证服务器 .113 只在校园网/VPN 内可达（家庭网络 502）。
    数据服务器 .112 公网可达。所以在校园网里能全自动，校外需用
    「半自动粘贴」模式兜底。

数据接口（强智教务，ASP.NET，返回 HTML 表格）：
  课表   http://202.119.81.112:9080/njlgdx/xskb/xskb_list.do?Ves632DSdyV=NEW_XSD_PYGL
  成绩   http://202.119.81.112:9080/njlgdx/kscj/cjcx_list
  考试   http://202.119.81.112:9080/njlgdx/kscj/djkscj_list（本爬虫抓 DDL 的主来源）
  登录   http://202.119.81.112:9080/njlgdx/xk/Verifyservlet
"""

import hashlib
import random
import re
import base64

import requests
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.padding import PKCS7
from cryptography.hazmat.backends import default_backend

from crawler.base import BaseCrawler
from crawler import captcha

# ==================== 地址常量（接口变动时优先改这里） ====================
# 金智 ehall2 统一认证（CAS）
AUTH_LOGIN_URL = "https://ids.njust.edu.cn/authserver/login"
AUTH_CAPTCHA_CHECK_URL = "https://ids.njust.edu.cn/authserver/checkNeedCaptcha.htl"
AUTH_CAPTCHA_IMG_URL = "https://ids.njust.edu.cn/authserver/getCaptcha.htl"
AUTH_SERVICE = "https://ehall2.njust.edu.cn/login"   # 登录后回跳目标（服务标识）

# 强智教务系统（通过 bkjw 域名 + indexsso 桥访问，公网可达）
JW_BASE = "http://bkjw.njust.edu.cn/njlgdx"
JW_SSO_URL = JW_BASE + "/indexsso.jsp"                 # 门户→教务 的 SSO 桥（关键！）
JW_SCHEDULE_URL = JW_BASE + "/xskb/xskb_list.do?Ves632DSdyV=NEW_XSD_PYGL"   # 课表
JW_SCORE_URL = JW_BASE + "/kscj/cjcx_list"             # 成绩
JW_EXAM_URL = JW_BASE + "/xsks/xsksap_list"            # 考试安排（本爬虫抓 DDL 的主来源）
JW_MAIN_URL = JW_BASE + "/framework/main.jsp"          # 教务主框架

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

# ---- 密码加密（金智 ehall2 的 AES 方案，从登录页 encrypt.js 逆向）----
# 登录页 encrypt.js 的逻辑：
#   encryptPassword(n, f) = encryptAES(n, f)
#   encryptAES(n, f) = getAesString(randomString(64) + n, f, randomString(16))
#   getAesString(n, f, c) = AES-CBC(PKCS7) 加密，key=f(盐)，iv=c(16位随机)
# 所以提交的密码 = 64位随机前缀 + 明文，用页面给的盐做 AES 加密。
# 随机串字符集和 JS 里完全一致（去掉了易混淆的 ILO01 等）。
_SALT_CHARS = "ABCDEFGHJKMNPQRSTWXYZabcdefhijkmnprstwxyz2345678"


def _rand_str(n):
    """生成 n 位随机串（和 JS randomString 用同一字符集）"""
    return "".join(random.choice(_SALT_CHARS) for _ in range(n))


def _encrypt_password(plain, salt):
    """等价 JS 的 encryptPassword：AES-CBC 加密 + Base64 输出"""
    key = salt.encode("utf-8")
    iv = _rand_str(16).encode("utf-8")
    data = (_rand_str(64) + plain).encode("utf-8")
    padder = PKCS7(128).padder()
    padded = padder.update(data) + padder.finalize()
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    enc = cipher.encryptor()
    ct = enc.update(padded) + enc.finalize()
    return base64.b64encode(ct).decode("utf-8")


class JwxtCrawler(BaseCrawler):
    """南京理工大学教务系统爬虫（金智统一认证 + 强智教务）"""

    name = "jwxt"
    label = "教务系统（南理工）"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers["User-Agent"] = UA
        self._captcha_ocr = None   # 验证码识别器（懒加载，可禁用）

    # ---------------- 登录 ----------------

    def login(self, username, password):
        """登录南理工教务系统（纯 requests，公网可用）。失败抛异常。

        真实机制（2026-08-07 实测确认，家庭网络/无校园网已验证）：
          1) 金智统一认证登录（ids.njust.edu.cn/authserver）：
             - 取登录页，解析 execution 令牌 + pwdEncryptSalt 盐
             - 密码先 AES 加密（encrypt.js 逆向：64位随机前缀 + AES-CBC-PKCS7）
             - POST 提交，成功拿到 CASTGC 会话 cookie
             - 可能要求验证码（checkNeedCaptcha 判断），自动识别或人工输入
          2) 访问教务系统 SSO 桥 indexsso.jsp（bkjw.njust.edu.cn）：
             - 带 ehall2 会话访问，返回 MOD_AUTH_CAS cookie，自动建立教务会话
          3) 之后就能访问课表/成绩/考试接口
        """
        if not username or not password:
            raise Exception("请先填写教务系统账号和密码。")

        # 1. 打开统一认证登录页，取 execution 令牌 + 密码盐
        try:
            resp = self.session.get(
                AUTH_LOGIN_URL,
                params={"service": AUTH_SERVICE},
                timeout=15,
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            raise Exception(f"连不上统一认证服务器（ids.njust.edu.cn）：{e}")

        m = re.search(r'name=["\']execution["\']\s+value=["\']([^"\']+)["\']', resp.text)
        salt_m = re.search(r'pwdEncryptSalt["\s][^>]*value=["\']([^"\']+)["\']', resp.text)
        if not m or not salt_m:
            raise Exception("统一认证登录页解析失败（可能页面改版）。请改用「半自动粘贴」模式。")
        execution = m.group(1)
        salt = salt_m.group(1)

        # 2. 判断是否需要验证码
        need_captcha = False
        try:
            need = self.session.get(
                AUTH_CAPTCHA_CHECK_URL,
                params={"username": username},
                timeout=10,
            ).text
            need_captcha = "true" in need.lower()
        except requests.RequestException:
            need_captcha = False

        # 3. 提交登录（验证码阶段最多重试：OCR 认错 → 人工输入）
        code = ""
        use_manual = False
        attempt = 0
        max_attempts = 4
        while attempt < max_attempts:
            if need_captcha:
                # 第 1 次用 OCR，之后转人工输入（和梨课程体验一致）
                code = self._recognize_captcha(manual=use_manual)
                if code is None:
                    raise Exception("验证码等待超时，请重试。")
            data = {
                "username": username,
                "password": _encrypt_password(password, salt),
                "execution": execution,
                "_eventId": "submit",
                "geolocation": "",
                "rmShown": "1",
            }
            if code:
                data["captcha"] = code
            try:
                resp = self.session.post(
                    AUTH_LOGIN_URL,
                    params={"service": AUTH_SERVICE},
                    data=data,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    allow_redirects=False,
                    timeout=15,
                )
            except requests.RequestException as e:
                raise Exception(f"登录请求失败：{e}")

            # 登录成功：302 跳转并带 ticket
            if resp.status_code == 302:
                location = resp.headers.get("Location", "")
                if "ticket=" in location:
                    self._attach_jw()
                    return
                raise Exception("登录未成功：统一认证没有跳转到目标系统。")
            # 密码错误等硬错误
            if ("用户名或密码" in resp.text or "密码错误" in resp.text
                    or ("密码" in resp.text and "错误" in resp.text)):
                raise Exception("登录未成功：账号或密码不对，请检查后重试。")
            # 验证码问题 → 转人工输入重试
            use_manual = True
            attempt += 1

        raise Exception(
            "登录未成功：验证码连续没通过。请改用「半自动粘贴」模式。"
        )

    def _recognize_captcha(self, manual=False):
        """取统一认证验证码图片，先 OCR 再人工输入。"""
        img = self.session.get(AUTH_CAPTCHA_IMG_URL, timeout=10).content
        if not img:
            return None
        if not manual:
            try:
                import ddddocr
                code = ddddocr.DdddOcr(show_ad=False).classification(img)
                if code:
                    return code
            except Exception:
                pass
        # OCR 失败/要求人工 → 弹图让用户输入
        return captcha.request_captcha(img)

    def _attach_jw(self):
        """登录 ehall2 后，访问教务 SSO 桥 indexsso.jsp 建立教务会话。"""
        try:
            # 先跟随 ehall2 重定向（拿到门户会话）
            resp = self.session.get(AUTH_SERVICE, timeout=15, allow_redirects=False)
            # 访问 indexsso.jsp 建立教务会话（MOD_AUTH_CAS cookie）
            resp = self.session.get(JW_SSO_URL, timeout=15, allow_redirects=True)
            resp.raise_for_status()
        except requests.RequestException as e:
            raise Exception(f"登录成功，但关联教务系统失败：{e}")
        # 验证会话是否有效
        if "登录个人中心" in resp.text and "概念版" in resp.text:
            raise Exception(
                "教务系统会话建立失败。请改用「半自动粘贴」模式。"
            )

    # ---------------- 抓取 ----------------

    def fetch_deadlines(self):
        """抓取教务系统中的考试安排，转成 DDL 清单。

        返回 [{"title": 课程名+考试, "due_at": "YYYY-MM-DD HH:MM", "course": 课程名}, ...]
        当前学期没有已排考试时返回空列表。
        """
        return self._fetch_exams()

    def _fetch_exams(self):
        """考试安排：POST xsksap_list 带学期参数，返回 HTML 表格，逐行解析。

        强智考试页结构：查询页(xsksap_query)选学期 → POST 到 xsksap_list，
        表格列为：序号、考试场次、课程编号、课程名称、考试时间、考场、座位号。
        """
        # 获取默认学期（查询页里默认选中的那个）
        term = None
        try:
            q = self._load_page(JW_BASE + "/xsks/xsksap_query")
            m = re.search(r'<select[^>]*name="xnxqid"[\s\S]*?</select>', q)
            if m:
                m2 = re.search(r'<option[^>]*selected[^>]*value="([^"]*)"', m.group(0))
                if m2:
                    term = m2.group(1)
                else:
                    m3 = re.search(r'<option[^>]*value="([^"]*)"', m.group(0))
                    if m3:
                        term = m3.group(1)
        except requests.RequestException:
            term = None

        if not term:
            raise Exception("无法确定当前学期。请改用「半自动粘贴」模式。")

        # POST 查询考试安排
        try:
            page = self._load_page(JW_BASE + "/xsks/xsksap_list", post=True, data={"xnxqid": term})
        except requests.RequestException as e:
            raise Exception(f"查询考试安排失败：{e}")

        rows = _parse_html_table(page)
        items = []
        seen = set()
        for r in rows:
            exam = _exam_row_to_item(r)
            if not exam:
                continue
            key = (exam["title"], exam["due_at"])
            if key in seen:
                continue
            seen.add(key)
            items.append(exam)
        return items

    def _load_page(self, url, post=False, data=None):
        """统一入口：GET/POST 数据页。"""
        if post:
            resp = self.session.post(
                url, data=data or {},
                headers={"Referer": JW_BASE + "/xsks/xsksap_query"},
                timeout=20,
            )
        else:
            resp = self.session.get(url, timeout=20)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"
        return resp.text

    def fetch_schedule(self):
        """抓取课表，生成课程安排（含精确小节）。

        返回 [{"title", "course", "teacher", "weeks", "day", "sections",
               "location", "big_section"}, ...]
        其中 sections 是精确小节（如 "04-05" 表示第4~5小节），big_section 是大节名。
        课表页有两个表格：
          - 表格1(#kbtable): 图形课表，行=大节、列=星期，含周次，无精确小节
          - 表格2(结构化列表): 序号/课程号/课序号/课程名称/教师/时间/学分/地点，
            时间列含精确小节（如"星期一(01-03小节)"）
        两者按 (课程名+星期+节次) 合并，取精确小节 + 周次。
        """
        try:
            page = self._load_page(JW_SCHEDULE_URL)
        except requests.RequestException as e:
            raise Exception(f"查询课表失败：{e}")
        if "登录个人中心" in page and "概念版" in page:
            raise Exception("教务会话已失效，请重新同步。")
        return _parse_schedule(page)

    def fetch_scores(self):
        """抓取考试成绩（用于展示，可选）。返回 [{course, score, credit, term}, ...]"""
        try:
            page = self._load_page(JW_SCORE_URL)
        except requests.RequestException as e:
            raise Exception(f"查询成绩失败：{e}")
        if "登录个人中心" in page and "概念版" in page:
            raise Exception("教务会话已失效，请重新同步。")
        return _parse_scores(page)

    def close(self):
        self.session.close()


# ==================== 纯函数：HTML 表格解析（方便单独测试） ====================

def _parse_html_table(html):
    """
    从 HTML 里提取"表格行 → 单元格文本列表"。
    只要页面上有 <table> 就尝试解析，返回 [["课程","时间",...], ...]；
    页面没有表格时返回 []。只依赖正则，不用额外解析库。
    """
    tables = re.findall(r"<table[\s\S]*?</table>", html, flags=re.IGNORECASE)
    rows_out = []
    for table in tables:
        for row in re.findall(r"<tr[\s\S]*?</tr>", table, flags=re.IGNORECASE):
            cells = [
                _strip_tags(c).strip()
                for c in re.findall(r"<t[dh][\s\S]*?</t[dh]>", row, flags=re.IGNORECASE)
            ]
            cells = [c for c in cells if c]   # 去掉空单元格
            if cells:
                rows_out.append(cells)
    return rows_out


def _strip_tags(html):
    """去掉 HTML 标签和常用转义字符，取可见文本（含 font title 属性里的值）。"""
    # 优先取 title 属性（强智表格里 <font title="老师">张三</font> 这种结构）
    titles = re.findall(r'title=["\']([^"\']+)["\']', html)
    if titles:
        text = " ".join(titles)
    else:
        text = re.sub(r"<[^>]+>", "", html)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    return re.sub(r"\s+", " ", text)


def _looks_like_no_data(page):
    """页面是否明确表示"没有数据"（此时返回空列表而不是报结构变化）。"""
    return any(
        w in page
        for w in ("没有", "暂无", "无考试", "未安排", "0 条", "0条", "没有数据")
    )


def _exam_row_to_item(cells):
    """
    把一行考试安排（单元格列表）转成 DDL 项。
    强智考试表典型列：序号 | 考试场次 | 课程编号 | 课程名称 | 考试时间 | 考场 | 座位号
    （列序可能有差异，用"含考试时间/含课程名"的启发式定位，尽量稳健）
    """
    if not cells:
        return None
    text = " ".join(cells)
    # 表头行跳过
    if any(w in text for w in ("序号", "考试科目", "考试课程", "课程名称", "考试时间",
                                "学年", "星期", "考试地点", "考场", "座位号")):
        if not re.search(r"\d{4}[年\-/\.]", text):
            return None

    # 定位课程名：优先取"看起来像课程名"的那格（非序号、非学期、非纯时间/地点）
    title = ""
    for c in cells:
        c2 = c.strip()
        if not c2 or re.fullmatch(r"\d+", c2):          # 序号/座位号
            continue
        if re.fullmatch(r"20\d{2}-\d{2,4}-\d+", c2):     # 学年学期（如 2026-2027-1）
            continue
        if re.match(r"^\d{2}:\d{2}", c2) or re.search(r"\d{4}[-年/\.]", c2):  # 时间/日期
            continue
        if re.fullmatch(r"[一二三四五六日天]+", c2):      # 星期
            continue
        # 剩余的非空格，取"最像课程名"的（带中文/字母，长度合适）
        if re.search(r"[一-鿿A-Za-z]", c2) and len(c2) < 40:
            title = c2
            break
    # 兜底：含"考试"字样的格
    if not title:
        for c in cells:
            if "考试" in c and len(c.strip()) > 1:
                title = c.strip()
                break

    # 定位考试时间：优先匹配"2026-08-20 14:00"或"2026年8月20日 14:00"
    due_at = ""
    m = re.search(
        r"(20\d{2})[年\-/\.](\d{1,2})[月\-/\.](\d{1,2})日?(?:\s+|T)?(\d{1,2}):(\d{2})",
        text,
    )
    if m:
        due_at = (f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d} "
                  f"{int(m.group(4)):02d}:{m.group(5)}")
    else:
        # 只有日期没有时间：默认当天 23:59
        m = re.search(r"(20\d{2})[年\-/\.](\d{1,2})[月\-/\.](\d{1,2})日?", text)
        if m:
            due_at = (f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d} 23:59")

    if not title or not due_at:
        return None

    # 提取考场（含"考场/教室/楼"字样的格，或 I-101 / 一工B101 之类）
    location = ""
    for c in cells:
        c2 = c.strip()
        if re.search(r"(考场|教室|[A-Za-zⅠⅡⅢⅣ]|工|楼|教室)", c2) and not re.fullmatch(r"\d+", c2) and c2 != title:
            if c2 != due_at.split(" ")[0]:
                location = c2
                break
    # 课程名去掉"（考试）"后缀（可能已带，避免重复）
    course = title
    for suf in ("（考试）", "(考试)", "期末考试", "期中考试"):
        course = course.replace(suf, "")
    course = course.strip()
    # title 里若已含"考试"就不再加后缀
    if "考试" not in title:
        title = f"{title}（考试）"
    return {"title": title, "due_at": due_at, "course": course, "location": location}


# ==================== 课表 / 成绩 解析 ====================

def _parse_schedule(page):
    """
    解析课表页，合并两个数据源：
      1) kbtable 图形课表 → (课程名, 星期, 大节, 周次, 老师, 教室)
      2) 结构化列表 → (课程名, 星期, 精确小节, 老师, 教室)
    以结构化列表的精确小节为准，补上 kbtable 的周次。
    返回 [{"title","course","teacher","weeks","day","sections","location","big_section"}, ...]
    """
    # ---- 数据源1: 结构化列表（精确小节，主）----
    precise = []   # (course, day, start, end, teacher, location)
    for m in re.finditer(r"<tr[\s\S]*?</tr>", page, re.I):
        row = m.group(0)
        if "小节" not in row or "课程名称" in row:
            continue
        cells = [_strip_tags(c).strip() for c in re.findall(r"<t[dh][\s\S]*?</t[dh]>", row, re.I)]
        if len(cells) < 6 or not cells[3] or "课程名称" in cells[3]:
            continue
        course = cells[3]
        teacher = cells[4]
        time_str = cells[5]
        location = cells[7] if len(cells) > 7 else ""
        # 地点去重：结构化列表里同一个地点重复出现（如"逸夫楼104,逸夫楼104,..."）
        if location:
            locs = [x.strip() for x in location.split(",") if x.strip()]
            seen_loc = []
            for x in locs:
                if x not in seen_loc:
                    seen_loc.append(x)
            location = ", ".join(seen_loc)
        # 解析 星期(XX-XX小节) 组合
        for dm in re.finditer(r"(星期[一二三四五六日])\((\d{1,2})-(\d{1,2})小节\)", time_str):
            day, start, end = dm.group(1), int(dm.group(2)), int(dm.group(3))
            precise.append({
                "course": course, "teacher": teacher, "day": day,
                "start": start, "end": end, "location": location,
            })

    # ---- 数据源2: kbtable 图形课表（周次，辅）----
    kb = re.search(r"<table[^>]*id=\"?kbtable\"?[\s\S]*?</table>", page, re.I)
    if not kb:
        for tb in re.findall(r"<table[\s\S]*?</table>", page, re.I):
            if "kbcontent1" in tb:
                kb = re.match(r"<table[\s\S]*?</table>", tb)
                break
    weeks_map = {}   # (course, day, slot) -> weeks
    weeks_by_course_day = {}   # (course, day) -> [weeks, ...]  兜底
    if kb:
        rows = re.findall(r"<tr[\s\S]*?</tr>", kb.group(0), re.I)
        for row in rows:
            slot_m = re.search(r"<th[^>]*>([^<]*)</th>", row)
            slot = slot_m.group(1).strip().replace("&nbsp;", "").strip() if slot_m else ""
            # 大节行 或 网课行（"中午"）都处理
            if not (("大节" in slot) or ("中午" in slot) or (not slot and "kbcontent1" in row)):
                continue
            cells = re.findall(r"<td[^>]*>([\s\S]*?)</td>", row)
            for cell in cells:
                cid = re.search(r'id="([^"]*)"', cell)
                if not cid:
                    continue
                parts = cid.group(1).split("-")
                if len(parts) < 3:
                    continue
                try:
                    col = int(parts[-2])
                except ValueError:
                    continue
                vis = re.search(r'class="kbcontent1"[^>]*>([\s\S]*?)</div>', cell)
                if not vis or "&nbsp;" in vis.group(1):
                    continue
                clean = re.sub(r"<[^>]+>", " ", vis.group(1))
                lines = [l.strip() for l in clean.split() if l.strip()]
                if not lines:
                    continue
                title = lines[0]
                wm = re.search(r"title='周次\(节次\)'[^>]*>([^<]+)", cell)
                weeks = wm.group(1).strip() if wm else ""
                # 列号 1~7 对应 星期一~星期日
                day = "星期" + ("一二三四五六日"[col - 1] if 1 <= col <= 7 else "?")
                weeks_map[(title, day, slot)] = weeks
                weeks_by_course_day.setdefault((title, day), []).append(weeks)

    # ---- 合并: 精确小节 + 补周次 ----
    results = []
    seen = set()
    for p in precise:
        # 用精确小节推算大节
        slot = _big_section_for(p["start"])
        # 从 kbtable 找周次
        weeks = weeks_map.get((p["course"], p["day"], slot), "")
        # 也尝试按节次范围匹配周次（kbtable 可能把课拆到多行）
        if not weeks:
            for (c, d, s), w in weeks_map.items():
                if c == p["course"] and d == p["day"] and _big_section_for(p["start"]) == s:
                    weeks = w
                    break
        # 兜底：按课程名+星期匹配周次（不要求大节一致）
        if not weeks:
            wlist = weeks_by_course_day.get((p["course"], p["day"]), [])
            if wlist:
                weeks = wlist[-1]
        # 兜底2：同课程其他天有周次，则复用（军事理论等多天课周次相同）
        if not weeks:
            for (c, d), wl in weeks_by_course_day.items():
                if c == p["course"] and wl:
                    weeks = wl[-1]
                    break
        key = (p["course"], p["day"], p["start"], p["end"])
        if key in seen:
            continue
        seen.add(key)
        results.append({
            "title": p["course"],
            "course": p["course"],
            "teacher": p["teacher"],
            "weeks": weeks,
            "day": p["day"],
            "sections": f"{p['start']:02d}-{p['end']:02d}",
            "location": p["location"],
            "big_section": slot,
        })
    return results


# ---- 南理工作息表（用户确认 2026-08-07）----
# 第1,2,3小节=第一大节, 4,5=第二大节, 6,7=第三大节, 8,9,10=第四大节,
# 11,12,13=第五大节, 14=网课
BIG_SECTION_MAP = [
    (1, 3, "第一大节"), (4, 5, "第二大节"), (6, 7, "第三大节"),
    (8, 10, "第四大节"), (11, 13, "第五大节"), (14, 14, "网课"),
]
# 每小节的开始时间（分钟），1~14
SECTION_TIMES_MIN = {
    1: 8 * 60, 2: 8 * 60 + 50, 3: 9 * 60 + 40,
    4: 10 * 60 + 40, 5: 11 * 60 + 30,
    6: 14 * 60, 7: 14 * 60 + 50,
    8: 15 * 60 + 50, 9: 16 * 60 + 40, 10: 17 * 60 + 30,
    11: 19 * 60, 12: 19 * 60 + 50, 13: 20 * 60 + 40,
    14: 21 * 60 + 30,
}


def _big_section_for(section):
    """小节号 → 大节名（南理工作息）"""
    for lo, hi, name in BIG_SECTION_MAP:
        if lo <= section <= hi:
            return name
    return ""


def _section_start_time(section):
    """小节号 → 开始时间 "HH:MM"（或 "网课"）"""
    minutes = SECTION_TIMES_MIN.get(section)
    if minutes is None:
        return ""
    if section == 14:
        return "网课"
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _parse_scores(page):
    """
    解析成绩页，提取各科成绩。
    强智成绩页表格列：序号、开课学期、课程编号、课程名称、成绩、成绩标识、学分...
    返回 [{"term": 学期, "course": 课程名, "score": 成绩, "credit": 学分, "course_code": 编号}, ...]
    """
    tables = re.findall(r"<table[\s\S]*?</table>", page, flags=re.IGNORECASE)
    results = []
    for table in tables:
        rows = re.findall(r"<tr[\s\S]*?</tr>", table, flags=re.IGNORECASE)
        for row in rows:
            cells = [_strip_tags(c).strip() for c in re.findall(r"<t[dh][\s\S]*?</t[dh]>", row, flags=re.IGNORECASE)]
            if len(cells) < 5:
                continue
            # 表头行跳过
            if any("课程" in c for c in cells[:4]):
                continue
            term = cells[1] if len(cells) > 1 else ""
            code = cells[2] if len(cells) > 2 else ""
            course = cells[3] if len(cells) > 3 else ""
            score = cells[4] if len(cells) > 4 else ""
            credit = cells[6] if len(cells) > 6 else ""
            if not course or course == "课程名称":
                continue
            results.append({
                "term": term,
                "course": course,
                "score": score,
                "credit": credit,
                "course_code": code,
            })
    return results
