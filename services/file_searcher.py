import logging
import os
import re
import time

from utils.helpers import read_file_chunk
from constants import TEXT_CONTENT_EXTENSIONS
from services.index_manager import PersistentIndex

SKIP_DIRS = frozenset({
    "node_modules", ".git", ".svn", "__pycache__", "venv", ".venv",
    ".env", "build", "dist", ".next", ".nuxt", "target", "bin", "obj",
    "vendor", ".idea", ".vscode", ".hg", ".gradle",
})


class FileSearcher:
    def __init__(self):
        self._file_cache: dict[str, list[tuple[str, str, str, str]]] = {}
        self._index = PersistentIndex()

    def invalidate_cache(self) -> None:
        self._file_cache.clear()

    def ensure_index(self, config: dict) -> bool:
        if self._index.load_index():
            return True
        paths = self._get_search_paths(config)
        if not paths:
            return False
        self._index.build_index(paths)
        return True

    def rebuild_index(self, config: dict) -> None:
        paths = self._get_search_paths(config)
        if paths:
            self._index.build_index(paths)

    def incremental_update(self, config: dict) -> int:
        paths = self._get_search_paths(config)
        if not paths:
            return 0
        return self._index.incremental_update(paths)

    def get_index_stats(self) -> dict:
        return self._index.get_stats()

    def _get_search_paths(self, config: dict) -> list[str]:
        from config import get_valid_scopes
        scopes = get_valid_scopes(config)
        if not scopes:
            return []
        paths = []
        for scope in scopes:
            for p in scope.get("paths", []):
                if p and os.path.exists(p):
                    paths.append(p)
        return paths

    def _extract_keywords(self, question: str) -> tuple[list[str], list[str]]:
        phrases = re.findall(r'"([^"]+)"', question)
        words = [w for w in re.findall(r"[\u4e00-\u9fff\w]+", question.lower()) if len(w) >= 2]
        return words, phrases

    def _scroll_content(self, content: str, keyword: str, context_chars: int = 200) -> str:
        idx = content.lower().find(keyword.lower())
        if idx == -1:
            return content[:800]
        start = max(0, idx - context_chars)
        end = min(len(content), idx + len(keyword) + context_chars)
        prefix = "..." if start > 0 else ""
        suffix = "..." if end < len(content) else ""
        return f"{prefix}{content[start:end]}{suffix}"

    def search_kb_for_question(self, question: str, config: dict) -> str:
        from config import get_valid_scopes
        scopes = get_valid_scopes(config)
        if not scopes:
            return ""
        paths = scopes[0]["paths"]
        if not paths:
            return ""

        # 优先使用持久化索引
        if self._index.load_index():
            words, phrases = self._extract_keywords(question)
            search_terms = words + [p.lower() for p in phrases]
            query = " ".join(search_terms)
            index_results = self._index.search(query, max_results=5)
            if index_results:
                result_parts = []
                for r in index_results:
                    snippet = r.get("content_preview", "")[:800]
                    result_parts.append(f"【知识库 - {r['filename']}】{snippet}")
                return "\n\n---\n\n".join(result_parts)

        # 索引不可用时回退到原始遍历
        words, phrases = self._extract_keywords(question)
        if not words and not phrases:
            return ""

        search_terms = words + [p.lower() for p in phrases]
        kb_scores: dict[str, tuple[int, str, str, str]] = {}
        seen_files: set[str] = set()
        SCAN_TIMEOUT = 25.0

        for base_path in paths:
            if not os.path.exists(base_path):
                continue

            scan_start = time.time()
            file_list = self._file_cache.get(base_path)
            if file_list is None:
                file_list = []
                try:
                    for root, dirs, files in os.walk(base_path):
                        if time.time() - scan_start > SCAN_TIMEOUT:
                            break
                        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".") and not d.startswith("$")]
                        for fname in files:
                            if time.time() - scan_start > SCAN_TIMEOUT:
                                break
                            ext = os.path.splitext(fname)[1].lower()
                            if ext not in TEXT_CONTENT_EXTENSIONS:
                                continue
                            fpath = os.path.join(root, fname)
                            if fpath in seen_files:
                                continue
                            seen_files.add(fpath)
                            content = read_file_chunk(fpath, 1500)
                            if content is None:
                                continue
                            rel_path = os.path.relpath(fpath, base_path)
                            file_list.append((fpath, fname, content, rel_path))
                except PermissionError:
                    pass
                except Exception as e:
                    logging.warning(f"扫描目录异常 {base_path}: {e}")
                self._file_cache[base_path] = file_list

            for fpath, fname, content, rel_path in file_list:
                fname_lower = fname.lower()
                freq_map: dict[str, int] = {}
                content_lower = content.lower()
                for w in search_terms:
                    freq_map[w] = (1 if w in fname_lower else 0) + content_lower.count(w)

                max_freq = max(freq_map.values()) if freq_map else 0
                if max_freq == 0:
                    continue

                effective_terms = [t for t, c in freq_map.items() if c > 0]
                best_hit = max(effective_terms, key=lambda t: freq_map[t])
                snippet = self._scroll_content(content, best_hit)

                name_score = sum(1 for w in search_terms if w in fname_lower) * 3
                tf_score = freq_map[best_hit] / max_freq if max_freq > 0 else 0
                content_score = int(sum(freq_map.values()) * (0.5 + tf_score * 0.5))

                score = name_score + content_score
                if score > 0:
                    if fname not in kb_scores or score > kb_scores[fname][0]:
                        kb_scores[fname] = (score, fname, snippet, rel_path)

        if not kb_scores:
            return ""

        scored_list = sorted(kb_scores.values(), key=lambda x: -x[0])
        result_parts = []
        for score, fname, snippet, rel_path in scored_list[:5]:
            result_parts.append(f"【知识库 - {fname}】{snippet}")
        return "\n\n---\n\n".join(result_parts)

    def search_files_with_index(self, query: str, config: dict,
                                  max_results: int = 50) -> list[dict]:
        if self._index.load_index():
            return self._index.search(query, max_results)
        return []