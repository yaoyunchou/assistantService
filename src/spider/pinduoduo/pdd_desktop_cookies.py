# -*- coding: utf-8 -*-
"""
从拼多多桌面客户端（PddWebWorkbench / 内嵌 Chromium）读取并解密 Cookie，
转换成 Playwright `context.add_cookies()` 可直接使用的格式。

拼多多工作台是 Chromium 内核，用户数据目录默认在：
    C:\\Users\\Public\\Documents\\PDD\\PddBrowser104\\User Data
登录态分散在多个 `cs_XXXXXXXX` profile（按店铺区分），主 profile `StaticPddBrowser`
一般是空的。本模块会自动挑出「最近活跃且含 ERP 登录 cookie」的 profile。

Cookie 值用 AES-256-GCM 加密，主密钥用 Windows DPAPI 保护（当前登录用户可解），
加密 key 存在 `User Data\\Local State` 的 `os_crypt.encrypted_key`。

注意：
- 必须在「登录过拼多多工作台」的 Windows 用户下运行，否则 DPAPI 解不开。
- 拼多多工作台运行时 Cookies 文件被 SQLite 锁，本模块先复制到临时文件再读。
- 只读不写，不会影响桌面端登录态。
"""
from __future__ import annotations

import base64
import json
import shutil
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from utils.logger import get_logger

logger = get_logger('PddDesktopCookies')

DEFAULT_USER_DATA_DIR = Path(r"C:\Users\Public\Documents\PDD\PddBrowser104\User Data")
# ERP 登录态关键 cookie：mms_<shopid> 是 MMS 会话；JSESSIONID 是后端 session
# 只要含其中任一个，就认为该 profile 登录过 ERP
ERP_LOGIN_COOKIE_NAMES = ("mms_b84d1838", "JSESSIONID")
# 只关心 pinduoduo 域，避免把无关 cookie 也塞进去
TARGET_HOST_SUFFIX = "pinduoduo.com"


def _get_master_key(user_data_dir: Path) -> bytes:
    """从 Local State 取出并用 DPAPI 解密 AES 主密钥。"""
    local_state_path = user_data_dir / "Local State"
    if not local_state_path.is_file():
        raise FileNotFoundError(f"找不到 Local State: {local_state_path}")
    data = json.loads(local_state_path.read_text(encoding="utf-8"))
    encrypted_key_b64 = data.get("os_crypt", {}).get("encrypted_key")
    if not encrypted_key_b64:
        raise ValueError("Local State 里没有 os_crypt.encrypted_key")
    encrypted_key = base64.b64decode(encrypted_key_b64)
    # Chrome 在前面加了 "DPAPI" 5 字节标记
    if encrypted_key.startswith(b"DPAPI"):
        encrypted_key = encrypted_key[5:]
    import win32crypt
    _, master_key = win32crypt.CryptUnprotectData(encrypted_key, None, None, None, 0)
    return master_key


def _decrypt_value(enc_value: bytes, master_key: bytes) -> str:
    """解密单条 cookie 值。v10/v11 前缀 + 12 字节 nonce + 密文(GCM tag 16 字节)。"""
    if not enc_value:
        return ""
    # 旧版直接 DPAPI
    if enc_value[:4] == b"\x01\x00\x00\x00":
        try:
            import win32crypt
            _, val = win32crypt.CryptUnprotectData(enc_value, None, None, None, 0)
            return val.decode("utf-8", "replace")
        except Exception:
            pass
    prefix = enc_value[:3]
    if prefix in (b"v10", b"v11"):
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        nonce = enc_value[3:15]          # 12 bytes
        ciphertext = enc_value[15:]       # 含末尾 16 字节 GCM tag
        aes = AESGCM(master_key)
        plain = aes.decrypt(nonce, ciphertext, None)
        return plain.decode("utf-8", "replace")
    return enc_value.decode("utf-8", "replace")


# Chrome 时间戳：自 1601-01-01 起的微秒数 → unix 秒
_CHROME_EPOCH_OFFSET_US = 11644473600 * 1_000_000


def _chrome_to_unix(expires_utc: int) -> float:
    """Chrome expires_utc（微秒，1601 起）转 unix 秒；0/负值表示 session cookie。"""
    if not expires_utc or expires_utc <= 0:
        return -1.0
    return expires_utc / 1_000_000 - 11644473600


def _row_to_playwright_cookie(row: sqlite3.Row, master_key: bytes) -> Optional[Dict[str, Any]]:
    """把 SQLite 一行转成 Playwright add_cookies 格式。"""
    enc = row["encrypted_value"]
    plain = ""
    if enc:
        try:
            plain = _decrypt_value(bytes(enc), master_key)
        except Exception as e:
            logger.debug("解密 cookie %s 失败: %s", row["name"], e)
            return None
    value = plain or (row["value"] or "")
    if not value:
        # 空值 cookie 没意义，跳过
        return None
    same_site_raw = row["samesite"]
    # Chromium 104 schema: samesite INTEGER (0=Unspecified,1=None,2=Lax,3=Strict)
    same_site = {0: "Lax", 1: "None", 2: "Lax", 3: "Strict"}.get(same_site_raw, "Lax")
    expires = _chrome_to_unix(row["expires_utc"])
    return {
        "name": row["name"],
        "value": value,
        "domain": row["host_key"],
        "path": row["path"] or "/",
        "expires": expires,
        "httpOnly": bool(row["is_httponly"]),
        "secure": bool(row["is_secure"]),
        "sameSite": same_site,
    }


