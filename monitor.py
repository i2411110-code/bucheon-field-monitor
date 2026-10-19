import os, re, sys, json, time, requests
from datetime import date
from pathlib import Path
from bs4 import BeautifulSoup

FACILITIES = {68: "부천체육관", 71: "오정대공원", 208: "원미축구장1",
              78: "원미축구장2", 175: "역곡축구장"}
DETAIL = "https://reserv.bucheon.go.kr/site/main/lending/lendingDetail"
LIST_URL = ("https://reserv.bucheon.go.kr/site/main/lending/"
            "lendingList?inst_cate=01&lending_inst_nm=football")
START_MIN, START_MAX = 6, 12     # 시작 시각 6시 이상 12시 미만
MONTHS_AHEAD = 1                 # 0=이번 달만, 1=다음 달까지
STATE = Path("notified.json")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "ko-KR,ko;q=0.9",
}
SLOT = re.compile(r"((\d{2}):\d{2}~\d{2}:\d{2})\s*(예약가능|예약완료)")

TG_TOKEN = os.environ["TG_TOKEN"]
TG_CHAT_ID = os.environ["TG_CHAT_ID"]

def notify(text):
    r = requests.post(
        f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
        data={"chat_id": TG_CHAT_ID, "text": text,
              "disable_web_page_preview": True}, timeout=10)
    r.raise_for_status()

def saturday_slots(seq, year, month):
    # year/month 파라미터명은 추정값 (3단계에서 확인 필요)
    r = requests.get(DETAIL, headers=HEADERS, timeout=20, params={
        "lending_info_seq": seq, "inst_cate": "01",
        "year": year, "month": month})
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    found, sats = [], 0
    for tr in soup.select("table tr"):
        tds = tr.find_all("td")
        if len(tds) != 7:
            continue
        text = tds[6].get_text(" ", strip=True)        # 토요일 칸
        m = re.match(r"(\d{1,2})", text)
        if not m:
            continue
        sats += 1
        d = date(year, month, int(m.group(1)))
        if d < date.today():
            continue
        for rng, hh, status in SLOT.findall(text):
            if status == "예약가능" and START_MIN <= int(hh) < START_MAX:
                found.append((d.isoformat(), rng))
    if sats == 0:
        raise RuntimeError(
            f"달력 없음 status={r.status_code} len={len(r.text)} head={r.text[:200]!r}")
    return found

def months_to_check():
    t, out = date.today(), []
    y, m = t.year, t.month
    for _ in range(MONTHS_AHEAD + 1):
        out.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out

def main():
    try:
        r0 = requests.get(DETAIL, headers=HEADERS, timeout=20,
                          params={"lending_info_seq": 68, "inst_cate": "01"})
        print("noparam:", r0.status_code, len(r0.text),
              "예약완료" in r0.text or "예약가능" in r0.text)
    except Exception as e:
        print("noparam error:", e)

    old = json.loads(STATE.read_text()) if STATE.exists() else {}
    new_state, alerts, ok = {}, [], 0
    for seq, name in FACILITIES.items():
        for y, m in months_to_check():
            scope = f"{seq}|{y}-{m:02d}"
            try:
                found = saturday_slots(seq, y, m)
            except Exception as e:
                print("error:", scope, e)
                new_state[scope] = old.get(scope, [])   # 실패 시 기존 기록 유지
                continue
            ok += 1
            keys = {f"{d}|{rng}" for d, rng in found}
            for k in sorted(keys - set(old.get(scope, []))):
                d, rng = k.split("|")
                alerts.append(f"{name} {d[5:]}(토) {rng}")
            new_state[scope] = sorted(keys)
            print(scope, "예약가능:", sorted(keys))
            time.sleep(2)

    if alerts:
        notify("토요일 빈자리 생김!\n" + "\n".join(alerts) + f"\n{LIST_URL}")
    STATE.write_text(json.dumps(new_state, ensure_ascii=False, indent=1))
    if ok == 0:
        sys.exit(1)      # 전부 실패하면 Actions 실패로 표시 (메일 알림)

if __name__ == "__main__":
    main()
