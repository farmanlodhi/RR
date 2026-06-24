"""
Receipt and Invoice Scanner App
A mobile-friendly Python app using KivyMD for Android/iOS
"""

from kivymd.app import MDApp
from kivymd.uix.screen import MDScreen
from kivymd.uix.screenmanager import MDScreenManager
from kivymd.uix.button import MDFlatButton, MDRaisedButton
from kivymd.uix.dialog import MDDialog
from kivymd.uix.datatables import MDDataTable
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.label import MDLabel
from kivymd.uix.textfield import MDTextField
from kivymd.uix.scrollview import MDScrollView
from kivymd.uix.toolbar import MDTopAppBar
from kivymd.uix.menu import MDDropdownMenu
from kivy.uix.image import Image
from kivy.clock import Clock
from kivy.logger import Logger
from kivy.uix.filechooser import FileChooserIconView
import os
import csv
import json
import re
import shutil
from datetime import datetime
import platform

# Try to import camera and AI modules
try:
    from plyer import camera
    CAMERA_AVAILABLE = True
except ImportError:
    CAMERA_AVAILABLE = False
    Logger.warning("Plyer not available - camera functionality disabled")

try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    Logger.warning("OpenAI not available - install with: pip install openai")

try:
    import base64
    BASE64_AVAILABLE = True
except ImportError:
    BASE64_AVAILABLE = False

try:
    from PIL import Image as PILImage
    import io
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    Logger.warning("PIL not available - image processing disabled")


class AIConfig:
    """
    Persists AI provider settings (provider, model, API key, base URL)
    to a JSON file in the app data directory.  All other code reads
    config through the singleton get() method.
    """
    _instance = None

    # Provider presets: display name -> (default base_url, default model, notes)
    PROVIDERS = {
        "OpenAI": {
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-4o-mini",
            "notes": "Needs an OpenAI API key from platform.openai.com",
        },
        "Anthropic Claude": {
            "base_url": "https://api.anthropic.com/v1",
            "model": "claude-opus-4-6",
            "notes": "Needs an Anthropic API key from console.anthropic.com",
        },
        "Custom / Local": {
            "base_url": "",
            "model": "",
            "notes": "Any OpenAI-compatible endpoint (e.g. Ollama, LM Studio, Azure)",
        },
    }

    def __init__(self):
        self.provider = "OpenAI"
        self.api_key = ""
        self.model = "gpt-4o-mini"
        self.base_url = "https://api.openai.com/v1"
        self._config_path = None   # set lazily after app data dir is known

    @classmethod
    def get(cls):
        if cls._instance is None:
            cls._instance = cls()
            cls._instance._load()
        return cls._instance

    def _resolve_path(self):
        """Return path to config file, creating directory if needed."""
        if self._config_path:
            return self._config_path
        try:
            from kivymd.app import MDApp
            app = MDApp.get_running_app()
            if app:
                data_dir = app.get_data_directory()
            else:
                data_dir = os.path.join(os.path.expanduser("~"), "ReceiptReader")
        except Exception:
            data_dir = os.path.join(os.path.expanduser("~"), "ReceiptReader")
        os.makedirs(data_dir, exist_ok=True)
        self._config_path = os.path.join(data_dir, ".ai_config.json")
        return self._config_path

    def _load(self):
        """Load saved settings; fall back to environment variable if no key saved."""
        try:
            path = self._resolve_path()
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.provider = data.get("provider", self.provider)
                self.api_key = data.get("api_key", "")
                self.model = data.get("model", self.model)
                self.base_url = data.get("base_url", self.base_url)
        except Exception as e:
            Logger.error(f"AIConfig: failed to load: {e}")

        # Fall back to environment variables if no key stored
        if not self.api_key:
            self.api_key = os.getenv("OPENAI_API_KEY", "") or os.getenv("ANTHROPIC_API_KEY", "")

        # Try legacy config.py
        if not self.api_key:
            try:
                import config as _cfg
                self.api_key = getattr(_cfg, "OPENAI_API_KEY", "") or getattr(_cfg, "ANTHROPIC_API_KEY", "")
            except ImportError:
                pass

    def save(self):
        """Persist settings to disk."""
        try:
            path = self._resolve_path()
            with open(path, "w", encoding="utf-8") as f:
                json.dump({
                    "provider": self.provider,
                    "api_key": self.api_key,
                    "model": self.model,
                    "base_url": self.base_url,
                }, f, indent=2)
            Logger.info("AIConfig: settings saved")
        except Exception as e:
            Logger.error(f"AIConfig: failed to save: {e}")

    @property
    def is_configured(self):
        return bool(self.api_key and self.model and self.base_url)


class InvoiceExtractor:
    """
    Extract receipt/invoice data using an AI Vision model.
    Uses whatever provider the user has configured in AIConfig.
    Anthropic Claude is called via its own SDK; all others are called
    through the openai-compatible client.
    """

    def __init__(self):
        self.client = None
        self._build_client()

    def _build_client(self):
        """(Re)initialise the API client from current AIConfig."""
        cfg = AIConfig.get()
        self.client = None

        if not cfg.is_configured:
            Logger.warning("InvoiceExtractor: AI not configured — open Menu > AI Settings")
            return

        if cfg.provider == "Anthropic Claude":
            # Use Anthropic SDK if available; fall back to openai-compat endpoint
            try:
                import anthropic
                self.client = anthropic.Anthropic(api_key=cfg.api_key)
                self._mode = "anthropic"
                Logger.info("InvoiceExtractor: Anthropic client ready")
            except ImportError:
                Logger.warning("InvoiceExtractor: anthropic SDK not installed; "
                               "falling back to openai-compat endpoint")
                self._init_openai_compat(cfg)
        else:
            self._init_openai_compat(cfg)

    def _init_openai_compat(self, cfg):
        if not OPENAI_AVAILABLE:
            Logger.error("InvoiceExtractor: openai package not installed")
            return
        try:
            self.client = openai.OpenAI(
                api_key=cfg.api_key,
                base_url=cfg.base_url,
            )
            self._mode = "openai"
            Logger.info(f"InvoiceExtractor: OpenAI-compat client ready ({cfg.base_url})")
        except Exception as e:
            Logger.error(f"InvoiceExtractor: client init failed: {e}")
            self.client = None

    def reload(self):
        """Call this after the user saves new AI settings."""
        self._build_client()

    def encode_image(self, image_path):
        """Encode image to base64 for API."""
        try:
            with open(image_path, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")
        except Exception as e:
            Logger.error(f"InvoiceExtractor: encode_image failed: {e}")
            return None

    # ── shared prompt ────────────────────────────────────────────────
    _PROMPT = (
        'Analyze this receipt or invoice image and extract the following '
        'information in JSON format:\n'
        '{\n'
        '    "invoice_number": "invoice or receipt number if visible",\n'
        '    "vendor": "company or store name",\n'
        '    "invoicee_name": "customer name or Bill To name if visible",\n'
        '    "date": "date of the invoice/receipt",\n'
        '    "amount": "subtotal or amount before tax",\n'
        '    "tax": "tax amount if visible",\n'
        '    "total": "total amount including tax",\n'
        '    "description": "brief description of items or services"\n'
        '}\n\n'
        'Extract only information clearly visible in the image. '
        'Use an empty string for missing fields. '
        'Return ONLY valid JSON, no extra text.'
    )

    def analyze_with_ai(self, image_path):
        """Send image to AI and return parsed dict."""
        if not self.client:
            return {}
        if not BASE64_AVAILABLE:
            Logger.error("InvoiceExtractor: base64 not available")
            return {}

        base64_image = self.encode_image(image_path)
        if not base64_image:
            return {}

        cfg = AIConfig.get()

        try:
            if getattr(self, "_mode", "openai") == "anthropic":
                response_text = self._call_anthropic(base64_image, cfg)
            else:
                response_text = self._call_openai_compat(base64_image, cfg)

            # Parse JSON from response
            json_match = re.search(r'\{[^{}]*\}', response_text, re.DOTALL)
            raw = json_match.group(0) if json_match else response_text
            result = json.loads(raw)

            for field in ['invoice_number', 'vendor', 'invoicee_name', 'date',
                          'amount', 'tax', 'total', 'description']:
                result.setdefault(field, '')
                result[field] = str(result[field]).strip()

            Logger.info(f"InvoiceExtractor: extraction OK: {result}")
            return result

        except json.JSONDecodeError as e:
            Logger.error(f"InvoiceExtractor: JSON parse error: {e}")
            return {}
        except Exception as e:
            Logger.error(f"InvoiceExtractor: API call failed: {e}")
            raise   # re-raise so caller can show a useful error message

    def _call_openai_compat(self, base64_image, cfg):
        response = self.client.chat.completions.create(
            model=cfg.model,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": self._PROMPT},
                    {"type": "image_url",
                     "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}},
                ],
            }],
            max_tokens=500,
            temperature=0.1,
        )
        return response.choices[0].message.content.strip()

    def _call_anthropic(self, base64_image, cfg):
        response = self.client.messages.create(
            model=cfg.model,
            max_tokens=500,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image",
                     "source": {"type": "base64",
                                "media_type": "image/jpeg",
                                "data": base64_image}},
                    {"type": "text", "text": self._PROMPT},
                ],
            }],
        )
        return response.content[0].text.strip()

    def extract_invoice_data(self, image_path):
        """Public entry point."""
        if not self.client:
            Logger.warning("InvoiceExtractor: client not ready — check AI Settings")
            return {}
        return self.analyze_with_ai(image_path)


