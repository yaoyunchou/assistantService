# -*- coding: utf-8 -*-
"""复制并分析 PDD 桌面端的登录/数据存储，找长期 token。"""
import os, sys, shutil, sqlite3, tempfile
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from pathlib import Path

PDD = Path(r"C:\Users\Public\Documents\PDD")

def copy_if_locked(src: Path) -> Path | None:
    """复制文件到临时目录（绕过占用锁）。"""
    if not src.is_file():
        return None
    tmp = Path(tempfile.mkdtemp(prefix="pdd_data_")) / src.name
    try:
        shutil.copy2(src, tmp)
        return tmp
    except Exception as e:
        print(f"  复制失败 {src.name}: {e}")
        return None

def is_sqlite(p: Path) -> bool:
    try:
        with open(p, "rb") as f:
            return f.read(16).startswith(b"SQLite format 3")
    except Exception:
        return False

def dump_sqlite(p: Path, label: str):
    print(f"  [SQLite] {label}")
    try:
        c = sqlite3.connect(str(p))
        tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        print(f"    表: {tables}")
        for t in tables:
            try:
                cols = [r[1] for r in c.execute(f"PRAGMA table_info('{t}')").fetchall()]
                cnt = c.execute(f"SELECT COUNT(*) FROM '{t}'").fetchone()[0]
                print(f"    [{t}] 列={cols} 行数={cnt}")
                if cnt > 0 and cnt < 50:
                    for row in c.execute(f"SELECT * FROM '{t}' LIMIT 20"):
                        vals = []
                        for v in row:
                            s = repr(v)
                            if len(s) > 120: s = s[:120] + "...(截断)"
                            vals.append(s)
                        print(f"      {vals}")
            except Exception as e:
                print(f"    [{t}] 读取失败: {e}")
        c.close()
    except Exception as e:
        print(f"    打开失败(可能加密): {e}")

def dump_file(p: Path, label: str, max_bytes=2000):
    print(f"  [文件] {label}  ({p.stat().st_size} 字节)")
    try:
        data = p.read_bytes()
    except Exception as e:
        print(f"    读取失败: {e}")
        return
    # 头部 hex
    print(f"    头32字节hex: {data[:32].hex()}")
    # 可打印预览
    printable = "".join(chr(b) if 32 <= b < 127 else "." for b in data)
    print(f"    预览: {printable[:max_bytes]}")

print("=" * 70)
print("PDDData 目录")
print("=" * 70)
pdddata = PDD / "PDDData"
if pdddata.is_dir():
    for f in sorted(pdddata.iterdir()):
        if f.is_file():
            if f.suffix == ".db":
                tmp = copy_if_locked(f)
                if tmp:
                    if is_sqlite(tmp):
                        dump_sqlite(tmp, f.name)
                    else:
                        dump_file(tmp, f.name, 800)
                    tmp.unlink()
            else:
                dump_file(f, f.name, 1500)

print()
print("=" * 70)
print("WorkbenchDB/LoginData")
print("=" * 70)
ld = PDD / "WorkbenchDB" / "LoginData" / "Data"
if ld.is_dir():
    for f in sorted(ld.iterdir()):
        if f.is_file() and f.suffix == ".db":
            tmp = copy_if_locked(f)
            if tmp:
                if is_sqlite(tmp):
                    dump_sqlite(tmp, f.name)
                else:
                    dump_file(tmp, f.name, 800)
                tmp.unlink()
