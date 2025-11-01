import logging
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import aiohttp
from typing import Dict, List

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = "7866642235:AAH0cC6HomjFmxAZODZ7Kea5rBFTqVkt9Uc"

# Центры муниципальных округов Вологодской области
VOLOGDA_REGION_LOCATIONS = {
    # Города
    "бабаево": {"lat": 59.3833, "lon": 35.9500, "type": "город"},
    "белозерск": {"lat": 60.0333, "lon": 37.7833, "type": "город"},
    "великий устюг": {"lat": 60.7585, "lon": 46.3044, "type": "город"},
    "вологда": {"lat": 59.3000, "lon": 39.9000, "type": "город"},
    "вытегра": {"lat": 61.0000, "lon": 36.4500, "type": "город"},
    "грязовец": {"lat": 58.8833, "lon": 40.2500, "type": "город"},
    "кириллов": {"lat": 59.8667, "lon": 38.3833, "type": "город"},
    "никольск": {"lat": 59.5333, "lon": 45.4500, "type": "город"},
    "сокол": {"lat": 59.4667, "lon": 40.1167, "type": "город"},
    "тотьма": {"lat": 59.9833, "lon": 42.7667, "type": "город"},
    "устюжна": {"lat": 58.8333, "lon": 36.4333, "type": "город"},
    "харовск": {"lat": 59.9500, "lon": 40.2000, "type": "город"},
    "череповец": {"lat": 59.0000, "lon": 38.0000, "type": "город"},
    
    # Поселки
    "вожега": {"lat": 60.4667, "lon": 40.2167, "type": "поселок"},
    "кадуй": {"lat": 59.2000, "lon": 37.1500, "type": "поселок"},
    "чагода": {"lat": 59.1667, "lon": 35.3333, "type": "поселок"},
    "шексна": {"lat": 59.2167, "lon": 38.5000, "type": "поселок"},
    
    # Села
    "имени бабушкина": {"lat": 59.7500, "lon": 43.1167, "type": "село"},
    "липин бор": {"lat": 60.3667, "lon": 37.9333, "type": "село"},
    "верховажье": {"lat": 60.7167, "lon": 41.9833, "type": "село"},
    "кичменгский городок": {"lat": 59.9833, "lon": 45.7833, "type": "село"},
    "шуйское": {"lat": 59.2500, "lon": 40.6667, "type": "село"},
    "нюксеница": {"lat": 60.4167, "lon": 44.2333, "type": "село"},
    "сямжа": {"lat": 60.0167, "lon": 41.0667, "type": "село"},
    "тарногский городок": {"lat": 60.5000, "lon": 43.5833, "type": "село"},
    "устье": {"lat": 59.6500, "lon": 39.7167, "type": "село"},
    
    # Альтернативные названия для удобства поиска
    "великийустюг": {"lat": 60.7585, "lon": 46.3044, "type": "город"},
    "им бабушкина": {"lat": 59.7500, "lon": 43.1167, "type": "село"},
    "кичменгский": {"lat": 59.9833, "lon": 45.7833, "type": "село"},
    "тарногский": {"lat": 60.5000, "lon": 43.5833, "type": "село"},
    "бабушкина": {"lat": 59.7500, "lon": 43.1167, "type": "село"}
}

