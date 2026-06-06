"""
키워드(호재/악재) vs AI 요약(Gemini) 비교 테스트 (도커 없이)

[준비] .env 에 NAVER_CLIENT_ID/SECRET (뉴스) + GEMINI_API_KEY (요약)
[실행]
    cd kospi200-app
    pip install requests
    python scripts/test_summary.py 삼성전자
    python scripts/test_summary.py 카카오
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import config, news, sentiment, summarize  # noqa: E402


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "삼성전자"
    print(f"종목: {name}")
    print(f"NAVER 키: {'O' if config.NAVER_CLIENT_ID else 'X'} | "
          f"GEMINI 키: {'O' if config.GEMINI_API_KEY else 'X'}\n")

    res = news.get_news(name)
    items = res.get("items", [])
    if res.get("error"):
        print(f"[뉴스 오류] {res['error']} (NAVER 키 확인)")
        return
    if not items:
        print("최근 24시간 내 뉴스가 없습니다.")
        return

    if not summarize.enabled():
        print("(GEMINI_API_KEY 없음 → AI 요약 비활성. 무료 사용자는 제목만 표시)\n")
        for i, it in enumerate(items, 1):
            print(f"{i:>2}. {it['title']}")
        return
    res = summarize.get_summaries(name, items)
    print("── [AI 종합] ──────────────────────────────────")
    print(f"종합: {res['sentiment']} {res['score']}%")
    print(res["overall"] or "(생성 실패)", "\n")
    print("── [기사별] AI 라벨 + 요약 ─────────────────────")
    for i, it in enumerate(items, 1):
        print(f"{i:>2}. [{res['labels'][i-1]}] {it['title']}")
        print(f"     ↳ {res['summaries'][i-1] or '(생성 실패)'}")


if __name__ == "__main__":
    main()
