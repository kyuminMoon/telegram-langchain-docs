"""data/docs/ 변경 감시 → 증분 인덱싱 (옵션 A)"""
import logging
import os
import threading
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from config import DOCS_DIR
from indexer import delete_source, reindex_path

logger = logging.getLogger(__name__)

_DEBOUNCE_S = 2.0


class _DocsHandler(FileSystemEventHandler):
    """저장 이벤트가 폭주(create+modify+rename) 하는 에디터 동작 흡수용 디바운서."""

    def __init__(self) -> None:
        self._timers: dict[str, threading.Timer] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _is_md(path: str) -> bool:
        return path.endswith(".md")

    def _schedule(self, path: str, action: str) -> None:
        if not self._is_md(path):
            return
        with self._lock:
            if path in self._timers:
                self._timers[path].cancel()
            t = threading.Timer(_DEBOUNCE_S, self._fire, args=[path, action])
            t.daemon = True
            t.start()
            self._timers[path] = t

    def _fire(self, path: str, action: str) -> None:
        with self._lock:
            self._timers.pop(path, None)
        try:
            if action == "delete" or not Path(path).exists():
                delete_source(os.path.basename(path))
                logger.info("watcher: %s 삭제 처리", os.path.basename(path))
            else:
                n = reindex_path(path)
                logger.info("watcher: %s 재인덱싱 (%d 청크)", os.path.basename(path), n)
        except Exception:
            logger.exception("watcher 처리 실패: %s", path)

    def on_created(self, event):
        if event.is_directory:
            return
        self._schedule(event.src_path, "reindex")

    def on_modified(self, event):
        if event.is_directory:
            return
        self._schedule(event.src_path, "reindex")

    def on_moved(self, event):
        if event.is_directory:
            return
        if hasattr(event, "dest_path") and event.dest_path:
            self._schedule(event.dest_path, "reindex")
        self._schedule(event.src_path, "delete")

    def on_deleted(self, event):
        if event.is_directory:
            return
        self._schedule(event.src_path, "delete")


def build_observer() -> Observer:
    obs = Observer()
    obs.schedule(_DocsHandler(), DOCS_DIR, recursive=False)
    return obs
