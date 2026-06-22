import hashlib
import json
import logging
import os
import time

from utils.helpers import read_file_chunk
from constants import TEXT_CONTENT_EXTENSIONS

SKIP_DIRS = frozenset({
    "node_modules", ".git", ".svn", "__pycache__", "venv", ".venv",
    ".env", "build", "dist", ".next", ".nuxt", "target", "bin", "obj",
    "vendor", ".idea", ".vscode", ".hg", ".gradle",
})

INDEX_VERSION = "1.0"
INDEX_DIR = "search_index"
INDEX_FILE = "index.json"


def _path_hash(filepath: str) -> str:
    return hashlib.md5(filepath.encode("utf-8")).hexdigest()


class PersistentIndex:
    def __init__(self, base_dir: str = "."):
        self._base_dir = os.path.abspath(base_dir)
        self._index_dir = os.path.join(self._base_dir, INDEX_DIR)
        self._index_path = os.path.join(self._index_dir, INDEX_FILE)

        self._files: dict[str, dict] = {}
        self._inverted_index: dict[str, dict[str, int]] = {}
        self._build_time: str = ""
        self._root_paths: list[str] = []

    # ── Public API ──────────────────────────────────────

    def build_index(self, root_paths: list[str]) -> None:
        seen: dict[str, dict] = {}
        inv: dict[str, dict[str, int]] = {}

        for base_path in root_paths:
            if not os.path.exists(base_path):
                continue
            self._walk_and_index(base_path, base_path, seen, inv)

        self._files = seen
        self._inverted_index = inv
        self._root_paths = root_paths
        self._build_time = time.strftime("%Y-%m-%dT%H:%M:%S")
        self._save()

    def load_index(self) -> bool:
        if not os.path.exists(self._index_path):
            return False
        try:
            with open(self._index_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("version") != INDEX_VERSION:
                logging.warning("索引版本不匹配，需重建")
                return False
            self._files = data.get("files", {})
            self._inverted_index = data.get("inverted_index", {})
            self._build_time = data.get("build_time", "")
            self._root_paths = data.get("root_paths", [])
            return True
        except Exception as e:
            logging.warning(f"索引加载失败: {e}")
            return False

    def search(self, query: str, max_results: int = 50) -> list[dict]:
        if not query.strip():
            return []

        tokens = self._segment(query)
        if not tokens:
            return []

        scores: dict[str, tuple[float, dict]] = {}
        token_total_freq: dict[str, int] = {}
        for token, file_map in self._inverted_index.items():
            if any(t in token for t in tokens):
                token_total_freq[token] = sum(file_map.values())

        for token, file_map in self._inverted_index.items():
            if any(t in token for t in tokens):
                total_freq = token_total_freq.get(token, 1)
                for fhash, freq in file_map.items():
                    finfo = self._files.get(fhash)
                    if not finfo:
                        continue
                    cur_score, _ = scores.get(fhash, (0.0, finfo))
                    tf = freq / (total_freq + 1)
                    name_bonus = 2.0 if any(t in finfo.get("name", "").lower() for t in tokens) else 0.0
                    new_score = cur_score + (tf * 10 + name_bonus)
                    scores[fhash] = (new_score, finfo)

        if not scores:
            return []

        ranked = sorted(scores.values(), key=lambda x: -x[0])
        results = []
        for score, finfo in ranked[:max_results]:
            filepath = finfo["path"]
            content_preview = self._get_content_preview(filepath, query, 300)
            results.append({
                "filepath": filepath,
                "filename": finfo.get("name", ""),
                "size": finfo.get("size", 0),
                "mtime": finfo.get("mtime", 0),
                "rel_path": finfo.get("rel_path", ""),
                "score": round(score, 2),
                "content_preview": content_preview,
            })

        return results

    def incremental_update(self, root_paths: list[str]) -> int:
        if not self._files:
            self.build_index(root_paths)
            return len(self._files)

        changed = 0
        new_seen: dict[str, dict] = {}
        new_inv: dict[str, dict[str, int]] = {}

        for base_path in root_paths:
            if not os.path.exists(base_path):
                continue
            for root, dirs, files in os.walk(base_path):
                dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".") and not d.startswith("$")]
                for fname in files:
                    ext = os.path.splitext(fname)[1].lower()
                    if ext not in TEXT_CONTENT_EXTENSIONS:
                        continue
                    fpath = os.path.join(root, fname)
                    fhash = _path_hash(fpath)
                    existing = self._files.get(fhash)
                    try:
                        current_mtime = os.path.getmtime(fpath)
                    except OSError:
                        continue
                    if existing and existing.get("mtime") == current_mtime:
                        new_seen[fhash] = existing
                        if existing.get("tokens"):
                            existing_tokens = existing.get("tokens", [])
                            for t in existing_tokens:
                                t_map = new_inv.setdefault(t, {})
                                t_map[fhash] = t_map.get(fhash, 0) + 1
                        continue

                    content = read_file_chunk(fpath, 5000)
                    if content is None:
                        continue
                    rel_path = os.path.relpath(fpath, base_path)
                    tokens = self._do_segment(content)
                    finfo = {
                        "path": fpath,
                        "name": fname,
                        "mtime": current_mtime,
                        "size": os.path.getsize(fpath),
                        "rel_path": rel_path,
                        "content_len": len(content),
                        "tokens": tokens,
                    }
                    new_seen[fhash] = finfo
                    for t in tokens:
                        t_map = new_inv.setdefault(t, {})
                        t_map[fhash] = t_map.get(fhash, 0) + 1
                    changed += 1

        self._files = new_seen
        self._inverted_index = new_inv
        self._root_paths = root_paths
        self._build_time = time.strftime("%Y-%m-%dT%H:%M:%S")
        self._save()
        return changed

    def get_stats(self) -> dict:
        return {
            "file_count": len(self._files),
            "token_count": len(self._inverted_index),
            "build_time": self._build_time,
            "root_paths": self._root_paths,
            "index_path": self._index_path,
        }

    # ── Internal ────────────────────────────────────────

    def _walk_and_index(self, base_path: str, scan_root: str,
                         seen: dict, inv: dict) -> None:
        for root, dirs, files in os.walk(base_path):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".") and not d.startswith("$")]
            for fname in files:
                ext = os.path.splitext(fname)[1].lower()
                if ext not in TEXT_CONTENT_EXTENSIONS:
                    continue
                fpath = os.path.join(root, fname)
                fhash = _path_hash(fpath)
                if fhash in seen:
                    continue
                content = read_file_chunk(fpath, 5000)
                if content is None:
                    continue

                rel_path = os.path.relpath(fpath, scan_root)
                tokens = self._do_segment(content)

                try:
                    mtime = os.path.getmtime(fpath)
                    size = os.path.getsize(fpath)
                except OSError:
                    mtime = 0
                    size = 0

                finfo = {
                    "path": fpath,
                    "name": fname,
                    "mtime": mtime,
                    "size": size,
                    "rel_path": rel_path,
                    "content_len": len(content),
                    "tokens": tokens,
                }
                seen[fhash] = finfo

                for t in tokens:
                    t_map = inv.setdefault(t, {})
                    t_map[fhash] = t_map.get(fhash, 0) + 1

    def _segment(self, text: str) -> list[str]:
        try:
            import jieba
            words = jieba.lcut(text.lower())
        except ImportError:
            import re
            words = re.findall(r"[\u4e00-\u9fff\w]+", text.lower())
        return [w for w in words if len(w) >= 2]

    def _do_segment(self, text: str) -> list[str]:
        return self._segment(text)

    def _save(self) -> None:
        os.makedirs(self._index_dir, exist_ok=True)
        data = {
            "version": INDEX_VERSION,
            "build_time": self._build_time,
            "root_paths": self._root_paths,
            "file_count": len(self._files),
            "files": self._files,
            "inverted_index": self._inverted_index,
        }
        tmp_path = self._index_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, self._index_path)

    def _get_content_preview(self, filepath: str, query: str, max_chars: int = 300) -> str:
        try:
            content = read_file_chunk(filepath, 5000)
            if not content:
                return ""
            idx = content.lower().find(query.lower())
            if idx == -1:
                return content[:max_chars]
            start = max(0, idx - 100)
            end = min(len(content), idx + len(query) + 100)
            prefix = "..." if start > 0 else ""
            suffix = "..." if end < len(content) else ""
            return f"{prefix}{content[start:end]}{suffix}"
        except Exception:
            return ""
