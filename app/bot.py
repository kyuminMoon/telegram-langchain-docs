"""Telegram 봇"""
import asyncio
import logging
import os

from telegram import Update
from telegram.constants import ChatAction
from telegram.error import TimedOut
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from telegram.request import HTTPXRequest

from config import (
    DOCS_DIR,
    MAX_TELEGRAM_MESSAGE_LEN,
    TELEGRAM_ALLOWED_USER_IDS,
    TELEGRAM_BOT_TOKEN,
    WATCHER_ENABLED,
)
from indexer import reindex_path, safe_filename
from rag import answer

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def _is_authorized(user_id: int | None) -> bool:
    if not TELEGRAM_ALLOWED_USER_IDS:
        return True
    return user_id in TELEGRAM_ALLOWED_USER_IDS


def _truncate(text: str, limit: int = MAX_TELEGRAM_MESSAGE_LEN) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 20] + "\n... (이하 생략)"


async def _respond(update: Update, question: str) -> None:
    chat = update.effective_chat
    if chat is None:
        return
    await chat.send_action(ChatAction.TYPING)
    try:
        result = await asyncio.to_thread(answer, question)
        text = result["answer"]
        if result["sources"]:
            text += f"\n\n출처: {', '.join(result['sources'])}"
        await update.effective_message.reply_text(_truncate(text))
    except Exception as exc:  # noqa: BLE001
        logger.exception("RAG 처리 실패")
        await update.effective_message.reply_text(f"오류 발생: {exc}")


async def start_command(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "안녕하세요. 사내 문서 기반 도우미입니다.\n"
        "사용법:\n"
        "  /ask <질문>\n"
        "  또는 일반 메시지로 질문\n"
        "  마크다운(.md) 파일을 첨부하면 자동 인덱싱됩니다."
    )


async def ask_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user and not _is_authorized(user.id):
        await update.effective_message.reply_text("이 봇 사용 권한이 없습니다.")
        return
    question = " ".join(context.args).strip() if context.args else ""
    if not question:
        await update.effective_message.reply_text("질문을 입력해주세요. 예: /ask 휴가 며칠 쓸 수 있어?")
        return
    await _respond(update, question)


async def text_message(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user and not _is_authorized(user.id):
        return
    question = (update.effective_message.text or "").strip()
    if not question:
        return
    await _respond(update, question)


async def document_handler(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    """텔레그램으로 .md 파일 첨부 시 자동 인덱싱."""
    user = update.effective_user
    if user and not _is_authorized(user.id):
        return
    msg = update.effective_message
    doc = msg.document if msg else None
    if doc is None:
        return

    raw_name = doc.file_name or ""
    safe = safe_filename(raw_name)
    if not safe:
        await msg.reply_text(
            f"마크다운(.md) 파일만 받습니다. (받은 파일: {raw_name or '이름없음'})"
        )
        return

    chat = update.effective_chat
    if chat is not None:
        await chat.send_action(ChatAction.UPLOAD_DOCUMENT)

    target_path = os.path.join(DOCS_DIR, safe)
    try:
        os.makedirs(DOCS_DIR, exist_ok=True)
        # Telegram API 가 일시적으로 느려지는 경우가 있어 1회 재시도
        last_exc: Exception | None = None
        for attempt in range(2):
            try:
                tg_file = await doc.get_file()
                await tg_file.download_to_drive(custom_path=target_path)
                last_exc = None
                break
            except TimedOut as exc:
                last_exc = exc
                logger.warning("Telegram 다운로드 타임아웃 (시도 %d/2): %s", attempt + 1, exc)
                await asyncio.sleep(1.5)
        if last_exc is not None:
            raise last_exc

        n = await asyncio.to_thread(reindex_path, target_path)
        await msg.reply_text(f"✓ {safe} 인덱싱 완료 ({n} 청크)")
    except Exception as exc:  # noqa: BLE001
        logger.exception("문서 업로드 처리 실패")
        await msg.reply_text(f"인덱싱 실패: {exc}")


async def post_init(app: Application) -> None:
    me = await app.bot.get_me()
    logger.info("봇 준비 완료: @%s (id=%s)", me.username, me.id)

    if WATCHER_ENABLED:
        try:
            from watcher import build_observer
            obs = build_observer()
            obs.start()
            app.bot_data["_observer"] = obs
            logger.info("watcher 시작: %s 감시 중", DOCS_DIR)
        except Exception:
            logger.exception("watcher 시작 실패 (계속 진행)")


async def post_shutdown(app: Application) -> None:
    obs = app.bot_data.get("_observer") if app.bot_data else None
    if obs is not None:
        try:
            obs.stop()
            obs.join(timeout=3)
            logger.info("watcher 종료")
        except Exception:
            logger.exception("watcher 종료 중 오류")


def run() -> None:
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN 환경변수가 필요합니다")

    # 일반 API 호출 (sendMessage / getFile / 파일 다운로드 등) - 기본 5s 너무 짧아 늘림
    request = HTTPXRequest(
        connect_timeout=10.0,
        read_timeout=60.0,
        write_timeout=60.0,
        pool_timeout=10.0,
    )
    # getUpdates 는 long polling 이라 read_timeout 길게 (기본 동작과 유사)
    get_updates_request = HTTPXRequest(
        connect_timeout=10.0,
        read_timeout=60.0,
        write_timeout=10.0,
        pool_timeout=10.0,
    )

    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .request(request)
        .get_updates_request(get_updates_request)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("ask", ask_command))
    app.add_handler(MessageHandler(filters.Document.ALL, document_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message))
    app.run_polling(allowed_updates=Update.ALL_TYPES)