class WeatherAnalyzer:
    def __init__(self):
        self.base_url = "https://api.open-meteo.com/v1/forecast"
    
    async def get_weather_data(self, lat: float, lon: float) -> Dict:
        """Получение ТОЛЬКО текущих данных о погоде с OpenMeteo"""
        try:
            params = {
                'latitude': lat,
                'longitude': lon,
                'current': [
                    'temperature_2m', 'wind_speed_10m', 'wind_gusts_10m', 
                    'relative_humidity_2m', 'precipitation', 'weather_code',
                    'pressure_msl', 'cloud_cover'
                ],
                'timezone': 'Europe/Moscow'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(self.base_url, params=params, timeout=10) as response:
                    response.raise_for_status()
                    return await response.json()
        except Exception as e:
            logger.error(f"Ошибка получения данных погоды: {e}")
            return None

class TerrainAnalyzer:
    """Анализатор типа местности"""
    
    async def analyze_terrain(self, lat: float, lon: float, location_name: str, location_type: str) -> Dict:
        """Анализ типа местности"""
        try:
            # Используем OpenStreetMap для определения местности
            async with aiohttp.ClientSession() as session:
                url = f"https://nominatim.openstreetmap.org/reverse"
                params = {
                    'lat': lat,
                    'lon': lon,
                    'format': 'json',
                    'zoom': 10
                }
                
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        return self._parse_osm_data(data, location_name, location_type)
                    else:
                        return self._get_default_terrain(location_name, location_type)
                        
        except Exception as e:
            logger.error(f"Ошибка анализа местности: {e}")
            return self._get_default_terrain(location_name, location_type)
    
    def _parse_osm_data(self, osm_data: Dict, location_name: str, location_type: str) -> Dict:
        """Парсинг данных OSM"""
        display_name = osm_data.get('display_name', '').lower()
        
        # Определяем тип местности
        terrain_type = "равнинная местность"
        features = []
        
        if any(word in display_name for word in ['лес', 'forest', 'wood']):
            terrain_type = "лесная местность"
            features.extend(['деревья near ЛЭП', 'риск падения деревьев', 'ограниченная видимость'])
        elif any(word in display_name for word in ['озеро', 'река', 'водоем', 'lake', 'river']):
            terrain_type = "приозерная местность"
            features.extend(['повышенная влажность', 'туманы', 'коррозионная нагрузка'])
        elif any(word in display_name for word in ['холм', 'гора', 'hill', 'mountain']):
            terrain_type = "холмистая местность"
            features.extend(['перепады высот', 'усиленная ветровая нагрузка'])
        elif any(word in display_name for word in ['промзона', 'завод', 'factory', 'industrial']):
            terrain_type = "промышленная зона"
            features.extend(['техногенные воздействия', 'загрязнение воздуха'])
        
        return {
            'type': terrain_type,
            'features': features if features else ['стандартные условия'],
            'description': f'{terrain_type} в районе {location_name} ({location_type})',
            'location_type': location_type
        }
    
    def _get_default_terrain(self, location_name: str, location_type: str) -> Dict:
        """Резервный метод определения местности"""
        return {
            'type': 'равнинная местность',
            'features': ['стандартные условия'],
            'description': f'Основная местность вокруг {location_name} ({location_type})',
            'location_type': location_type
        }

class G4FGenerator:
    """Генератор рекомендаций через g4f"""
    
    def __init__(self):
        try:
            from g4f.client import Client
            self.client = Client()
            self.g4f_available = True
            logger.info("✅ g4f доступен")
        except ImportError:
            self.g4f_available = False
            logger.warning("❌ g4f недоступен")
    
    async def generate_recommendations(self, weather_data: Dict, terrain_data: Dict, location: str) -> str:
        """Генерация рекомендаций через g4f"""
        if not self.g4f_available:
            return self._get_fallback_recommendations(weather_data, terrain_data, location)
        
        prompt = self._create_prompt(weather_data, terrain_data, location)
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                web_search=False,
                timeout=30
            )
            
            result = response.choices[0].message.content
            return result[:2000] if len(result) > 2000 else result
            
        except Exception as e:
            logger.error(f"Ошибка генерации рекомендаций: {e}")
            return self._get_fallback_recommendations(weather_data, terrain_data, location)
    
    def _create_prompt(self, weather_data: Dict, terrain_data: Dict, location: str) -> str:
        """Создание промпта для нейросети"""
        
        current = weather_data.get('current', {})
        
        weather_info = f"""
МЕСТОПОЖЕНИЕ: {location.upper()} (Вологодская область)
ТИП МЕСТНОСТИ: {terrain_data.get('type', 'неизвестно')}
ОСОБЕННОСТИ МЕСТНОСТИ: {', '.join(terrain_data.get('features', []))}

ТЕКУЩИЕ ПОГОДНЫЕ УСЛОВИЯ:
- Температура: {current.get('temperature_2m', 'N/A')}°C
- Скорость ветра: {current.get('wind_speed_10m', 'N/A')} м/с
- Порывы ветра: {current.get('wind_gusts_10m', 'N/A')} м/с
- Влажность: {current.get('relative_humidity_2m', 'N/A')}%
- Осадки: {current.get('precipitation', 'N/A')} мм
- Давление: {current.get('pressure_msl', 'N/A')} гПа
- Облачность: {current.get('cloud_cover', 'N/A')}%

Проанализируй ТЕКУЩИЕ риски для линий электропередач и дай практические рекомендации для ремонтных бригад.
Ответ должен быть до 2000 символов и содержать:
1. Основные риски
2. Рекомендации для бригад
3. Технические мероприятия
"""
        return weather_info
    
    def _get_fallback_recommendations(self, weather_data: Dict, terrain_data: Dict, location: str) -> str:
        """Резервные рекомендации если g4f не работает"""
        current = weather_data.get('current', {})
        temp = current.get('temperature_2m', 0)
        wind = current.get('wind_speed_10m', 0)
        gusts = current.get('wind_gusts_10m', 0)
        humidity = current.get('relative_humidity_2m', 0)
        
        # Анализ рисков
        risks = []
        if temp < -15 and humidity > 70:
            risks.append("❄️ ВЫСОКИЙ РИСК ОБЛЕДЕНЕНИЯ ПРОВОДОВ")
        if wind > 15 or gusts > 20:
            risks.append("💨 ОПАСНАЯ ВЕТРОВАЯ НАГРУЗКА")
        if temp < -25:
            risks.append("🥶 ЭКСТРЕМАЛЬНО НИЗКАЯ ТЕМПЕРАТУРА")
        
        recommendations = []
        if risks:
            recommendations.extend([
                "• Увеличить частоту патрулирования ЛЭП",
                "• Подготовить аварийные бригады к выезду",
                "• Проверить систему оповещения"
            ])
        if wind > 10:
            recommendations.extend([
                "• Осмотреть крепление опор и арматуры",
                "• Проверить натяжение проводов"
            ])
        
        return f"""
📊 ОТЧЕТ ДЛЯ: {location.upper()}

🏞 МЕСТНОСТЬ: {terrain_data.get('type', 'неизвестно')}
📍 ОСОБЕННОСТИ: {', '.join(terrain_data.get('features', []))}

📈 ТЕКУЩИЕ УСЛОВИЯ:
• Температура: {temp}°C
• Ветер: {wind} м/с (порывы {gusts} м/с)
• Влажность: {humidity}%
• Осадки: {current.get('precipitation', 0)} мм

🚨 ОСНОВНЫЕ РИСКИ:
{chr(10).join(f'- {risk}' for risk in risks) if risks else '- Стабильные условия'}

💡 РЕКОМЕНДАЦИИ:
{chr(10).join(recommendations) if recommendations else '- Стандартный режим работы'}

⚠️ Нейросеть временно недоступна.
"""

