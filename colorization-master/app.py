import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageOps, ImageTk
import json
import logging
import os
import sys
import subprocess
import threading
import traceback
from datetime import datetime
from io import BytesIO
from importlib import import_module

from colorize_engine import ColorizeEngine
from upscaler import OUTPUT_PRESETS, Upscaler

logger = logging.getLogger(__name__)


def create_root():
    try:
        dnd_module = import_module("tkinterdnd2")

        class DragDropCTk(ctk.CTk, dnd_module.TkinterDnD.DnDWrapper):
            def __init__(self):
                ctk.CTk.__init__(self)
                self.TkdndVersion = dnd_module.TkinterDnD._require(self)

        return DragDropCTk(), dnd_module.DND_FILES
    except Exception as exc:
        logger.info("Optional tkinterdnd2 support is unavailable: %s", exc)
        return ctk.CTk(), None


# --- THEME CONFIG BLOCK ---
THEMES = {
    "Crimson Gold":  {"bg":"#0B0707","panel":"#140D0D","surface":"#1D1313","border":"#33201A","primary":"#E5B84B","primary_hover":"#FFD97A","secondary":"#E11D48","text":"#FBEFE4","muted":"#9A8478","on_primary":"#0B0707","glow":"#5C4A1E"},
    "Ruby on Gold":  {"bg":"#0A0606","panel":"#130B0B","surface":"#1C1010","border":"#3A1A1A","primary":"#E11D48","primary_hover":"#FF4D6D","secondary":"#F5C84C","text":"#FFF1E0","muted":"#A08478","on_primary":"#FFFFFF","glow":"#5E1224"},
    "Red Gold Neon": {"bg":"#080505","panel":"#110909","surface":"#1A0D0D","border":"#3D1414","primary":"#FF2D4F","primary_hover":"#FF6B85","secondary":"#FFC93C","text":"#FFF4E6","muted":"#A38A7A","on_primary":"#080505","glow":"#6B1426"},
    "Royal Gold":    {"bg":"#0A0A0A","panel":"#121212","surface":"#1A1A1A","border":"#2A2417","primary":"#D4AF37","primary_hover":"#F2CF66","secondary":"#8C6B1F","text":"#F5F0E1","muted":"#8A8470","on_primary":"#0A0A0A","glow":"#4D3F14"},
    "Gold Neon":     {"bg":"#080808","panel":"#101010","surface":"#181818","border":"#2E2610","primary":"#FFC93C","primary_hover":"#FFE07A","secondary":"#FF6A00","text":"#FFF6DC","muted":"#9A8F70","on_primary":"#080808","glow":"#5E4A12"},
    "Cyber Neon":    {"bg":"#05050A","panel":"#0B0B14","surface":"#12121F","border":"#1F1F3A","primary":"#00F0FF","primary_hover":"#7DF9FF","secondary":"#FF2BD6","text":"#EAF6FF","muted":"#6B7A90","on_primary":"#05050A","glow":"#0A4A52"},
}

ctk.set_appearance_mode("dark")