class CameraScreen(MDScreen):
    """Screen for taking photos of receipts/invoices"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = "camera"
        self.extractor = InvoiceExtractor()
        self.captured_image_path = None
        self.invoices = []
        self.current_filename = "noname.json"
        self.data_table = None
        self.has_unsaved_changes = False
        self.saved_invoices_state = []  # Track saved state to detect changes
        
        from kivy.metrics import dp
        from kivymd.uix.chip import MDChip

        # Main layout with top app bar
        main_layout = MDBoxLayout(orientation='vertical', spacing=0)
        
        # Top App Bar with menu
        self.top_app_bar = MDTopAppBar(
            title="Receipt Reader",
            elevation=4,
            md_bg_color=(0.0, 0.588, 0.533, 1),  # Teal 600
        )
        self.top_app_bar.left_action_items = [["menu", lambda x: self.open_menu(self.top_app_bar)]]
        self.top_app_bar.right_action_items = [
            ["content-save", lambda x: self.save_current_file(x)],
            ["folder-open", lambda x: self.open_file(x)],
        ]
        main_layout.add_widget(self.top_app_bar)
        
        # Main scroll view
        main_scroll = MDScrollView()
        layout = MDBoxLayout(orientation='vertical', padding=dp(16), spacing=dp(14), size_hint_y=None)
        layout.bind(minimum_height=layout.setter('height'))
        
        # ── File status row ──────────────────────────────────────────
        file_row = MDBoxLayout(orientation='horizontal', spacing=dp(8),
                               size_hint_y=None, height=dp(36))
        
        self.filename_label = MDLabel(
            text=f"📂  {self.current_filename}",
            theme_text_color="Secondary",
            halign="left",
            font_style="Caption",
            size_hint_y=None,
            height=dp(36),
        )
        file_row.add_widget(self.filename_label)
        
        new_file_chip = MDRaisedButton(
            text="New",
            on_press=self.new_file,
            size_hint=(None, None),
            size=(dp(72), dp(32)),
            font_size="12sp",
        )
        file_row.add_widget(new_file_chip)
        layout.add_widget(file_row)
        
        # ── Instructions ─────────────────────────────────────────────
        instructions = MDLabel(
            text="Point your camera at a receipt, or pick an image from your gallery.",
            theme_text_color="Secondary",
            halign="center",
            size_hint_y=None,
            height=dp(44),
        )
        layout.add_widget(instructions)
        
        # ── Camera/File button ────────────────────────────────────────
        self.camera_btn = MDRaisedButton(
            text="📷   Scan Receipt",
            size_hint=(0.85, None),
            height=dp(52),
            pos_hint={'center_x': 0.5},
            font_size="16sp",
            md_bg_color=(0.0, 0.588, 0.533, 1),
        )
        self.camera_btn.bind(on_press=self.take_photo)
        layout.add_widget(self.camera_btn)
        
        # ── Image preview ─────────────────────────────────────────────
        self.image_preview = Image(
            size_hint_y=None,
            height=dp(260),
            allow_stretch=True,
            keep_ratio=True,
        )
        layout.add_widget(self.image_preview)
        
        # ── Extract button (shown after photo is taken) ───────────────
        self.extract_btn = MDRaisedButton(
            text="✦  Read Receipt Data",
            size_hint=(0.75, None),
            height=dp(48),
            pos_hint={'center_x': 0.5},
            opacity=0,
            font_size="15sp",
            md_bg_color=(1.0, 0.6, 0.0, 1),  # Amber accent
        )
        self.extract_btn.bind(on_press=self.extract_data)
        layout.add_widget(self.extract_btn)
        
        # ── Export row ────────────────────────────────────────────────
        export_label = MDLabel(
            text="EXPORT",
            theme_text_color="Secondary",
            halign="left",
            font_style="Overline",
            size_hint_y=None,
            height=dp(24),
        )
        layout.add_widget(export_label)
        
        file_btn_layout = MDBoxLayout(orientation='horizontal', spacing=dp(8),
                                      size_hint_y=None, height=dp(44))
        
        self.export_csv_btn = MDRaisedButton(
            text="CSV",
            on_press=self.export_csv,
            size_hint_x=0.5,
        )
        file_btn_layout.add_widget(self.export_csv_btn)
        
        self.export_pdf_btn = MDRaisedButton(
            text="PDF",
            on_press=self.export_pdf,
            size_hint_x=0.5,
        )
        file_btn_layout.add_widget(self.export_pdf_btn)
        
        layout.add_widget(file_btn_layout)
        
        # ── Receipts table label ──────────────────────────────────────
        table_label = MDLabel(
            text="RECEIPTS IN THIS FILE",
            theme_text_color="Secondary",
            halign="left",
            font_style="Overline",
            size_hint_y=None,
            height=dp(32),
        )
        
        # Scroll view for table
        self.table_scroll = MDScrollView(size_hint_y=None, height=400)
        layout.add_widget(self.table_scroll)
        
        # Initialize table
        self.update_table()
        
        main_scroll.add_widget(layout)
        main_layout.add_widget(main_scroll)
        self.add_widget(main_layout)
        
        # Load last opened file or noname.json
        self.load_last_file()
    
    def open_menu(self, instance):
        """Open the menu"""
        def make_callback(item_name):
            def callback(*args):
                self.menu_callback(item_name)
            return callback
        
        cfg = AIConfig.get()
        ai_status = "✓ Configured" if cfg.is_configured else "⚠ Not configured"
        
        menu_items = [
            {
                "text": f"AI Settings  [{ai_status}]",
                "viewclass": "OneLineListItem",
                "on_release": make_callback("AI Settings"),
            },
            {
                "text": "About",
                "viewclass": "OneLineListItem",
                "on_release": make_callback("About"),
            },
        ]
        menu = MDDropdownMenu(
            caller=instance,
            items=menu_items,
            width_mult=5,
        )
        menu.open()
    
    def menu_callback(self, item):
        """Handle menu item selection"""
        if item == "About":
            self.show_about_dialog()
        elif item == "AI Settings":
            self.show_ai_settings_dialog()
    
    def show_ai_settings_dialog(self):
        """Dialog for configuring AI provider, model, API key and base URL."""
        from kivy.metrics import dp

        cfg = AIConfig.get()
        provider_names = list(AIConfig.PROVIDERS.keys())

        content = MDBoxLayout(
            orientation='vertical',
            spacing=dp(12),
            size_hint_y=None,
            padding=[dp(4), dp(4), dp(4), dp(4)],
        )
        content.bind(minimum_height=content.setter('height'))

        # ── Provider selector ────────────────────────────────────────
        prov_label = MDLabel(
            text="PROVIDER",
            theme_text_color="Secondary",
            font_style="Overline",
            halign="left",
            size_hint_y=None,
            height=dp(20),
        )
        content.add_widget(prov_label)

        # We'll use a simple MDTextField (read-only tap-to-cycle) for provider
        # because MDDropdownMenu inside a dialog needs extra care on mobile.
        # Instead: a row of flat buttons acting as a segmented control.
        prov_row = MDBoxLayout(orientation='horizontal', spacing=dp(4),
                               size_hint_y=None, height=dp(36))
        
        self._selected_provider = cfg.provider
        prov_buttons = {}

        def select_provider(name):
            self._selected_provider = name
            preset = AIConfig.PROVIDERS[name]
            # Pre-fill base_url and model only if fields are empty or were a preset
            if not base_url_field.text or any(
                    base_url_field.text == p["base_url"] for p in AIConfig.PROVIDERS.values()):
                base_url_field.text = preset["base_url"]
            if not model_field.text or any(
                    model_field.text == p["model"] for p in AIConfig.PROVIDERS.values()):
                model_field.text = preset["model"]
            notes_label.text = preset["notes"]
            # Update button styles
            for n, btn in prov_buttons.items():
                btn.md_bg_color = (0.0, 0.588, 0.533, 1) if n == name else (0.8, 0.8, 0.8, 1)

        for pname in provider_names:
            is_sel = (pname == cfg.provider)
            btn = MDRaisedButton(
                text=pname.split("/")[0].strip(),   # shorten "Custom / Local" -> "Custom"
                size_hint_x=1,
                font_size="11sp",
                md_bg_color=(0.0, 0.588, 0.533, 1) if is_sel else (0.8, 0.8, 0.8, 1),
            )
            prov_buttons[pname] = btn
            btn.bind(on_press=lambda inst, n=pname: select_provider(n))
            prov_row.add_widget(btn)

        content.add_widget(prov_row)

        # ── Notes label ──────────────────────────────────────────────
        notes_label = MDLabel(
            text=AIConfig.PROVIDERS[cfg.provider]["notes"],
            theme_text_color="Secondary",
            font_style="Caption",
            halign="left",
            size_hint_y=None,
            height=dp(32),
        )
        content.add_widget(notes_label)

        # ── API Key ──────────────────────────────────────────────────
        api_key_field = MDTextField(
            hint_text="API Key",
            text=cfg.api_key,
            password=True,
            size_hint_y=None,
            height=dp(56),
        )
        content.add_widget(api_key_field)

        # Toggle key visibility
        show_key_row = MDBoxLayout(orientation='horizontal', size_hint_y=None, height=dp(28))
        show_key_btn = MDFlatButton(
            text="Show key",
            font_size="12sp",
            size_hint_x=None,
            width=dp(90),
        )
        def toggle_key_visibility(inst):
            api_key_field.password = not api_key_field.password
            show_key_btn.text = "Hide key" if not api_key_field.password else "Show key"
        show_key_btn.bind(on_press=toggle_key_visibility)
        show_key_row.add_widget(show_key_btn)
        content.add_widget(show_key_row)

        # ── Model ────────────────────────────────────────────────────
        model_field = MDTextField(
            hint_text="Model name  (e.g. gpt-4o-mini)",
            text=cfg.model,
            size_hint_y=None,
            height=dp(56),
        )
        content.add_widget(model_field)

        # ── Base URL ─────────────────────────────────────────────────
        base_url_field = MDTextField(
            hint_text="Base URL  (e.g. https://api.openai.com/v1)",
            text=cfg.base_url,
            size_hint_y=None,
            height=dp(56),
        )
        content.add_widget(base_url_field)

        # ── Test status label ────────────────────────────────────────
        test_label = MDLabel(
            text="",
            theme_text_color="Secondary",
            font_style="Caption",
            halign="center",
            size_hint_y=None,
            height=dp(28),
        )
        content.add_widget(test_label)

        # ── Buttons ──────────────────────────────────────────────────
        def save_settings(inst):
            key = api_key_field.text.strip()
            model = model_field.text.strip()
            url = base_url_field.text.strip()
            if not key:
                test_label.text = "⚠  API key cannot be empty."
                test_label.theme_text_color = "Error"
                return
            if not model:
                test_label.text = "⚠  Model name cannot be empty."
                test_label.theme_text_color = "Error"
                return
            if not url:
                test_label.text = "⚠  Base URL cannot be empty."
                test_label.theme_text_color = "Error"
                return
            cfg.provider = self._selected_provider
            cfg.api_key = key
            cfg.model = model
            cfg.base_url = url
            cfg.save()
            # Reload the extractor with new settings
            self.extractor.reload()
            dialog.dismiss()
            self.show_info(
                f"AI settings saved.\n"
                f"Provider: {cfg.provider}\n"
                f"Model: {cfg.model}"
            )

        def test_connection(inst):
            test_label.text = "Testing…"
            test_label.theme_text_color = "Secondary"

            def do_test(dt):
                key = api_key_field.text.strip()
                model = model_field.text.strip()
                url = base_url_field.text.strip()
                provider = self._selected_provider

                if not key or not model or not url:
                    test_label.text = "⚠  Fill in all fields before testing."
                    test_label.theme_text_color = "Error"
                    return

                try:
                    if provider == "Anthropic Claude":
                        try:
                            import anthropic
                            client = anthropic.Anthropic(api_key=key)
                            client.messages.create(
                                model=model,
                                max_tokens=10,
                                messages=[{"role": "user", "content": "Hi"}],
                            )
                        except ImportError:
                            # Fall back to openai-compat
                            if not OPENAI_AVAILABLE:
                                raise RuntimeError("Neither anthropic nor openai SDK installed")
                            client = openai.OpenAI(api_key=key, base_url=url)
                            client.chat.completions.create(
                                model=model, messages=[{"role": "user", "content": "Hi"}], max_tokens=5
                            )
                    else:
                        if not OPENAI_AVAILABLE:
                            raise RuntimeError("openai SDK not installed")
                        client = openai.OpenAI(api_key=key, base_url=url)
                        client.chat.completions.create(
                            model=model, messages=[{"role": "user", "content": "Hi"}], max_tokens=5
                        )
                    test_label.text = "✓  Connection successful!"
                    test_label.theme_text_color = "Custom"
                    test_label.text_color = (0.0, 0.6, 0.2, 1)
                except Exception as e:
                    short = str(e)[:120]
                    test_label.text = f"✗  {short}"
                    test_label.theme_text_color = "Error"

            Clock.schedule_once(do_test, 0.1)

        dialog = MDDialog(
            title="AI Settings",
            type="custom",
            content_cls=content,
            buttons=[
                MDFlatButton(
                    text="Test Connection",
                    on_release=test_connection,
                ),
                MDFlatButton(
                    text="Cancel",
                    on_release=lambda x: dialog.dismiss(),
                ),
                MDRaisedButton(
                    text="Save",
                    on_release=save_settings,
                    md_bg_color=(0.0, 0.588, 0.533, 1),
                ),
            ],
            size_hint=(0.92, None),
        )
        dialog.open()
    
    def show_about_dialog(self):
        """Show About splash screen"""
        content = MDBoxLayout(orientation='vertical', spacing=20, size_hint_y=None, padding=30)
        content.bind(minimum_height=content.setter('height'))
        
        # App name
        app_name = MDLabel(
            text="Receipt Reader",
            theme_text_color="Primary",
            halign="center",
            font_style="H3",
            size_hint_y=None,
            height=60
        )
        content.add_widget(app_name)
        
        # Version
        version = MDLabel(
            text="Version 1.0.0",
            theme_text_color="Secondary",
            halign="center",
            font_style="H6",
            size_hint_y=None,
            height=40
        )
        content.add_widget(version)
        
        # Release date
        release_date = MDLabel(
            text=f"Release Date: {datetime.now().strftime('%B %d, %Y')}",
            theme_text_color="Secondary",
            halign="center",
            font_style="Body1",
            size_hint_y=None,
            height=30
        )
        content.add_widget(release_date)
        
        # Developer
        developer = MDLabel(
            text="Developer: GSI PK 2026",
            theme_text_color="Primary",
            halign="center",
            font_style="H6",
            size_hint_y=None,
            height=50
        )
        content.add_widget(developer)
        
        dialog = MDDialog(
            title="",
            type="custom",
            content_cls=content,
            buttons=[
                MDFlatButton(text="Close", on_release=lambda x: dialog.dismiss())
            ],
            size_hint=(0.8, None)
        )
        dialog.open()
    
    def take_photo(self, instance):
        """Take a photo using the device camera or file picker"""
        # On desktop/Windows, use file picker as fallback
        is_desktop = platform.system() in ['Windows', 'Linux', 'Darwin']
        
        if CAMERA_AVAILABLE and not is_desktop:
            # Try camera on mobile devices
            try:
                camera.take_picture(
                    filename=self.get_image_path(),
                    on_complete=self.on_camera_complete
                )
                return
            except Exception as e:
                Logger.error(f"Camera error: {e}")
                # Fall through to file picker
        
        # Use file picker for desktop or if camera fails
        self.show_file_picker()
    
    def get_image_path(self):
        """Get path for saving captured image"""
        app = MDApp.get_running_app()
        images_dir = app.get_images_directory()
        os.makedirs(images_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(images_dir, f"invoice_{timestamp}.jpg")
        return path
    
    def on_camera_complete(self, filename):
        """Callback when photo is taken"""
        if filename and os.path.exists(filename):
            self.captured_image_path = filename
            self.image_preview.source = filename
            self.image_preview.reload()
            self.extract_btn.opacity = 1
            Logger.info(f"Photo saved to: {filename}")
        else:
            self.show_error("Failed to capture photo")
    
    def extract_data(self, instance):
        """Extract invoice data from captured image"""
        if not self.captured_image_path:
            self.show_error("No image captured")
            return
        
        if not AIConfig.get().is_configured or not self.extractor.client:
            # AI not configured - show empty form for manual entry
            self.show_info(
                "AI is not configured. Open Menu → AI Settings to add your API key, "
                "or fill in the receipt details manually."
            )
            empty_data = {
                'invoice_number': '',
                'invoicee_name': '',
                'date': '',
                'amount': '',
                'tax': '',
                'total': '',
                'vendor': '',
                'description': '',
                'image_path': self.captured_image_path if self.captured_image_path else ''
            }
            self.show_extracted_data(empty_data)
            return
        
        # Show loading dialog
        dialog = MDDialog(
            text="Reading your receipt… this usually takes a few seconds.",
            auto_dismiss=False
        )
        dialog.open()
        
        def process_extraction(dt):
            try:
                # Extract invoice data using AI
                invoice_data = self.extractor.extract_invoice_data(self.captured_image_path)
                
                # Close loading dialog
                dialog.dismiss()
                
                if not invoice_data or not any(invoice_data.values()):
                    # If extraction failed or returned empty, show empty form
                    self.show_info("Could not extract data from image. Please enter data manually.")
                    empty_data = {
                        'invoice_number': '',
                        'invoicee_name': '',
                        'date': '',
                        'amount': '',
                        'tax': '',
                        'total': '',
                        'vendor': '',
                        'description': ''
                    }
                    self.show_extracted_data(empty_data)
                else:
                    # Show extracted data dialog
                    self.show_extracted_data(invoice_data)
            except Exception as e:
                dialog.dismiss()
                self.show_error(f"AI analysis failed: {e}. You can still enter data manually.")
                # Show empty form as fallback
                empty_data = {
                    'invoice_number': '',
                    'invoicee_name': '',
                    'date': '',
                    'amount': '',
                    'tax': '',
                    'total': '',
                    'vendor': '',
                    'description': ''
                }
                self.show_extracted_data(empty_data)
        
        Clock.schedule_once(process_extraction, 0.1)
    
    def show_extracted_data(self, data):
        """Show extracted data in a dialog for review/editing"""
        # Add image path to invoice data
        if self.captured_image_path:
            data['image_path'] = self.captured_image_path
        else:
            data['image_path'] = ''
        app = MDApp.get_running_app()
        app.show_edit_dialog(data, is_new=True, camera_screen=True)
        # Mark as unsaved when new receipt is added (will be saved when user saves)
        self.has_unsaved_changes = True
    
    def show_error(self, message):
        """Show error dialog"""
        dialog = MDDialog(
            text=message,
            buttons=[
                MDFlatButton(text="OK", on_release=lambda x: dialog.dismiss())
            ]
        )
        dialog.open()
    
    def show_info(self, message):
        """Show info dialog"""
        dialog = MDDialog(
            text=message,
            buttons=[
                MDFlatButton(text="OK", on_release=lambda x: dialog.dismiss())
            ]
        )
        dialog.open()
    
    def go_to_view(self, instance):
        """Navigate to view screen"""
        app = MDApp.get_running_app()
        app.root.current = "view"
    
    def go_to_save(self, instance):
        """Navigate to save screen"""
        app = MDApp.get_running_app()
        app.root.current = "save"
    
    def load_invoices(self, instance):
        """Load invoices from CSV file and merge with existing"""
        app = MDApp.get_running_app()
        app.show_file_picker(load=True, merge=True)
    
    def save_current_file(self, instance):
        """Save current invoices to the current file - ask for filename if needed"""
        app = MDApp.get_running_app()
        
        # If current file is noname.json, ask for filename
        if self.current_filename == "noname.json" or self.current_filename.endswith("noname.json"):
            self.show_save_as_dialog()
        else:
            # Save to current file
            filepath = app.get_json_path(self.current_filename.replace('.json', ''))
            try:
                app.save_invoices_to_json(self.invoices, filepath)
                self.has_unsaved_changes = False
                self.saved_invoices_state = [inv.copy() for inv in self.invoices]
                app.save_last_opened_file(self.current_filename)
                self.show_info(f"Saved {len(self.invoices)} receipts to {self.current_filename}")
            except Exception as e:
                self.show_error(f"Save failed: {e}")
    
    def show_save_as_dialog(self):
        """Show dialog to save file with a new name"""
        app = MDApp.get_running_app()
        
        content = MDBoxLayout(orientation='vertical', spacing=10, size_hint_y=None, height=120)
        
        filename_input = MDTextField(
            hint_text="Enter filename (without .json extension)",
            text=self.current_filename.replace('.json', ''),
            size_hint_y=None,
            height=60
        )
        content.add_widget(filename_input)
        
        def save_with_filename(instance):
            filename = filename_input.text.strip()
            if not filename:
                app.show_error("Please enter a filename")
                return
            
            filepath = app.get_json_path(filename)
            try:
                app.save_invoices_to_json(self.invoices, filepath)
                self.update_filename_label(filepath)
                self.has_unsaved_changes = False
                self.saved_invoices_state = [inv.copy() for inv in self.invoices]
                app.save_last_opened_file(self.current_filename)
                dialog.dismiss()
                self.show_info(f"Saved {len(self.invoices)} receipts to {self.current_filename}")
            except Exception as e:
                app.show_error(f"Save failed: {e}")
        
        dialog = MDDialog(
            title="Save File As",
            type="custom",
            content_cls=content,
            buttons=[
                MDFlatButton(text="Cancel", on_release=lambda x: dialog.dismiss()),
                MDRaisedButton(text="Save", on_release=save_with_filename)
            ],
            size_hint=(0.8, None)
        )
        dialog.open()
    
    def new_file(self, instance):
        """Create a new file"""
        # Check for unsaved changes
        if self.has_unsaved_changes:
            self.confirm_new_file()
        else:
            self.create_new_file()
    
    def confirm_new_file(self):
        """Confirm creating new file when there are unsaved changes"""
        content = MDBoxLayout(orientation='vertical', spacing=10, size_hint_y=None, height=100)
        
        message = MDLabel(
            text=f"Current file '{self.current_filename}' has unsaved changes. Save before creating new file?",
            theme_text_color="Primary",
            halign="center"
        )
        content.add_widget(message)
        
        def save_and_new(instance):
            dialog.dismiss()
            # Save current file
            app = MDApp.get_running_app()
            filepath = app.get_json_path(self.current_filename.replace('.json', ''))
            try:
                app.save_invoices_to_json(self.invoices, filepath)
                app.save_last_opened_file(self.current_filename)
                self.create_new_file()
            except Exception as e:
                self.show_error(f"Save failed: {e}")
        
        def discard_and_new(instance):
            dialog.dismiss()
            self.create_new_file()
        
        dialog = MDDialog(
            title="Unsaved Changes",
            type="custom",
            content_cls=content,
            buttons=[
                MDFlatButton(text="Cancel", on_release=lambda x: dialog.dismiss()),
                MDFlatButton(text="Don't Save", on_release=discard_and_new),
                MDRaisedButton(text="Save", on_release=save_and_new)
            ],
            size_hint=(0.8, None)
        )
        dialog.open()
    
    def create_new_file(self):
        """Create a new empty file"""
        self.invoices = []
        self.current_filename = "noname.json"
        self.has_unsaved_changes = False
        self.saved_invoices_state = []
        self.update_filename_label()
        self.update_table()
        app = MDApp.get_running_app()
        app.save_last_opened_file(self.current_filename)
    
    def open_file(self, instance):
        """Open a new file"""
        # Check for unsaved changes
        if self.has_unsaved_changes:
            self.confirm_open_file()
        else:
            app = MDApp.get_running_app()
            app.show_file_picker(load=True, merge=False, camera_screen=True)
    
    def confirm_open_file(self):
        """Confirm opening file when there are unsaved changes"""
        content = MDBoxLayout(orientation='vertical', spacing=10, size_hint_y=None, height=100)
        
        message = MDLabel(
            text=f"Current file '{self.current_filename}' has unsaved changes. Save before opening another file?",
            theme_text_color="Primary",
            halign="center"
        )
        content.add_widget(message)
        
        def save_and_open(instance):
            dialog.dismiss()
            # Save current file
            app = MDApp.get_running_app()
            filepath = app.get_json_path(self.current_filename.replace('.json', ''))
            try:
                app.save_invoices_to_json(self.invoices, filepath)
                app.save_last_opened_file(self.current_filename)
                app.show_file_picker(load=True, merge=False, camera_screen=True)
            except Exception as e:
                self.show_error(f"Save failed: {e}")
        
        def discard_and_open(instance):
            dialog.dismiss()
            app = MDApp.get_running_app()
            app.show_file_picker(load=True, merge=False, camera_screen=True)
        
        dialog = MDDialog(
            title="Unsaved Changes",
            type="custom",
            content_cls=content,
            buttons=[
                MDFlatButton(text="Cancel", on_release=lambda x: dialog.dismiss()),
                MDFlatButton(text="Don't Save", on_release=discard_and_open),
                MDRaisedButton(text="Save", on_release=save_and_open)
            ],
            size_hint=(0.8, None)
        )
        dialog.open()
    
    def export_csv(self, instance):
        """Export invoices to CSV"""
        if not self.invoices:
            self.show_error("No receipts to export")
            return
        app = MDApp.get_running_app()
        app.show_file_picker(load=False, export_format='csv', camera_screen=True)
    
    def export_pdf(self, instance):
        """Export invoices to PDF"""
        if not self.invoices:
            self.show_error("No receipts to export")
            return
        app = MDApp.get_running_app()
        app.show_file_picker(load=False, export_format='pdf', camera_screen=True)
    
    def update_table(self):
        """Update the data table with current invoices"""
        if self.data_table:
            self.table_scroll.remove_widget(self.data_table)
        
        columns = [
            ("Invoice #", 25),
            ("Vendor", 30),
            ("Invoicee", 25),
            ("Date", 20),
            ("Amount", 18),
            ("Tax", 15),
            ("Total", 18),
        ]
        
        rows = []
        total_amount = 0.0
        total_tax = 0.0
        total_total = 0.0
        
        # Store a mapping of row data to invoice index for reliable lookup
        self.row_to_invoice_map = {}
        
        for idx, inv in enumerate(self.invoices):
            # Parse and calculate totals using helper method
            amount = self.parse_number(inv.get('amount', ''))
            tax = self.parse_number(inv.get('tax', ''))
            total = self.parse_number(inv.get('total', ''))
            
            total_amount += amount
            total_tax += tax
            total_total += total
            
            # Create row tuple with consistent formatting
            row_tuple = (
                str(inv.get('invoice_number', '')),
                str(inv.get('vendor', '')),
                str(inv.get('invoicee_name', '')),
                str(inv.get('date', '')),
                str(inv.get('amount', '')),
                str(inv.get('tax', '')),
                str(inv.get('total', '')),
            )
            rows.append(row_tuple)
            # Store mapping for quick lookup
            self.row_to_invoice_map[row_tuple] = idx
        
        # Add totals row
        rows.append((
            "TOTALS",
            "",
            "",
            "",
            f"{total_amount:.2f}",
            f"{total_tax:.2f}",
            f"{total_total:.2f}",
        ))
        
        self.data_table = MDDataTable(
            column_data=columns,
            row_data=rows,
            use_pagination=True,
            rows_num=10,
            check=False,  # No checkboxes
            elevation=2,
        )
        
        # Bind row press event
        self.data_table.bind(on_row_press=self.on_row_press)
        self.table_scroll.add_widget(self.data_table)
    
    def parse_number(self, value):
        """Parse a number string, handling commas, dollar signs, and spaces"""
        if not value:
            return 0.0
        try:
            # Convert to string and clean
            str_value = str(value).strip()
            # Remove common currency symbols and spaces
            str_value = str_value.replace('$', '').replace(',', '').replace(' ', '').strip()
            if not str_value:
                return 0.0
            return float(str_value)
        except (ValueError, AttributeError, TypeError):
            # Try regex to extract number
            try:
                import re
                match = re.search(r'[\d.]+', str(value))
                if match:
                    return float(match.group())
            except:
                pass
            return 0.0
    
    def on_row_press(self, instance_table, instance_row):
        """Handle row press - open edit dialog directly"""
        try:
            # Get row data from the clicked row
            row_data = None
            if hasattr(instance_row, 'row_data'):
                row_data = instance_row.row_data
            
            # Check if this is the totals row
            if row_data and len(row_data) > 0:
                first_col = str(row_data[0]).strip().upper()
                if first_col == "TOTALS":
                    return  # Don't open edit dialog for totals row
            
            actual_index = None
            
            # Method 1: Use the row_to_invoice_map for direct lookup
            if row_data and hasattr(self, 'row_to_invoice_map'):
                # Convert row_data to tuple for lookup (handle both tuple and list)
                if isinstance(row_data, list):
                    row_tuple = tuple(str(x) for x in row_data)
                else:
                    row_tuple = row_data
                
                if row_tuple in self.row_to_invoice_map:
                    actual_index = self.row_to_invoice_map[row_tuple]
                    Logger.info(f"Found invoice index {actual_index} using row_to_invoice_map")
            
            # Method 2: Match by row data fields
            if actual_index is None and row_data and len(row_data) >= 4:
                invoice_num = str(row_data[0]).strip() if len(row_data) > 0 else ''
                vendor = str(row_data[1]).strip() if len(row_data) > 1 else ''
                invoicee = str(row_data[2]).strip() if len(row_data) > 2 else ''
                date = str(row_data[3]).strip() if len(row_data) > 3 else ''
                
                Logger.info(f"Row clicked - invoice_num: '{invoice_num}', vendor: '{vendor}', invoicee: '{invoicee}', date: '{date}'")
                
                # Find matching invoice
                for idx, inv in enumerate(self.invoices):
                    inv_num = str(inv.get('invoice_number', '')).strip()
                    inv_vendor = str(inv.get('vendor', '')).strip()
                    inv_invoicee = str(inv.get('invoicee_name', '')).strip()
                    inv_date = str(inv.get('date', '')).strip()
                    
                    if (inv_num == invoice_num and 
                        inv_vendor == vendor and 
                        inv_invoicee == invoicee and 
                        inv_date == date):
                        actual_index = idx
                        Logger.info(f"Matched row data to invoice at index {actual_index}")
                        break
            
            # Method 3: Use row index with pagination (fallback)
            if actual_index is None:
                row_index = None
                if hasattr(instance_row, 'index'):
                    row_index = instance_row.index
                    Logger.info(f"Got row_index from instance_row: {row_index}")
                
                if row_index is not None:
                    # Handle pagination
                    if instance_table.use_pagination:
                        try:
                            if hasattr(instance_table, 'table_data') and hasattr(instance_table.table_data, 'pagination'):
                                pagination = instance_table.table_data.pagination
                                current_page = 1
                                
                                # Get current page number
                                if hasattr(pagination, 'get_current_page'):
                                    current_page = pagination.get_current_page()
                                elif hasattr(pagination, 'current_page'):
                                    current_page = pagination.current_page
                                elif hasattr(pagination, 'page'):
                                    current_page = pagination.page
                                
                                rows_per_page = instance_table.rows_num
                                # row_index is 0-indexed within the current page
                                actual_index = (current_page - 1) * rows_per_page + row_index
                                Logger.info(f"Using pagination: page={current_page}, rows_per_page={rows_per_page}, row_index={row_index}, actual_index={actual_index}")
                            else:
                                actual_index = row_index
                        except Exception as e:
                            Logger.warning(f"Error handling pagination: {e}")
                            actual_index = row_index
                    else:
                        actual_index = row_index
            
            # Validate index
            if actual_index is None:
                Logger.error(f"Could not determine row index. row_data: {row_data}")
                return
            
            # Check if this is the totals row
            if actual_index >= len(self.invoices):
                Logger.info("Clicked on totals row, ignoring")
                return
            
            # Verify index is valid and open edit dialog
            if 0 <= actual_index < len(self.invoices):
                invoice = self.invoices[actual_index].copy()
                app = MDApp.get_running_app()
                Logger.info(f"Opening edit dialog for invoice at index {actual_index} (invoice_number: {invoice.get('invoice_number', 'N/A')})")
                app.show_edit_dialog(invoice, is_new=False, index=actual_index, camera_screen=True)
            else:
                Logger.warning(f"Invalid index: {actual_index}, total invoices: {len(self.invoices)}")
            
        except Exception as e:
            Logger.error(f"Error in on_row_press: {e}")
            import traceback
            Logger.error(traceback.format_exc())
            self.show_error(f"Error selecting receipt: {e}")
    
    def load_current_file(self):
        """Load the current file"""
        app = MDApp.get_running_app()
        filepath = app.get_json_path(self.current_filename.replace('.json', ''))
        if os.path.exists(filepath):
            try:
                self.invoices = app.load_invoices_from_json(filepath)
                self.saved_invoices_state = [inv.copy() for inv in self.invoices]
                self.has_unsaved_changes = False
                self.update_table()
            except Exception as e:
                Logger.error(f"Error loading file: {e}")
                self.invoices = []
                self.saved_invoices_state = []
                self.update_table()
        else:
            # Initialize empty list
            self.invoices = []
            self.saved_invoices_state = []
            self.has_unsaved_changes = False
            self.update_table()
    
    def load_last_file(self):
        """Load the last opened file"""
        app = MDApp.get_running_app()
        last_file = app.get_last_opened_file()
        if last_file:
            self.current_filename = last_file
            self.update_filename_label()
        self.load_current_file()
    
    def check_unsaved_changes(self):
        """Check if there are unsaved changes by comparing current state with saved state"""
        if len(self.invoices) != len(self.saved_invoices_state):
            return True
        
        # Compare each invoice
        for i, inv in enumerate(self.invoices):
            if i >= len(self.saved_invoices_state):
                return True
            saved_inv = self.saved_invoices_state[i]
            for key in ['invoice_number', 'vendor', 'invoicee_name', 'date', 'amount', 'tax', 'total', 'description', 'image_path']:
                if str(inv.get(key, '')) != str(saved_inv.get(key, '')):
                    return True
        return False
    
    def update_filename_label(self, filename=None):
        """Update the filename label"""
        if filename:
            self.current_filename = os.path.basename(filename)
            if not self.current_filename.endswith('.json'):
                if self.current_filename.endswith('.csv'):
                    self.current_filename = self.current_filename[:-4]
                self.current_filename += '.json'
        self.filename_label.text = f"📂  {self.current_filename}"
    
    def show_file_picker(self):
        """Show file picker to select an image file"""
        from kivy.uix.popup import Popup
        
        # Create file chooser
        filechooser = FileChooserIconView()
        filechooser.path = os.path.expanduser("~")
        filechooser.filters = ['*.png', '*.jpg', '*.jpeg', '*.bmp', '*.gif']
        
        content = MDBoxLayout(orientation='vertical', spacing=10, padding=10)
        content.add_widget(filechooser)
        
        btn_layout = MDBoxLayout(orientation='horizontal', spacing=10, size_hint_y=None, height=50)
        
        def select_file(instance):
            if filechooser.selection:
                selected_file = filechooser.selection[0]
                if os.path.isfile(selected_file):
                    # Use the selected file
                    self.on_camera_complete(selected_file)
                    popup.dismiss()
                else:
                    self.show_error("Please select a valid image file")
            else:
                self.show_error("Please select an image file")
        
        def cancel(instance):
            popup.dismiss()
        
        select_btn = MDRaisedButton(text="Select", size_hint_x=0.5)
        select_btn.bind(on_press=select_file)
        btn_layout.add_widget(select_btn)
        
        cancel_btn = MDFlatButton(text="Cancel", size_hint_x=0.5)
        cancel_btn.bind(on_press=cancel)
        btn_layout.add_widget(cancel_btn)
        
        content.add_widget(btn_layout)
        
        popup = Popup(
            title='Select Image File',
            content=content,
            size_hint=(0.9, 0.9),
            auto_dismiss=False
        )
        popup.open()


class ViewScreen(MDScreen):
    """Screen for viewing and editing invoice data"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = "view"
        self.data_table = None
        self.invoices = []
        self.current_filename = "noname.json"
        
        from kivy.metrics import dp
        
        main_layout = MDBoxLayout(orientation='vertical', spacing=0)
        
        # Top App Bar
        top_bar = MDTopAppBar(
            title="Records",
            elevation=4,
            md_bg_color=(0.0, 0.588, 0.533, 1),
        )
        top_bar.left_action_items = [["arrow-left", lambda x: self.go_to_camera(x)]]
        main_layout.add_widget(top_bar)
        
        layout = MDBoxLayout(orientation='vertical', padding=dp(12), spacing=dp(10))
        
        # Current file name label
        self.filename_label = MDLabel(
            text=f"📂  {self.current_filename}",
            theme_text_color="Secondary",
            halign="left",
            font_style="Caption",
            size_hint_y=None,
            height=dp(28),
        )
        layout.add_widget(self.filename_label)
        
        # Buttons layout
        btn_layout = MDBoxLayout(orientation='horizontal', spacing=dp(8),
                                 size_hint_y=None, height=dp(44))
        
        load_btn = MDRaisedButton(
            text="Load",
            on_press=self.load_csv,
            size_hint_x=0.25,
        )
        btn_layout.add_widget(load_btn)
        
        add_btn = MDRaisedButton(
            text="Add",
            on_press=self.add_invoice,
            size_hint_x=0.25,
        )
        btn_layout.add_widget(add_btn)
        
        edit_btn = MDRaisedButton(
            text="Edit",
            on_press=self.edit_selected,
            size_hint_x=0.25,
        )
        btn_layout.add_widget(edit_btn)
        
        save_btn = MDRaisedButton(
            text="Save",
            on_press=self.save_csv,
            size_hint_x=0.25,
            md_bg_color=(0.0, 0.588, 0.533, 1),
        )
        btn_layout.add_widget(save_btn)
        
        layout.add_widget(btn_layout)
        
        # Export section
        export_label = MDLabel(
            text="EXPORT",
            theme_text_color="Secondary",
            halign="left",
            font_style="Overline",
            size_hint_y=None,
            height=dp(22),
        )
        layout.add_widget(export_label)
        
        export_btn_layout = MDBoxLayout(orientation='horizontal', spacing=dp(8),
                                        size_hint_y=None, height=dp(44))
        
        export_csv_btn = MDRaisedButton(
            text="CSV",
            on_press=self.export_csv,
            size_hint_x=0.33,
        )
        export_btn_layout.add_widget(export_csv_btn)
        
        export_excel_btn = MDRaisedButton(
            text="Excel",
            on_press=self.export_excel,
            size_hint_x=0.33,
        )
        export_btn_layout.add_widget(export_excel_btn)
        
        export_pdf_btn = MDRaisedButton(
            text="PDF",
            on_press=self.export_pdf,
            size_hint_x=0.34,
        )
        export_btn_layout.add_widget(export_pdf_btn)
        
        layout.add_widget(export_btn_layout)
        
        # Scroll view for table
        self.scroll = MDScrollView()
        layout.add_widget(self.scroll)
        
        # Data table - will be created in update_table
        self.data_table = None
        self.update_table()
        
        main_layout.add_widget(layout)
        self.add_widget(main_layout)
    
    def update_filename_label(self, filename=None):
        """Update the filename label"""
        if filename:
            self.current_filename = os.path.basename(filename)
            if not self.current_filename.endswith('.json'):
                # Remove .csv if present, add .json
                if self.current_filename.endswith('.csv'):
                    self.current_filename = self.current_filename[:-4]
                self.current_filename += '.json'
        self.filename_label.text = f"📂  {self.current_filename}"
    
    def update_table(self):
        """Update the data table with current invoices"""
        if self.data_table:
            self.scroll.remove_widget(self.data_table)
        
        columns = [
            ("Invoice #", 25),
            ("Vendor", 30),
            ("Invoicee", 25),
            ("Date", 20),
            ("Amount", 18),
            ("Tax", 15),
            ("Total", 18),
        ]
        
        rows = []
        for inv in self.invoices:
            rows.append((
                str(inv.get('invoice_number', '')),
                str(inv.get('vendor', '')),
                str(inv.get('invoicee_name', '')),
                str(inv.get('date', '')),
                str(inv.get('amount', '')),
                str(inv.get('tax', '')),
                str(inv.get('total', '')),
            ))
        
        self.data_table = MDDataTable(
            column_data=columns,
            row_data=rows,
            use_pagination=True,
            rows_num=12,
            check=True,
            elevation=2,
        )
        
        self.data_table.bind(on_row_press=self.on_row_press)
        self.scroll.add_widget(self.data_table)
    
    def on_row_press(self, instance_table, instance_row):
        """Handle row press - show edit dialog"""
        try:
            # Get the row data tuple from the table
            row_data = instance_row.row_data if hasattr(instance_row, 'row_data') else None
            
            if row_data:
                # Find the invoice by matching the row data
                # Compare the row data tuple with our invoices
                for idx, inv in enumerate(self.invoices):
                    # Create a tuple from invoice data matching the table columns
                    inv_row = (
                        str(inv.get('invoice_number', '')),
                        str(inv.get('vendor', '')),
                        str(inv.get('invoicee_name', '')),
                        str(inv.get('date', '')),
                        str(inv.get('amount', '')),
                        str(inv.get('tax', '')),
                        str(inv.get('total', '')),
                    )
                    # Compare row data (handle potential type differences)
                    if tuple(str(x) for x in row_data) == tuple(str(x) for x in inv_row):
                        invoice = inv.copy()
                        app = MDApp.get_running_app()
                        app.show_edit_dialog(invoice, is_new=False, index=idx)
                        return
            
            # Fallback: try to get row index from table
            # Get the index from the row
            row_index = getattr(instance_row, 'index', None)
            if row_index is not None:
                # Account for pagination
                if instance_table.use_pagination and hasattr(instance_table, 'table_data'):
                    try:
                        pagination = instance_table.table_data.pagination
                        current_page = pagination.get_current_page() if hasattr(pagination, 'get_current_page') else 1
                        rows_per_page = instance_table.rows_num
                        # row_index is the index within the current page
                        actual_index = (current_page - 1) * rows_per_page + row_index
                        if 0 <= actual_index < len(self.invoices):
                            invoice = self.invoices[actual_index].copy()
                            app = MDApp.get_running_app()
                            app.show_edit_dialog(invoice, is_new=False, index=actual_index)
                            return
                    except Exception as e:
                        Logger.warning(f"Error getting pagination info: {e}")
                
                # If no pagination or pagination failed, use row_index directly
                if 0 <= row_index < len(self.invoices):
                    invoice = self.invoices[row_index].copy()
                    app = MDApp.get_running_app()
                    app.show_edit_dialog(invoice, is_new=False, index=row_index)
                    return
            
            # Final fallback: show error
            self.show_error("Could not identify the selected invoice")
            
        except Exception as e:
            Logger.error(f"Error in on_row_press: {e}")
            self.show_error(f"Error selecting invoice: {e}")
    
    def load_csv(self, instance):
        """Load invoices from CSV file"""
        app = MDApp.get_running_app()
        app.show_file_picker(load=True)
    
    def save_csv(self, instance):
        """Save invoices to CSV file"""
        if not self.invoices:
            self.show_error("No invoices to save")
            return
        app = MDApp.get_running_app()
        app.show_file_picker(load=False)
    
    def export_csv(self, instance):
        """Export invoices to CSV"""
        if not self.invoices:
            self.show_error("No invoices to export")
            return
        
        app = MDApp.get_running_app()
        app.show_file_picker(load=False, export_format='csv')
    
    def export_excel(self, instance):
        """Export invoices to Excel"""
        if not self.invoices:
            self.show_error("No invoices to export")
            return
        
        app = MDApp.get_running_app()
        app.show_file_picker(load=False, export_format='excel')
    
    def export_pdf(self, instance):
        """Export invoices to PDF"""
        if not self.invoices:
            self.show_error("No invoices to export")
            return
        
        app = MDApp.get_running_app()
        app.show_file_picker(load=False, export_format='pdf')
    
    def add_invoice(self, instance):
        """Add a new empty invoice"""
        new_invoice = {
            'invoice_number': '',
            'invoicee_name': '',
            'date': '',
            'amount': '',
            'tax': '',
            'total': '',
            'vendor': '',
            'description': '',
            'image_path': ''
        }
        app = MDApp.get_running_app()
        app.show_edit_dialog(new_invoice, is_new=True)
    
    def edit_selected(self, instance):
        """Edit the first selected invoice or show selection dialog"""
        if not self.invoices:
            self.show_error("No invoices to edit. Please add an invoice first.")
            return
        
        if not self.data_table:
            # If no table, just edit the first invoice
            invoice = self.invoices[0].copy()
            app = MDApp.get_running_app()
            app.show_edit_dialog(invoice, is_new=False, index=0)
            return
        
        # Try to get selected rows
        try:
            # Check if table has get_selected_rows method
            if hasattr(self.data_table, 'get_selected_rows'):
                selected_rows = self.data_table.get_selected_rows()
                if selected_rows and len(selected_rows) > 0:
                    selected_row = selected_rows[0]
                    if isinstance(selected_row, (list, tuple)) and len(selected_row) > 0:
                        row_index = selected_row[0]
                    else:
                        row_index = selected_row
                    
                    # Account for pagination
                    if self.data_table.use_pagination and hasattr(self.data_table, 'table_data'):
                        try:
                            pagination = self.data_table.table_data.pagination
                            current_page = pagination.get_current_page() if hasattr(pagination, 'get_current_page') else 1
                            rows_per_page = self.data_table.rows_num
                            row_index = (current_page - 1) * rows_per_page + row_index
                        except:
                            pass
                    
                    if 0 <= row_index < len(self.invoices):
                        invoice = self.invoices[row_index].copy()
                        app = MDApp.get_running_app()
                        app.show_edit_dialog(invoice, is_new=False, index=row_index)
                        return
        except Exception as e:
            Logger.warning(f"Could not get selected rows: {e}")
        
        # Fallback: show dialog to select which invoice to edit
        self.show_invoice_selector()
    
    def show_invoice_selector(self):
        """Show dialog to select which invoice to edit"""
        if not self.invoices:
            self.show_error("No invoices to edit")
            return
        
        content = MDBoxLayout(orientation='vertical', spacing=10, size_hint_y=None)
        scroll = MDScrollView()
        scroll_content = MDBoxLayout(orientation='vertical', spacing=10, size_hint_y=None)
        scroll_content.bind(minimum_height=scroll_content.setter('height'))
        
        for idx, invoice in enumerate(self.invoices):
            inv_num = invoice.get('invoice_number', 'N/A')
            vendor = invoice.get('vendor', 'N/A')
            total = invoice.get('total', 'N/A')
            btn_text = f"#{idx+1}: {inv_num} - {vendor} (${total})"
            
            btn = MDRaisedButton(
                text=btn_text,
                size_hint_y=None,
                height=50
            )
            
            def make_edit_handler(i):
                def edit_handler(instance):
                    inv = self.invoices[i].copy()
                    app = MDApp.get_running_app()
                    app.show_edit_dialog(inv, is_new=False, index=i)
                    dialog.dismiss()
                return edit_handler
            
            btn.bind(on_press=make_edit_handler(idx))
            scroll_content.add_widget(btn)
        
        scroll.add_widget(scroll_content)
        content.add_widget(scroll)
        
        dialog = MDDialog(
            title="Select Invoice to Edit",
            type="custom",
            content_cls=content,
            buttons=[
                MDFlatButton(text="Cancel", on_release=lambda x: dialog.dismiss())
            ],
            size_hint=(0.9, 0.8)
        )
        dialog.open()
    
    def show_error(self, message):
        """Show error dialog"""
        dialog = MDDialog(
            text=message,
            buttons=[
                MDFlatButton(text="OK", on_release=lambda x: dialog.dismiss())
            ]
        )
        dialog.open()
    
    def go_to_camera(self, instance):
        """Navigate to camera screen"""
        app = MDApp.get_running_app()
        app.root.current = "camera"