class PowerRiskBot:
    def __init__(self, token: str):
        self.application = Application.builder().token(token).build()
        self.weather_analyzer = WeatherAnalyzer()
        self.terrain_analyzer = TerrainAnalyzer()
        self.ai_generator = G4FGenerator()
        
        self.setup_handlers()
    
    def setup_handlers(self):
        """Настройка обработчиков команд"""
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("cities", self.cities_command))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        КОМАНДА /start - начать работу с ботом
        
        Что делает:
        • Показывает приветственное сообщение
        • Объясняет основные возможности бота
        • Сообщает доступные команды
        • Помогает начать работу
        
        Когда использовать:
        • При первом запуске бота
        • Если нужно вспомнить основные команды
        • Чтобы проверить, что бот активен
        """
        welcome_text = """
🔌 Бот анализа рисков для ЛЭП Вологодской области

🤖 Использую нейросеть для анализа ТЕКУЩИХ погодных условий

Я анализирую погоду и даю рекомендации для:
• Линий электропередач
• Опор ЛЭП  
• Ремонтных бригад

📋 Команды:
/start - начать работу (это сообщение)
/help - подробная помощь и инструкция
/cities - список всех доступных населенных пунктов

📍 Просто напишите название города, поселка или села для анализа
Например: "Вологда", "Череповец", "Великий Устюг"
        """
        await update.message.reply_text(welcome_text)
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        КОМАНДА /help - подробная помощь
        
        Что делает:
        • Подробно объясняет как работать с ботом
        • Описывает процесс анализа
        • Рассказывает об анализируемых данных
        • Сообщает особенности работы
        
        Когда использовать:
        • Если непонятно как пользоваться ботом
        • Хотите узнать больше о возможностях
        • Нужно понять какие данные анализируются
        """
        help_text = """
ℹ️ КАК ПОЛЬЗОВАТЬСЯ БОТОМ - подробная инструкция:

1️⃣ ОТПРАВЬТЕ НАЗВАНИЕ НАСЕЛЕННОГО ПУНКТА
   Например: "Вологда", "Череповец", "Великий Устюг"
   Или: "Липин Бор", "Шексна", "им. Бабушкина"

2️⃣ БОТ ПРОАНАЛИЗИРУЕТ:
   • ТЕКУЩИЕ данные о погоде (OpenMeteo API)
   • Тип местности (OpenStreetMap)
   • Риски для линий электропередач
   • Угрозы для опор и оборудования

3️⃣ ПОЛУЧИТЕ РЕКОМЕНДАЦИИ:
   • Меры безопасности для ремонтных бригад
   • Технические мероприятия для ЛЭП
   • Аварийная готовность
   • Профилактические работы

💡 Используйте /cities чтобы увидеть все доступные населенные пункты
        """
        await update.message.reply_text(help_text)
    
    async def cities_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        КОМАНДА /cities - список всех населенных пунктов
        
        Что делает:
        • Показывает ВСЕ доступные населенные пункты
        • Группирует по типам (города, поселки, села)
        • Сортирует по алфавиту для удобства поиска
        • Дает подсказки по альтернативным названиям
        
        Когда использовать:
        • Чтобы узнать какие города/села поддерживаются
        • Если не уверены в правильности названия
        • Нужно найти конкретный муниципальный округ
        • Чтобы увидеть все варианты для анализа
        """
        # Группируем по типам населенных пунктов
        cities_by_type = {
            "Города": [],
            "Поселки": [],
            "Села": []
        }
        
        # Проходим по ВСЕМ локациям без фильтрации
        for location_name, location_data in VOLOGDA_REGION_LOCATIONS.items():
            # Пропускаем только альтернативные названия (сокращения)
            if location_name in ["великийустюг", "им бабушкина", "кичменгский", 
                               "тарногский", "бабушкина"]:
                continue
                
            # Форматируем красивое название для отображения
            display_name = self._format_location_name(location_name)
            
            # Добавляем в соответствующую категорию
            if location_data['type'] == 'город':
                cities_by_type["Города"].append(display_name)
            elif location_data['type'] == 'поселок':
                cities_by_type["Поселки"].append(display_name)
            elif location_data['type'] == 'село':
                cities_by_type["Села"].append(display_name)
        
        # Формируем текст сообщения
        cities_text = "🏙 ЦЕНТРЫ МУНИЦИПАЛЬНЫХ ОКРУГОВ ВОЛОГОДСКОЙ ОБЛАСТИ:\n\n"
        
        for loc_type, locations in cities_by_type.items():
            if locations:
                cities_text += f"📍 {loc_type}:\n"
                # Сортируем по алфавиту и добавляем с эмодзи
                sorted_locations = sorted(locations)
                for loc in sorted_locations:
                    cities_text += f"   • {loc}\n"
                cities_text += "\n"
        
        # Добавляем подсказки по альтернативным названиям
        cities_text += """💡 ПОДСКАЗКИ ПО НАЗВАНИЯМ:
