"""
주제 로테이션 — 하루 3개 슬롯에 3개 주제(1=경제, 2=사건사고, 3=건강)를 하나씩 배정하고,
매일 한 칸씩 밀어서 각 주제가 모든 시간대를 돌아가게 한다.

슬롯: 0 = 카드뉴스(KST 07:30) / 1 = 릴스#1(KST 12:00) / 2 = 릴스#2(KST 18:00)

카드뉴스는 UTC 22:30(=KST 다음날 07:30)에 실행되므로 UTC 날짜로 계산하면 릴스와 하루가 어긋난다.
따라서 반드시 KST 날짜 기준으로 계산한다.
"""
import datetime

KST = datetime.timezone(datetime.timedelta(hours=9))
CATEGORY_NAME = {"1": "경제", "2": "사건사고", "3": "건강"}


def topic_for_slot(slot):
    """slot(0~2)에 오늘 배정된 주제 인덱스('1'~'3') 반환"""
    doy = datetime.datetime.now(KST).timetuple().tm_yday
    return str(((doy + slot) % 3) + 1)


def describe(slot):
    idx = topic_for_slot(slot)
    return idx, CATEGORY_NAME[idx]


def reel_length_variant(slot):
    """릴스 러닝타임 A/B — 'long'(90초대) / 'short'(45초대)

    "90초는 작은 계정에 부담" vs "90초 이상으로 해달라"를 근거 없이 어느 한쪽으로
    정하지 않고, 실제 완주율·팔로우 전환으로 판정하기 위한 배정 함수.

    (doy + slot) % 2 로 나누므로:
      - 같은 슬롯(시간대)에서 하루씩 번갈아 나간다
      - 주제 로테이션이 %3이라 6일이면 (주제 x 길이) 6조합이 한 번씩 돈다
        → 길이 차이가 주제·시간대 차이에 오염되지 않는다
    """
    doy = datetime.datetime.now(KST).timetuple().tm_yday
    return "long" if (doy + slot) % 2 == 0 else "short"
