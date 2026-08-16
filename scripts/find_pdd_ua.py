import json, pathlib, re
base = pathlib.Path(r'C:\Users\Public\Documents\PDD\PddBrowser104\User Data')
for prof in ['cs_9245b98e7871327fbdeda414271d70d9', 'StaticPddBrowser']:
    p = base / prof / 'Preferences'
    if not p.is_file():
        continue
    d = json.loads(p.read_text(encoding='utf-8'))
    s = json.dumps(d, ensure_ascii=False)
    print(f"=== {prof} ===")
    for m in re.findall(r'"user_agent[^"]*":\s*"[^"]+"', s)[:10]:
        print(" ", m)
    uam = d.get('user_agent_metadata', {})
    if uam:
        print("  ua_metadata:", json.dumps(uam, ensure_ascii=False)[:400])
    # 也找 intersitial
    print()
