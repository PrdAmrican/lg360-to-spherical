"""Tkinter drag-and-drop GUI for the LG 360 -> spherical converter.

The conversion runs on a background thread; it communicates with the Tk main
loop through a thread-safe queue that is polled with ``root.after`` (Tkinter is
not thread-safe, so widgets are only ever touched from the main thread).
"""

import os
import queue
import subprocess
import sys
import threading

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD

    _DND_AVAILABLE = True
except Exception:  # noqa: BLE001 - drag-and-drop is optional
    _DND_AVAILABLE = False

from app import __version__, converter, ffmpeg_runner

_SUPPORTED = (".mp4", ".mov")


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("LG 360 CAM -> Spherical 360 Converter")
        self.root.minsize(580, 540)

        self.msg_queue = queue.Queue()
        self.input_path = None
        self.last_output = None
        self.worker = None
        self._indeterminate = False

        self.ffmpeg = ffmpeg_runner.find_ffmpeg()
        self.v360 = ffmpeg_runner.has_v360(self.ffmpeg) if self.ffmpeg else False

        self.file_var = tk.StringVar(value="No file selected")
        self.mode_var = tk.StringVar(value=converter.MODE_REPROJECT)
        self.fov_var = tk.StringVar(value="189")
        self.codec_var = tk.StringVar(value="H.264 (libx264)")
        self.crf_var = tk.StringVar(value="18")
        self.outdir_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="Ready")
        self.show_advanced = tk.BooleanVar(value=False)

        self._build_ui()
        self._apply_capabilities()
        self.root.after(100, self._poll_queue)

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        main = ttk.Frame(self.root, padding=12)
        main.pack(fill="both", expand=True)
        main.columnconfigure(0, weight=1)

        ttk.Label(
            main, text="LG 360 CAM -> Spherical 360 Video",
            font=("Segoe UI", 14, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            main,
            text="Drag an LG 360 CAM .mp4 below, choose a mode, then Convert.",
            foreground="#555555",
        ).grid(row=1, column=0, sticky="w", pady=(0, 10))

        # Drop zone (also clickable to browse).
        self.drop_label = tk.Label(
            main,
            text="\n  Drag a .mp4 / .mov file here  \n\n(or click to browse)\n",
            relief="ridge", borderwidth=2, background="#f2f4f7",
            foreground="#333333", justify="center",
        )
        self.drop_label.grid(row=2, column=0, sticky="ew", ipady=16)
        self.drop_label.bind("<Button-1>", lambda _e: self._browse_input())
        if _DND_AVAILABLE:
            self.drop_label.drop_target_register(DND_FILES)
            self.drop_label.dnd_bind("<<Drop>>", self._on_drop)

        file_row = ttk.Frame(main)
        file_row.grid(row=3, column=0, sticky="ew", pady=(8, 8))
        file_row.columnconfigure(0, weight=1)
        ttk.Label(file_row, textvariable=self.file_var).grid(row=0, column=0, sticky="w")
        ttk.Button(file_row, text="Browse...", command=self._browse_input).grid(row=0, column=1)

        # Mode selection.
        mode_frame = ttk.LabelFrame(main, text="Conversion mode", padding=8)
        mode_frame.grid(row=4, column=0, sticky="ew")
        self.reproject_radio = ttk.Radiobutton(
            mode_frame,
            text="Reproject dual-fisheye -> equirectangular, then add 360 metadata",
            value=converter.MODE_REPROJECT, variable=self.mode_var,
        )
        self.reproject_radio.grid(row=0, column=0, sticky="w")
        ttk.Radiobutton(
            mode_frame,
            text="Add 360 metadata only (video is already equirectangular)",
            value=converter.MODE_METADATA, variable=self.mode_var,
        ).grid(row=1, column=0, sticky="w")

        # Advanced options (collapsible).
        ttk.Checkbutton(
            main, text="Advanced options", variable=self.show_advanced,
            command=self._toggle_advanced,
        ).grid(row=5, column=0, sticky="w", pady=(8, 0))

        self.adv_frame = ttk.Frame(main, padding=(0, 4))
        self.adv_frame.columnconfigure(1, weight=1)
        ttk.Label(self.adv_frame, text="Input FOV (deg):").grid(row=0, column=0, sticky="w")
        ttk.Entry(self.adv_frame, textvariable=self.fov_var, width=8).grid(
            row=0, column=1, sticky="w", pady=2)
        ttk.Label(self.adv_frame, text="Video codec:").grid(row=1, column=0, sticky="w")
        ttk.Combobox(
            self.adv_frame, textvariable=self.codec_var, state="readonly",
            values=["H.264 (libx264)", "HEVC (libx265)"], width=18,
        ).grid(row=1, column=1, sticky="w", pady=2)
        ttk.Label(self.adv_frame, text="Quality (CRF, lower=better):").grid(
            row=2, column=0, sticky="w")
        ttk.Spinbox(self.adv_frame, from_=0, to=51, textvariable=self.crf_var, width=6).grid(
            row=2, column=1, sticky="w", pady=2)
        ttk.Label(self.adv_frame, text="Output folder:").grid(row=3, column=0, sticky="w")
        out_row = ttk.Frame(self.adv_frame)
        out_row.grid(row=3, column=1, sticky="ew", pady=2)
        out_row.columnconfigure(0, weight=1)
        ttk.Entry(out_row, textvariable=self.outdir_var).grid(row=0, column=0, sticky="ew")
        ttk.Button(out_row, text="...", width=3, command=self._browse_outdir).grid(row=0, column=1)

        # Convert / open buttons.
        btn_row = ttk.Frame(main)
        btn_row.grid(row=7, column=0, sticky="ew", pady=(10, 6))
        self.convert_btn = ttk.Button(btn_row, text="Convert", command=self._start_conversion)
        self.convert_btn.grid(row=0, column=0)
        self.open_btn = ttk.Button(
            btn_row, text="Open output folder", command=self._open_output, state="disabled")
        self.open_btn.grid(row=0, column=1, padx=(8, 0))

        # Progress + status.
        self.progress = ttk.Progressbar(main, mode="determinate", maximum=100)
        self.progress.grid(row=8, column=0, sticky="ew")
        ttk.Label(main, textvariable=self.status_var, foreground="#555555").grid(
            row=9, column=0, sticky="w", pady=(4, 8))

        # Log.
        log_frame = ttk.LabelFrame(main, text="Log", padding=4)
        log_frame.grid(row=10, column=0, sticky="nsew")
        main.rowconfigure(10, weight=1)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log_text = tk.Text(
            log_frame, height=8, wrap="word", state="disabled",
            background="#0f111a", foreground="#d6deeb", insertbackground="#d6deeb",
        )
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.log_text.config(yscrollcommand=scroll.set)

    def _toggle_advanced(self):
        if self.show_advanced.get():
            self.adv_frame.grid(row=6, column=0, sticky="ew")
        else:
            self.adv_frame.grid_forget()

    def _apply_capabilities(self):
        self._append_log("LG 360 Spherical Converter v%s" % __version__)
        if self.ffmpeg:
            self._append_log("ffmpeg: " + self.ffmpeg)
        else:
            self._append_log("ffmpeg: NOT FOUND. Only 'metadata only' mode is available.")
        if self.v360:
            self._append_log("v360 filter available - dual-fisheye reprojection enabled.")
            self.mode_var.set(converter.MODE_REPROJECT)
        else:
            self._append_log(
                "v360 filter unavailable - reprojection disabled. Install a full "
                "ffmpeg build on PATH to enable it."
            )
            self.reproject_radio.config(state="disabled")
            self.mode_var.set(converter.MODE_METADATA)

    # -------------------------------------------------------------- inputs
    def _browse_input(self):
        path = filedialog.askopenfilename(
            title="Choose an LG 360 CAM video",
            filetypes=[("Video files", "*.mp4 *.mov"), ("All files", "*.*")],
        )
        if path:
            self._set_input(path)

    def _on_drop(self, event):
        paths = self.root.tk.splitlist(event.data)
        if paths:
            self._set_input(paths[0])

    def _set_input(self, path):
        path = os.path.abspath(path)
        if not os.path.isfile(path):
            messagebox.showerror("Not a file", "Could not read: %s" % path)
            return
        if os.path.splitext(path)[1].lower() not in _SUPPORTED:
            messagebox.showwarning("Unsupported", "Please choose a .mp4 or .mov file.")
            return
        self.input_path = path
        self.file_var.set(path)
        self.status_var.set("Ready")

    def _browse_outdir(self):
        path = filedialog.askdirectory(title="Choose output folder")
        if path:
            self.outdir_var.set(path)

    # ---------------------------------------------------------- conversion
    def _start_conversion(self):
        if self.worker and self.worker.is_alive():
            return
        if not self.input_path:
            messagebox.showwarning("No file", "Please choose an LG 360 CAM .mp4 first.")
            return
        mode = self.mode_var.get()
        if mode == converter.MODE_REPROJECT and not self.v360:
            messagebox.showerror(
                "Reprojection unavailable",
                "The v360 filter is not available in the detected ffmpeg build.\n"
                "Install a full ffmpeg on PATH, or use 'metadata only' mode.",
            )
            return
        try:
            fov = float(self.fov_var.get())
        except ValueError:
            messagebox.showerror("Invalid FOV", "FOV must be a number, e.g. 189.")
            return
        try:
            crf = int(float(self.crf_var.get()))
        except ValueError:
            messagebox.showerror("Invalid CRF", "CRF must be an integer between 0 and 51.")
            return
        vcodec = "libx265" if "265" in self.codec_var.get() else "libx264"
        output_dir = self.outdir_var.get().strip() or None
        options = converter.ConversionOptions(
            mode=mode, fov=fov, vcodec=vcodec, crf=crf, output_dir=output_dir
        )

        self.convert_btn.config(state="disabled")
        self.open_btn.config(state="disabled")
        self.last_output = None
        self._set_progress(0.0, "Starting...")
        self._append_log("--- Converting: %s ---" % self.input_path)

        self.worker = threading.Thread(
            target=self._run_worker, args=(self.input_path, options), daemon=True
        )
        self.worker.start()

    def _run_worker(self, input_path, options):
        def progress_cb(fraction, message):
            self.msg_queue.put(("progress", fraction, message))

        def log(message):
            self.msg_queue.put(("log", message))

        try:
            out = converter.convert(input_path, options, progress_cb=progress_cb, log=log)
            self.msg_queue.put(("done", out))
        except Exception as exc:  # noqa: BLE001 - surface to the UI
            self.msg_queue.put(("error", str(exc)))

    # ------------------------------------------------------- queue polling
    def _poll_queue(self):
        try:
            while True:
                item = self.msg_queue.get_nowait()
                kind = item[0]
                if kind == "progress":
                    self._set_progress(item[1], item[2])
                elif kind == "log":
                    self._append_log(item[1])
                elif kind == "done":
                    self._on_done(item[1])
                elif kind == "error":
                    self._on_error(item[1])
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    def _on_done(self, output_path):
        self.last_output = output_path
        self._set_progress(1.0, "Done")
        self._append_log("Output: " + output_path)
        self.convert_btn.config(state="normal")
        self.open_btn.config(state="normal")
        messagebox.showinfo("Success", "360 video created:\n\n" + output_path)

    def _on_error(self, message):
        self._stop_indeterminate()
        self.progress["value"] = 0
        self.status_var.set("Failed")
        self.convert_btn.config(state="normal")
        self._append_log("ERROR: " + message)
        messagebox.showerror("Conversion failed", message)

    # ------------------------------------------------------- progress/log
    def _set_progress(self, fraction, message):
        if message:
            self.status_var.set(message)
        if fraction is None:
            if not self._indeterminate:
                self.progress.config(mode="indeterminate")
                self.progress.start(12)
                self._indeterminate = True
        else:
            self._stop_indeterminate()
            self.progress.config(mode="determinate")
            self.progress["value"] = max(0.0, min(100.0, fraction * 100.0))

    def _stop_indeterminate(self):
        if self._indeterminate:
            self.progress.stop()
            self._indeterminate = False

    def _append_log(self, message):
        self.log_text.config(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def _open_output(self):
        if not self.last_output or not os.path.exists(self.last_output):
            return
        folder = os.path.dirname(self.last_output)
        try:
            if os.name == "nt":
                os.startfile(folder)  # noqa: S606 - opening a known local folder
            elif sys.platform == "darwin":
                subprocess.run(["open", folder])
            else:
                subprocess.run(["xdg-open", folder])
        except Exception:  # noqa: BLE001
            pass


def main():
    root = TkinterDnD.Tk() if _DND_AVAILABLE else tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
