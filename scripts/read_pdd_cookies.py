# -*- coding: utf-8 -*-
"""
读取拼多多桌面客户端（PddWebWorkbench / 内嵌 Chromium）的 Cookie。

拼多多工作台是 Chromium 内核，用户数据目录固定在：
    C:\\Users\\Public\\Documents\\PDD\\PddBrowser104\\User Data
默认 profile：StaticPddBrowser
Cookie 文件：StaticPddBrowser\\Network\\Cookies （SQLite，值用 AES-GCM 加密）
AES key 用 Windows DPAPI 保护，加密 key 存在 Local State 的 os_crypt.encrypted_key。

用法：
    python scripts/read_pdd_cookies.py
    python scripts/read_pdd_cookies.py --host mms.pinduoduo.com
"""
import argparse
import base64
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

import win32crypt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

DEFAULT_USER_DATA = Path(r"C:\Users\Public\Documents\PDD\PddBrowser104\User Data")
DEFAULT_PROFILE = "StaticPddBrowser"


def get_master_key(user_data_dir: Path) -> bytes:
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
    # DPAPI 解密（当前用户）
    _, master_key = win32crypt.CryptUnprotectData(encrypted_key, None, None, None, 0)
    return master_key


def decrypt_value(enc_value: bytes, master_key: bytes) -> str:
    """解密单条 cookie 值。v10/v11 前缀 + 12 字节 nonce + 密文(GCM tag 16 字节)。"""
    if not enc_value:
        return ""
    # 旧版直接 DPAPI（v10 之前），这里也兼容一下
    if enc_value.startswith(b"\x01\x00\x00\x00") or enc_value[:4] == b"\x01\x00\x00\x00":
        try:
            _, val = win32crypt.CryptUnprotectData(enc_value, None, None, None, 0)
            return val.decode("utf-8", "replace")
        except Exception:
            pass
    prefix = enc_value[:3]
    if prefix in (b"v10", b"v11"):
        nonce = enc_value[3:15]          # 12 bytes
        ciphertext = enc_value[15:]       # 含末尾 16 字节 GCM tag
        aes = AESGCM(master_key)
        plain = aes.decrypt(nonce, ciphertext, None)
        return plain.decode("utf-8", "replace")
    # 未知前缀，直接返回
    return enc_value.decode("utf-8", "replace")


def read_cookies(user_data_dir: Path, profile: str, host_filter: str = None):
    cookies_path = user_data_dir / profile / "Network" / "Cookies"
    if not cookies_path.is_file():
        raise FileNotFoundError(f"找不到 Cookies 文件: {cookies_path}")

    # Cookies 文件被浏览器占用（SQLite 锁），先复制到临时文件再读
    tmp = Path(tempfile.mkdtemp(prefix="pdd_ck_")) / "Cookies"
    shutil.copy2(cookies_path, tmp)
    try:
        master_key = get_master_key(user_data_dir)
        conn = sqlite3.connect(str(tmp))
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        sql = (
            "SELECT host_key, name, encrypted_value, value, path, "
            "expires_utc, is_secure, is_httponly "
            "FROM cookies"
        )
        params = ()
        if host_filter:
            sql += " WHERE host_key LIKE ?"
            params = (f"%{host_filter}%",)
        sql += " ORDER BY host_key, name"
        cur.execute(sql, params)
        rows = cur.fetchall()
        conn.close()
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass
        try:
            tmp.parent.rmdir()
        except OSError:
            pass

    results = []
    for r in rows:
        enc = r["encrypted_value"]
        plain = ""
        if enc:
            try:
                plain = decrypt_value(bytes(enc), master_key)
            except Exception as e:
                plain = f"<解密失败: {e}>"
        results.append({
            "host": r["host_key"],
            "name": r["name"],
            "value": plain or r["value"],
            "path": r["path"],
            "expires_utc": r["expires_utc"],
            "secure": bool(r["is_secure"]),
            "httponly": bool(r["is_httponly"]),
        })
    return results


def main():
    parser = argparse.ArgumentParser(description="读取拼多多桌面客户端 Cookie")
    parser.add_argument("--user-data", default=str(DEFAULT_USER_DATA),
                        help="PddBrowser User Data 目录")
    parser.add_argument("--profile", default=DEFAULT_PROFILE,
                        help="profile 目录名")
    parser.add_argument("--host", default=None,
                        help="按 host 过滤，例如 mms.pinduoduo.com")
    parser.add_argument("--cookie", default=None,
                        help="进一步按 cookie name 过滤")
    parser.add_argument("--show-value", action="store_true",
                        help="打印 cookie 值（默认只列名称）")
    args = parser.parse_args()

    user_data = Path(args.user_data)
    rows = read_cookies(user_data, args.profile, args.host)
    if not rows:
        print("没有读到任何 cookie（确认拼多多工作台是否登录过该 profile）")
        return

    print(f"共 {len(rows)} 条 cookie")
    for r in rows:
        if args.cookie and args.cookie.lower() not in r["name"].lower():
            continue
        line = f"{r['host']:40s} {r['name']:30s} path={r['path']}"
        if args.show_value:
            v = r["value"]
            if len(v) > 80:
                v = v[:80] + "...(截断)"
            line += f"  value={v!r}"
        print(line)


if __name__ == "__main__":
    main()
