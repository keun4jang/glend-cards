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