• "имени бабушкина" → можно писать "им бабушкина" или "бабушкина"
• "великий устюг" → можно писать "великийустюг" 
• "кичменгский городок" → можно писать "кичменгский"
• "тарногский городок" → можно писать "тарногский"

📝 Просто напишите название города, поселка или села для анализа"""
        
        await update.message.reply_text(cities_text)
    
    def _format_location_name(self, location_name: str) -> str:
        """Форматирует название локации для красивого отображения"""
        name_mapping = {
            "имени бабушкина": "им. Бабушкина",
            "кичменгский городок": "Кичменгский Городок", 
            "тарногский городок": "Тарногский Городок",
            "великий устюг": "Великий Устюг"
        }
        
        # Если есть специальное форматирование - используем его
        if location_name in name_mapping:
            return name_mapping[location_name]
        
        # Иначе просто capitalize
        return location_name.title()
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка текстовых сообщений с названиями городов"""
        user_input = update.message.text.strip().lower()
        
        if user_input in VOLOGDA_REGION_LOCATIONS:
            await self.analyze_location(update, user_input)
        else:
            similar = self.find_similar_cities(user_input)
            if similar:
                text = f"❓ Населённый пункт '{user_input}' не найден.\n\nВозможно вы имели в виду:\n" + "\n".join(f"• {c}" for c in similar)
            else:
                text = f"❓ Населённый пункт '{user_input}' не найден.\nИспользуйте /cities для списка всех доступных населенных пунктов."
            await update.message.reply_text(text)
    
    def find_similar_cities(self, user_input: str) -> List[str]:
        """Поиск похожих городов"""
        similar = []
        for location in VOLOGDA_REGION_LOCATIONS.keys():
            if (user_input in location or 
                any(word in location for word in user_input.split()) or
                any(location.startswith(part) for part in user_input.split())):
                # Форматируем красивое название для вывода
                display_name = self._format_location_name(location)
                similar.append(display_name)
        return list(set(similar))[:5]
    
    async def analyze_location(self, update: Update, location_name: str):
        """Полный анализ местоположения"""
        location_data = VOLOGDA_REGION_LOCATIONS[location_name]
        
        # Форматируем красивое название для вывода
        display_name = self._format_location_name(location_name)
        
        # Сообщение о начале анализа
        analysis_msg = await update.message.reply_text(
            f"🔍 Анализирую {display_name}...\n"
            f"📡 Получаю ТЕКУЩИЕ данные о погоде..."
        )
        
        try:
            # Получаем ТОЛЬКО текущие данные о погоде
            weather_data = await self.weather_analyzer.get_weather_data(
                location_data['lat'], location_data['lon']
            )
            
            if not weather_data:
                await analysis_msg.edit_text("❌ Ошибка получения данных о погоде. Попробуйте позже.")
                return
            
            # Анализируем местность
            terrain_data = await self.terrain_analyzer.analyze_terrain(
                location_data['lat'], location_data['lon'], display_name, location_data['type']
            )
            
            await analysis_msg.edit_text(
                f"📍 {display_name} - данные получены\n"
                f"🏞 Местность: {terrain_data['type']}\n"
                f"🤖 Анализирую ТЕКУЩИЕ условия нейросетью..."
            )
            
            # Генерируем рекомендации через g4f
            recommendations = await self.ai_generator.generate_recommendations(
                weather_data, terrain_data, display_name
            )
            
            # Проверяем длину ответа и обрезаем если нужно
            if len(recommendations) > 2000:
                recommendations = recommendations[:1997] + "..."
            
            # Форматируем и отправляем результат
            result_text = f"📊 ОТЧЕТ ДЛЯ: {display_name.upper()}\n(на основе ТЕКУЩИХ погодных условий)\n\n{recommendations}"
            
            await update.message.reply_text(result_text)
            await analysis_msg.delete()
            
        except Exception as e:
            logger.error(f"Ошибка анализа: {e}")
            await analysis_msg.edit_text("❌ Произошла ошибка при анализе. Попробуйте позже.")

def main():
    """Основная функция запуска бота"""
    
    # Проверяем токен
    if BOT_TOKEN.startswith('789789789') or len(BOT_TOKEN) < 10:
        print("❌ ЗАМЕНИТЕ BOT_TOKEN НА ВАШ РЕАЛЬНЫЙ ТОКЕН ОТ @BotFather!")
        return
    
    # Создаем и запускаем бота
    bot = PowerRiskBot(BOT_TOKEN)
    
    print("🤖 Бот запущен...")
    print("📍 Доступно населенных пунктов:", len(VOLOGDA_REGION_LOCATIONS))
    print("🏙 Города: 13")
    print("🏘 Поселки: 4") 
    print("🏡 Села: 9")
    print("🤖 Нейросеть:", "Доступна" if bot.ai_generator.g4f_available else "Недоступна")
    print("🌤️ Анализ: только ТЕКУЩИЕ погодные условия")
    
    # Запускаем бота
    bot.application.run_polling()

if __name__ == '__main__':
    main()
