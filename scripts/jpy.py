"""매일 JPY→KRW 환율을 기록하고, 추적 시작일 이후 최저가를 새로 찍으면 알림 문구를 만든다.

데이터: Frankfurter (유럽중앙은행 기준환율, 평일 갱신). 은행 매매기준율과 거의 같고,
실제 환전 시에는 은행 수수료(스프레드)가 붙는다.
출력: rates.json 갱신. 새 저점이면 alert.md 를 쓰고 종료 코드 0 (워크플로가 이슈를 만든다).
"""
import json
import os
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RATES = os.path.join(ROOT, "rates.json")
ALERT = os.path.join(ROOT, "alert.md")
TRACK_START = "2026-11-24"
TRIP = "2027-01-01"
MIN_DROP = 0.3  # 100엔당 ₩0.3 이상 내려가야 '새 저점'으로 본다 (잡음 방지)


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "jpy-tracker/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def main():
    with open(RATES, encoding="utf-8") as f:
        data = json.load(f)
    hist = {h["date"]: h["krw100"] for h in data["history"]}

    # 최근 14일을 다시 받아 빠진 날을 채운다
    last = sorted(hist)[-1]
    j = fetch(f"https://api.frankfurter.dev/v1/{last}..?base=JPY&symbols=KRW")
    new_days = []
    for d, v in sorted(j["rates"].items()):
        val = round(v["KRW"] * 100, 2)
        if d not in hist:
            new_days.append(d)
        hist[d] = val

    data["history"] = [{"date": d, "krw100": hist[d]} for d in sorted(hist)]
    tracked = [h for h in data["history"] if h["date"] >= TRACK_START]
    latest = data["history"][-1]

    prev_low = data.get("low")
    alert = None
    for d in new_days:
        if d < TRACK_START:
            continue
        v = hist[d]
        if prev_low is None or v <= prev_low["krw100"] - MIN_DROP:
            if prev_low is not None:
                alert = (d, v, prev_low)
            prev_low = {"date": d, "krw100": v}
    if prev_low is None and tracked:
        prev_low = min(tracked, key=lambda h: h["krw100"])
    data["low"] = prev_low
    data["latest"] = latest

    with open(RATES, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write("\n")

    if alert:
        d, v, old = alert
        start = next((h for h in data["history"] if h["date"] >= TRACK_START), latest)
        last30 = [h["krw100"] for h in data["history"][-22:]]
        avg30 = sum(last30) / len(last30)
        with open(ALERT, "w", encoding="utf-8") as f:
            f.write(
                f"## 엔화 새 저점: 100엔 = ₩{v:,.2f} ({d})\n\n"
                f"- 이전 저점: ₩{old['krw100']:,.2f} ({old['date']})\n"
                f"- 추적 시작({start['date']}) 대비: {v - start['krw100']:+,.2f}원\n"
                f"- 최근 약 한 달 평균: ₩{avg30:,.2f} (평균보다 {v - avg30:+,.2f}원)\n"
                f"- ¥100,000 환전 시 기준환율로 약 ₩{v * 1000:,.0f} (은행 수수료 별도)\n\n"
                "유럽중앙은행 기준환율이에요. 은행 앱의 실제 환전 가격과는 조금 다를 수 있어요.\n\n"
                "일정표: https://zel-da.github.io/tokyo-2027/#info\n\n@Zel-da\n"
            )
        print(f"NEW LOW {d} {v}")
    else:
        print(f"latest {latest['date']} {latest['krw100']} low {prev_low}")


if __name__ == "__main__":
    sys.exit(main())