_DEFAULT_THEME = THEMES["Crimson Gold"]
class ColorizerApp:
    def __init__(self, root, dnd_files=None):
        self.root = root
        self.dnd_files = dnd_files
        self.theme_name = "Crimson Gold"
        self.theme = THEMES[self.theme_name]
        self.theme_var = ctk.StringVar(value=self.theme_name)
        self._theme_bindings = []
        self._active_nav = "Home"
        self._nav_glows = []
        self._hover_color_pairs = {}
        self._hover_animation_ids = {}
        self._hover_bindings = set()
        self._pulse_phase = False
        self.root.title("AI PHOTO RESTORATION STUDIO")
        self.root.geometry("1280x720")
        self.root.minsize(1100, 650)
        self.root.configure(fg_color=self.theme["bg"])

        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        self.storage_folder = os.path.join(self.script_dir, "Neural_Chroma_Storage")
        try:
            os.makedirs(self.storage_folder, exist_ok=True)
        except OSError as exc:
            messagebox.showerror(
                "Storage unavailable", f"The output folder could not be created.\n\n{exc}"
            )
            raise
        self.settings_path = os.path.join(self.script_dir, "settings.json")
        self.settings = self.load_settings()
        self.engine = ColorizeEngine()
        self.upscaler = Upscaler(
            os.path.join(self.script_dir, "tools", "realesrgan-ncnn-vulkan", "realesrgan-ncnn-vulkan.exe")
        )
        self._missing_upscaler_notified = False
        self._is_busy = False
        self._cancel_event = None
        self._animations_enabled = True
        self._single_processing = False

        self.preview_size = (320, 320)
        self._comparison_width = None
        self.input_image = None
        self.output_image = None
        self.comparison_position = self.preview_size[0] // 2
        self.comparison_photo = None
        self.model_var = ctk.StringVar(value=self.settings["model"])
        self.output_size_var = ctk.StringVar(value=self.settings["output_size"])
        self.colorize_var = ctk.BooleanVar(value=self.settings["colorize"])
        self.format_var = ctk.StringVar(value="PNG")
        self.jpg_quality = 92
        self.setup_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self._setup_drag_drop()

    def set_theme(self, theme_name):
        if theme_name not in THEMES:
            raise ValueError(f"Unknown theme: {theme_name}")
        for job_id in self._hover_animation_ids.values():
            try:
                self.root.after_cancel(job_id)
            except tk.TclError:
                pass
        self._hover_animation_ids.clear()
        self.theme_name = theme_name
        self.theme = THEMES[theme_name]
        self.theme_var.set(theme_name)
        self.root.configure(fg_color=self.theme["bg"])
        for widget, color_options in self._theme_bindings:
            widget.configure(
                **{option: self.theme[key] for option, key in color_options.items()}
            )
        if hasattr(self, "process_glow"):
            self.btn_start.configure(border_color=self.theme["primary"])
            self.process_glow.configure(fg_color=self.theme["glow"])
        if hasattr(self, "theme_label"):
            self.theme_label.configure(text=self.theme_name)
        if hasattr(self, "nav_items"):
            self._apply_nav_styles()
        if hasattr(self, "canvas_in"):
            self._show_input_preview()
        if hasattr(self, "canvas_out"):
            self._draw_comparison()

    def _register_theme(self, widget, **color_options):
        self._theme_bindings.append((widget, color_options))
        widget.configure(
            **{option: self.theme[key] for option, key in color_options.items()}
        )
        return widget

    def _apply_nav_styles(self):
        for label, button, glow in zip(("Home", "Batch", "Ask AI"), self.nav_items, self._nav_glows):
            job_id = self._hover_animation_ids.pop(button, None)
            if job_id is not None:
                try:
                    self.root.after_cancel(job_id)
                except tk.TclError:
                    pass
            active = label == self._active_nav
            fill = "primary" if active else "panel"
            hover = "primary_hover" if active else "surface"
            self._hover_color_pairs[button] = (
                lambda key=fill: self.theme[key],
                lambda key=hover: self.theme[key],
            )
            self._bind_hover_transition(button)
            button.configure(
                fg_color=self.theme[fill],
                hover_color=self.theme[hover],
                text_color=self.theme["on_primary"] if active else self.theme["text"],
                border_color=self.theme["primary"] if active else self.theme["border"],
            )
            glow.configure(fg_color=self.theme["glow"] if active else self.theme["bg"])

    def _select_nav(self, label):
        self._active_nav = label
        self._apply_nav_styles()
        if label == "Batch":
            self.start_batch()
        elif label == "Ask AI":
            self.open_ai_chat()

    @staticmethod
    def _mix_hex(start, end, fraction):
        start_rgb = tuple(int(start[index:index + 2], 16) for index in (1, 3, 5))
        end_rgb = tuple(int(end[index:index + 2], 16) for index in (1, 3, 5))
        mixed = tuple(
            round(first + (second - first) * fraction)
            for first, second in zip(start_rgb, end_rgb)
        )
        return "#{:02X}{:02X}{:02X}".format(*mixed)

    def _bind_hover_transition(self, button):
        if button in self._hover_bindings:
            return
        self._hover_bindings.add(button)
        button.bind("<Enter>", lambda _event, button=button: self._animate_button_fill(button, True), add="+")
        button.bind("<Leave>", lambda _event, button=button: self._animate_button_fill(button, False), add="+")

    def _animate_button_fill(self, button, entering):
        pair = self._hover_color_pairs.get(button)
        if pair is None:
            return
        previous_job = self._hover_animation_ids.pop(button, None)
        if previous_job is not None:
            try:
                self.root.after_cancel(previous_job)
            except tk.TclError:
                pass
        resting_color = pair[0]()
        hover_color = pair[1]()
        current_color = resting_color if entering else hover_color
        target_color = hover_color if entering else resting_color

        def animate(step):
            fraction = min(1.0, step / 6)
            button.configure(fg_color=self._mix_hex(current_color, target_color, fraction))
            if fraction < 1.0:
                try:
                    self._hover_animation_ids[button] = self.root.after(
                        20, lambda: animate(step + 1)
                    )
                except tk.TclError:
                    self._hover_animation_ids.pop(button, None)
        animate(0)

    def _pulse_process_border(self):
        if not hasattr(self, "btn_start"):
            return
        self._pulse_phase = not self._pulse_phase
        subtle = self.theme_name in ("Crimson Gold", "Royal Gold")
        self.btn_start.configure(
            border_width=1 if subtle else 2,
            border_color=self.theme["glow"] if self._pulse_phase else self.theme["primary"],
        )
        try:
            self._process_pulse_id = self.root.after(500, self._pulse_process_border)
        except tk.TclError:
            self._process_pulse_id = None

    def load_settings(self):
        defaults = {"model": "siggraph17", "output_size": "Original", "colorize": True}
        try:
            with open(self.settings_path, "r", encoding="utf-8") as settings_file:
                values = json.load(settings_file)
            if not isinstance(values, dict):
                raise ValueError("Settings must be a JSON object.")
            model = values.get("model", defaults["model"])
            output_size = values.get("output_size", defaults["output_size"])
            colorize = values.get("colorize", defaults["colorize"])
            return {
                "model": model if model in ("siggraph17", "eccv16") else defaults["model"],
                "output_size": output_size if output_size in OUTPUT_PRESETS else defaults["output_size"],
                "colorize": colorize if isinstance(colorize, bool) else defaults["colorize"],
            }
        except FileNotFoundError:
            return defaults
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            logger.warning("Could not read settings from %s: %s", self.settings_path, exc)
            self.root.after(
                0,
                lambda exc=exc: messagebox.showwarning(
                    "Settings not loaded", f"Default settings will be used.\n\n{exc}"
                )
            )
            return defaults

    def save_settings(self):
        values = {
            "model": self.model_var.get(),
            "output_size": self.output_size_var.get(),
            "colorize": bool(self.colorize_var.get()),
        }
        try:
            temporary_path = f"{self.settings_path}.tmp"
            with open(temporary_path, "w", encoding="utf-8") as settings_file:
                json.dump(values, settings_file, indent=2)
                settings_file.write("\n")
            os.replace(temporary_path, self.settings_path)
        except OSError as exc:
            logger.exception("Could not save settings")
            messagebox.showerror("Settings not saved", f"Your settings could not be saved.\n\n{exc}")

    def _settings_changed(self, *_):
        self.save_settings()

    def _format_changed(self, selected_format):
        slider_state = "normal" if selected_format == "JPG" else "disabled"
        self.quality_slider.configure(state=slider_state)
        self._refresh_output_size()

    def _quality_changed(self, value):
        self.jpg_quality = round(float(value))
        self.quality_label.configure(text=f"JPG QUALITY  {self.jpg_quality}")
        self._refresh_output_size()

    def _refresh_output_size(self):
        if self.output_image is None:
            return
        try:
            memory_file = BytesIO()
            image_format = "JPEG" if self.format_var.get() == "JPG" else "PNG"
            if image_format == "JPEG":
                save_options = {"quality": self.jpg_quality, "optimize": True}
            else:
                save_options = {"optimize": True}
            self.output_image.save(memory_file, format=image_format, **save_options)
            size_bytes = memory_file.tell()
            self.output_size_label.configure(text=f"Output file size: {self._format_bytes(size_bytes)}")
        except OSError as exc:
            logger.exception("Could not estimate output size")
            self.output_size_label.configure(text=f"Output file size unavailable: {exc}")

    @staticmethod
    def _format_bytes(size_bytes):
        if size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        return f"{size_bytes / (1024 * 1024):.2f} MB"

    def setup_ui(self):
        self._register_theme(self.root, bg="bg")
        self.window_glow = self._register_theme(
            ctk.CTkFrame(self.root, corner_radius=24),
            fg_color="glow",
        )
        self.window_glow.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        self.window_glow.grid_rowconfigure(0, weight=1)
        self.window_glow.grid_columnconfigure(0, weight=1)
        self.app_shell = self._register_theme(
            ctk.CTkFrame(self.window_glow, corner_radius=20, border_width=1),
            fg_color="bg",
            border_color="border",
        )
        self.app_shell.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        for row, weight in ((0, 0), (1, 0), (2, 0), (3, 1), (4, 0)):
            self.app_shell.grid_rowconfigure(row, weight=weight)
        self.app_shell.grid_columnconfigure(0, weight=1)

        self.navbar = self._register_theme(
            ctk.CTkFrame(self.app_shell, corner_radius=0),
            fg_color="bg",
        )
        self.navbar.grid(row=0, column=0, sticky="ew", padx=24, pady=(16, 8))
        self.navbar.grid_columnconfigure(0, weight=1)
        self.nav_logo = self._register_theme(
            ctk.CTkLabel(
                self.navbar,
                text="AI  PHOTO  RESTORATION  STUDIO",
                font=("Segoe UI", 22, "bold"),
                anchor="w",
            ),
            text_color="primary",
        )
        self.nav_logo.grid(row=0, column=0, sticky="w")
        self.nav_right = self._register_theme(
            ctk.CTkFrame(self.navbar),
            fg_color="bg",
        )
        self.nav_right.grid(row=0, column=1, sticky="e")

        self.nav_items = []
        for label in ("Home", "Batch", "Ask AI"):
            holder = self._register_theme(
                ctk.CTkFrame(self.nav_right, width=88, height=48, corner_radius=24),
                fg_color="bg",
            )
            holder.pack(side="left", padx=8)
            holder.pack_propagate(False)
            glow = self._register_theme(
                ctk.CTkFrame(holder, corner_radius=22),
                fg_color="glow",
            )
            glow.place(relx=0.5, rely=0.5, relwidth=1, relheight=1, anchor="center")
            self._nav_glows.append(glow)
            btn = self._register_theme(
                ctk.CTkButton(
                    holder,
                    text=label,
                    command=lambda label=label: self._select_nav(label),
                    border_width=1,
                    corner_radius=20,
                    height=40,
                    width=80,
                    font=("Segoe UI", 13, "bold"),
                    cursor="hand2",
                ),
                fg_color="panel",
                hover_color="surface",
                text_color="text",
                border_color="border",
            )
            btn.place(relx=0.5, rely=0.5, anchor="center")
            self.nav_items.append(btn)

        self.theme_menu = self._register_theme(
            ctk.CTkOptionMenu(
                self.nav_right,
                variable=self.theme_var,
                values=list(THEMES),
                command=self.set_theme,
                width=152,
                height=40,
                corner_radius=20,
                font=("Segoe UI", 11),
                dropdown_font=("Segoe UI", 11),
            ),
            fg_color="surface",
            button_color="surface",
            button_hover_color="border",
            text_color="text",
            dropdown_fg_color="panel",
            dropdown_hover_color="surface",
            dropdown_text_color="text",
        )
        self.theme_menu.pack(side="left", padx=(8, 0))

        self.nav_line = self._register_theme(
            ctk.CTkFrame(self.app_shell, height=1, corner_radius=0),
            fg_color="primary",
        )
        self.nav_line.grid(row=1, column=0, sticky="ew")

        self._setup_options()
        self.container = self._register_theme(
            ctk.CTkFrame(self.app_shell),
            fg_color="bg",
        )
        self.container.grid(row=3, column=0, sticky="nsew", padx=16, pady=8)
        self.container.grid_rowconfigure(0, weight=1)
        self.container.grid_columnconfigure(0, weight=1, uniform="preview_panels")
        self.container.grid_columnconfigure(1, weight=0, minsize=200)
        self.container.grid_columnconfigure(2, weight=1, uniform="preview_panels")

        self.left_frame = self.create_slot(self.container, "SOURCE INPUT", 0)
        self.canvas_in = self._register_theme(
            tk.Canvas(self.left_frame, width=1, height=1,
                      highlightthickness=0, bd=0),
            bg="panel",
        )
        self.canvas_in.grid(row=1, column=0, sticky="nsew", padx=16, pady=16)
        self.canvas_in.bind("<Configure>", lambda _event: self._show_input_preview())
        self.btn_import = self.create_styled_button(
            self.left_frame, "IMPORT IMAGE", self.select_image, outline="primary"
        )
        self.btn_import.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 16))

        self.action_frame = self._register_theme(
            ctk.CTkFrame(self.container),
            fg_color="bg",
        )
        self.action_frame.grid(row=0, column=1, sticky="nsew", padx=12)
        self.action_frame.grid_rowconfigure(0, weight=1)
        self.action_frame.grid_rowconfigure(2, weight=1)
        self.process_stack = self._register_theme(
            ctk.CTkFrame(self.action_frame),
            fg_color="bg",
        )
        self.process_stack.grid(row=1, column=0, sticky="ew")
        self.process_glow = self._register_theme(
            ctk.CTkFrame(self.process_stack, height=80, corner_radius=40),
            fg_color="glow",
        )
        self.process_glow.pack(fill="x", pady=8)
        self.process_glow.pack_propagate(False)
        self.btn_start = self.create_styled_button(
            self.process_glow, "PROCESS", self.start_thread, outline=None,
            height=64, font=("Segoe UI", 13, "bold"),
        )
        self.btn_start.configure(border_width=2, border_color=self.theme["primary"])
        self.btn_start.place(relx=0.5, rely=0.5, relwidth=0.94, anchor="center")
        self.btn_batch = self.create_styled_button(
            self.process_stack, "BATCH FOLDER", self.start_batch, outline="secondary"
        )
        self.btn_batch.pack(fill="x", pady=8)
        self.progress_frame = self._register_theme(
            ctk.CTkFrame(self.process_stack),
            fg_color="bg",
        )
        self.progress_bar = self._register_theme(
            ctk.CTkProgressBar(self.progress_frame, height=8),
            progress_color="primary",
            fg_color="surface",
        )
        self.progress_bar.set(0)
        self.progress_bar.pack(fill="x", pady=(12, 4))
        self.progress_label = self._register_theme(
            ctk.CTkLabel(self.progress_frame, text="0/0", font=("Segoe UI", 11)),
            text_color="primary",
        )
        self.progress_label.pack(pady=(0, 4))
        self.btn_cancel = self.create_styled_button(
            self.progress_frame, "CANCEL", self.cancel_batch, outline="primary"
        )

        self.right_frame = self.create_slot(self.container, "AI GENERATION", 2)
        self.canvas_out = self._register_theme(
            tk.Canvas(self.right_frame, width=1, height=1,
                      highlightthickness=0, bd=0),
            bg="panel",
        )
        self.canvas_out.grid(row=1, column=0, sticky="nsew", padx=16, pady=16)
        self.canvas_out.bind("<Configure>", lambda _event: self._draw_comparison())
        self.canvas_out.bind("<Button-1>", self.move_comparison_divider)
        self.canvas_out.bind("<B1-Motion>", self.move_comparison_divider)
        self.canvas_out.bind("<Double-Button-1>", self._reset_comparison_divider)
        self.canvas_out.bind("<Motion>", self._update_divider_cursor)
        self.btn_save = self.create_styled_button(
            self.right_frame, "SAVE TO GALLERY", self.save_to_local_storage, outline="primary"
        )
        self.btn_save.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 8))
        self.btn_open_folder = self.create_styled_button(
            self.right_frame, "OPEN OUTPUT FOLDER", self.open_output_folder, outline="primary"
        )
        self.btn_open_folder.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 16))

        self.footer = self._register_theme(
            ctk.CTkFrame(self.app_shell),
            fg_color="bg",
        )
        self.footer.grid(row=4, column=0, sticky="ew", padx=24, pady=8)
        self.footer.grid_columnconfigure(1, weight=1)
        self.output_size_label = self._register_theme(
            ctk.CTkLabel(self.footer, text="Output file size: —", font=("Segoe UI", 11), anchor="w"),
            text_color="muted",
        )
        self.output_size_label.grid(row=0, column=0, sticky="w")
        self.label_status = self._register_theme(
            ctk.CTkLabel(self.footer, text="SYSTEM INITIALIZED • READY", font=("Segoe UI", 11)),
            text_color="primary",
        )
        self.label_status.grid(row=0, column=1)
        self.theme_label = self._register_theme(
            ctk.CTkLabel(self.footer, text=self.theme_name, font=("Segoe UI", 11, "bold")),
            text_color="secondary",
        )
        self.theme_label.grid(row=0, column=2, sticky="e")
        self._apply_nav_styles()
        self._show_input_preview()
        self._draw_comparison()
        self._pulse_process_border()

    def _setup_options(self):
        self.options_frame = self._register_theme(
            ctk.CTkFrame(self.app_shell, corner_radius=14, border_width=1),
            fg_color="surface",
            border_color="border",
        )
        self.options_frame.grid(row=2, column=0, sticky="ew", padx=16, pady=8)
        for column, weight in enumerate((2, 2, 2, 1, 2)):
            self.options_frame.grid_columnconfigure(column, weight=weight, uniform="controls")

        options = (
            ("COLORIZER MODEL", self.model_var, ("siggraph17", "eccv16"), self._settings_changed),
            ("OUTPUT SIZE", self.output_size_var, OUTPUT_PRESETS, self._settings_changed),
            ("SAVE FORMAT", self.format_var, ("PNG", "JPG"), self._format_changed),
        )
        for column, (label, variable, choices, callback) in enumerate(options):
            title = self._register_theme(
                ctk.CTkLabel(
                    self.options_frame, text=label, font=("Segoe UI", 11, "bold"), anchor="w"
                ),
                text_color="muted",
            )
            title.grid(row=0, column=column, sticky="ew", padx=16, pady=(8, 8))
            option_menu = self._register_theme(
                ctk.CTkOptionMenu(
                    self.options_frame,
                    variable=variable,
                    values=list(choices),
                    command=callback,
                    height=40,
                    corner_radius=12,
                    font=("Segoe UI", 11),
                    dropdown_font=("Segoe UI", 11),
                ),
                fg_color="panel",
                button_color="panel",
                button_hover_color="border",
                text_color="text",
                dropdown_fg_color="panel",
                dropdown_hover_color="surface",
                dropdown_text_color="text",
            )
            option_menu.grid(row=1, column=column, sticky="ew", padx=16, pady=(0, 8))
            if variable is self.model_var:
                self.model_menu = option_menu
            elif variable is self.output_size_var:
                self.output_size_menu = option_menu
            else:
                self.format_menu = option_menu

        self.colorize_toggle = self._register_theme(
            ctk.CTkCheckBox(
                self.options_frame,
                text="COLORIZE",
                variable=self.colorize_var,
                command=self._settings_changed,
                onvalue=True,
                offvalue=False,
                border_width=2,
                corner_radius=5,
                font=("Segoe UI", 11, "bold"),
            ),
            fg_color="primary",
            hover_color="primary_hover",
            border_color="secondary",
            checkmark_color="on_primary",
            text_color="text",
        )
        self.colorize_toggle.grid(row=1, column=3, padx=16, pady=(0, 8))

        self.quality_frame = self._register_theme(
            ctk.CTkFrame(self.options_frame),
            fg_color="surface",
        )
        self.quality_frame.grid(row=0, column=4, rowspan=2, sticky="ew", padx=16, pady=8)
        self.quality_label = self._register_theme(
            ctk.CTkLabel(
                self.quality_frame,
                text=f"JPG QUALITY  {self.jpg_quality}",
                font=("Segoe UI", 11, "bold"),
                anchor="w",
            ),
            text_color="muted",
        )
        self.quality_label.pack(anchor="w", pady=(0, 8))
        self.quality_slider = self._register_theme(
            ctk.CTkSlider(
                self.quality_frame,
                from_=50,
                to=100,
                number_of_steps=50,
                command=self._quality_changed,
                height=16,
            ),
            progress_color="primary",
            button_color="primary",
            button_hover_color="primary_hover",
            fg_color="panel",
        )
        self.quality_slider.set(self.jpg_quality)
        self.quality_slider.pack(fill="x")
        self._format_changed(self.format_var.get())

    def create_slot(self, parent, title, col):
        frame = self._register_theme(
            ctk.CTkFrame(parent, corner_radius=18, border_width=1),
            fg_color="panel",
            border_color="border",
        )
        frame.grid(row=0, column=col, sticky="nsew", padx=8, pady=8)
        frame.grid_rowconfigure(1, weight=1)
        frame.grid_columnconfigure(0, weight=1)
        label = self._register_theme(
            ctk.CTkLabel(frame, text=title, font=("Segoe UI", 16, "bold")),
            text_color="text",
        )
        label.grid(row=0, column=0, pady=(16, 0))

        return frame

    def create_styled_button(self, parent, text, cmd, outline="primary", height=40, font=None):
        if outline is None:
            foreground_key = "primary"
            text_key = "on_primary"
            border_key = "primary"
            hover_key = "primary_hover"
            border_width = 0
        else:
            foreground_key = "panel"
            text_key = outline
            border_key = outline
            hover_key = "primary"
            border_width = 1
        button = self._register_theme(
            ctk.CTkButton(
                parent,
                text=text,
                command=cmd,
                border_width=border_width,
                corner_radius=height // 2,
                height=height,
                font=font or ("Segoe UI", 13, "bold"),
                cursor="hand2",
            ),
            fg_color=foreground_key,
            hover_color=hover_key,
            text_color=text_key,
            border_color=border_key,
        )
        if outline is not None:
            button.bind(
                "<Enter>",
                lambda _event, button=button: button.configure(text_color=self.theme["on_primary"]),
            )
            button.bind(
                "<Leave>",
                lambda _event, button=button, key=text_key:
                button.configure(text_color=self.theme[key]),
            )
        if outline is None:
            self._hover_color_pairs[button] = (
                lambda: self.theme["primary"],
                lambda: self.theme["primary_hover"],
            )
        else:
            self._hover_color_pairs[button] = (
                lambda: self.theme["panel"],
                lambda: self.theme["primary"],
            )
        self._bind_hover_transition(button)
        return button

    def select_image(self):
        path = filedialog.askopenfilename(
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.bmp *.webp"), ("All files", "*.*")]
        )
        if path:
            self._load_image(path)

    def _load_image(self, path):
        if self._is_busy:
            return
        supported = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
        if os.path.splitext(path)[1].lower() not in supported:
            messagebox.showerror("Unsupported image", "Choose a PNG, JPG, JPEG, BMP, or WEBP image.")
            return
        try:
            with Image.open(path) as source:
                self.input_image = source.convert("RGB")
            self.raw_path = path
            self._show_input_preview()
            self.output_image = None
            self.output_size_label.configure(text="Output file size: —")
            self._draw_comparison()
            self.update_status("IMAGE LOADED SUCCESSFULLY")
        except (OSError, ValueError) as exc:
            messagebox.showerror("Unable to open image", f"The selected file could not be opened.\n\n{exc}")

    def _setup_drag_drop(self):
        if self.dnd_files is None or not hasattr(self.canvas_in, "drop_target_register"):
            return
        try:
            self.canvas_in.drop_target_register(self.dnd_files)
            self.canvas_in.dnd_bind("<<Drop>>", self._handle_drop)
        except Exception:
            logger.exception("Drag-and-drop could not be enabled; use IMPORT IMAGE instead")

    def _handle_drop(self, event):
        try:
            paths = self.root.tk.splitlist(event.data)
            if paths:
                self._load_image(paths[0])
        except (tk.TclError, OSError, ValueError) as exc:
            messagebox.showerror("Unable to load dropped image", f"The dropped file could not be loaded.\n\n{exc}")

    def _fit_preview(self, image, size):
        preview = Image.new("RGB", size, self.theme["panel"])
        fitted = ImageOps.contain(image.convert("RGB"), size, Image.Resampling.LANCZOS)
        preview.paste(
            fitted,
            ((size[0] - fitted.width) // 2, (size[1] - fitted.height) // 2)
        )
        return preview

    @staticmethod
    def _preview_dimensions(canvas):
        width = canvas.winfo_width()
        height = canvas.winfo_height()
        return (width, height) if width > 1 and height > 1 else (320, 320)

    def _show_input_preview(self):
        width, height = self._preview_dimensions(self.canvas_in)
        self.canvas_in.delete("all")
        if self.input_image is None:
            self.canvas_in.create_text(
                width // 2,
                height // 2,
                text="Drop an image here or click Import",
                fill=self.theme["muted"],
                font=("Segoe UI", 11),
                width=max(120, width - 48),
            )
        else:
            preview_size = (max(1, width - 20), max(1, height - 20))
            self.img_in = ImageTk.PhotoImage(self._fit_preview(self.input_image, preview_size))
            self.canvas_in.create_image(width // 2, height // 2, image=self.img_in)
        self.canvas_in.create_rectangle(
            4, 4, width - 4, height - 4,
            outline=self.theme["secondary"],
            dash=(6, 4),
            tags="preview_border",
        )

    def _reset_comparison_divider(self, _event=None):
        """Reset the comparison divider to the centre of the canvas on double-click.

        Tkinter always fires <Double-Button-1> *after* <Button-1>, so the single-click
        move that happens on the first click of a double-click is immediately overridden
        by this reset — no delay or cancellation logic needed.
        """
        self._comparison_width = None  # cleared so _draw_comparison re-centres
        self._draw_comparison()

    def _update_divider_cursor(self, event):
        """Show a horizontal-resize cursor when hovering within 20 px of the divider."""
        if self.output_image is None or self.input_image is None:
            self.canvas_out.configure(cursor="")
            return
        near = abs(event.x - self.comparison_position) <= 20
        self.canvas_out.configure(cursor="sb_h_double_arrow" if near else "")

    def move_comparison_divider(self, event):
        width, _height = self._preview_dimensions(self.canvas_out)
        # Use event.x directly — it is already in canvas-widget coordinates for a
        # non-scrolled canvas, and avoids any offset that canvasx() can introduce.
        self.comparison_position = max(10, min(width - 10, event.x))
        self._comparison_width = width
        self._draw_comparison()

    def _draw_comparison(self):
        width, height = self._preview_dimensions(self.canvas_out)
        if self._comparison_width is None:
            self.comparison_position = width // 2
        elif self._comparison_width != width:
            self.comparison_position = round(
                self.comparison_position * width / self._comparison_width
            )
        self._comparison_width = width
        self.canvas_out.delete("all")
        if self.output_image is None or self.input_image is None:
            if self._single_processing and self.input_image is not None:
                empty_text = "PROCESSING IMAGE...\nCPU colorization can take a moment"
                empty_color = self.theme["primary"]
            else:
                empty_text = "Result appears here"
                empty_color = self.theme["muted"]
            self.canvas_out.create_text(
                width // 2,
                height // 2,
                text=empty_text,
                fill=empty_color,
                font=("Segoe UI", 13 if self._single_processing else 11, "bold" if self._single_processing else "normal"),
                width=max(120, width - 48),
            )
        else:
            preview_size = (max(1, width - 20), max(1, height - 20))
            input_preview = self._fit_preview(self.input_image, preview_size)
            output_preview = self._fit_preview(self.output_image, preview_size)

            # divider_x: position within the PIL image (which starts at canvas x=10)
            divider_x = max(0, min(preview_size[0], self.comparison_position - 10))
            # Paste output right-half on top of input preview
            input_preview.paste(
                output_preview.crop((divider_x, 0, preview_size[0], preview_size[1])),
                (divider_x, 0),
            )
            self.comparison_photo = ImageTk.PhotoImage(input_preview)
            self.canvas_out.create_image(width // 2, height // 2, image=self.comparison_photo)

            # INPUT / OUTPUT labels
            cx = divider_x + 10  # divider in canvas coordinates
            self.canvas_out.create_text(
                16, 16, anchor="nw", text="INPUT",
                fill=self.theme["text"], font=("Segoe UI", 11, "bold"),
            )
            self.canvas_out.create_text(
                width - 16, 16, anchor="ne", text="OUTPUT",
                fill=self.theme["text"], font=("Segoe UI", 11, "bold"),
            )

            # Divider line
            self.canvas_out.create_line(
                cx, 8, cx, height - 8,
                fill=self.theme["primary"], width=3,
                tags="divider",
            )

            # Drag handle — a circle with ◀ ▶ arrows so it is clearly grabbable
            mid_y = height // 2
            r = 16
            self.canvas_out.create_oval(
                cx - r, mid_y - r, cx + r, mid_y + r,
                fill=self.theme["primary"],
                outline=self.theme["bg"],
                width=2,
                tags="divider_handle",
            )
            self.canvas_out.create_text(
                cx, mid_y,
                text="◀▶",
                fill=self.theme["on_primary"],
                font=("Segoe UI", 9, "bold"),
                tags="divider_handle",
            )

            # Bind drag directly to the handle items as well, so grabbing the
            # circle itself also moves the divider.
            self.canvas_out.tag_bind("divider_handle", "<ButtonPress-1>",
                                     self.move_comparison_divider)
            self.canvas_out.tag_bind("divider_handle", "<B1-Motion>",
                                     self.move_comparison_divider)

        self.canvas_out.create_rectangle(
            4, 4, width - 4, height - 4,
            outline=self.theme["secondary"],
            dash=(6, 4),
            tags="preview_border",
        )


    def update_status(self, text, _color=None):
        self.label_status.configure(text=text, text_color=self.theme["primary"])

    def open_ai_chat(self):
        if not self._animations_enabled:
            return
        try:
            from ai_chat import AIChatPanel
            AIChatPanel(self.root, self)
        except Exception as exc:
            logger.exception("Could not open AI chat")
            messagebox.showerror("AI Assistant unavailable", f"Could not open the assistant.\n\n{exc}")

    def start_thread(self):
        if self._is_busy:
            return
        if not hasattr(self, "raw_path"):
            messagebox.showwarning("Warning", "Please import a photo!")
            return
        settings = self._current_settings()
        self._show_missing_upscaler_notice(settings["output_size"])
        self._begin_job()
        self._single_processing = True
        self.update_status("PROCESSING IMAGE...")
        self._draw_comparison()
        self.btn_cancel.pack_forget()
        self.progress_label.configure(text="AI COLORIZATION • CPU MAY TAKE A MOMENT")
        self.progress_frame.pack(fill="x", pady=(8, 0))
        self.progress_bar.start()
        threading.Thread(
            target=self._run_single_image,
            args=(self.raw_path, settings),
            daemon=True
        ).start()

    def _current_settings(self):
        return {
            "model": self.model_var.get(),
            "output_size": self.output_size_var.get(),
            "colorize": bool(self.colorize_var.get()),
            "format": self.format_var.get(),
            "quality": self.jpg_quality,
        }

    def _show_missing_upscaler_notice(self, preset):
        if preset == "Original" or self.upscaler.available or self._missing_upscaler_notified:
            return
        self._missing_upscaler_notified = True
        # Show a quiet status-bar note instead of a blocking dialog so processing is not interrupted.
        logger.info(
            "Real-ESRGAN not found; Lanczos fallback will be used. "
            "Place realesrgan-ncnn-vulkan.exe in %s",
            os.path.join(self.script_dir, "tools", "realesrgan-ncnn-vulkan"),
        )
        self.update_status("Real-ESRGAN not found — using Lanczos fallback for upscaling")

    def _begin_job(self):
        self._is_busy = True
        self._animations_enabled = False
        self.btn_start.configure(state="disabled", text="PROCESSING...")
        self.btn_batch.configure(state="disabled")
        self.btn_import.configure(state="disabled")
        self.model_menu.configure(state="disabled")
        self.output_size_menu.configure(state="disabled")
        self.colorize_toggle.configure(state="disabled")
        self.format_menu.configure(state="disabled")
        self.quality_slider.configure(state="disabled")

    def _finish_job(self):
        self._is_busy = False
        self._animations_enabled = True
        if self._single_processing:
            self.progress_bar.stop()
            self.progress_frame.pack_forget()
            self._single_processing = False
            self.progress_label.configure(text="0/0")
            self._draw_comparison()
        self.btn_start.configure(state="normal", text="PROCESS")
        self.btn_batch.configure(state="normal")
        self.btn_import.configure(state="normal")
        self.model_menu.configure(state="normal")
        self.output_size_menu.configure(state="normal")
        self.colorize_toggle.configure(state="normal")
        self.format_menu.configure(state="normal")
        self.quality_slider.configure(state="normal" if self.format_var.get() == "JPG" else "disabled")

    def _run_pipeline(self, source_image, settings):
        result = source_image.copy()
        if settings["colorize"]:
            result = self.engine.colorize(result, settings["model"])
        return self.upscaler.upscale(result, settings["output_size"])

    def _run_single_image(self, source_path, settings):
        try:
            with Image.open(source_path) as opened_image:
                source_image = opened_image.convert("RGB")
            output_image = self._run_pipeline(source_image, settings)
            self.ui(lambda: self.show_result(source_image, output_image))
        except Exception as exc:
            logger.exception("Image processing failed for %s", source_path)
            self.ui(lambda exc=exc: self.report_processing_error(exc))
        finally:
            self.ui(self._finish_job)

    def ui(self, callback):
        self.root.after(0, callback)

    def report_processing_error(self, error):
        self.update_status("PROCESSING FAILED")
        messagebox.showerror(
            "Processing failed",
            f"The image could not be processed.\n\n{error}\n\nCheck that the required Python packages and model weights are available."
        )

    def show_result(self, input_image, output_image):
        self.input_image = input_image
        self.output_image = output_image
        self._show_input_preview()
        self._draw_comparison()
        self._refresh_output_size()
        self.update_status("PROCESSING COMPLETE")
        self.btn_save.configure(state="normal")

    def save_to_local_storage(self):
        if self.output_image is None:
            return messagebox.showwarning("Warning", "Nothing to save yet!")
        try:
            base_name = os.path.splitext(os.path.basename(getattr(self, "raw_path", "restored")))[0]
            extension = ".jpg" if self.format_var.get() == "JPG" else ".png"
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            dest = os.path.join(self.storage_folder, f"{base_name}_restored_{timestamp}{extension}")
            self._save_image(self.output_image, dest, self.format_var.get(), self.jpg_quality)
            self.output_size_label.configure(
                text=f"Output file size: {self._format_bytes(os.path.getsize(dest))}"
            )
        except OSError as exc:
            messagebox.showerror("Save failed", f"The output could not be saved.\n\n{exc}")
            return
        self.update_status("SAVED TO GALLERY")

    @staticmethod
    def _save_image(image, path, image_format, quality):
        if image_format == "JPG":
            image.convert("RGB").save(path, format="JPEG", quality=quality, optimize=True)
        else:
            image.save(path, format="PNG", optimize=True)

    def open_output_folder(self):
        try:
            if sys.platform == "win32":
                os.startfile(self.storage_folder)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", self.storage_folder])
            else:
                subprocess.Popen(["xdg-open", self.storage_folder])
        except (OSError, subprocess.SubprocessError) as exc:
            messagebox.showerror("Unable to open folder", f"The output folder could not be opened.\n\n{exc}")

    def start_batch(self):
        if self._is_busy:
            return
        input_folder = filedialog.askdirectory(title="Choose a folder of images")
        if not input_folder:
            return
        supported_extensions = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
        try:
            image_paths = sorted(
                os.path.join(input_folder, name)
                for name in os.listdir(input_folder)
                if os.path.splitext(name)[1].lower() in supported_extensions
                and os.path.isfile(os.path.join(input_folder, name))
            )
        except OSError as exc:
            messagebox.showerror("Unable to read folder", f"The selected folder could not be read.\n\n{exc}")
            return
        if not image_paths:
            messagebox.showinfo("No images found", "The selected folder has no supported image files.")
            return

        settings = self._current_settings()
        self._show_missing_upscaler_notice(settings["output_size"])
        batch_folder = os.path.join(
            self.storage_folder, f"batch_{datetime.now():%Y%m%d_%H%M%S_%f}"
        )
        try:
            os.makedirs(batch_folder, exist_ok=False)
        except OSError as exc:
            messagebox.showerror("Batch could not start", f"The output folder could not be created.\n\n{exc}")
            return

        self._cancel_event = threading.Event()
        self._begin_job()
        self.progress_frame.pack(fill="x", pady=(8, 0))
        self.btn_cancel.pack(pady=(0, 4), fill="x")
        self.progress_bar.set(0)
        self.progress_label.configure(text=f"0/{len(image_paths)}")
        threading.Thread(
            target=self._run_batch,
            args=(image_paths, batch_folder, settings, self._cancel_event),
            daemon=True
        ).start()

    def cancel_batch(self):
        if self._cancel_event is not None:
            self._cancel_event.set()
            self.btn_cancel.configure(state="disabled", text="CANCELLING...")

    def _run_batch(self, image_paths, batch_folder, settings, cancel_event):
        total = len(image_paths)
        completed_count = 0
        failed_count = 0
        cancelled = False
        log_path = os.path.join(batch_folder, "batch_errors.log")
        try:
            for index, source_path in enumerate(image_paths, start=1):
                if cancel_event.is_set():
                    cancelled = True
                    break
                try:
                    with Image.open(source_path) as opened_image:
                        source_image = opened_image.convert("RGB")
                    output_image = self._run_pipeline(source_image, settings)
                    extension = ".jpg" if settings["format"] == "JPG" else ".png"
                    output_path = self._batch_output_path(batch_folder, source_path, extension)
                    self._save_image(output_image, output_path, settings["format"], settings["quality"])
                except Exception as exc:
                    failed_count += 1
                    logger.exception("Batch processing failed for %s", source_path)
                    try:
                        with open(log_path, "a", encoding="utf-8") as error_log:
                            error_log.write(f"{source_path}\n{type(exc).__name__}: {exc}\n")
                            error_log.write(traceback.format_exc() + "\n")
                    except OSError:
                        logger.exception("Could not write batch error log %s", log_path)
                completed_count = index
                self.ui(
                    lambda index=index, total=total, name=os.path.basename(source_path):
                    self.update_batch_progress(index, total, name)
                )
            cancelled = cancelled or cancel_event.is_set()
            self.ui(
                lambda: self.finish_batch(
                    completed_count, total, failed_count, cancelled, log_path
                )
            )
        except Exception as exc:
            logger.exception("Batch processing could not continue")
            self.ui(lambda exc=exc: self.report_batch_error(exc))

    @staticmethod
    def _batch_output_path(batch_folder, source_path, extension):
        stem = os.path.splitext(os.path.basename(source_path))[0]
        destination = os.path.join(batch_folder, f"{stem}_restored{extension}")
        suffix = 2
        while os.path.exists(destination):
            destination = os.path.join(batch_folder, f"{stem}_restored_{suffix}{extension}")
            suffix += 1
        return destination

    def update_batch_progress(self, completed, total, filename):
        self.progress_bar.set(completed / total if total else 0)
        self.progress_label.configure(text=f"{completed}/{total}")
        self.update_status(f"{completed}/{total} • {filename}")

    def finish_batch(self, completed, total, failed, cancelled, log_path):
        self._finish_job()
        self.progress_frame.pack_forget()
        status = f"BATCH CANCELLED • {completed}/{total}" if cancelled else f"BATCH COMPLETE • {completed}/{total}"
        if failed:
            status += f" • {failed} failed"
            status += f" • see {os.path.basename(log_path)}"
        self.update_status(status)
        self._cancel_event = None

    def report_batch_error(self, error):
        self._finish_job()
        self.progress_frame.pack_forget()
        self._cancel_event = None
        self.report_processing_error(error)

    def on_close(self):
        for job_id in self._hover_animation_ids.values():
            try:
                self.root.after_cancel(job_id)
            except tk.TclError:
                pass
        pulse_id = getattr(self, "_process_pulse_id", None)
        if pulse_id is not None:
            try:
                self.root.after_cancel(pulse_id)
            except tk.TclError:
                pass
        self.save_settings()
        self.root.destroy()


if __name__ == "__main__":
    root, dnd_files = create_root()
    app = ColorizerApp(root, dnd_files)
    root.mainloop()