class SaveScreen(MDScreen):
    """Screen for saving/loading JSON files and exporting"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = "save"
        
        from kivy.metrics import dp
        
        main_outer = MDBoxLayout(orientation='vertical', spacing=0)
        
        top_bar = MDTopAppBar(
            title="File Management",
            elevation=4,
            md_bg_color=(0.0, 0.588, 0.533, 1),
        )
        top_bar.left_action_items = [["arrow-left", lambda x: self.go_to_camera(x)]]
        main_outer.add_widget(top_bar)
        
        # Main scroll view
        main_scroll = MDScrollView()
        layout = MDBoxLayout(orientation='vertical', padding=dp(20), spacing=dp(16), size_hint_y=None)
        layout.bind(minimum_height=layout.setter('height'))
        
        # File name input
        self.filename_input = MDTextField(
            hint_text="File name (without .json)",
            size_hint_y=None,
            height=dp(60),
        )
        layout.add_widget(self.filename_input)
        
        # Save/Load buttons
        btn_layout1 = MDBoxLayout(orientation='horizontal', spacing=dp(10),
                                  size_hint_y=None, height=dp(48))
        
        save_btn = MDRaisedButton(
            text="Save JSON",
            on_press=self.save_file,
            size_hint_x=0.5,
            md_bg_color=(0.0, 0.588, 0.533, 1),
        )
        btn_layout1.add_widget(save_btn)
        
        load_btn = MDRaisedButton(
            text="Load JSON",
            on_press=self.load_file,
            size_hint_x=0.5,
        )
        btn_layout1.add_widget(load_btn)
        
        layout.add_widget(btn_layout1)
        
        # Export buttons
        export_label = MDLabel(
            text="Export to:",
            theme_text_color="Secondary",
            halign="center",
            size_hint_y=None,
            height=30
        )
        layout.add_widget(export_label)
        
        # Export buttons in vertical layout for better visibility
        export_layout = MDBoxLayout(orientation='vertical', spacing=10, size_hint_y=None)
        export_layout.bind(minimum_height=export_layout.setter('height'))
        
        export_csv_btn = MDRaisedButton(
            text="Export to CSV",
            on_press=self.export_csv,
            size_hint_y=None,
            height=50
        )
        export_layout.add_widget(export_csv_btn)
        
        export_excel_btn = MDRaisedButton(
            text="Export to Excel",
            on_press=self.export_excel,
            size_hint_y=None,
            height=50
        )
        export_layout.add_widget(export_excel_btn)
        
        export_pdf_btn = MDRaisedButton(
            text="Export to PDF",
            on_press=self.export_pdf,
            size_hint_y=None,
            height=50
        )
        export_layout.add_widget(export_pdf_btn)
        
        layout.add_widget(export_layout)
        
        # Info label
        self.info_label = MDLabel(
            text="",
            theme_text_color="Secondary",
            halign="center",
            size_hint_y=None,
            height=100
        )
        layout.add_widget(self.info_label)
        
        main_scroll.add_widget(layout)
        main_outer.add_widget(main_scroll)
        self.add_widget(main_outer)
    
    def save_file(self, instance):
        """Save current invoices to JSON"""
        filename = self.filename_input.text.strip()
        if not filename:
            self.show_error("Please enter a filename")
            return
        
        app = MDApp.get_running_app()
        view_screen = app.root.get_screen("view")
        
        if not view_screen.invoices:
            self.show_error("No invoices to save")
            return
        
        try:
            filepath = app.get_json_path(filename)
            app.save_invoices_to_json(view_screen.invoices, filepath)
            view_screen.update_filename_label(filepath)
            self.info_label.text = f"Saved to: {filepath}"
        except Exception as e:
            self.show_error(f"Save failed: {e}")
    
    def load_file(self, instance):
        """Load invoices from JSON"""
        filename = self.filename_input.text.strip()
        if not filename:
            self.show_error("Please enter a filename")
            return
        
        app = MDApp.get_running_app()
        
        try:
            filepath = app.get_json_path(filename)
            invoices = app.load_invoices_from_json(filepath)
            
            view_screen = app.root.get_screen("view")
            view_screen.invoices = invoices
            view_screen.update_filename_label(filepath)
            view_screen.update_table()
            
            self.info_label.text = f"Loaded {len(invoices)} invoices from: {filepath}"
        except FileNotFoundError:
            self.show_error(f"File not found: {filename}.json")
        except Exception as e:
            self.show_error(f"Load failed: {e}")
    
    def export_csv(self, instance):
        """Export invoices to CSV"""
        filename = self.filename_input.text.strip()
        if not filename:
            self.show_error("Please enter a filename for export")
            return
        
        app = MDApp.get_running_app()
        view_screen = app.root.get_screen("view")
        
        if not view_screen.invoices:
            self.show_error("No invoices to export")
            return
        
        try:
            # Use CSV extension
            if not filename.endswith('.csv'):
                filename += '.csv'
            filepath = os.path.join(app.get_data_directory(), filename)
            app.export_invoices_to_csv(view_screen.invoices, filepath)
            self.info_label.text = f"Exported to CSV: {filepath}"
        except Exception as e:
            self.show_error(f"CSV export failed: {e}")
    
    def export_excel(self, instance):
        """Export invoices to Excel"""
        filename = self.filename_input.text.strip()
        if not filename:
            self.show_error("Please enter a filename for export")
            return
        
        app = MDApp.get_running_app()
        view_screen = app.root.get_screen("view")
        
        if not view_screen.invoices:
            self.show_error("No invoices to export")
            return
        
        try:
            # Use XLSX extension
            if not filename.endswith('.xlsx'):
                if filename.endswith('.xls'):
                    filename = filename[:-4] + '.xlsx'
                else:
                    filename += '.xlsx'
            filepath = os.path.join(app.get_data_directory(), filename)
            app.export_invoices_to_excel(view_screen.invoices, filepath)
            self.info_label.text = f"Exported to Excel: {filepath}"
        except ImportError as e:
            self.show_error(f"Excel export requires openpyxl. Install with: pip install openpyxl")
        except Exception as e:
            self.show_error(f"Excel export failed: {e}")
    
    def export_pdf(self, instance):
        """Export invoices to PDF with images"""
        filename = self.filename_input.text.strip()
        if not filename:
            self.show_error("Please enter a filename for export")
            return
        
        app = MDApp.get_running_app()
        view_screen = app.root.get_screen("view")
        
        if not view_screen.invoices:
            self.show_error("No invoices to export")
            return
        
        try:
            # Use PDF extension
            if not filename.endswith('.pdf'):
                if filename.endswith('.PDF'):
                    filename = filename[:-4] + '.pdf'
                else:
                    filename += '.pdf'
            filepath = os.path.join(app.get_data_directory(), filename)
            app.export_invoices_to_pdf(view_screen.invoices, filepath)
            self.info_label.text = f"Exported to PDF: {filepath}"
        except ImportError as e:
            self.show_error(f"PDF export requires reportlab. Install with: pip install reportlab")
        except Exception as e:
            self.show_error(f"PDF export failed: {e}")
    
    def show_error(self, message):
        """Show error dialog"""
        dialog = MDDialog(
            text=message,
            buttons=[
                MDFlatButton(text="OK", on_release=lambda x: dialog.dismiss())
            ]
        )
        dialog.open()
    
    def go_to_camera(self, instance):
        """Navigate to camera screen"""
        app = MDApp.get_running_app()
        app.root.current = "camera"


class ReceiptReaderApp(MDApp):
    """Main application class"""
    
    def build(self):
        """Build the app"""
        # Set theme — teal/green palette suits receipts & finance
        self.theme_cls.theme_style = "Light"
        self.theme_cls.primary_palette = "Teal"
        self.theme_cls.accent_palette = "Amber"
        
        # Create screen manager
        sm = MDScreenManager()
        sm.add_widget(CameraScreen())
        sm.add_widget(ViewScreen())
        sm.add_widget(SaveScreen())
        sm.current = "camera"  # Set initial screen
        return sm
    
    def on_start(self):
        """Called after build — show startup file dialog"""
        Clock.schedule_once(self._show_startup_dialog, 0.5)
    
    def _show_startup_dialog(self, dt):
        """Show startup dialog: continue last file or start new one"""
        last_file = self.get_last_opened_file()
        
        if not last_file or last_file == "noname.json":
            # No meaningful previous session — go straight to new file
            camera_screen = self.root.get_screen("camera")
            camera_screen.create_new_file()
            return
        
        # Strip .json for display
        display_name = last_file.replace('.json', '')
        
        # Check if last file actually exists on disk
        filepath = self.get_json_path(display_name)
        file_exists = os.path.exists(filepath)
        
        from kivy.metrics import dp
        from kivymd.uix.card import MDCard
        
        # Build dialog content
        content = MDBoxLayout(
            orientation='vertical',
            spacing=dp(16),
            size_hint_y=None,
            padding=[dp(4), dp(8), dp(4), dp(4)],
        )
        content.bind(minimum_height=content.setter('height'))
        
        if file_exists:
            subtitle_text = f"Continue with [b]{display_name}[/b] or start a brand-new file?"
        else:
            subtitle_text = "Start a new file for today's receipts."
        
        subtitle = MDLabel(
            text=subtitle_text,
            markup=True,
            theme_text_color="Secondary",
            halign="center",
            size_hint_y=None,
            height=dp(48),
        )
        content.add_widget(subtitle)
        
        def use_last(instance):
            dialog.dismiss()
            camera_screen = self.root.get_screen("camera")
            camera_screen.current_filename = last_file
            camera_screen.update_filename_label()
            camera_screen.load_current_file()
        
        def start_new(instance):
            dialog.dismiss()
            camera_screen = self.root.get_screen("camera")
            camera_screen.create_new_file()
        
        buttons = []
        if file_exists:
            buttons = [
                MDFlatButton(
                    text="New File",
                    theme_text_color="Custom",
                    text_color=self.theme_cls.primary_color,
                    on_release=start_new,
                ),
                MDRaisedButton(
                    text=f"Open  {display_name}",
                    on_release=use_last,
                    md_bg_color=self.theme_cls.primary_color,
                ),
            ]
        else:
            buttons = [
                MDRaisedButton(
                    text="Start New File",
                    on_release=start_new,
                    md_bg_color=self.theme_cls.primary_color,
                ),
            ]
        
        dialog = MDDialog(
            title="Welcome back!",
            type="custom",
            content_cls=content,
            buttons=buttons,
            size_hint=(0.88, None),
        )
        dialog.open()
    
    def get_data_directory(self):
        """Get directory for storing app data"""
        if hasattr(self, 'user_data_dir'):
            return self.user_data_dir
        # Fallback for desktop
        return os.path.join(os.path.expanduser("~"), "ReceiptReader")
    
    def get_images_directory(self):
        """Get directory for storing images"""
        return os.path.join(self.get_data_directory(), "images")
    
    def get_json_path(self, filename):
        """Get full path for JSON file"""
        if not filename.endswith('.json'):
            filename += '.json'
        return os.path.join(self.get_data_directory(), filename)
    
    def get_last_opened_file_path(self):
        """Get path to file storing last opened file name"""
        return os.path.join(self.get_data_directory(), ".last_file")
    
    def save_last_opened_file(self, filename):
        """Save the last opened file name"""
        try:
            last_file_path = self.get_last_opened_file_path()
            os.makedirs(os.path.dirname(last_file_path), exist_ok=True)
            with open(last_file_path, 'w', encoding='utf-8') as f:
                f.write(filename)
        except Exception as e:
            Logger.error(f"Failed to save last opened file: {e}")
    
    def get_last_opened_file(self):
        """Get the last opened file name"""
        try:
            last_file_path = self.get_last_opened_file_path()
            if os.path.exists(last_file_path):
                with open(last_file_path, 'r', encoding='utf-8') as f:
                    filename = f.read().strip()
                    if filename:
                        return filename
        except Exception as e:
            Logger.error(f"Failed to load last opened file: {e}")
        return None
    
    def get_project_images_directory(self, project_name):
        """Get directory for storing images for a specific project"""
        base_name = os.path.splitext(os.path.basename(project_name))[0]
        return os.path.join(self.get_data_directory(), "projects", base_name, "images")
    
    def save_invoices_to_json(self, invoices, filepath):
        """Save invoices to JSON file with image storage"""
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        # Get project images directory
        project_images_dir = self.get_project_images_directory(filepath)
        os.makedirs(project_images_dir, exist_ok=True)
        
        # Process invoices - copy images to project directory
        processed_invoices = []
        for invoice in invoices:
            processed_invoice = invoice.copy()
            image_path = invoice.get('image_path', '')
            
            if image_path and os.path.exists(image_path):
                # Copy image to project directory
                image_filename = os.path.basename(image_path)
                # Add timestamp to avoid conflicts
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                name, ext = os.path.splitext(image_filename)
                new_image_filename = f"{name}_{timestamp}{ext}"
                new_image_path = os.path.join(project_images_dir, new_image_filename)
                
                try:
                    shutil.copy2(image_path, new_image_path)
                    # Store relative path from project directory
                    processed_invoice['image_path'] = os.path.join("images", new_image_filename)
                except Exception as e:
                    Logger.error(f"Failed to copy image {image_path}: {e}")
                    processed_invoice['image_path'] = ''
            else:
                processed_invoice['image_path'] = ''
            
            processed_invoices.append(processed_invoice)
        
        # Save to JSON
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(processed_invoices, f, indent=2, ensure_ascii=False)
    
    def load_invoices_from_json(self, filepath):
        """Load invoices from JSON file"""
        invoices = []
        if not os.path.exists(filepath):
            return invoices
        
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if isinstance(data, list):
                invoices = data
            else:
                invoices = [data]
        
        # Convert relative image paths to absolute paths
        project_dir = os.path.dirname(filepath)
        for invoice in invoices:
            image_path = invoice.get('image_path', '')
            if image_path:
                # If it's a relative path, make it absolute
                if not os.path.isabs(image_path):
                    absolute_path = os.path.join(project_dir, image_path)
                    if os.path.exists(absolute_path):
                        invoice['image_path'] = absolute_path
                    else:
                        invoice['image_path'] = ''
                elif not os.path.exists(image_path):
                    invoice['image_path'] = ''
        
        return invoices
    
    def export_invoices_to_csv(self, invoices, filepath):
        """Export invoices to CSV file (without images)"""
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        fieldnames = ['invoice_number', 'vendor', 'invoicee_name', 'date', 
                     'amount', 'tax', 'total', 'description']
        
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for invoice in invoices:
                # Only write fields that are in fieldnames
                row = {k: invoice.get(k, '') for k in fieldnames}
                writer.writerow(row)
    
    def export_invoices_to_excel(self, invoices, filepath):
        """Export invoices to Excel file"""
        try:
            import openpyxl
            from openpyxl import Workbook
        except ImportError:
            raise ImportError("openpyxl is required for Excel export. Install with: pip install openpyxl")
        
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        wb = Workbook()
        ws = wb.active
        ws.title = "Invoices"
        
        # Headers
        headers = ['Invoice Number', 'Vendor', 'Invoicee Name', 'Date', 
                  'Amount', 'Tax', 'Total', 'Description']
        ws.append(headers)
        
        # Data rows
        for invoice in invoices:
            row = [
                invoice.get('invoice_number', ''),
                invoice.get('vendor', ''),
                invoice.get('invoicee_name', ''),
                invoice.get('date', ''),
                invoice.get('amount', ''),
                invoice.get('tax', ''),
                invoice.get('total', ''),
                invoice.get('description', '')
            ]
            ws.append(row)
        
        # Auto-adjust column widths
        for column in ws.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 50)
            ws.column_dimensions[column_letter].width = adjusted_width
        
        wb.save(filepath)
    
    def export_invoices_to_pdf(self, invoices, filepath):
        """Export invoices to PDF file with images in table format"""
        try:
            from reportlab.lib.pagesizes import letter, A4
            from reportlab.lib.units import inch
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as RLImage, PageBreak, Table, TableStyle, KeepTogether
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
            from reportlab.lib import colors
            from reportlab.platypus.flowables import HRFlowable
        except ImportError:
            raise ImportError("reportlab is required for PDF export. Install with: pip install reportlab")
        
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        # Create PDF document with margins
        doc = SimpleDocTemplate(filepath, pagesize=letter, 
                                rightMargin=0.5*inch, leftMargin=0.5*inch,
                                topMargin=0.5*inch, bottomMargin=0.5*inch)
        story = []
        
        # Define styles with word wrapping
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=18,
            textColor=colors.HexColor('#1976D2'),
            spaceAfter=30,
            alignment=TA_CENTER
        )
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#424242'),
            spaceAfter=12,
            spaceBefore=12,
            alignment=TA_CENTER
        )
        
        # Cell styles for word wrapping
        cell_style = ParagraphStyle(
            'CellStyle',
            parent=styles['Normal'],
            fontSize=9,
            leading=11,
            alignment=TA_LEFT,
            wordWrap='CJK'  # Enable word wrapping
        )
        
        cell_style_center = ParagraphStyle(
            'CellStyleCenter',
            parent=cell_style,
            alignment=TA_CENTER
        )
        
        cell_style_right = ParagraphStyle(
            'CellStyleRight',
            parent=cell_style,
            alignment=TA_RIGHT
        )
        
        normal_style = ParagraphStyle(
            'NormalStyle',
            parent=styles['Normal'],
            fontSize=10,
            alignment=TA_CENTER
        )
        
        # Title
        story.append(Paragraph("Receipt Report", title_style))
        story.append(Spacer(1, 0.2*inch))
        
        # Prepare data for table with word wrapping
        table_data = []
        # Header row
        table_data.append([
            Paragraph('<b>S.No.</b>', cell_style_center),
            Paragraph('<b>Invoice #</b>', cell_style_center),
            Paragraph('<b>Vendor</b>', cell_style_center),
            Paragraph('<b>Invoicee</b>', cell_style_center),
            Paragraph('<b>Date</b>', cell_style_center),
            Paragraph('<b>Amount</b>', cell_style_right),
            Paragraph('<b>Tax</b>', cell_style_right),
            Paragraph('<b>Total</b>', cell_style_right),
            Paragraph('<b>Image Ref</b>', cell_style_center)
        ])
        
        # Calculate totals
        total_amount = 0.0
        total_tax = 0.0
        total_total = 0.0
        
        # Store images with their serial numbers
        images_with_refs = []
        image_serial = 1
        
        # Helper function to parse numbers
        def parse_number(value):
            """Parse a number string, handling commas, dollar signs, and spaces"""
            if not value:
                return 0.0
            try:
                str_value = str(value).strip()
                str_value = str_value.replace('$', '').replace(',', '').replace(' ', '').strip()
                if not str_value:
                    return 0.0
                return float(str_value)
            except (ValueError, AttributeError, TypeError):
                try:
                    import re
                    match = re.search(r'[\d.]+', str(value))
                    if match:
                        return float(match.group())
                except:
                    pass
                return 0.0
        
        # Helper function to format number with commas
        def format_number(value):
            """Format a number with commas for display"""
            try:
                num = float(value) if isinstance(value, str) else value
                return f"{num:,.2f}"
            except:
                return str(value) if value else "0.00"
        
        # Add invoice rows with word wrapping
        for idx, invoice in enumerate(invoices, 1):
            # Get original values for display
            amount_orig = str(invoice.get('amount', '')).strip()
            tax_orig = str(invoice.get('tax', '')).strip()
            total_orig = str(invoice.get('total', '')).strip()
            
            # Parse numbers for calculation
            amount = parse_number(amount_orig)
            tax = parse_number(tax_orig)
            total = parse_number(total_orig)
            
            # Add to totals
            total_amount += amount
            total_tax += tax
            total_total += total
            
            # Check if image exists - try multiple path resolutions
            image_path = invoice.get('image_path', '')
            image_ref = ''
            resolved_image_path = None
            
            if image_path:
                # Try absolute path first
                if os.path.isabs(image_path) and os.path.exists(image_path):
                    resolved_image_path = image_path
                else:
                    # Try relative to data directory
                    data_dir = self.get_data_directory()
                    # Check if it's a relative path from project directory
                    possible_paths = [
                        os.path.join(data_dir, image_path),
                        os.path.join(data_dir, "projects", os.path.splitext(os.path.basename(filepath))[0], image_path),
                        image_path  # Try as-is
                    ]
                    
                    for path in possible_paths:
                        if os.path.exists(path):
                            resolved_image_path = path
                            break
                
                if resolved_image_path and os.path.exists(resolved_image_path):
                    image_ref = f"#{image_serial}"
                    images_with_refs.append((image_serial, resolved_image_path))
                    image_serial += 1
                else:
                    Logger.warning(f"Image not found: {image_path}")
            
            # Format amounts for display - use formatted number with commas
            amount_str = format_number(amount) if amount > 0 else (amount_orig if amount_orig else "0.00")
            tax_str = format_number(tax) if tax > 0 else (tax_orig if tax_orig else "0.00")
            total_str = format_number(total) if total > 0 else (total_orig if total_orig else "0.00")
            
            # Add row to table with word-wrapped cells
            table_data.append([
                Paragraph(str(idx), cell_style_center),
                Paragraph(str(invoice.get('invoice_number', '')), cell_style),
                Paragraph(str(invoice.get('vendor', '')), cell_style),
                Paragraph(str(invoice.get('invoicee_name', '')), cell_style),
                Paragraph(str(invoice.get('date', '')), cell_style_center),
                Paragraph(amount_str, cell_style_right),
                Paragraph(tax_str, cell_style_right),
                Paragraph(total_str, cell_style_right),
                Paragraph(image_ref, cell_style_center)
            ])
        
        # Add totals row - format with commas (using the same format_number function)
        totals_amount_str = format_number(total_amount)
        totals_tax_str = format_number(total_tax)
        totals_total_str = format_number(total_total)
        
        table_data.append([
            Paragraph('<b>TOTALS</b>', cell_style),
            Paragraph('', cell_style),
            Paragraph('', cell_style),
            Paragraph('', cell_style),
            Paragraph('', cell_style),
            Paragraph(f"<b>{totals_amount_str}</b>", cell_style_right),
            Paragraph(f"<b>{totals_tax_str}</b>", cell_style_right),
            Paragraph(f"<b>{totals_total_str}</b>", cell_style_right),
            Paragraph('', cell_style)
        ])
        
        # Create table with better column widths
        col_widths = [0.4*inch, 0.9*inch, 1.3*inch, 1.1*inch, 0.9*inch, 0.8*inch, 0.7*inch, 0.8*inch, 0.7*inch]
        table = Table(table_data, colWidths=col_widths, repeatRows=1)
        
        # Style the table
        table_style = TableStyle([
            # Header row
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1976D2')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('TOPPADDING', (0, 0), (-1, 0), 12),
            
            # Data rows
            ('BACKGROUND', (0, 1), (-1, -2), colors.white),
            ('TEXTCOLOR', (0, 1), (-1, -2), colors.black),
            ('FONTNAME', (0, 1), (-1, -2), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -2), 9),
            ('BOTTOMPADDING', (0, 1), (-1, -2), 8),
            ('TOPPADDING', (0, 1), (-1, -2), 8),
            ('LEFTPADDING', (0, 1), (-1, -2), 4),
            ('RIGHTPADDING', (0, 1), (-1, -2), 4),
            
            # Totals row
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#E3F2FD')),
            ('TEXTCOLOR', (0, -1), (-1, -1), colors.black),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, -1), (-1, -1), 10),
            ('BOTTOMPADDING', (0, -1), (-1, -1), 10),
            ('TOPPADDING', (0, -1), (-1, -1), 10),
            
            # Grid
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('LINEBELOW', (0, 0), (-1, 0), 2, colors.whitesmoke),
            ('LINEABOVE', (0, -1), (-1, -1), 2, colors.grey),
        ])
        
        table.setStyle(table_style)
        
        # Center the table
        from reportlab.platypus.flowables import Spacer as FlowableSpacer
        story.append(Spacer(1, 0.1*inch))
        story.append(table)
        story.append(Spacer(1, 0.3*inch))
        
        # Add images section if there are images
        if images_with_refs:
            story.append(PageBreak())
            story.append(Paragraph("Receipt Images", heading_style))
            story.append(Spacer(1, 0.3*inch))
            
            # Standard image size (4 inches width, maintain aspect ratio)
            standard_width = 4 * inch
            standard_height = 3 * inch  # 4:3 aspect ratio
            
            for serial, image_path in images_with_refs:
                try:
                    # Verify image exists
                    if not os.path.exists(image_path):
                        Logger.error(f"Image path does not exist: {image_path}")
                        error_style = ParagraphStyle('Error', parent=normal_style, textColor=colors.red)
                        story.append(Paragraph(f"Image {serial}: [Image file not found]", error_style))
                        story.append(Spacer(1, 0.2*inch))
                        continue
                    
                    if PIL_AVAILABLE:
                        # Open and resize image to standard size
                        img = PILImage.open(image_path)
                        img_width, img_height = img.size
                        
                        # Calculate size maintaining aspect ratio, fitting within standard dimensions
                        ratio = min(standard_width / img_width, standard_height / img_height)
                        new_width = img_width * ratio
                        new_height = img_height * ratio
                        
                        # Add centered image label with serial number
                        image_label_style = ParagraphStyle(
                            'ImageLabel',
                            parent=normal_style,
                            fontSize=12,
                            alignment=TA_CENTER,
                            spaceAfter=6
                        )
                        story.append(Paragraph(f"<b>Image {serial}</b>", image_label_style))
                        story.append(Spacer(1, 0.1*inch))
                        
                        # Add centered image to PDF using a table for centering
                        pdf_image = RLImage(image_path, width=new_width, height=new_height)
                        # Calculate available width
                        available_width = letter[0] - doc.leftMargin - doc.rightMargin
                        # Create a single-cell table to center the image
                        image_table = Table([[pdf_image]], colWidths=[available_width])
                        image_table.setStyle(TableStyle([
                            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                            ('LEFTPADDING', (0, 0), (-1, -1), 0),
                            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                            ('TOPPADDING', (0, 0), (-1, -1), 0),
                            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
                        ]))
                        story.append(image_table)
                        story.append(Spacer(1, 0.3*inch))
                    else:
                        # Try to add image directly with standard size
                        image_label_style = ParagraphStyle(
                            'ImageLabel',
                            parent=normal_style,
                            fontSize=12,
                            alignment=TA_CENTER,
                            spaceAfter=6
                        )
                        story.append(Paragraph(f"<b>Image {serial}</b>", image_label_style))
                        story.append(Spacer(1, 0.1*inch))
                        
                        pdf_image = RLImage(image_path, width=standard_width, height=standard_height)
                        # Center using table
                        available_width = letter[0] - doc.leftMargin - doc.rightMargin
                        image_table = Table([[pdf_image]], colWidths=[available_width])
                        image_table.setStyle(TableStyle([
                            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                            ('LEFTPADDING', (0, 0), (-1, -1), 0),
                            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                            ('TOPPADDING', (0, 0), (-1, -1), 0),
                            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
                        ]))
                        story.append(image_table)
                        story.append(Spacer(1, 0.3*inch))
                except Exception as e:
                    Logger.error(f"Failed to add image {image_path} to PDF: {e}")
                    error_style = ParagraphStyle('Error', parent=normal_style, textColor=colors.red)
                    story.append(Paragraph(f"Image {serial}: [Error loading image: {str(e)}]", error_style))
                    story.append(Spacer(1, 0.2*inch))
        
        # Build PDF
        doc.build(story)
    
    def show_edit_dialog(self, invoice_data, is_new=True, index=None, camera_screen=False):
        """Show dialog for editing invoice data"""
        content = MDBoxLayout(orientation='vertical', spacing=10, size_hint_y=None, height=500)
        scroll = MDScrollView()
        scroll_content = MDBoxLayout(orientation='vertical', spacing=10, size_hint_y=None)
        scroll_content.bind(minimum_height=scroll_content.setter('height'))
        
        fields = {
            'invoice_number': 'Invoice Number',
            'vendor': 'Vendor/Company',
            'invoicee_name': 'Invoicee Name',
            'date': 'Date',
            'amount': 'Amount',
            'tax': 'Tax',
            'total': 'Total',
            'description': 'Description'
        }
        
        text_fields = {}
        for key, label in fields.items():
            field = MDTextField(
                hint_text=label,
                text=str(invoice_data.get(key, '')),
                size_hint_y=None,
                height=60
            )
            text_fields[key] = field
            scroll_content.add_widget(field)
        
        scroll.add_widget(scroll_content)
        content.add_widget(scroll)
        
        def save_invoice(instance):
            # Get values from text fields
            updated_data = {}
            for key, field in text_fields.items():
                updated_data[key] = field.text.strip()
            
            # Preserve image_path if it exists in original data
            if 'image_path' in invoice_data:
                updated_data['image_path'] = invoice_data['image_path']
            else:
                updated_data['image_path'] = ''
            
            app = MDApp.get_running_app()
            
            if camera_screen:
                # Update camera screen
                camera_screen_obj = self.root.get_screen("camera")
                if is_new:
                    camera_screen_obj.invoices.append(updated_data)
                    camera_screen_obj.has_unsaved_changes = True
                else:
                    if index is not None:
                        camera_screen_obj.invoices[index] = updated_data
                        camera_screen_obj.has_unsaved_changes = True
                    else:
                        camera_screen_obj.invoices.append(updated_data)
                        camera_screen_obj.has_unsaved_changes = True
                
                camera_screen_obj.update_table()
                
                # Auto-save to current file (noname.json if no file is open)
                filepath = app.get_json_path(camera_screen_obj.current_filename.replace('.json', ''))
                app.save_invoices_to_json(camera_screen_obj.invoices, filepath)
                camera_screen_obj.has_unsaved_changes = False
                camera_screen_obj.saved_invoices_state = [inv.copy() for inv in camera_screen_obj.invoices]
                app.save_last_opened_file(camera_screen_obj.current_filename)
            else:
                # Update view screen (backward compatibility)
                view_screen = self.root.get_screen("view")
                if is_new:
                    view_screen.invoices.append(updated_data)
                else:
                    if index is not None:
                        view_screen.invoices[index] = updated_data
                    else:
                        view_screen.invoices.append(updated_data)
                
                view_screen.update_table()
            
            dialog.dismiss()
        
        def delete_invoice(instance):
            app = MDApp.get_running_app()
            
            if not is_new and index is not None:
                # Confirm deletion
                def confirm_delete(confirm_instance):
                    if camera_screen:
                        camera_screen_obj = self.root.get_screen("camera")
                        camera_screen_obj.invoices.pop(index)
                        camera_screen_obj.has_unsaved_changes = True
                        camera_screen_obj.update_table()
                        # Auto-save to current file
                        camera_screen_obj.save_current_file(None)
                    else:
                        view_screen = self.root.get_screen("view")
                        view_screen.invoices.pop(index)
                        view_screen.update_table()
                    
                    confirm_dialog.dismiss()
                    dialog.dismiss()
                    app.show_success("Receipt deleted successfully")
                
                confirm_content = MDBoxLayout(orientation='vertical', spacing=10, size_hint_y=None, height=80)
                message = MDLabel(
                    text="Are you sure you want to delete this receipt?",
                    theme_text_color="Primary",
                    halign="center"
                )
                confirm_content.add_widget(message)
                
                confirm_dialog = MDDialog(
                    title="Confirm Delete",
                    type="custom",
                    content_cls=confirm_content,
                    buttons=[
                        MDFlatButton(text="Cancel", on_release=lambda x: confirm_dialog.dismiss()),
                        MDRaisedButton(text="Delete", on_release=confirm_delete, md_bg_color=(1, 0, 0, 1))
                    ],
                    size_hint=(0.8, None)
                )
                confirm_dialog.open()
            else:
                # If it's a new invoice, just close the dialog
                dialog.dismiss()
        
        def cancel_edit(instance):
            dialog.dismiss()
        
        dialog = MDDialog(
            title="Edit Invoice Data",
            type="custom",
            content_cls=content,
            buttons=[
                MDFlatButton(text="Cancel", on_release=cancel_edit),
                MDRaisedButton(text="Delete", on_release=delete_invoice, md_bg_color=(1, 0, 0, 1)),
                MDRaisedButton(text="Save", on_release=save_invoice)
            ],
            size_hint=(0.9, 0.9)
        )
        dialog.open()
    
    def show_file_picker(self, load=True, merge=False, export_format=None, camera_screen=False):
        """Show file picker dialog with folder navigation"""
        from kivy.uix.popup import Popup
        
        # Create file chooser
        filechooser = FileChooserIconView()
        
        # Determine file extension and filters based on export format
        if export_format == 'csv':
            file_ext = '.csv'
            file_filter = ['*.csv']
            hint_text = "Enter filename (without .csv extension)"
        elif export_format == 'excel':
            file_ext = '.xlsx'
            file_filter = ['*.xlsx', '*.xls']
            hint_text = "Enter filename (without .xlsx extension)"
        elif export_format == 'pdf':
            file_ext = '.pdf'
            file_filter = ['*.pdf']
            hint_text = "Enter filename (without .pdf extension)"
        else:
            file_ext = '.json'
            file_filter = ['*.json']
            hint_text = "Enter filename (without .json extension)"
        
        # Set initial path
        if load:
            # For loading, start in data directory
            initial_path = self.get_data_directory()
            if not os.path.exists(initial_path):
                initial_path = os.path.expanduser("~")
            filechooser.path = initial_path
            filechooser.filters = ['*.json']  # Only show JSON files for loading
        else:
            # For saving/exporting, start in data directory
            initial_path = self.get_data_directory()
            if not os.path.exists(initial_path):
                os.makedirs(initial_path, exist_ok=True)
            filechooser.path = initial_path
            filechooser.filters = file_filter
        
        path_label = MDLabel(
            text=filechooser.path,
            theme_text_color="Secondary",
            halign="left",
            shorten=True,
            shorten_from="left",
            size_hint_y=None,
            height=40,
        )
        filechooser.bind(path=lambda instance, value: setattr(path_label, 'text', value))

        content = MDBoxLayout(orientation='vertical', spacing=10, padding=10)
        content.add_widget(path_label)
        content.add_widget(filechooser)
        
        # Filename input for save/export
        filename_input = None
        if not load:
            filename_input = MDTextField(
                hint_text=hint_text,
                size_hint_y=None,
                height=50
            )
            content.add_widget(filename_input)
        
        btn_layout = MDBoxLayout(orientation='horizontal', spacing=10, size_hint_y=None, height=50)
        
        def process_file(instance):
            if load:
                # Loading: use selected file
                if filechooser.selection:
                    selected_file = filechooser.selection[0]
                    if os.path.isfile(selected_file) and selected_file.endswith('.json'):
                        try:
                            loaded_invoices = self.load_invoices_from_json(selected_file)
                            
                            if camera_screen:
                                # Update camera screen
                                camera_screen_obj = self.root.get_screen("camera")
                                if merge:
                                    # Merge with existing invoices (avoid duplicates)
                                    existing_invoices = camera_screen_obj.invoices.copy()
                                    existing_ids = {(inv.get('invoice_number', ''), inv.get('date', '')) for inv in existing_invoices}
                                    
                                    # Add only new invoices
                                    new_count = 0
                                    for inv in loaded_invoices:
                                        inv_id = (inv.get('invoice_number', ''), inv.get('date', ''))
                                        if inv_id not in existing_ids:
                                            existing_invoices.append(inv)
                                            existing_ids.add(inv_id)
                                            new_count += 1
                                    
                                    camera_screen_obj.invoices = existing_invoices
                                    camera_screen_obj.has_unsaved_changes = True
                                    popup.dismiss()
                                    if new_count > 0:
                                        self.show_success(f"Added {new_count} new receipts. Total: {len(existing_invoices)} receipts")
                                    else:
                                        self.show_info("No new receipts to add. All receipts already exist.")
                                else:
                                    # Replace existing invoices
                                    camera_screen_obj.invoices = loaded_invoices
                                    camera_screen_obj.saved_invoices_state = [inv.copy() for inv in loaded_invoices]
                                    camera_screen_obj.has_unsaved_changes = False
                                    camera_screen_obj.update_filename_label(selected_file)
                                    # Save last opened file
                                    filename = os.path.basename(selected_file)
                                    self.save_last_opened_file(filename)
                                    popup.dismiss()
                                    self.show_success(f"Loaded {len(loaded_invoices)} receipts from {filename}")
                                
                                camera_screen_obj.update_table()
                            else:
                                # Update view screen (backward compatibility)
                                view_screen = self.root.get_screen("view")
                                if merge:
                                    # Merge with existing invoices (avoid duplicates)
                                    existing_invoices = view_screen.invoices.copy()
                                    existing_ids = {(inv.get('invoice_number', ''), inv.get('date', '')) for inv in existing_invoices}
                                    
                                    # Add only new invoices
                                    new_count = 0
                                    for inv in loaded_invoices:
                                        inv_id = (inv.get('invoice_number', ''), inv.get('date', ''))
                                        if inv_id not in existing_ids:
                                            existing_invoices.append(inv)
                                            existing_ids.add(inv_id)
                                            new_count += 1
                                    
                                    view_screen.invoices = existing_invoices
                                    popup.dismiss()
                                    if new_count > 0:
                                        self.show_success(f"Added {new_count} new invoices. Total: {len(existing_invoices)} invoices")
                                    else:
                                        self.show_info("No new invoices to add. All invoices already exist.")
                                else:
                                    # Replace existing invoices
                                    view_screen.invoices = loaded_invoices
                                    view_screen.update_filename_label(selected_file)
                                    popup.dismiss()
                                    self.show_success(f"Loaded {len(loaded_invoices)} invoices from {os.path.basename(selected_file)}")
                                
                                view_screen.update_table()
                        except Exception as e:
                            self.show_error(f"Error loading file: {e}")
                    else:
                        self.show_error("Please select a valid JSON file")
                else:
                    self.show_error("Please select a JSON file to load")
            else:
                # Saving/Exporting: use filename input or selected file
                filename = ""
                if filename_input:
                    filename = filename_input.text.strip()
                
                # Determine filepath
                if filename:
                    # Use provided filename
                    if not filename.endswith(file_ext):
                        filename += file_ext
                    filepath = os.path.join(filechooser.path, filename)
                elif filechooser.selection:
                    # Use selected file/directory
                    selected = filechooser.selection[0]
                    if os.path.isfile(selected) and selected.endswith(file_ext):
                        filepath = selected
                    else:
                        # Directory selected, use default name
                        default_name = f"invoices{file_ext}"
                        filepath = os.path.join(selected if os.path.isdir(selected) else filechooser.path, default_name)
                else:
                    # No selection, use default name in current directory
                    default_name = f"invoices{file_ext}"
                    filepath = os.path.join(filechooser.path, default_name)
                
                try:
                    if camera_screen:
                        # Use camera screen invoices
                        camera_screen_obj = self.root.get_screen("camera")
                        if not camera_screen_obj.invoices:
                            self.show_error("No receipts to save/export")
                            return
                        
                        # Handle different export formats
                        if export_format == 'csv':
                            self.export_invoices_to_csv(camera_screen_obj.invoices, filepath)
                            popup.dismiss()
                            self.show_success(f"Exported {len(camera_screen_obj.invoices)} receipts to CSV: {os.path.basename(filepath)}")
                        elif export_format == 'excel':
                            self.export_invoices_to_excel(camera_screen_obj.invoices, filepath)
                            popup.dismiss()
                            self.show_success(f"Exported {len(camera_screen_obj.invoices)} receipts to Excel: {os.path.basename(filepath)}")
                        elif export_format == 'pdf':
                            self.export_invoices_to_pdf(camera_screen_obj.invoices, filepath)
                            popup.dismiss()
                            self.show_success(f"Exported {len(camera_screen_obj.invoices)} receipts to PDF: {os.path.basename(filepath)}")
                        else:
                            # Default: save as JSON
                            self.save_invoices_to_json(camera_screen_obj.invoices, filepath)
                            camera_screen_obj.update_filename_label(filepath)
                            popup.dismiss()
                            self.show_success(f"Saved {len(camera_screen_obj.invoices)} receipts to {os.path.basename(filepath)}")
                    else:
                        # Use view screen invoices (backward compatibility)
                        view_screen = self.root.get_screen("view")
                        if not view_screen.invoices:
                            self.show_error("No invoices to save/export")
                            return
                        
                        # Handle different export formats
                        if export_format == 'csv':
                            self.export_invoices_to_csv(view_screen.invoices, filepath)
                            popup.dismiss()
                            self.show_success(f"Exported {len(view_screen.invoices)} invoices to CSV: {os.path.basename(filepath)}")
                        elif export_format == 'excel':
                            self.export_invoices_to_excel(view_screen.invoices, filepath)
                            popup.dismiss()
                            self.show_success(f"Exported {len(view_screen.invoices)} invoices to Excel: {os.path.basename(filepath)}")
                        elif export_format == 'pdf':
                            self.export_invoices_to_pdf(view_screen.invoices, filepath)
                            popup.dismiss()
                            self.show_success(f"Exported {len(view_screen.invoices)} invoices to PDF: {os.path.basename(filepath)}")
                        else:
                            # Default: save as JSON
                            self.save_invoices_to_json(view_screen.invoices, filepath)
                            view_screen.update_filename_label(filepath)
                            popup.dismiss()
                            self.show_success(f"Saved {len(view_screen.invoices)} invoices to {os.path.basename(filepath)}")
                except ImportError as e:
                    popup.dismiss()
                    if 'openpyxl' in str(e):
                        self.show_error(f"Excel export requires openpyxl. Install with: pip install openpyxl")
                    elif 'reportlab' in str(e):
                        self.show_error(f"PDF export requires reportlab. Install with: pip install reportlab")
                    else:
                        self.show_error(f"Export failed: {e}")
                except Exception as e:
                    popup.dismiss()
                    self.show_error(f"Error saving/exporting file: {e}")
        
        def cancel(instance):
            popup.dismiss()
        
        # Determine button text
        if load:
            btn_text = "Load"
        elif export_format:
            btn_text = f"Export {export_format.upper()}"
        else:
            btn_text = "Save"
        
        action_btn = MDRaisedButton(
            text=btn_text,
            size_hint_x=0.5,
            on_press=process_file
        )
        btn_layout.add_widget(action_btn)
        
        cancel_btn = MDFlatButton(
            text="Cancel",
            size_hint_x=0.5,
            on_press=cancel
        )
        btn_layout.add_widget(cancel_btn)
        
        content.add_widget(btn_layout)
        
        # Determine popup title
        if load:
            popup_title = 'Select JSON File'
        elif export_format == 'csv':
            popup_title = 'Export to CSV'
        elif export_format == 'excel':
            popup_title = 'Export to Excel'
        elif export_format == 'pdf':
            popup_title = 'Export to PDF'
        else:
            popup_title = 'Save JSON File'
        
        popup = Popup(
            title=popup_title,
            content=content,
            size_hint=(0.9, 0.9),
            auto_dismiss=False
        )
        popup.open()
    
    def show_error(self, message):
        """Show error dialog"""
        dialog = MDDialog(
            title="Something went wrong",
            text=message,
            buttons=[
                MDRaisedButton(text="OK", on_release=lambda x: dialog.dismiss())
            ]
        )
        dialog.open()
    
    def show_success(self, message):
        """Show success dialog"""
        dialog = MDDialog(
            title="Done",
            text=message,
            buttons=[
                MDRaisedButton(text="OK", on_release=lambda x: dialog.dismiss())
            ]
        )
        dialog.open()
    
    def show_info(self, message):
        """Show info dialog"""
        dialog = MDDialog(
            text=message,
            buttons=[
                MDFlatButton(text="OK", on_release=lambda x: dialog.dismiss())
            ]
        )
        dialog.open()


if __name__ == "__main__":
    ReceiptReaderApp().run()
