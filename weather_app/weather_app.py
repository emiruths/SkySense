import customtkinter as ctk
from PIL import Image
import os
import pandas as pd
from difflib import get_close_matches
from datetime import datetime, timezone, timedelta 
import geocoder
import threading
import requests
import sys
from collections import defaultdict
import locale

# --- Tema ve Genel Ayarlar ---
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

class UltimateWeatherApp(ctk.CTk):
    API_KEY = "YOUR_API_KEY"

    def __init__(self):
        super().__init__()
        self.title("🔥 Ultimate Weather App (Yerel İkonlar)")
        self.geometry("900x600")
        self.resizable(False, False)
        
        try:
            locale.setlocale(locale.LC_TIME, 'tr_TR.UTF-8')
        except locale.Error:
            try:
                locale.setlocale(locale.LC_TIME, 'tr_TR') 
            except locale.Error:
                print("Uyarı: Türkçe lokal 'tr_TR' bulunamadı. Varsayılan (İngilizce) kullanılacak.")
                locale.setlocale(locale.LC_TIME, 'C') 

        self.city_list = self._load_city_data()
        self.current_theme = ctk.get_appearance_mode().lower()
        self._anim_id = None
        self.current_timezone_offset = int(datetime.now(timezone.utc).astimezone().utcoffset().total_seconds())

        self.load_local_icons()

        self.setup_ui_frames()
        self.setup_left_frame_widgets()
        self.setup_right_frame_widgets()
        
        self.after(500, self.auto_location_weather_threaded)
        self.update_clock()

    def _load_city_data(self):
        try:
            base_dir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
            file_path = os.path.join(base_dir, "worldcities.csv")
            cities_df = pd.read_csv(file_path)
            return cities_df["city"].dropna().unique().tolist()
        except Exception as e:
            print(f"HATA: 'worldcities.csv' yüklenemedi: {e}")
            return []

    def load_local_icons(self):
        self.weather_icons = {}
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")
        icon_files = ["day_clear", "night_clear", "partly_cloudy_day", "partly_cloudy_night", "cloudy", "rain", "snow", "mist", "thunderstorm", "unknown"]
        for name in icon_files:
            try:
                pil_image = Image.open(os.path.join(icon_path, f"{name}.png"))
                self.weather_icons[name] = ctk.CTkImage(light_image=pil_image, dark_image=pil_image, size=(120, 120))
                self.weather_icons[f"{name}_small"] = ctk.CTkImage(light_image=pil_image, dark_image=pil_image, size=(40, 40))
            except FileNotFoundError:
                print(f"Uyarı: '{name}.png' ikonu 'icons' klasöründe bulunamadı.")
                self.weather_icons[name] = None
                self.weather_icons[f"{name}_small"] = None

    def setup_ui_frames(self):
        self.left_frame = ctk.CTkFrame(self, width=280, corner_radius=20)
        self.left_frame.pack(side="left", fill="y", padx=20, pady=20)
        self.left_frame.pack_propagate(False)
        
        self.right_frame = ctk.CTkFrame(self, corner_radius=20, fg_color="#1f1f1f")
        self.right_frame.pack(side="right", fill="both", expand=True, padx=(0, 20), pady=20)
        self.right_frame.pack_propagate(False)

    def setup_left_frame_widgets(self):
        self.search_label = ctk.CTkLabel(self.left_frame, text="🌍 Şehir Ara", font=("Arial", 22, "bold"))
        self.search_label.pack(pady=(30, 10))

        self.city_entry = ctk.CTkEntry(self.left_frame, placeholder_text="Bir şehir giriniz...")
        self.city_entry.pack(pady=5, padx=20, fill="x")
        self.city_entry.bind("<KeyRelease>", self.show_suggestions)

        self.suggestion_frame = ctk.CTkFrame(self.left_frame, fg_color="transparent")
        self.suggestion_frame.pack(pady=5, padx=20, fill="x")
        self.suggestion_buttons = []

        self.search_button = ctk.CTkButton(self.left_frame, text="🔍 Ara", command=self.search_weather_threaded)
        self.search_button.pack(pady=10, padx=20, fill="x")

        theme_button_text = "☀️ Açık Tema" if self.current_theme == "dark" else "🌙 Koyu Tema"
        self.mode_button = ctk.CTkButton(self.left_frame, text=theme_button_text, command=self.toggle_theme)
        self.mode_button.pack(side="bottom", pady=20, padx=20, fill="x")

    def setup_right_frame_widgets(self):
        self.top_right_frame = ctk.CTkFrame(self.right_frame, fg_color="transparent")
        self.top_right_frame.place(relx=0.98, rely=0.05, anchor="ne")

        # 🕒 SAAT
        self.clock_label = ctk.CTkLabel(self.top_right_frame, text="", font=("Arial", 14), justify="right")
        self.clock_label.pack(pady=(0, 10))

        # 📍 KONUM YENİLE BUTONU — saat altına alındı
        self.refresh_button = ctk.CTkButton(self.top_right_frame, text="📍 Konumu Yenile", width=120, command=self.auto_location_weather_threaded)
        self.refresh_button.pack()

        self.city_label = ctk.CTkLabel(self.right_frame, text="🌎 Konum Bilgisi Alınıyor...", font=("Arial", 32, "bold"))
        self.city_label.pack(pady=(40, 5))

        self.icon_label = ctk.CTkLabel(self.right_frame, text="")
        self.icon_label.pack()

        self.temp_label = ctk.CTkLabel(self.right_frame, text="", font=("Arial", 60, "bold"))
        self.temp_label.pack()

        self.description_label = ctk.CTkLabel(self.right_frame, text="", font=("Arial", 22))
        self.description_label.pack(pady=(5, 15))

        self.details_frame = ctk.CTkFrame(self.right_frame, fg_color="transparent")
        self.details_frame.pack(pady=(0, 20))

        self.feels_like_label = ctk.CTkLabel(self.details_frame, text="", font=("Arial", 16))
        self.feels_like_label.grid(row=0, column=0, padx=15, pady=5)
        self.humidity_label = ctk.CTkLabel(self.details_frame, text="", font=("Arial", 16))
        self.humidity_label.grid(row=0, column=1, padx=15, pady=5)
        self.wind_label = ctk.CTkLabel(self.details_frame, text="", font=("Arial", 16))
        self.wind_label.grid(row=0, column=2, padx=15, pady=5)

        self.forecast_frame = ctk.CTkFrame(self.right_frame, corner_radius=15, fg_color="#1a1a1a")
        self.forecast_frame.pack(side="bottom", pady=20, padx=20, fill="x")

    # (Diğer tüm fonksiyonlar aynı)
    # ... (update_ui, update_clock, show_suggestions, vs.)

    # --- Aşağıya diğer fonksiyonlar eklenecek (kısaltıldı) ---
    # ------------------- SAAT GÜNCELLEME -------------------
    def update_clock(self):
        """Saat ve tarihi, 'self.current_timezone_offset'a göre günceller."""
        try:
            utc_now = datetime.now(timezone.utc)
            city_time = utc_now + timedelta(seconds=self.current_timezone_offset)
            date_str = city_time.strftime("%d %B %Y, %A")
            time_str = city_time.strftime("%H:%M:%S")
            self.clock_label.configure(text=f"{date_str}\n{time_str}")
        except Exception as e:
            # Eğer bir sorun olursa fallback olarak yerel zamanı göster
            now = datetime.now().strftime("%d %B %Y\n%H:%M:%S")
            self.clock_label.configure(text=now)
        finally:
            self.after(1000, self.update_clock)

    # ------------------- HAVA DURUMU FONKSİYONLARI -------------------
    def update_ui(self, data, forecast_data):
        # Aranan şehrin timezone offset'ini (saniye) alıyoruz
        try:
            self.current_timezone_offset = int(data.get('timezone', 0))
        except Exception:
            self.current_timezone_offset = 0

        city_name, country = data.get("name", "—"), data.get("sys", {}).get("country", "")
        desc = data["weather"][0]["description"].capitalize() if data.get("weather") else ""
        icon_code = data["weather"][0]["icon"] if data.get("weather") else "01d"
        self.city_label.configure(text=f"{self.country_to_flag(country)} {city_name}, {country}")
        self.temp_label.configure(text=f"{round(data['main']['temp'])}°C")
        self.description_label.configure(text=desc)
        self.feels_like_label.configure(text=f"🤔 Hissedilen: {round(data['main']['feels_like'])}°C")
        self.humidity_label.configure(text=f"💧 Nem: %{data['main']['humidity']}")
        self.wind_label.configure(text=f"💨 Rüzgar: {data['wind']['speed']} m/s")
        self.update_dynamic_elements(desc, icon_code)
        self.display_forecast(forecast_data)

    def update_dynamic_elements(self, desc, icon_code):
        is_day = 'd' in icon_code
        desc_lower = desc.lower()
        if "fırtına" in desc_lower or "thunderstorm" in desc_lower:
            target_color = "#483D8B"
        elif "yağmur" in desc_lower:
            target_color = "#537188"
        elif "kar" in desc_lower:
            target_color = "#B0E0E6"
        elif "açık" in desc_lower:
            target_color = "#62a7e3" if is_day else "#192f44"
        elif "bulut" in desc_lower:
            target_color = "#768c8c"
        else:
            target_color = "#1f1f1f" if self.current_theme == "dark" else "#f1f2f6"
        self.animate_color_change(target_color)
        icon_key = self.get_icon_key(icon_code)
        self.icon_label.configure(image=self.weather_icons.get(icon_key))

    def display_forecast(self, forecast_data):
        for widget in self.forecast_frame.winfo_children():
            widget.destroy()
        daily_forecast = defaultdict(list)

        # Bugünün tarihini şehir saat dilimine göre al
        current_city_today = (datetime.now(timezone.utc) + timedelta(seconds=self.current_timezone_offset)).strftime("%Y-%m-%d")

        for item in forecast_data.get("list", []):
            # API'den gelen 'dt' UTC timestamp => şehrin local zamanına çevir
            item_time_local = datetime.fromtimestamp(item['dt'], tz=timezone.utc) + timedelta(seconds=self.current_timezone_offset)
            date = item_time_local.strftime("%Y-%m-%d")
            if date != current_city_today:
                daily_forecast[date].append(item)

        for i, (date, values) in enumerate(list(daily_forecast.items())[:5]):
            frame = ctk.CTkFrame(self.forecast_frame, corner_radius=10, fg_color="#2b2b2b")
            frame.grid(row=0, column=i, padx=10, pady=10, sticky="nsew")
            self.forecast_frame.grid_columnconfigure(i, weight=1)
            day_name = datetime.strptime(date, "%Y-%m-%d").strftime("%a").capitalize()
            min_temp = round(min(v['main']['temp_min'] for v in values))
            max_temp = round(max(v['main']['temp_max'] for v in values))
            icons = [v['weather'][0]['icon'] for v in values]
            main_icon_code = max(set(icons), key=icons.count).replace('n', 'd')
            ctk.CTkLabel(frame, text=day_name, font=("Arial", 14, "bold")).pack(pady=(10, 5))
            icon_label = ctk.CTkLabel(frame, text="")
            icon_label.pack()
            icon_key_small = self.get_icon_key(main_icon_code) + "_small"
            icon_label.configure(image=self.weather_icons.get(icon_key_small))
            ctk.CTkLabel(frame, text=f"{max_temp}° / {min_temp}°", font=("Arial", 14)).pack(pady=(5, 10))

    def get_icon_key(self, icon_code):
        if "11" in icon_code: return "thunderstorm"
        if "01d" in icon_code: return "day_clear"
        if "01n" in icon_code: return "night_clear"
        if "02d" in icon_code: return "partly_cloudy_day"
        if "02n" in icon_code: return "partly_cloudy_night"
        if "03" in icon_code or "04" in icon_code: return "cloudy"
        if "09" in icon_code or "10" in icon_code: return "rain"
        if "13" in icon_code: return "snow"
        if "50" in icon_code: return "mist"
        return "unknown"

    # ------------------- YARDIMCI FONKSİYONLAR -------------------
    def animate_color_change(self, target_color):
        if self._anim_id is not None:
            self.after_cancel(self._anim_id)
        start_color = self.right_frame.cget("fg_color")
        start_rgb = self.winfo_rgb(start_color)
        target_rgb = self.winfo_rgb(target_color)
        steps = 20
        r_step = (target_rgb[0] - start_rgb[0]) / steps
        g_step = (target_rgb[1] - start_rgb[1]) / steps
        b_step = (target_rgb[2] - start_rgb[2]) / steps
        def step_animation(current_step):
            if current_step > steps:
                self.right_frame.configure(fg_color=target_color)
                return
            r = int(start_rgb[0] + r_step * current_step)
            g = int(start_rgb[1] + g_step * current_step)
            b = int(start_rgb[2] + b_step * current_step)
            color = f"#{r//256:02x}{g//256:02x}{b//256:02x}"
            self.right_frame.configure(fg_color=color)
            self._anim_id = self.after(20, step_animation, current_step + 1)
        step_animation(1)

    def toggle_theme(self):
        if self.current_theme == "dark":
            ctk.set_appearance_mode("light")
            self.current_theme = "light"
            self.mode_button.configure(text="🌙 Koyu Tema")
        else:
            ctk.set_appearance_mode("dark")
            self.current_theme = "dark"
            self.mode_button.configure(text="☀️ Açık Tema")
        # Yeniden önerileri göster (tema değişince renkler güncellensin)
        self.show_suggestions(None)

    def auto_location_weather_threaded(self):
        self.city_label.configure(text="🌎 Otomatik Konum Alınıyor...")
        threading.Thread(target=self.auto_location_task, daemon=True).start()

    def auto_location_task(self):
        try:
            city = geocoder.ip("me").city
            if city:
                self.after(0, self._fetch_weather_data, city)
            else:
                self.after(0, self.show_error, "Otomatik konum bulunamadı.")
        except Exception:
            self.after(0, self.show_error, "Konum servisi hatası.")

    def search_weather_threaded(self):
        city = self.city_entry.get().strip()
        if city:
            self.city_label.configure(text=f"🔍 '{city}' Aranıyor...")
            threading.Thread(target=self._fetch_weather_data, args=(city,), daemon=True).start()
        else:
            self.show_error("Lütfen bir şehir adı girin.")

    def _fetch_weather_data(self, city):
        # Doğru URL'ler ve params ile istek yap
        weather_url = "https://api.openweathermap.org/data/2.5/weather"
        forecast_url = "https://api.openweathermap.org/data/2.5/forecast"
        params = {"q": city, "appid": self.API_KEY, "units": "metric", "lang": "tr"}

        try:
            weather_res = requests.get(weather_url, params=params, timeout=7)
            forecast_res = requests.get(forecast_url, params=params, timeout=7)

            if weather_res.status_code == 200 and forecast_res.status_code == 200:
                self.after(0, self.update_ui, weather_res.json(), forecast_res.json())
            else:
                msg = f"'{city}' şehri bulunamadı (weather:{weather_res.status_code}, forecast:{forecast_res.status_code})."
                self.after(0, self.show_error, msg)
        except requests.exceptions.RequestException:
            self.after(0, self.show_error, "Ağ bağlantısı hatası.")

    def show_suggestions(self, event=None):
        prefix = self.city_entry.get().strip().capitalize()
        for btn in self.suggestion_buttons:
            btn.destroy()
        self.suggestion_buttons.clear()
        if prefix and self.city_list:
            matches = [c for c in self.city_list if c.startswith(prefix)]
            if not matches:
                matches = get_close_matches(prefix, self.city_list, n=5, cutoff=0.7)
            fg_color, hover_color = ("#2b2b2b", "#4b4b4b") if self.current_theme == "dark" else ("gray90", "gray70")
            for city_name in matches[:5]:
                btn = ctk.CTkButton(self.suggestion_frame, text=city_name, height=25,
                                    fg_color=fg_color, hover_color=hover_color, anchor="w",
                                    command=lambda c=city_name: self.select_city(c))
                btn.pack(fill="x", padx=2, pady=1)
                self.suggestion_buttons.append(btn)

    def select_city(self, city):
        self.city_entry.delete(0, "end")
        self.city_entry.insert(0, city)
        for btn in self.suggestion_buttons:
            btn.destroy()
        self.suggestion_buttons.clear()
        self.search_weather_threaded()

    def country_to_flag(self, country_code):
        if not isinstance(country_code, str) or len(country_code) != 2:
            return "🏳️"
        return "".join(chr(ord(char.upper()) + 127397) for char in country_code)

    def show_error(self, message):
        # Hata gösterimi
        try:
            self.city_label.configure(text=message, text_color="red")
        except Exception:
            self.city_label.configure(text=message)
        if self._anim_id:
            self.after_cancel(self._anim_id)
        for label in [self.temp_label, self.description_label, self.feels_like_label, self.humidity_label, self.wind_label]:
            label.configure(text="")
        self.icon_label.configure(text="", image=self.weather_icons.get("unknown"))
        for widget in self.forecast_frame.winfo_children():
            widget.destroy()
        self.right_frame.configure(fg_color="#1f1f1f" if self.current_theme == "dark" else "#f1f2f6")

        # Hata durumunda saati tekrar kullanıcının yerel saatine döndür
        try:
            self.current_timezone_offset = int(datetime.now(timezone.utc).astimezone().utcoffset().total_seconds())
        except Exception:
            self.current_timezone_offset = 0

        self.after(4000, lambda: self.city_label.configure(text_color=ctk.ThemeManager.theme["CTkLabel"]["text_color"]))

# --- Uygulama Başlat ---
if __name__ == "__main__":
    app = UltimateWeatherApp()
    app.mainloop()
