"""
뉴스 기능 단독 테스트 (도커 없이)

[준비] .env 에 NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 채우기
[실행]
    cd kospi200-app
    pip install requests
    python scripts/test_news.py 삼성전자
    python scripts/test_news.py            # 기본: 삼성전자
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import config, news  # noqa: E402


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "삼성전자"
    print(f"종목명: {name}")
    print(f"NAVER 키 설정: ID={'있음' if config.NAVER_CLIENT_ID else '없음'} / "
          f"SECRET={'있음' if config.NAVER_CLIENT_SECRET else '없음'}")
    if not (config.NAVER_CLIENT_ID and config.NAVER_CLIENT_SECRET):
        print("\n[안내] .env 에 NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 를 먼저 넣어주세요.")
        return

    result = news.get_news(name)
    if result.get("error"):
        print(f"\n[오류] {result['error']}")
        return

    items = result["items"]
    print(f"\n최근 24시간 뉴스 {len(items)}건 (최신순, 최대 10):\n")
    if not items:
        print("  (최근 24시간 내 뉴스 없음)")
        return
    for i, it in enumerate(items, 1):
        print(f"  {i:>2}. {it['title']}")
        print(f"      {it['source']} · {it['pub']}")
        print(f"      {it['link']}")


if __name__ == "__main__":
    main()
