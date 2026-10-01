"""A small native startup window; no WebView or app-core import required."""

from __future__ import annotations

import os
import threading
from collections.abc import Callable
from types import SimpleNamespace


class StartupCancelled(Exception):
    pass


class StartupWindow:
    def __init__(self, log: Callable[[str], None] = lambda _message: None):
        self.log = log
        self.cancelled = threading.Event()
        self._close = threading.Event()
        self._activate = threading.Event()
        self._ready = threading.Event()
        self.events = SimpleNamespace(shown=self._ready)
        self._message = "正在检查安装文件，请稍后…"
        self._thread = None
        self._form = None

    def update(self, message: str) -> None:
        self._message = message
        self.log(f"startup check: {message}")

    def start(self) -> None:
        if os.name != "nt":
            return
        try:
            import clr

            clr.AddReference("System.Windows.Forms")
            clr.AddReference("System.Drawing")
            from System.Threading import ApartmentState, Thread, ThreadStart

            self._thread = Thread(ThreadStart(self._run))
            self._thread.IsBackground = True
            self._thread.SetApartmentState(ApartmentState.STA)
            self._thread.Start()
            # Native UI failure must never become an application-start blocker.
            self._ready.wait(3)
        except Exception as error:
            self._ready.set()
            self.log(f"startup window unavailable: {type(error).__name__}: {error}")

    def _run(self) -> None:
        form = timer = None
        try:
            from System.Drawing import ColorTranslator, Font, FontStyle, Point, Size
            from System.Windows.Forms import (
                Application, Form, FormBorderStyle, FormStartPosition, Label, Timer,
                FormWindowState,
            )

            Application.EnableVisualStyles()
            form = Form()
            self._form = form
            form.Text = "Yanami Sub · 准备启动"
            form.ClientSize = Size(460, 166)
            form.FormBorderStyle = FormBorderStyle.FixedDialog
            form.StartPosition = FormStartPosition.CenterScreen
            form.MaximizeBox = form.MinimizeBox = False
            form.BackColor = ColorTranslator.FromHtml("#F2F3F5")
            form.ForeColor = ColorTranslator.FromHtml("#1A1A1E")

            def label(text, x, y, width, height, size, bold=False):
                control = Label()
                control.Text = text
                control.Location = Point(x, y)
                control.Size = Size(width, height)
                control.Font = Font("Segoe UI", size, FontStyle.Bold if bold else FontStyle.Regular)
                form.Controls.Add(control)
                return control

            label("Yanami Sub", 24, 20, 412, 30, 16, True)
            status = label(self._message, 24, 66, 412, 44, 10)
            caption = label("仅检测本机环境，不会请求模型或消耗额度。", 24, 126, 412, 24, 9)
            caption.ForeColor = ColorTranslator.FromHtml("#686B73")

            def tick(_sender, _event):
                if self._close.is_set():
                    form.Close()
                    return
                status.Text = self._message
                if self._activate.is_set():
                    self._activate.clear()
                    form.WindowState = FormWindowState.Normal
                    form.Show()
                    form.Activate()

            def closed(_sender, _event):
                if not self._close.is_set():
                    self.cancelled.set()

            form.Shown += lambda _sender, _event: self._ready.set()
            form.FormClosed += closed
            timer = Timer()
            timer.Interval = 100
            timer.Tick += tick
            timer.Start()
            Application.Run(form)
        except Exception as error:
            self.log(f"startup window failed: {type(error).__name__}: {error}")
        finally:
            self._ready.set()
            if timer is not None:
                timer.Dispose()
            if form is not None:
                form.Dispose()
            self._form = None

    def show(self) -> None:
        self._activate.set()

    def restore(self) -> None:
        self.show()

    def close(self) -> None:
        self._close.set()

    def check_cancelled(self) -> None:
        if self.cancelled.is_set():
            raise StartupCancelled()
