import os
import re
import threading
import tkinter as tk
from tkinter import ttk

from constants import COLORS, AI_CONFIGS
from services.ai_service import call_ollama, call_openai_compat, call_zhipu_websearch
from ui.widgets import configure_answer_tags

_conv_counter = 0


def _next_conv_id() -> str:
    global _conv_counter
    _conv_counter += 1
    return f"conv_{_conv_counter}"


class WebPanel:
    _PROVIDER_KEYS = list(AI_CONFIGS.keys())

    def __init__(self, parent: tk.Frame, config: dict, ai_provider: str, api_key: str):
        self._parent = parent
        self._config = config
        self._is_answering: bool = False
        self._answer_cancelled: bool = False
        self._stream_buffer: str = ""
        self._attached_doc: dict | None = None

        self._chat_widget: tk.Text | None = None
        self._thinking_id: int | None = None
        self._thinking_pos: str | None = None
        self._thinking_count: int = 0
        self._ai_start_pos: str | None = None
        self._first_chunk: bool = True
        self._welcome_shown: bool = True

        self.web_var = tk.StringVar()
        self._conversations: dict[str, dict] = {}
        self._active_conv_id: str | None = None

        self._frame = tk.Frame(parent, bg=COLORS["bg"])
        self._build_sidebar()
        self._build_right_panel()
        self.update_config(config, ai_provider, api_key)

    @property
    def frame(self) -> tk.Frame:
        return self._frame

    def update_config(self, config: dict, ai_provider: str, api_key: str) -> None:
        self._config = config
        self._provider = ai_provider or "ollama"
        self._api_key = api_key or self._read_api_key(self._provider)
        self._sync_model_ui()

    def _read_api_key(self, provider: str) -> str:
        custom = self._config.get("ai_custom_config", {})
        if isinstance(custom, dict):
            prov = custom.get(provider, {})
            return prov.get("api_key", "") if isinstance(prov, dict) else ""
        return ""

    # ── Model bar ─────────────────────────────────

    def _build_model_bar(self, parent: tk.Frame) -> None:
        bar = tk.Frame(parent, bg="white", height=38)
        bar.pack(fill=tk.X)
        bar.pack_propagate(False)

        sep = tk.Frame(bar, bg="#E2E8F0", height=1)
        sep.pack(side=tk.BOTTOM, fill=tk.X)

        inner = tk.Frame(bar, bg="white")
        inner.pack(fill=tk.X, padx=20)

        tk.Label(inner, text="\U0001F916",
                 font=("Segoe UI Emoji", 11), bg="white").pack(side=tk.LEFT)

        self._model_var = tk.StringVar()
        self._model_cb = ttk.Combobox(
            inner, textvariable=self._model_var,
            state="readonly", width=20,
            font=("Microsoft YaHei UI", 10),
        )
        self._model_cb.pack(side=tk.LEFT, padx=(8, 10), pady=5)
        self._model_cb.bind("<<ComboboxSelected>>", self._on_model_change)

        style = ttk.Style()
        style.configure("Model.TCombobox",
            fieldbackground="white", background="white",
            foreground=COLORS["text"],
            arrowcolor="#94A3B8",
            selectbackground="white", selectforeground=COLORS["text"],
        )
        style.map("Model.TCombobox",
            fieldbackground=[("readonly", "white")],
            foreground=[("readonly", COLORS["text"])],
        )
        style.configure("Model.TCombobox.Listbox",
            font=("Microsoft YaHei UI", 10),
            background="white", foreground=COLORS["text"],
            selectbackground="#DBEAFE", selectforeground="#1E293B",
            borderwidth=1,
        )
        self._model_cb.configure(style="Model.TCombobox")

        settings_btn = tk.Button(
            inner, text="\u2699 设置",
            font=("Microsoft YaHei UI", 9),
            bg="white", fg="#64748B",
            bd=0, relief="flat", cursor="hand2",
            activebackground="#F0F4F8",
            activeforeground=COLORS["primary"],
            command=self._open_ai_settings,
        )
        settings_btn.pack(side=tk.LEFT)

    def _rebuild_model_menu(self) -> None:
        labels = []
        self._provider_list = list(self._PROVIDER_KEYS)
        for pid in self._PROVIDER_KEYS:
            cfg = AI_CONFIGS[pid]
            name = cfg.get("name", pid)
            custom = self._config.get("ai_custom_config", {}).get(pid, {})
            has_key = bool(custom.get("api_key")) if cfg.get("need_key") else True
            labels.append(name if has_key else f"{name}（未配置）")
        self._model_cb["values"] = labels

    def _sync_model_ui(self) -> None:
        if not hasattr(self, "_model_cb"):
            return
        self._rebuild_model_menu()
        try:
            idx = self._PROVIDER_KEYS.index(self._provider)
            self._model_cb.current(idx)
        except ValueError:
            pass

    def _on_model_change(self, event=None) -> None:
        idx = self._model_cb.current()
        if idx < 0 or idx >= len(self._PROVIDER_KEYS):
            return
        provider = self._PROVIDER_KEYS[idx]
        self._provider = provider
        cfg = AI_CONFIGS.get(provider, {})
        custom = self._config.get("ai_custom_config", {}).get(provider, {})
        if isinstance(custom, dict):
            self._api_key = custom.get("api_key", "") or self._api_key

    def _open_ai_settings(self) -> None:
        try:
            from ui.settings_window import SettingsWindow
            SettingsWindow(
                self._parent.winfo_toplevel(),
                self._config, self._provider, self._api_key,
                [], on_save=self._on_settings_saved,
            )
        except Exception:
            pass

    def _on_settings_saved(self, config: dict, ai_provider: str, api_key: str) -> None:
        self._config = config
        self._provider = ai_provider or "ollama"
        if not api_key:
            api_key = (config.get("ai_custom_config", {})
                       .get(self._provider, {})
                       .get("api_key", ""))
        self._api_key = api_key
        self._sync_model_ui()

    # ── Sidebar ──────────────────────────────────────

    def _build_sidebar(self) -> None:
        self._sidebar = tk.Frame(self._frame, bg="#F8FAFC", width=180)
        self._sidebar.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 1))
        self._sidebar.pack_propagate(False)

        sep_right = tk.Frame(self._sidebar, bg="#E2E8F0", width=1)
        sep_right.pack(side=tk.RIGHT, fill=tk.Y)

        tk.Label(
            self._sidebar, text="\U0001F916 对话列表",
            font=("Microsoft YaHei UI", 10, "bold"),
            fg="#64748B", bg="#F8FAFC",
        ).pack(fill=tk.X, padx=14, pady=(16, 8))

        tk.Button(
            self._sidebar, text="\U00002795 新对话",
            font=("Microsoft YaHei UI", 10),
            bg=COLORS["primary"], fg="white",
            bd=0, relief="flat", cursor="hand2",
            activebackground="#0284C7",
            padx=8, pady=5,
            command=self._new_conversation,
        ).pack(fill=tk.X, padx=10, pady=(0, 8))

        self._conv_listbox = tk.Listbox(
            self._sidebar,
            font=("Microsoft YaHei UI", 10),
            bg="#F8FAFC", fg="#475569",
            bd=0, highlightthickness=0,
            selectbackground="#DBEAFE",
            selectforeground="#1E293B",
            activestyle="none",
            exportselection=False,
            relief="flat",
        )
        self._conv_listbox.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0, 10))
        self._conv_listbox.bind("<<ListboxSelect>>", self._on_conv_select)

    # ── Right panel ──────────────────────────────────

    def _build_right_panel(self) -> None:
        right = tk.Frame(self._frame, bg=COLORS["bg"])
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._build_model_bar(right)
        self._build_input_bar(right)
        self._build_chat_area(right)

    def _build_chat_area(self, parent: tk.Frame) -> None:
        container = tk.Frame(parent, bg=COLORS["bg"])
        container.pack(fill=tk.BOTH, expand=True)
        self._chat_container = container

        self._build_chat_widget()
        self._chat_widget.bind("<MouseWheel>", self._on_mousewheel)
        self._chat_widget.bind("<Button-3>", self._show_context_menu)

    def _build_chat_widget(self) -> None:
        self._chat_widget = tk.Text(
            self._chat_container,
            font=("Microsoft YaHei UI", 11),
            bg=COLORS["bg"], fg=COLORS["text"],
            wrap="word", bd=0, relief="flat",
            padx=28, pady=18,
            spacing1=2, spacing3=10,
            cursor="xterm",
        )
        self._chat_widget.pack(fill=tk.BOTH, expand=True)

        self._chat_widget.tag_configure("sel", background="#BFDBFE", foreground="#1E293B")

        self._chat_widget.tag_configure("user", justify="right", foreground=COLORS["text"],
                                         font=("Microsoft YaHei UI", 11),
                                         background="#E0F2FE",
                                         spacing3=6, spacing1=4,
                                         lmargin1=60, lmargin2=60, rmargin=6,
                                         wrap="word")
        self._chat_widget.tag_configure("user_label", justify="right",
                                         font=("Microsoft YaHei UI", 10, "bold"),
                                         foreground="#0284C7", spacing3=2,
                                         background="#E0F2FE",
                                         lmargin1=60, lmargin2=60, rmargin=6)
        self._chat_widget.tag_configure("ai_name", justify="left",
                                        font=("Microsoft YaHei UI", 11, "bold"),
                                        foreground="#0284C7", spacing3=2,
                                        background=COLORS["bg"])
        self._chat_widget.tag_configure("ai", justify="left", foreground=COLORS["text"],
                                        font=("Microsoft YaHei UI", 11), spacing3=10,
                                        background="#F8FAFC",
                                        lmargin1=6, lmargin2=6, rmargin=30,
                                        wrap="word")
        self._chat_widget.tag_configure("loading", justify="left", foreground="#94A3B8",
                                        font=("Microsoft YaHei UI", 11, "italic"),
                                        background=COLORS["bg"])
        self._chat_widget.tag_configure("thinking_text", justify="left", foreground="#94A3B8",
                                        font=("Microsoft YaHei UI", 11),
                                        background=COLORS["bg"])
        self._chat_widget.tag_configure("sep", justify="center",
                                        foreground="#CBD5E1",
                                        font=("Microsoft YaHei UI", 8),
                                        spacing1=6, spacing3=4,
                                        background=COLORS["bg"])

        configure_answer_tags(self._chat_widget)
        self._chat_widget.tag_configure("welcome", justify="center",
                                        foreground="#94A3B8",
                                        font=("Microsoft YaHei UI", 11),
                                        background=COLORS["bg"],
                                        spacing1=6)
        self._show_welcome()

    def _show_context_menu(self, event: tk.Event) -> None:
        menu = tk.Menu(self._chat_widget, tearoff=0, bg="white", fg=COLORS["text"],
                       activebackground="#DBEAFE", activeforeground="#1E293B",
                       font=("Microsoft YaHei UI", 10))
        menu.add_command(label="\U0001F4CB 复制", command=self._copy_selection)
        menu.add_separator()
        menu.add_command(label="全选", command=self._select_all)
        menu.add_command(label="复制全部对话", command=self._copy_all)
        menu.tk_popup(event.x_root, event.y_root)

    def _copy_selection(self) -> None:
        try:
            selected = self._chat_widget.get(tk.SEL_FIRST, tk.SEL_LAST)
            if selected:
                self._chat_widget.clipboard_clear()
                self._chat_widget.clipboard_append(selected)
        except tk.TclError:
            pass

    def _select_all(self) -> None:
        self._chat_widget.config(state="normal")
        self._chat_widget.tag_add(tk.SEL, "1.0", "end-1c")
        self._chat_widget.config(state="disabled")
        self._chat_widget.see("1.0")

    def _copy_all(self) -> None:
        content = self._chat_widget.get("1.0", "end-1c")
        self._chat_widget.clipboard_clear()
        self._chat_widget.clipboard_append(content)

    def _show_welcome(self) -> None:
        self._welcome_shown = True
        self._chat_widget.insert("end", "\n\n\n\n")
        self._chat_widget.insert("end", "  \U0001F31F\n\n", "welcome")
        self._chat_widget.insert("end", "  向我提问，我会结合专业知识为你解答", "welcome")
        self._welcome_end = self._chat_widget.index("end-1c")
        self._chat_widget.config(state="disabled")

    def _build_input_bar(self, parent: tk.Frame) -> None:
        bar = tk.Frame(parent, bg="white", height=60)
        bar.pack(side=tk.BOTTOM, fill=tk.X)
        bar.pack_propagate(False)

        sep = tk.Frame(bar, bg="#E2E8F0", height=1)
        sep.pack(side=tk.TOP, fill=tk.X)

        inner = tk.Frame(bar, bg="white")
        inner.pack(fill=tk.BOTH, padx=20, pady=10)

        self.web_entry = tk.Entry(
            inner, textvariable=self.web_var,
            font=("Microsoft YaHei UI", 13),
            bg="white", fg=COLORS["text"],
            bd=0, relief="flat",
            highlightthickness=1,
            highlightbackground="#CBD5E1",
            highlightcolor=COLORS["primary"],
        )
        self.web_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8), ipady=7)
        self.web_entry.insert(0, "向 AI 提问...")
        self.web_entry.config(fg="#94A3B8")
        self.web_entry.bind("<Return>", lambda e: self._on_send_click())
        self.web_entry.bind("<FocusIn>", self._on_entry_focus)
        self.web_entry.bind("<FocusOut>", self._on_entry_blur)

        self.upload_btn = tk.Button(
            inner, text="\U0001F4CE",
            font=("Segoe UI Emoji", 14),
            bg="white", fg="#64748B",
            bd=0, relief="flat", cursor="hand2",
            activebackground="#F0F4F8",
            activeforeground=COLORS["primary"],
            command=self._on_upload_file,
        )
        self.upload_btn.pack(side=tk.LEFT, padx=(0, 8))

        self.send_btn = tk.Button(
            inner, text="\u25B6 发送",
            font=("Microsoft YaHei UI", 11, "bold"),
            bg=COLORS["primary"], fg="white",
            bd=0, relief="flat", cursor="hand2",
            activebackground="#0284C7",
            padx=24, pady=8,
            command=self._on_send_click,
        )
        self.send_btn.pack(side=tk.RIGHT)

    # ── Events ───────────────────────────────────────

    def _on_entry_focus(self, _: tk.Event) -> None:
        if self.web_var.get() == "向 AI 提问...":
            self.web_entry.delete(0, tk.END)
            self.web_entry.config(fg=COLORS["text"])

    def _on_entry_blur(self, _: tk.Event) -> None:
        if not self.web_var.get():
            self.web_entry.insert(0, "向 AI 提问...")
            self.web_entry.config(fg="#94A3B8")

    # ── File upload ────────────────────────────────────

    def _on_upload_file(self) -> None:
        from tkinter import filedialog
        from services.document_parser import parse_document

        filetypes = [
            ("所有支持格式", "*.docx;*.pdf;*.xlsx;*.xls;*.pptx;*.txt;*.md"),
            ("Word文档", "*.docx;*.doc"),
            ("PDF文档", "*.pdf"),
            ("Excel表格", "*.xlsx;*.xls"),
            ("PPT演示", "*.pptx;*.ppt"),
            ("纯文本", "*.txt;*.md"),
        ]
        filepath = filedialog.askopenfilename(title="选择要分析的文档", filetypes=filetypes)
        if not filepath:
            return

        self._show_parsing_hint(os.path.basename(filepath))

        def _parse_thread():
            try:
                from services.document_parser import parse_document
                parsed = parse_document(filepath)
                self._parent.after(0, lambda: self._on_parse_complete(parsed, filepath))
            except Exception as e:
                self._parent.after(0, lambda: self._show_parse_error(str(e)))

        threading.Thread(target=_parse_thread, daemon=True).start()

    def _show_parsing_hint(self, filename: str) -> None:
        self._chat_widget.config(state="normal")
        if self._welcome_shown:
            self._chat_widget.delete("1.0", self._welcome_end)
            self._welcome_shown = False
        self._chat_widget.insert("end", "\n— — —\n", "sep")
        self._chat_widget.insert("end", f"\U0001F4CE {filename}\n", "user_label")
        self._chat_widget.insert("end", "正在解析文件...\n", "loading")
        self._chat_widget.config(state="disabled")
        self._chat_widget.see("end")

    def _show_parse_error(self, error: str) -> None:
        self._chat_widget.config(state="normal")
        self._chat_widget.insert("end", f"\U0000274C 文件解析失败: {error}\n", "loading")
        self._chat_widget.config(state="disabled")
        self._chat_widget.see("end")

    def _on_parse_complete(self, parsed, filepath: str) -> None:
        self._chat_widget.config(state="normal")

        doc_meta = {
            "filename": parsed.filename,
            "filepath": filepath,
            "file_type": parsed.file_type,
            "text_content": parsed.text_content,
            "structured_content": parsed.structured_content,
            "summary": parsed.summary,
            "metadata": dict(parsed.metadata) if hasattr(parsed, "metadata") else {},
        }
        self._attached_doc = doc_meta

        conv = self._conversations.get(self._active_conv_id) if self._active_conv_id else None
        if conv:
            conv["attached_doc"] = doc_meta

        self._chat_widget.delete("end-2l", "end-1c")
        self._chat_widget.insert("end", "\U0001F4CE  ", "user_label")

        file_size = doc_meta["metadata"].get("file_size", 0)
        size_str = f"{file_size / 1024:.1f} KB" if file_size < 1048576 else f"{file_size / 1048576:.1f} MB"

        info_lines = [
            f"\U0001F4C4 {parsed.filename}",
            f"类型: {parsed.file_type.upper()}  |  大小: {size_str}",
            parsed.summary,
        ]
        for line in info_lines:
            self._chat_widget.insert("end", line + "\n", "user")
        self._chat_widget.insert("end", "\n", "user")

        self._chat_widget.config(state="disabled")
        self._chat_widget.see("end")

        self.web_entry.delete(0, tk.END)
        self.web_entry.insert(0, "请分析这份文档")
        self.web_entry.config(fg=COLORS["text"])

    def _on_mousewheel(self, event: tk.Event) -> None:
        self._chat_widget.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _on_send_click(self) -> None:
        if self._is_answering:
            self._answer_cancelled = True
        else:
            self._answer_question()

    # ── Conversation management ───────────────────────

    def _new_conversation(self) -> None:
        if self._thinking_id:
            try:
                self._parent.after_cancel(self._thinking_id)
            except Exception:
                pass
            self._thinking_id = None
        if self._is_answering:
            self._answer_cancelled = True
        self._is_answering = False
        self._stream_buffer = ""
        self._first_chunk = True
        self._thinking_pos = None
        self._ai_start_pos = None
        self._welcome_shown = True
        self.send_btn.config(text="\u25B6 发送", bg=COLORS["primary"])

        conv_id = _next_conv_id()
        self._conversations[conv_id] = {
            "title": "新对话",
            "messages": [],
            "history": [],
            "attached_doc": None,
        }
        self._active_conv_id = conv_id
        self._attached_doc = None
        self._sync_listbox()
        self._chat_widget.config(state="normal")
        self._chat_widget.delete("1.0", "end")
        self._show_welcome()

    def _on_conv_select(self, _: tk.Event = None) -> None:
        if self._is_answering:
            return
        sel = self._conv_listbox.curselection()
        if not sel:
            return
        conv_ids = list(self._conversations.keys())
        idx = sel[0]
        if idx >= len(conv_ids):
            return
        conv_id = conv_ids[idx]
        if conv_id == self._active_conv_id:
            return

        self._save_current_messages()
        self._active_conv_id = conv_id
        self._load_conv_messages(conv_id)

    def _sync_listbox(self) -> None:
        self._conv_listbox.delete(0, tk.END)
        for cid, conv in self._conversations.items():
            title = conv["title"]
            icon = "\U0001F4AC" if cid == self._active_conv_id else "\U0001F4DD"
            self._conv_listbox.insert(tk.END, f"  {icon}  {title}")

    def _save_current_messages(self) -> None:
        if not self._active_conv_id:
            return
        conv = self._conversations.get(self._active_conv_id)
        if conv is None:
            return
        if conv["messages"] and conv["messages"][-1]["role"] == "assistant":
            if self._ai_start_pos:
                current_text = self._chat_widget.get(self._ai_start_pos, "end-1c")
                if current_text.strip():
                    conv["messages"][-1]["text"] = current_text

    def _load_conv_messages(self, conv_id: str) -> None:
        self._first_chunk = True
        self._thinking_pos = None
        self._ai_start_pos = None
        conv = self._conversations.get(conv_id)
        if conv is None:
            return

        self._attached_doc = conv.get("attached_doc")

        self._chat_widget.config(state="normal")
        self._chat_widget.delete("1.0", "end")

        if not conv["messages"]:
            self._show_welcome()
            self._chat_widget.config(state="disabled")
            return

        for i, msg in enumerate(conv["messages"]):
            role = msg.get("role", "")
            text = msg.get("text", "")
            if role == "user":
                q_num = (i // 2) + 1
                self._chat_widget.insert("end", f"问题{q_num}  ", "user_label")
                self._chat_widget.insert("end", f"\n{text}\n", "user")
            elif role == "assistant":
                if text:
                    self._chat_widget.insert("end", "知识库+：\n", "ai_name")
                    self._chat_widget.insert("end", text + "\n", "ai")

        self._chat_widget.config(state="disabled")
        self._chat_widget.see("end")

    # ── Answer flow ───────────────────────────────────

    @staticmethod
    def _format_text(text: str) -> str:
        t = text
        t = re.sub(r'^#{1,6}\s*', '', t, flags=re.MULTILINE)
        t = re.sub(r'\*\*(.+?)\*\*', r'\1', t)
        t = re.sub(r'\*(.+?)\*', r'\1', t)
        t = re.sub(r'^-\s+', '• ', t, flags=re.MULTILINE)
        t = re.sub(r'\n{3,}', '\n\n', t)
        return t.strip()

    def _answer_question(self) -> None:
        question = self.web_var.get().strip()
        if question in ("", "向 AI 提问..."):
            return

        self.web_entry.delete(0, tk.END)

        if not self._active_conv_id or not self._conversations.get(self._active_conv_id):
            self._new_conversation()

        conv = self._conversations[self._active_conv_id]
        if conv["title"] == "新对话":
            conv["title"] = question[:14] + ("..." if len(question) > 14 else "")
            self._sync_listbox()

        self._is_answering = True
        self._answer_cancelled = False
        self._stream_buffer = ""
        self._first_chunk = True
        self._thinking_count = 0
        self.send_btn.config(text="\u25A0 停止", bg="#EF4444")

        conv["messages"].append({"role": "user", "text": question})

        self._chat_widget.config(state="normal")
        if self._welcome_shown:
            self._chat_widget.delete("1.0", self._welcome_end)
            self._welcome_shown = False
        else:
            self._chat_widget.insert("end", "\n— — —\n", "sep")
        msg_count = sum(1 for m in conv["messages"] if m["role"] == "user")
        self._chat_widget.insert("end", f"问题{msg_count}  ", "user_label")
        self._chat_widget.insert("end", f"\n{question}\n", "user")
        self._chat_widget.insert("end", "知识库+：\n", "ai_name")
        self._thinking_pos = self._chat_widget.index("end-1c")
        self._chat_widget.insert("end", "思考中.", "loading")
        self._chat_widget.config(state="disabled")
        self._chat_widget.see("end")

        self._thinking_id = self._parent.after(300, self._animate_thinking)
        threading.Thread(target=self._call_ai, args=(question,), daemon=True).start()

    def _animate_thinking(self) -> None:
        if not self._is_answering or self._answer_cancelled:
            return
        self._thinking_count += 1
        dots = "." * ((self._thinking_count % 9) + 1)
        try:
            self._chat_widget.config(state="normal")
            if self._thinking_pos:
                self._chat_widget.delete(self._thinking_pos, "end-1c")
            self._chat_widget.insert(self._thinking_pos, f"思考中{dots}", "thinking_text")
            self._chat_widget.config(state="disabled")
        except Exception:
            pass
        self._thinking_id = self._parent.after(300, self._animate_thinking)

    def _truncate_for_model(self, content: str, provider: str) -> str:
        max_tokens = AI_CONFIGS.get(provider, {}).get("max_context_tokens", 4096)
        max_chars = int(max_tokens * 1.5 * 0.8)
        if len(content) > max_chars:
            return content[:max_chars] + f"\n\n...（内容已截断，原文约 {len(content)} 字符）"
        return content

    def _get_provider_config(self) -> dict:
        provider = self._provider
        base = dict(AI_CONFIGS.get(provider, {}))
        custom = self._config.get("ai_custom_config", {}).get(provider, {})
        if isinstance(custom, dict):
            for k, v in custom.items():
                if v:
                    base[k] = v
        return base

    def _call_ai(self, question: str) -> None:
        provider = self._provider
        custom = self._get_provider_config()
        history = None

        conv = self._conversations.get(self._active_conv_id) if self._active_conv_id else None
        if conv and conv.get("history"):
            history = conv["history"].copy()

        # 注入附件文档内容
        doc_content = ""
        if self._attached_doc and self._attached_doc.get("structured_content"):
            doc_content = self._truncate_for_model(
                self._attached_doc["structured_content"], provider
            )
            if "【上传文档】" not in question:
                fname = self._attached_doc.get("filename", "文档")
                question = f"【上传文档：{fname}】\n{question}"

        def stream_cb(text: str) -> None:
            if self._answer_cancelled:
                return
            self._parent.after(0, lambda: self._stream_update(text))

        cancelled = lambda: self._answer_cancelled

        try:
            if provider == "ollama":
                result = call_ollama(
                    question, doc_content, "",
                    stream_callback=stream_cb,
                    cancelled_flag=cancelled,
                    history=history,
                    custom_config=custom,
                )
            elif provider == "zhipu_cloud":
                key = custom.get("api_key", "") or self._api_key
                result = call_zhipu_websearch(
                    question, doc_content, "", key,
                    stream_callback=stream_cb,
                    cancelled_flag=cancelled,
                    history=history,
                    custom_config=custom,
                )
            elif provider in ("deepseek_api", "sensenova"):
                key = custom.get("api_key", "") or self._api_key
                result = call_openai_compat(
                    provider, question, doc_content, "",
                    api_key=key,
                    stream_callback=stream_cb,
                    cancelled_flag=cancelled,
                    history=history,
                    custom_config=custom,
                )
            else:
                result = "请先在设置中选择一个可用的AI服务"

            if result:
                self._parent.after(0, lambda: self._finalize_answer(result, question=question))
        except Exception as e:
            self._parent.after(0, lambda: self._finalize_answer(
                f"[错误] AI调用失败: {e}", question=question,
            ))

    def _stream_update(self, text: str) -> None:
        if self._answer_cancelled:
            return
        try:
            self._chat_widget.config(state="normal")
            if self._first_chunk:
                if self._thinking_id:
                    try:
                        self._parent.after_cancel(self._thinking_id)
                    except Exception:
                        pass
                    self._thinking_id = None
                if self._thinking_pos:
                    self._chat_widget.delete(self._thinking_pos, "end-1c")
                    self._thinking_pos = None
                self._ai_start_pos = self._chat_widget.index("end-1c")
                clean = self._format_text(text)
                self._chat_widget.insert(self._ai_start_pos, clean + "\n", "ai")
                self._stream_buffer = text
                self._first_chunk = False
            else:
                self._chat_widget.delete(self._ai_start_pos, "end-1c")
                clean = self._format_text(text)
                self._chat_widget.insert(self._ai_start_pos, clean + "\n", "ai")
                self._stream_buffer = text

            self._chat_widget.config(state="disabled")
            self._chat_widget.see("end")
        except Exception:
            pass

    def _finalize_answer(self, text: str, question: str = "") -> None:
        self._is_answering = False
        self.send_btn.config(text="\u25B6 发送", bg=COLORS["primary"])

        if self._thinking_id:
            try:
                self._parent.after_cancel(self._thinking_id)
            except Exception:
                pass
            self._thinking_id = None

        if not self._first_chunk:
            try:
                self._chat_widget.config(state="normal")
                if self._ai_start_pos:
                    clean = self._format_text(text)
                    self._chat_widget.delete(self._ai_start_pos, "end-1c")
                    self._chat_widget.insert(self._ai_start_pos, clean + "\n", "ai")
                self._chat_widget.config(state="disabled")
            except Exception:
                pass
        elif text and "[错误]" not in text:
            try:
                self._chat_widget.config(state="normal")
                clean = self._format_text(text)
                self._chat_widget.insert("end", "知识库+：\n", "ai_name")
                self._chat_widget.insert("end", clean + "\n", "ai")
                self._chat_widget.config(state="disabled")
            except Exception:
                pass

        if text and "[错误]" not in text and self._active_conv_id:
            conv = self._conversations.get(self._active_conv_id)
            if conv:
                clean = self._format_text(text)
                conv["messages"].append({"role": "assistant", "text": clean})
                conv["history"].append({"role": "user", "content": question})
                conv["history"].append({"role": "assistant", "content": clean[:2000]})
                if len(conv["history"]) > 12:
                    conv["history"] = conv["history"][2:]