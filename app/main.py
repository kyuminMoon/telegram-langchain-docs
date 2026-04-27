"""진입점"""
import asyncio
import sys

from bot import run

if __name__ == "__main__":
    # Python 3.14+ 호환: get_event_loop() 가 메인 스레드에서 자동 생성하지 않으므로
    # ptb 21.7 의 run_polling() 이 RuntimeError 를 내는 문제 우회.
    if sys.version_info >= (3, 14):
        asyncio.set_event_loop(asyncio.new_event_loop())
    run()
