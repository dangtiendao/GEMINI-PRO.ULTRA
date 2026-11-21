#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Giao diện đồ họa (Tkinter) điều khiển bộ công cụ Google AI Pro/Ultra."""
import json
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

BASE = Path(__file__).resolve().parent
REPORT_DIR = BASE / "ultra0-report"
NO_WINDOW_FLAGS = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


class UltraApp(tk.Tk):
    """Cửa sổ chính quản lý môi trường, chạy các bước và xem báo cáo."""

    def __init__(self):
        super().__init__()
        self.title("Google AI Pro / Ultra — Bảng điều khiển")

        self.proc: subprocess.Popen | None = None
        self.log_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self.running = False
        self.details_visible = True

        self._setup_style()
        self._build_ui()
        self.update_idletasks()

        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        self.max_w = max(860, screen_w - 40)
        self.max_h = max(540, screen_h - 80)

        controls_w = self.left_inner.winfo_reqwidth() + 28
        controls_h = self.left_inner.winfo_reqheight() + self.hdr_frame.winfo_reqheight() + self.bar_frame.winfo_reqheight() + 44
        self.collapsed_w = min(max(900, controls_w), self.max_w)
        self.expanded_w = min(max(1380, self.collapsed_w + 460), self.max_w)
        self.default_h = min(max(680, controls_h), self.max_h)

        self.geometry(f"{self.expanded_w}x{self.default_h}")
        self.minsize(min(820, self.max_w), min(500, self.max_h))
        self.after(50, self._init_pane_sash)
        self.after(80, self._poll_queue)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _setup_style(self):
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("Title.TLabel", font=("Segoe UI", 13, "bold"))
        style.configure("Section.TLabelframe.Label", font=("Segoe UI", 9, "bold"))
        style.configure("Accent.TButton", font=("Segoe UI", 9, "bold"))

    def _build_ui(self):
        self.root_frame = ttk.Frame(self, padding=10)
        self.root_frame.pack(fill=tk.BOTH, expand=True)

        # Header
        self.hdr_frame = ttk.Frame(self.root_frame)
        self.hdr_frame.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(self.hdr_frame, text="Google AI Pro (5TB) / Ultra — Điều khiển 1 chạm", style="Title.TLabel").pack(side=tk.LEFT)
        self.status_var = tk.StringVar(value="Sẵn sàng")
        ttk.Label(self.hdr_frame, textvariable=self.status_var, foreground="#1f6feb").pack(side=tk.RIGHT)

        # Compact status & controls bar (always visible at bottom)
        self.bar_frame = ttk.LabelFrame(self.root_frame, text="Trạng thái & Điều khiển", padding=8, style="Section.TLabelframe")
        self.bar_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(8, 0))

        self.progress = ttk.Progressbar(self.bar_frame, mode="indeterminate", length=140)
        self.progress.pack(side=tk.LEFT, padx=(0, 8))

        self.last_line_var = tk.StringVar(value="Chưa có tác vụ nào đang chạy.")
        ttk.Label(self.bar_frame, textvariable=self.last_line_var, width=48, anchor="w").pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))

        self.enter_btn = ttk.Button(self.bar_frame, text="Gửi Enter (Tiếp tục)", command=self._send_enter, state=tk.DISABLED)
        self.enter_btn.pack(side=tk.LEFT, padx=(0, 6))
        self.stop_btn = ttk.Button(self.bar_frame, text="Dừng tác vụ", command=self._stop_proc, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=(0, 6))
        self.toggle_btn = ttk.Button(self.bar_frame, text="Ẩn chi tiết / Báo cáo", command=self._toggle_details)
        self.toggle_btn.pack(side=tk.RIGHT)

        # Main 2-pane workspace: Left (scrollable controls) + Right (Log & Report Notebook)
        self.main_pane = ttk.PanedWindow(self.root_frame, orient=tk.HORIZONTAL)
        self.main_pane.pack(fill=tk.BOTH, expand=True)

        self.left_container = ttk.Frame(self.main_pane)
        self.left_canvas = tk.Canvas(self.left_container, highlightthickness=0, borderwidth=0)
        self.left_vscroll = ttk.Scrollbar(self.left_container, orient=tk.VERTICAL, command=self.left_canvas.yview)
        self.left_inner = ttk.Frame(self.left_canvas)

        self.left_inner_id = self.left_canvas.create_window((0, 0), window=self.left_inner, anchor="nw")
        self.left_canvas.configure(yscrollcommand=self.left_vscroll.set)

        self.left_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.left_vscroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.left_inner.bind("<Configure>", self._on_left_inner_configure)
        self.left_canvas.bind("<Configure>", self._on_left_canvas_configure)
        self.left_canvas.bind("<Enter>", lambda _e: self.left_canvas.bind_all("<MouseWheel>", self._on_left_mousewheel))
        self.left_canvas.bind("<Leave>", lambda _e: self.left_canvas.unbind_all("<MouseWheel>"))

        # Top columns: Left (Quick actions) + Right (Custom run)
        top = ttk.Frame(self.left_inner)
        top.pack(fill=tk.X, pady=(0, 8))
        top.columnconfigure(0, weight=1)
        top.columnconfigure(1, weight=1)

        self._build_quick_panel(top)
        self._build_custom_panel(top)
        self._build_payments_auth_panel(self.left_inner)
        self._build_shared_card_panel(self.left_inner)

        # Right pane: Notebook (Log & Report)
        self.nb = ttk.Notebook(self.main_pane)
        log_tab = ttk.Frame(self.nb, padding=6)
        rep_tab = ttk.Frame(self.nb, padding=6)
        self.nb.add(log_tab, text="Nhật ký chi tiết")
        self.nb.add(rep_tab, text="Báo cáo (ultra0-report)")

        self._build_log_tab(log_tab)
        self._build_report_tab(rep_tab)

        self.main_pane.add(self.left_container, weight=3)
        self.main_pane.add(self.nb, weight=2)

    def _build_quick_panel(self, parent):
        box = ttk.LabelFrame(parent, text="Thao tác nhanh (Môi trường, Pro 5TB & Ultra)", padding=8, style="Section.TLabelframe")
        box.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        for c in range(2):
            box.columnconfigure(c, weight=1)

        actions = [
            ("Cài đặt môi trường", self._act_setup_env, 0, 0),
            ("0. Kiểm tra môi trường", self._act_check_env, 0, 1),
            ("1. Xem danh sách Offer", self._act_list_offers, 1, 0),
            ("2. Pro 12 tháng (Bước 1)", lambda: self._run_pro("pro12", stack=False), 1, 1),
            ("3. Pro +6 tháng (Bước 2)", lambda: self._run_pro("pro6", stack=True), 2, 0),
            ("4. Pro +6 tháng (Bước 3)", lambda: self._run_pro("pro6b", stack=True), 2, 1),
            ("5. Pro Dự phòng (+6 tháng)", lambda: self._run_pro("pro6c", stack=True), 3, 0),
            ("Mở Gói đăng ký (Thiết bị)", self._act_open_subs_device, 3, 1),
            ("6. Ultra 30TB -90% ($19.99 x 3T)", lambda: self._run_pro("ultra30_90p", stack=False), 4, 0),
            ("7. Ultra 20TB -90% ($9.99 x 3T)", lambda: self._run_pro("ultra20_90p", stack=False), 4, 1),
            ("EFT 15 tháng (eft15)", lambda: self._run_pro("eft15", stack=False), 5, 0),
            ("EFT +3 tháng (eft3)", lambda: self._run_pro("eft3", stack=True), 5, 1),
            ("Ultra 30TB -90% x3T (acq)", lambda: self._run_pro("u30_3m_90p", stack=False), 6, 0),
            ("Ultra 30TB -90% x1T (acq)", lambda: self._run_pro("u30_1m_90p", stack=False), 6, 1),
            ("Ultra 20TB -90% x3T", lambda: self._run_pro("u20_3m_90p", stack=False), 7, 0),
            ("Ultra 20TB -90% x3T (acq)", lambda: self._run_pro("u20_3m_90p_acq", stack=False), 7, 1),
            ("Quét 20TB giảm giá", lambda: self._run_pro("u20_discount", stack=False), 8, 0),
            ("Quét 30TB giảm giá", lambda: self._run_pro("u30_discount", stack=False), 8, 1),
            ("Tra SKU 20TB / 30TB", self._act_query_ultra_skus, 9, 0),
            ("Đóng hồ sơ thanh toán (Thiết bị)", self._act_open_payments_device, 10, 0),
        ]
        self.action_buttons: list[ttk.Button] = []
        for label, cmd, r, c in actions:
            btn = ttk.Button(box, text=label, command=cmd)
            span = 2 if r in (9, 10) else 1
            btn.grid(row=r, column=c, columnspan=span, sticky="ew", padx=3, pady=3)
            self.action_buttons.append(btn)

    def _build_custom_panel(self, parent):
        box = ttk.LabelFrame(parent, text="Chạy tùy chỉnh / Hàng loạt / Tra SKU", padding=8, style="Section.TLabelframe")
        box.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        box.columnconfigure(1, weight=1)

        self.mode_var = tk.StringVar(value="device")
        modes = ttk.Frame(box)
        modes.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 4))
        ttk.Radiobutton(modes, text="Thiết bị hiện tại", variable=self.mode_var, value="device", command=self._sync_inputs).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Radiobutton(modes, text="1 tài khoản", variable=self.mode_var, value="single", command=self._sync_inputs).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Radiobutton(modes, text="File accounts.txt", variable=self.mode_var, value="file", command=self._sync_inputs).pack(side=tk.LEFT)

        ttk.Label(box, text="Tài khoản / File:").grid(row=1, column=0, sticky="w", pady=2)
        self.target_var = tk.StringVar(value="current@device")
        self.target_entry = ttk.Entry(box, textvariable=self.target_var)
        self.target_entry.grid(row=1, column=1, sticky="ew", padx=4, pady=2)
        self.browse_btn = ttk.Button(box, text="Chọn file…", command=self._browse_file, width=10)
        self.browse_btn.grid(row=1, column=2, pady=2)

        ttk.Label(box, text="Gói (--plan):").grid(row=2, column=0, sticky="w", pady=2)
        self.plan_var = tk.StringVar(value="pro12")
        plan_cb = ttk.Combobox(
            box, textvariable=self.plan_var, state="readonly",
            values=[
                "pro12", "pro6", "pro6b", "pro6c",
                "eft15", "eft12", "eft6", "eft4", "eft3", "eft2", "eft1",
                "ultra30_90p", "ultra20_90p",
                "u30_3m_90p", "u30_1m_90p",
                "u20_3m_90p", "u20_3m_90p_acq",
                "u20_discount", "u30_discount",
                "auto", "5x", "20x",
            ], width=18,
        )
        plan_cb.grid(row=2, column=1, sticky="w", padx=4, pady=2)

        ttk.Label(box, text="Offer Token:").grid(row=3, column=0, sticky="w", pady=2)
        self.offer_token_var = tk.StringVar()
        ttk.Entry(box, textvariable=self.offer_token_var).grid(row=3, column=1, columnspan=2, sticky="ew", padx=4, pady=2)

        ttk.Label(box, text="Old Token (--old-token):").grid(row=4, column=0, sticky="w", pady=2)
        self.old_token_var = tk.StringVar()
        ttk.Entry(box, textvariable=self.old_token_var).grid(row=4, column=1, columnspan=2, sticky="ew", padx=4, pady=2)

        flags = ttk.Frame(box)
        flags.grid(row=5, column=0, columnspan=3, sticky="ew", pady=4)
        self.no_add_var = tk.BooleanVar(value=True)
        self.force_var = tk.BooleanVar(value=True)
        self.stack_var = tk.BooleanVar(value=False)
        self.list_only_var = tk.BooleanVar(value=False)
        self.discount_var = tk.BooleanVar(value=False)
        self.open_payments_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(flags, text="--no-add", variable=self.no_add_var).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Checkbutton(flags, text="--force", variable=self.force_var).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Checkbutton(flags, text="--stack", variable=self.stack_var).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Checkbutton(flags, text="--list", variable=self.list_only_var).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Checkbutton(flags, text="--discount (giảm giá)", variable=self.discount_var).pack(side=tk.LEFT)

        extra_flags = ttk.Frame(box)
        extra_flags.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(0, 4))
        ttk.Checkbutton(
            extra_flags,
            text="Mở trang đóng hồ sơ thanh toán trên thiết bị sau khi chạy",
            variable=self.open_payments_var,
        ).pack(side=tk.LEFT)

        run_row = ttk.Frame(box)
        run_row.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(4, 0))
        self.custom_run_btn = ttk.Button(run_row, text="Chạy tùy chỉnh", style="Accent.TButton", command=self._act_custom_run)
        self.custom_run_btn.pack(side=tk.LEFT, padx=(0, 6))
        self.action_buttons.append(self.custom_run_btn)

        ttk.Label(run_row, text="SKU:").pack(side=tk.LEFT, padx=(8, 4))
        self.sku_var = tk.StringVar(value="g1.2tb.ai.subs_variant")
        sku_cb = ttk.Combobox(
            run_row,
            textvariable=self.sku_var,
            values=[
                "g1.2tb.ai.subs_variant",
                "--ultra",
                "--20tb",
                "--30tb",
                "g1.20tb.3months_ip_90p",
                "g1.20tb.3months_ip_90p.acq",
                "g1.ai.ultra.3months_ip_90p.acq",
                "g1.ai.ultra.1month_ip_90p.acq",
                "g1.play.20tb",
                "g1.20tb",
                "g1.play.ai.pro",
                "g1.ai.pro",
            ],
            width=26,
        )
        sku_cb.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
        self.sku_btn = ttk.Button(run_row, text="Tra SKU", command=self._act_query_sku)
        self.sku_btn.pack(side=tk.LEFT)
        self.action_buttons.append(self.sku_btn)

        self._sync_inputs()

    def _build_payments_auth_panel(self, parent):
        box = ttk.LabelFrame(
            parent,
            text="Tài khoản thiết bị (Đăng nhập / Đăng xuất / Đóng hồ sơ thanh toán)",
            padding=8,
            style="Section.TLabelframe",
        )
        box.pack(fill=tk.X, pady=(0, 6))
        box.columnconfigure(1, weight=2)
        box.columnconfigure(3, weight=1)
        box.columnconfigure(5, weight=1)

        ttk.Label(box, text="Tài khoản (Email):").grid(row=0, column=0, sticky="w", padx=(0, 4))
        self.pay_email_var = tk.StringVar()
        ttk.Entry(box, textvariable=self.pay_email_var).grid(row=0, column=1, sticky="ew", padx=(0, 10))

        ttk.Label(box, text="Mật khẩu:").grid(row=0, column=2, sticky="w", padx=(0, 4))
        self.pay_pass_var = tk.StringVar()
        ttk.Entry(box, textvariable=self.pay_pass_var, show="*").grid(row=0, column=3, sticky="ew", padx=(0, 10))

        ttk.Label(box, text="2FA (nếu có):").grid(row=0, column=4, sticky="w", padx=(0, 4))
        self.pay_totp_var = tk.StringVar()
        ttk.Entry(box, textvariable=self.pay_totp_var).grid(row=0, column=5, sticky="ew")

        btn_row = ttk.Frame(box)
        btn_row.grid(row=1, column=0, columnspan=6, sticky="ew", pady=(6, 0))
        self.add_acc_btn = ttk.Button(
            btn_row,
            text="Đăng nhập / Thêm acc vào thiết bị",
            command=self._act_add_account_device,
        )
        self.add_acc_btn.pack(side=tk.LEFT, padx=(0, 8))
        self.action_buttons.append(self.add_acc_btn)

        self.rem_acc_btn = ttk.Button(
            btn_row,
            text="Đăng xuất / Xóa acc khỏi thiết bị",
            command=self._act_remove_account_device,
        )
        self.rem_acc_btn.pack(side=tk.LEFT)
        self.action_buttons.append(self.rem_acc_btn)

    def _build_shared_card_panel(self, parent):
        box = ttk.LabelFrame(
            parent,
            text="Thẻ thanh toán dùng chung (khi danh sách acc không kèm thẻ)",
            padding=8,
            style="Section.TLabelframe",
        )
        box.pack(fill=tk.X, pady=(0, 6))
        box.columnconfigure(1, weight=2)
        box.columnconfigure(3, weight=1)
        box.columnconfigure(5, weight=1)
        box.columnconfigure(7, weight=1)
        box.columnconfigure(9, weight=1)

        self.card_mode_var = tk.StringVar(value="none")
        top_row = ttk.Frame(box)
        top_row.grid(row=0, column=0, columnspan=10, sticky="ew", pady=(0, 4))
        ttk.Radiobutton(top_row, text="Không gắn thẻ", variable=self.card_mode_var, value="none", command=self._sync_card_inputs).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Radiobutton(top_row, text="Nhập thẻ trực tiếp", variable=self.card_mode_var, value="input", command=self._sync_card_inputs).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Radiobutton(top_row, text="Từ file thẻ (card.txt)", variable=self.card_mode_var, value="file", command=self._sync_card_inputs).pack(side=tk.LEFT)

        ttk.Label(box, text="Số thẻ:").grid(row=1, column=0, sticky="w", padx=(0, 4))
        self.card_num_var = tk.StringVar()
        self.card_num_entry = ttk.Entry(box, textvariable=self.card_num_var)
        self.card_num_entry.grid(row=1, column=1, sticky="ew", padx=(0, 8))

        ttk.Label(box, text="MM/YY:").grid(row=1, column=2, sticky="w", padx=(0, 4))
        self.card_exp_var = tk.StringVar()
        self.card_exp_entry = ttk.Entry(box, textvariable=self.card_exp_var, width=8)
        self.card_exp_entry.grid(row=1, column=3, sticky="ew", padx=(0, 8))

        ttk.Label(box, text="CVC:").grid(row=1, column=4, sticky="w", padx=(0, 4))
        self.card_cvc_var = tk.StringVar()
        self.card_cvc_entry = ttk.Entry(box, textvariable=self.card_cvc_var, width=6)
        self.card_cvc_entry.grid(row=1, column=5, sticky="ew", padx=(0, 8))

        ttk.Label(box, text="Chủ thẻ:").grid(row=1, column=6, sticky="w", padx=(0, 4))
        self.card_holder_var = tk.StringVar()
        self.card_holder_entry = ttk.Entry(box, textvariable=self.card_holder_var, width=14)
        self.card_holder_entry.grid(row=1, column=7, sticky="ew", padx=(0, 8))

        ttk.Label(box, text="ZIP:").grid(row=1, column=8, sticky="w", padx=(0, 4))
        self.card_zip_var = tk.StringVar(value="97201")
        self.card_zip_entry = ttk.Entry(box, textvariable=self.card_zip_var, width=8)
        self.card_zip_entry.grid(row=1, column=9, sticky="ew")

        file_row = ttk.Frame(box)
        file_row.grid(row=2, column=0, columnspan=10, sticky="ew", pady=(6, 0))
        file_row.columnconfigure(1, weight=1)
        ttk.Label(file_row, text="File thẻ:").grid(row=0, column=0, sticky="w", padx=(0, 6))
        self.card_file_var = tk.StringVar(value="card.txt")
        self.card_file_entry = ttk.Entry(file_row, textvariable=self.card_file_var)
        self.card_file_entry.grid(row=0, column=1, sticky="ew", padx=(0, 6))
        self.card_browse_btn = ttk.Button(file_row, text="Chọn file…", command=self._browse_card_file, width=10)
        self.card_browse_btn.grid(row=0, column=2)

        self.card_input_widgets = [
            self.card_num_entry, self.card_exp_entry, self.card_cvc_entry,
            self.card_holder_entry, self.card_zip_entry,
        ]
        self._sync_card_inputs()

    def _build_log_tab(self, parent):
        ctrl = ttk.Frame(parent)
        ctrl.pack(fill=tk.X, pady=(0, 4))
        ttk.Button(ctrl, text="Xóa nhật ký", command=self._clear_log).pack(side=tk.RIGHT)

        self.log_text = scrolledtext.ScrolledText(
            parent, wrap=tk.WORD, font=("Consolas", 9),
            width=54, height=20,
            bg="#11161d", fg="#e6edf3", insertbackground="#e6edf3",
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)
        self.log_text.configure(state=tk.DISABLED)

    def _build_report_tab(self, parent):
        top = ttk.Frame(parent)
        top.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(top, text="File báo cáo:").pack(side=tk.LEFT, padx=(0, 6))
        self.report_var = tk.StringVar()
        self.report_cb = ttk.Combobox(top, textvariable=self.report_var, state="readonly", width=36)
        self.report_cb.pack(side=tk.LEFT, padx=(0, 6))
        self.report_cb.bind("<<ComboboxSelected>>", lambda _e: self._load_selected_report())
        ttk.Button(top, text="Làm mới", command=self._refresh_reports).pack(side=tk.LEFT)

        self.report_text = scrolledtext.ScrolledText(
            parent, wrap=tk.WORD, font=("Consolas", 9),
            width=54, height=20,
            bg="#11161d", fg="#d2e0f0",
        )
        self.report_text.pack(fill=tk.BOTH, expand=True)
        self.report_text.configure(state=tk.DISABLED)
        self._refresh_reports()

    def _on_left_inner_configure(self, _event=None):
        self.left_canvas.configure(scrollregion=self.left_canvas.bbox("all"))

    def _on_left_canvas_configure(self, event):
        self.left_canvas.itemconfigure(self.left_inner_id, width=event.width)

    def _on_left_mousewheel(self, event):
        if self.left_inner.winfo_reqheight() > self.left_canvas.winfo_height():
            self.left_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _init_pane_sash(self):
        if not self.details_visible:
            return
        total_w = self.main_pane.winfo_width()
        if total_w > 200:
            sash_x = min(max(760, self.collapsed_w - 40), int(total_w * 0.62))
            self.main_pane.sashpos(0, sash_x)

    def _toggle_details(self):
        self.details_visible = not self.details_visible
        cur_h = min(max(self.winfo_height(), self.default_h), self.max_h)
        if self.details_visible:
            if str(self.nb) not in self.main_pane.panes():
                self.main_pane.add(self.nb, weight=2)
            self.toggle_btn.configure(text="Ẩn chi tiết / Báo cáo")
            target_w = min(max(self.winfo_width(), self.expanded_w), self.max_w)
            self.geometry(f"{target_w}x{cur_h}")
            self.after(30, self._init_pane_sash)
        else:
            if str(self.nb) in self.main_pane.panes():
                self.main_pane.forget(self.nb)
            self.toggle_btn.configure(text="Hiện chi tiết / Báo cáo")
            self.geometry(f"{self.collapsed_w}x{cur_h}")

    # ---------- Input & Button state ----------
    def _sync_inputs(self):
        m = self.mode_var.get()
        if m == "device":
            self.target_var.set("current@device")
            self.target_entry.configure(state="disabled")
            self.browse_btn.configure(state="disabled")
            self.no_add_var.set(True)
            self.force_var.set(True)
        elif m == "single":
            if self.target_var.get() == "current@device":
                self.target_var.set("")
            self.target_entry.configure(state="normal")
            self.browse_btn.configure(state="disabled")
            self.no_add_var.set(False)
            self.force_var.set(False)
        else:
            if self.target_var.get() == "current@device":
                self.target_var.set("accounts.txt")
            self.target_entry.configure(state="normal")
            self.browse_btn.configure(state="normal")
            self.no_add_var.set(False)
            self.force_var.set(False)

    def _sync_card_inputs(self):
        cm = self.card_mode_var.get()
        in_state = "normal" if cm == "input" else "disabled"
        file_state = "normal" if cm == "file" else "disabled"
        for w in self.card_input_widgets:
            w.configure(state=in_state)
        self.card_file_entry.configure(state=file_state)
        self.card_browse_btn.configure(state=file_state)

    def _browse_card_file(self):
        p = filedialog.askopenfilename(
            initialdir=str(BASE),
            title="Chọn file thẻ thanh toán",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if p:
            self.card_file_var.set(p)

    def _browse_file(self):
        p = filedialog.askopenfilename(
            initialdir=str(BASE),
            title="Chọn file tài khoản",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if p:
            self.target_var.set(p)

    def _set_running(self, running: bool, label: str = "Sẵn sàng"):
        self.running = running
        self.status_var.set(label)
        state = tk.DISABLED if running else tk.NORMAL
        for btn in self.action_buttons:
            btn.configure(state=state)
        self.stop_btn.configure(state=tk.NORMAL if running else tk.DISABLED)
        self.enter_btn.configure(state=tk.NORMAL if running else tk.DISABLED)
        if running:
            self.progress.start(12)
        else:
            self.progress.stop()

    # ---------- Actions ----------
    def _act_setup_env(self):
        self._start_cmd([sys.executable, "-u", "setup_env.py"], "Đang cài đặt môi trường…")

    def _act_check_env(self):
        self._start_cmd([sys.executable, "-u", "ultra0.py", "--check"], "Đang kiểm tra môi trường…")

    def _act_list_offers(self):
        self._start_cmd(
            [sys.executable, "-u", "ultra0.py", "--account", "current@device", "--no-add", "--force", "--list", "--plan", "pro12"],
            "Đang liệt kê offer Pro 5TB…",
        )

    def _append_payments_auth_args(self, cmd: list[str]):
        email = self.pay_email_var.get().strip()
        pw = self.pay_pass_var.get()
        totp_sec = self.pay_totp_var.get().strip()
        if email:
            cmd.extend(["--pay-email", email])
        if pw:
            cmd.extend(["--pay-pass", pw])
        if totp_sec:
            cmd.extend(["--pay-totp", totp_sec])

    def _append_token_args(self, cmd: list[str]):
        offer_tok = self.offer_token_var.get().strip()
        old_tok = self.old_token_var.get().strip()
        if offer_tok:
            cmd.extend(["--offer-token", offer_tok])
        if old_tok:
            cmd.extend(["--old-token", old_tok])

    def _run_pro(self, plan: str, stack: bool):
        cmd = [sys.executable, "-u", "ultra0.py", "--account", "current@device", "--no-add", "--force"]
        if stack:
            cmd.append("--stack")
        if self.open_payments_var.get():
            cmd.append("--open-payments-settings")
            self._append_payments_auth_args(cmd)
        self._append_token_args(cmd)
        cmd.extend(["--plan", plan])
        self._start_cmd(cmd, f"Đang chạy {plan}…")

    def _act_custom_run(self):
        mode = self.mode_var.get()
        target = self.target_var.get().strip()
        cmd = [sys.executable, "-u", "ultra0.py"]
        if mode == "device":
            cmd.extend(["--account", "current@device"])
        elif mode == "single":
            if not target:
                messagebox.showwarning("Thiếu thông tin", "Vui lòng nhập tài khoản dạng email:password:totp")
                return
            cmd.extend(["--account", target])
        else:
            if not target or not Path(target).exists():
                messagebox.showwarning("Thiếu file", f"Không tìm thấy file: {target}")
                return
            cmd.append(target)

        if self.no_add_var.get():
            cmd.append("--no-add")
        if self.force_var.get():
            cmd.append("--force")
        if self.stack_var.get():
            cmd.append("--stack")
        if self.list_only_var.get():
            cmd.append("--list")
        if self.discount_var.get():
            cmd.append("--discount")
        if self.open_payments_var.get():
            cmd.append("--open-payments-settings")
            self._append_payments_auth_args(cmd)
        self._append_token_args(cmd)
        cm = self.card_mode_var.get()
        if cm == "input":
            num = self.card_num_var.get().strip()
            if not num:
                messagebox.showwarning("Thiếu số thẻ", "Vui lòng nhập số thẻ hoặc chọn Không gắn thẻ.")
                return
            card_str = "----".join([
                num,
                self.card_exp_var.get().strip(),
                self.card_cvc_var.get().strip(),
                self.card_holder_var.get().strip(),
                self.card_zip_var.get().strip() or "97201",
            ])
            cmd.extend(["--card", card_str])
        elif cm == "file":
            cf = self.card_file_var.get().strip()
            if not cf or not Path(cf).exists():
                messagebox.showwarning("Thiếu file thẻ", f"Không tìm thấy file thẻ: {cf}")
                return
            cmd.extend(["--card-file", cf])
        cmd.extend(["--plan", self.plan_var.get()])
        self._start_cmd(cmd, f"Đang chạy ({self.plan_var.get()})…")

    def _act_query_sku(self):
        skus = self.sku_var.get().split()
        if not skus:
            messagebox.showwarning("Thiếu SKU", "Vui lòng nhập ít nhất 1 mã SKU.")
            return
        self._start_cmd([sys.executable, "-u", "query_sku.py", *skus], f"Đang tra SKU: {' '.join(skus)}…")

    def _act_query_ultra_skus(self):
        self._start_cmd([sys.executable, "-u", "query_sku.py", "--ultra"], "Đang tra toàn bộ SKU 20TB / 30TB…")

    def _act_open_subs_device(self):
        self._start_cmd([sys.executable, "-u", "ultra0.py", "--open-subs"], "Đang mở Gói đăng ký trên thiết bị…")

    def _act_open_payments_device(self):
        cmd = [sys.executable, "-u", "ultra0.py", "--open-payments"]
        self._append_payments_auth_args(cmd)
        self._start_cmd(cmd, "Đang mở cài đặt hồ sơ thanh toán trên thiết bị…")

    def _act_add_account_device(self):
        email = self.pay_email_var.get().strip()
        pw = self.pay_pass_var.get()
        if not email or not pw:
            messagebox.showwarning("Thiếu thông tin", "Vui lòng nhập Tài khoản (Email) và Mật khẩu.")
            return
        cmd = [sys.executable, "-u", "ultra0.py", "--add-only"]
        self._append_payments_auth_args(cmd)
        self._start_cmd(cmd, f"Đang đăng nhập / thêm {email} vào thiết bị…")

    def _act_remove_account_device(self):
        email = self.pay_email_var.get().strip()
        target_label = email if email else "tài khoản Google đang đăng nhập trên thiết bị"
        if not messagebox.askyesno("Xác nhận xóa tài khoản", f"Bạn có chắc muốn đăng xuất / xóa {target_label} khỏi thiết bị không?"):
            return
        cmd = [sys.executable, "-u", "ultra0.py", "--remove-account"]
        if email:
            cmd.extend(["--pay-email", email])
        self._start_cmd(cmd, f"Đang xóa tài khoản khỏi thiết bị…")

    # ---------- Subprocess & Logging ----------
    def _start_cmd(self, cmd: list[str], label: str):
        if self.running:
            messagebox.showinfo("Đang bận", "Đang có tác vụ chạy, vui lòng đợi hoặc bấm Dừng.")
            return
        self._append_log(f"\n$ {' '.join(cmd)}\n")
        self.last_line_var.set(label)
        self._set_running(True, label)

        def worker():
            env = dict(os.environ)
            env["PYTHONIOENCODING"] = "utf-8"
            env["PYTHONUNBUFFERED"] = "1"
            try:
                self.proc = subprocess.Popen(
                    cmd,
                    cwd=str(BASE),
                    env=env,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                    creationflags=NO_WINDOW_FLAGS,
                )
                assert self.proc.stdout is not None
                for line in self.proc.stdout:
                    self.log_queue.put(("log", line))
                rc = self.proc.wait()
                self.log_queue.put(("done", str(rc)))
            except Exception as exc:
                self.log_queue.put(("log", f"\n❌ Lỗi khởi chạy: {exc}\n"))
                self.log_queue.put(("done", "1"))
            finally:
                self.proc = None

        threading.Thread(target=worker, daemon=True).start()

    def _send_enter(self):
        if self.proc and self.proc.stdin:
            try:
                self.proc.stdin.write("\n")
                self.proc.stdin.flush()
                self._append_log("[Đã gửi Enter]\n")
                self.last_line_var.set("Đã gửi xác nhận Enter, đang tiếp tục…")
            except Exception as exc:
                self._append_log(f"[Không gửi được Enter: {exc}]\n")

    def _stop_proc(self):
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
                self._append_log("\n⚠️ Đã gửi yêu cầu dừng tác vụ.\n")
                self.last_line_var.set("Đã dừng tác vụ.")
            except Exception as exc:
                self._append_log(f"\n❌ Lỗi khi dừng: {exc}\n")

    def _poll_queue(self):
        try:
            while True:
                kind, payload = self.log_queue.get_nowait()
                if kind == "log":
                    self._append_log(payload)
                    clean = payload.strip()
                    if clean:
                        self.last_line_var.set(clean[:90])
                elif kind == "done":
                    self._append_log(f"\n[Kết thúc với mã thoát: {payload}]\n")
                    status = "Hoàn tất thành công" if payload == "0" else f"Kết thúc (mã={payload})"
                    self._set_running(False, status)
                    self._refresh_reports()
        except queue.Empty:
            pass
        self.after(80, self._poll_queue)

    def _append_log(self, text: str):
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, text)
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _clear_log(self):
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state=tk.DISABLED)

    # ---------- Reports ----------
    def _refresh_reports(self):
        if not REPORT_DIR.exists():
            self.report_cb["values"] = []
            return
        files = sorted((p.name for p in REPORT_DIR.glob("*.json")), key=str.lower)
        self.report_cb["values"] = files
        if files:
            cur = self.report_var.get()
            if cur not in files:
                self.report_var.set("current.json" if "current.json" in files else files[0])
            self._load_selected_report()

    def _load_selected_report(self):
        name = self.report_var.get()
        if not name:
            return
        path = REPORT_DIR / name
        if not path.exists():
            return
        try:
            raw = path.read_text(encoding="utf-8")
            parsed = json.loads(raw)
            content = json.dumps(parsed, ensure_ascii=False, indent=2)
        except Exception:
            content = path.read_text(encoding="utf-8", errors="replace")
        self.report_text.configure(state=tk.NORMAL)
        self.report_text.delete("1.0", tk.END)
        self.report_text.insert("1.0", content)
        self.report_text.configure(state=tk.DISABLED)

    def _on_close(self):
        if self.proc and self.proc.poll() is None:
            if not messagebox.askyesno("Đang chạy", "Tác vụ vẫn đang chạy. Bạn có muốn dừng và thoát không?"):
                return
            self._stop_proc()
        self.destroy()


if __name__ == "__main__":
    app = UltraApp()
    app.mainloop()