def _read_profile_cookies(
    user_data_dir: Path,
    profile_name: str,
    master_key: bytes,
    host_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """读取单个 profile 的 cookie（复制 SQLite 到临时文件以避开浏览器锁）。"""
    cookies_path = user_data_dir / profile_name / "Network" / "Cookies"
    if not cookies_path.is_file():
        return []
    tmp_dir = Path(tempfile.mkdtemp(prefix="pdd_ck_"))
    tmp = tmp_dir / "Cookies"
    try:
        shutil.copy2(cookies_path, tmp)
        conn = sqlite3.connect(str(tmp))
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        sql = (
            "SELECT host_key, name, encrypted_value, value, path, "
            "expires_utc, is_secure, is_httponly, samesite FROM cookies"
        )
        params: Tuple = ()
        if host_filter:
            sql += " WHERE host_key LIKE ?"
            params = (f"%{host_filter}%",)
        sql += " ORDER BY host_key, name"
        cur.execute(sql, params)
        rows = cur.fetchall()
        conn.close()
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
        try:
            tmp_dir.rmdir()
        except Exception:
            pass

    out: List[Dict[str, Any]] = []
    for r in rows:
        ck = _row_to_playwright_cookie(r, master_key)
        if ck:
            out.append(ck)
    return out


def list_profiles(user_data_dir: Path = DEFAULT_USER_DATA_DIR) -> List[Dict[str, Any]]:
    """列出所有含 Cookies 文件的 profile，附带最近修改时间与 cookie 数量。"""
    if not user_data_dir.is_dir():
        return []
    profiles: List[Dict[str, Any]] = []
    for prof in user_data_dir.iterdir():
        if not prof.is_dir():
            continue
        ck = prof / "Network" / "Cookies"
        if not ck.is_file():
            continue
        try:
            mtime = ck.stat().st_mtime
        except OSError:
            mtime = 0
        profiles.append({
            "name": prof.name,
            "cookies_path": str(ck),
            "mtime": mtime,
            "mtime_str": datetime.fromtimestamp(mtime, tz=timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S"),
        })
    profiles.sort(key=lambda x: x["mtime"], reverse=True)
    return profiles


def pick_best_profile(
    user_data_dir: Path = DEFAULT_USER_DATA_DIR,
    preferred: Optional[str] = None,
) -> Optional[str]:
    """挑出最近活跃且含 ERP 登录 cookie 的 profile。"""
    if not user_data_dir.is_dir():
        logger.warning("PddBrowser User Data 不存在: %s", user_data_dir)
        return None
    try:
        master_key = _get_master_key(user_data_dir)
    except Exception as e:
        logger.warning("读取 PddBrowser master key 失败（可能未登录桌面端或非登录用户）: %s", e)
        return None

    profiles = list_profiles(user_data_dir)
    # 指定 profile 优先
    if preferred:
        for p in profiles:
            if p["name"] == preferred:
                profiles = [p] + [x for x in profiles if x["name"] != preferred]
                break

    for p in profiles:
        try:
            cks = _read_profile_cookies(user_data_dir, p["name"], master_key, host_filter=TARGET_HOST_SUFFIX)
        except Exception as e:
            logger.debug("读 profile %s 失败: %s", p["name"], e)
            continue
        names = {c["name"] for c in cks}
        has_login = any(n in names for n in ERP_LOGIN_COOKIE_NAMES)
        if has_login:
            logger.info(
                "选中 PddBrowser profile=%s（最近活跃 %s，pinduoduo cookie %d 条）",
                p["name"], p["mtime_str"], len(cks),
            )
            return p["name"]
    logger.info("没有找到含 ERP 登录态的 PddBrowser profile（请先在拼多多工作台登录 ERP）")
    return None


def get_playwright_cookies(
    user_data_dir: Path = DEFAULT_USER_DATA_DIR,
    profile: Optional[str] = None,
    host_filter: str = TARGET_HOST_SUFFIX,
) -> List[Dict[str, Any]]:
    """
    读取并返回可直接喂给 `context.add_cookies()` 的 cookie 列表。

    Args:
        user_data_dir: PddBrowser User Data 目录
        profile: 指定 profile；None 则自动挑最近活跃且含 ERP 登录态的
        host_filter: 只取该域 cookie，默认 pinduoduo.com

    Returns:
        cookie dict 列表；失败/未登录返回空列表
    """
    if not user_data_dir.is_dir():
        logger.debug("PddBrowser User Data 不存在: %s", user_data_dir)
        return []
    try:
        master_key = _get_master_key(user_data_dir)
    except Exception as e:
        logger.warning("读取 PddBrowser master key 失败: %s", e)
        return []

    if not profile:
        profile = pick_best_profile(user_data_dir)
        if not profile:
            return []
    try:
        cks = _read_profile_cookies(user_data_dir, profile, master_key, host_filter=host_filter)
    except Exception as e:
        logger.warning("读取 profile %s cookie 失败: %s", profile, e)
        return []
    logger.info("从 PddBrowser profile=%s 读到 %d 条 %s cookie", profile, len(cks), host_filter)
    return cks


def import_cookies_to_context(context, cookies: List[Dict[str, Any]]) -> int:
    """把 cookie 列表注入 Playwright BrowserContext，返回成功条数。"""
    if not cookies:
        return 0
    try:
        context.add_cookies(cookies)
        return len(cookies)
    except Exception as e:
        logger.warning("add_cookies 失败: %s", e)
        return 0
