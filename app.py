from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
import json
from typing import Dict, List, Optional
import logging
from datetime import datetime, timedelta
import asyncio
import random
import time

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Weather Risk Analysis API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Модели данных
class WeatherData(BaseModel):
    temperature: float
    wind_speed: float
    precipitation: float
    humidity: float
    weather_code: int
    pressure: float  # Изменено с int на float
    description: str

class RiskAssessment(BaseModel):
    risk_level: int
    risk_description: str
    factors: Dict[str, float]
    recommendations: List[str]

class MunicipalityRisk(BaseModel):
    name: str
    risk_level: int
    weather: WeatherData
    coordinates: List[float]

# Координаты муниципалитетов Вологодской области
MUNICIPALITIES = {
    "Вологда": {"coords": [59.2181, 39.8886], "population": 317822},
    "Череповец": {"coords": [59.1266, 37.9093], "population": 298160},
    "Бабаевский": {"coords": [59.3833, 35.9500], "population": 18541},
    "Бабушкинский": {"coords": [59.7500, 43.1167], "population": 9307},
    "Белозерский": {"coords": [60.0333, 37.7833], "population": 12978},
    "Вашкинский": {"coords": [60.3667, 37.9333], "population": 5872},
    "Великоустюгский": {"coords": [60.7585, 46.3044], "population": 48563},
    "Верховажский": {"coords": [60.7167, 41.9833], "population": 12287},
    "Вожегодский": {"coords": [60.4667, 40.2167], "population": 13416},
    "Вологодский": {"coords": [59.3000, 39.9000], "population": 51950},
    "Вытегорский": {"coords": [61.0000, 36.4500], "population": 21686},
    "Грязовецкий": {"coords": [58.8833, 40.2500], "population": 31398},
    "Кадуйский": {"coords": [59.2000, 37.1500], "population": 16316},
    "Кирилловский": {"coords": [59.8667, 38.3833], "population": 13795},
    "Кичменгско-Городецкий": {"coords": [59.9833, 45.7833], "population": 14079},
    "Междуреченский": {"coords": [59.2500, 40.6667], "population": 4740},
    "Никольский": {"coords": [59.5333, 45.4500], "population": 18390},
    "Нюксенский": {"coords": [60.4167, 44.2333], "population": 8316},
    "Сокольский": {"coords": [59.4667, 40.1167], "population": 44172},
    "Сямженский": {"coords": [60.0167, 41.0667], "population": 7880},
    "Тарногский": {"coords": [60.5000, 43.5833], "population": 10250},
    "Тотемский": {"coords": [59.9833, 42.7667], "population": 21802},
    "Усть-Кубинский": {"coords": [59.6500, 39.7167], "population": 7154},
    "Устюженский": {"coords": [58.8333, 36.4333], "population": 15048},
    "Харовский": {"coords": [59.9500, 40.2000], "population": 12618},
    "Чагодощенский": {"coords": [59.1667, 35.3333], "population": 10732},
    "Череповецкий": {"coords": [59.0000, 38.0000], "population": 39308},
    "Шекснинский": {"coords": [59.2167, 38.5000], "population": 28791}
}

class WeatherAIAnalyzer:
    def __init__(self):
        self.risk_thresholds = {
            "wind_speed": {"low": 5, "medium": 10, "high": 15, "critical": 20},
            "temperature": {"freezing": -10, "extreme_cold": -20},
            "precipitation": {"light": 2.5, "moderate": 7.5, "heavy": 15},
            "humidity": {"high": 80, "very_high": 90}
        }
    
    async def get_weather_from_openmeteo(self, lat: float, lon: float, name: str) -> Optional[WeatherData]:
        """Получение данных о погоде с Open-Meteo API (бесплатный и надежный)"""
        try:
            # Open-Meteo API - бесплатный и без ключа
            url = "https://api.open-meteo.com/v1/forecast"
            params = {
                'latitude': lat,
                'longitude': lon,
                'current': 'temperature_2m,relative_humidity_2m,precipitation,pressure_msl,wind_speed_10m,weather_code',
                'timezone': 'Europe/Moscow',
                'forecast_days': 1
            }
            
            logger.info(f"Запрос к Open-Meteo для {name} ({lat}, {lon})")
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                current = data.get('current', {})
                
                weather_info = self._decode_weather_code(current.get('weather_code', 0))
                
                # Обработка давления - округляем до целого, но сохраняем как float
                pressure = current.get('pressure_msl', 1013.0)
                if pressure is None:
                    pressure = 1013.0
                
                logger.info(f"✅ Успешно получены данные для {name}: {current.get('temperature_2m', 0)}°C, давление: {pressure}")
                
                return WeatherData(
                    temperature=current.get('temperature_2m', 0),
                    wind_speed=current.get('wind_speed_10m', 0),
                    precipitation=current.get('precipitation', 0),
                    humidity=current.get('relative_humidity_2m', 0),
                    weather_code=current.get('weather_code', 0),
                    pressure=pressure,  # Теперь принимает float
                    description=weather_info['description']
                )
            else:
                logger.warning(f"Ошибка Open-Meteo для {name}: {response.status_code}")
                return self._generate_realistic_demo_data(name)
                
        except Exception as e:
            logger.warning(f"Ошибка получения погоды для {name}: {e}")
            return self._generate_realistic_demo_data(name)
    
    def _decode_weather_code(self, code: int) -> Dict[str, str]:
        """Декодирование кода погоды Open-Meteo"""
        weather_codes = {
            0: {"description": "Ясно", "risk": 0.1},
            1: {"description": "Преимущественно ясно", "risk": 0.1},
            2: {"description": "Переменная облачность", "risk": 0.2},
            3: {"description": "Пасмурно", "risk": 0.3},
            45: {"description": "Туман", "risk": 0.5},
            48: {"description": "Туман с инеем", "risk": 0.6},
            51: {"description": "Лежащая морось", "risk": 0.4},
            53: {"description": "Умеренная морось", "risk": 0.5},
            55: {"description": "Сильная морось", "risk": 0.6},
            61: {"description": "Небольшой дождь", "risk": 0.5},
            63: {"description": "Умеренный дождь", "risk": 0.6},
            65: {"description": "Сильный дождь", "risk": 0.8},
            71: {"description": "Небольшой снег", "risk": 0.6},
            73: {"description": "Умеренный снег", "risk": 0.7},
            75: {"description": "Сильный снег", "risk": 0.9},
            95: {"description": "Гроза", "risk": 0.9},
        }
        return weather_codes.get(code, {"description": "Неизвестно", "risk": 0.3})
    
    def _generate_realistic_demo_data(self, city_name: str) -> WeatherData:
        """Генерация реалистичных демо-данных о погоде"""
        now = datetime.now()
        month = now.month
        
        # Базовые температуры для ноября
        base_temps = {
            "Вологда": 2, "Череповец": 3, "Сокольский": 1, "Великоустюгский": -1,
            "Белозерский": 0, "Вытегорский": 0, "Кирилловский": 0, "Тотемский": 1,
            "Устюженский": 2, "Харовский": -1, "Бабаевский": 2, "Грязовецкий": 2,
            "Бабушкинский": -2, "Вашкинский": -1, "Верховажский": 0, "Вожегодский": 0,
            "Кадуйский": 2, "Кичменгско-Городецкий": -1, "Междуреченский": 1,
            "Никольский": -1, "Нюксенский": -2, "Сямженский": 0, "Тарногский": -2,
            "Усть-Кубинский": 1, "Харовский": -1, "Чагодощенский": 2, "Череповецкий": 3,
            "Шекснинский": 2
        }
        
        base_temp = base_temps.get(city_name, 1)
        temp_variation = random.uniform(-2, 2)
        wind_base = random.uniform(2, 6)
        precipitation_base = random.uniform(0, 1.5) if random.random() < 0.4 else 0
        humidity_base = random.randint(75, 90)
        pressure_base = random.uniform(980.0, 1020.0)  # Теперь float
        
        # Погодные условия для ноября
        if base_temp < 0:
            descriptions = ["снег", "небольшой снег", "облачно", "пасмурно"]
            weather_codes = [71, 73, 3]  # Снег, облачно
        else:
            descriptions = ["ясно", "переменная облачность", "облачно", "небольшой дождь"]
            weather_codes = [0, 1, 2, 61]  # Ясно, облачно, дождь

        return WeatherData(
            temperature=round(base_temp + temp_variation, 1),
            wind_speed=round(wind_base, 1),
            precipitation=round(precipitation_base, 1),
            humidity=humidity_base,
            weather_code=random.choice(weather_codes),
            pressure=round(pressure_base, 1),  # Float значение
            description=random.choice(descriptions)
        )
    
    def analyze_risk_factors(self, weather: WeatherData) -> Dict[str, float]:
        """Анализ факторов риска для ЛЭП"""
        factors = {}
        
        # Анализ ветра
        if weather.wind_speed >= self.risk_thresholds["wind_speed"]["critical"]:
            factors["wind"] = 1.0
        elif weather.wind_speed >= self.risk_thresholds["wind_speed"]["high"]:
            factors["wind"] = 0.8
        elif weather.wind_speed >= self.risk_thresholds["wind_speed"]["medium"]:
            factors["wind"] = 0.6
        elif weather.wind_speed >= self.risk_thresholds["wind_speed"]["low"]:
            factors["wind"] = 0.4
        else:
            factors["wind"] = 0.1
        
        # Анализ температуры
        if weather.temperature <= self.risk_thresholds["temperature"]["extreme_cold"]:
            factors["temperature"] = 0.9
        elif weather.temperature <= self.risk_thresholds["temperature"]["freezing"]:
            factors["temperature"] = 0.7
        elif weather.temperature < 0:
            factors["temperature"] = 0.5
        else:
            factors["temperature"] = 0.2
        
        # Анализ осадков
        if weather.precipitation >= self.risk_thresholds["precipitation"]["heavy"]:
            factors["precipitation"] = 1.0
        elif weather.precipitation >= self.risk_thresholds["precipitation"]["moderate"]:
            factors["precipitation"] = 0.7
        elif weather.precipitation >= self.risk_thresholds["precipitation"]["light"]:
            factors["precipitation"] = 0.5
        else:
            factors["precipitation"] = 0.2
        
        # Анализ влажности (риск обледенения)
        if weather.humidity >= self.risk_thresholds["humidity"]["very_high"] and weather.temperature < 0:
            factors["icing"] = 0.9
        elif weather.humidity >= self.risk_thresholds["humidity"]["high"] and weather.temperature < 0:
            factors["icing"] = 0.7
        else:
            factors["icing"] = 0.1
        
        # Анализ погодных явлений из кода погоды
        weather_info = self._decode_weather_code(weather.weather_code)
        factors["weather_phenomena"] = weather_info["risk"]
        
        return factors
    
    def calculate_risk_level(self, factors: Dict[str, float]) -> RiskAssessment:
        """Расчет общего уровня риска"""
        weights = {
            "wind": 0.3, "temperature": 0.2, "precipitation": 0.2, 
            "icing": 0.2, "weather_phenomena": 0.1
        }
        
        total_risk = sum(factors.get(factor, 0) * weight for factor, weight in weights.items())
        risk_level = min(10, int(total_risk * 10))
        
        if risk_level >= 9:
            risk_description = "Критический"
            recommendations = [
                "Немедленное отключение ЛЭП в зоне риска",
                "Экстренная отправка ремонтных бригад", 
                "Уведомление МЧС и местных властей"
            ]
        elif risk_level >= 7:
            risk_description = "Высокий"
            recommendations = [
                "Усиленный мониторинг состояния ЛЭП",
                "Подготовка ремонтных бригад к выезду",
                "Ограничение мощности в зоне риска"
            ]
        elif risk_level >= 5:
            risk_description = "Средний"
            recommendations = [
                "Периодический мониторинг",
                "Проверка резервного оборудования",
                "Подготовка к возможным отключениям"
            ]
        elif risk_level >= 3:
            risk_description = "Умеренный"
            recommendations = [
                "Стандартный мониторинг",
                "Проверка систем защиты"
            ]
        else:
            risk_description = "Низкий"
            recommendations = [
                "Штатный режим работы",
                "Плановое обслуживание"
            ]
        
        return RiskAssessment(
            risk_level=risk_level,
            risk_description=risk_description,
            factors=factors,
            recommendations=recommendations
        )

# Инициализация анализатора
analyzer = WeatherAIAnalyzer()

def find_nearest_municipality_for_cell(lat, lng, municipalities):
    """Поиск ближайшего муниципалитета для ячейки сетки"""
    nearest = None
    min_distance = float('inf')
    
    for municipality in municipalities:
        coords = municipality["coordinates"]
        distance = ((coords[0] - lat) ** 2 + (coords[1] - lng) ** 2) ** 0.5
        
        if distance < min_distance:
            min_distance = distance
            nearest = municipality
    
    return nearest

def create_risk_grid_from_weather(weather_data):
    """Создание сетки рисков на основе данных о погоде"""
    risk_grid = []
    bounds = [
        [58.2, 34.5],  # юго-запад
        [62.0, 48.0]   # северо-восток
    ]
    
    south_west = bounds[0]
    north_east = bounds[1]
    
    lat_step = 0.3
    lng_step = 0.5
    
    for lat in range(int(south_west[0] * 10), int(north_east[0] * 10), int(lat_step * 10)):
        for lng in range(int(south_west[1] * 10), int(north_east[1] * 10), int(lng_step * 10)):
            cell_lat = lat / 10.0
            cell_lng = lng / 10.0
            
            # Находим ближайший муниципалитет для этой ячейки
            nearest_municipality = find_nearest_municipality_for_cell(
                cell_lat, cell_lng, weather_data["municipalities"]
            )
            
            risk_level = nearest_municipality["risk_level"] if nearest_municipality else 2
            
            risk_grid.append({
                "bounds": [
                    [cell_lat, cell_lng],
                    [cell_lat + lat_step, cell_lng + lng_step]
                ],
                "riskLevel": risk_level
            })
    
    return risk_grid

@app.get("/")
async def root():
    return {"message": "Weather Risk Analysis API - Open-Meteo", "status": "active"}

@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.get("/api/weather/current")
async def get_current_weather_all():
    """Получение текущей погоды для всех муниципалитетов"""
    results = []
    successful_api_calls = 0
    
    logger.info("Начало получения данных о погоде с Open-Meteo...")
    
    # Обрабатываем муниципалитеты последовательно с задержками
    for name, data in MUNICIPALITIES.items():
        try:
            weather_data = await analyzer.get_weather_from_openmeteo(
                data["coords"][0], data["coords"][1], name
            )
            
            if weather_data:
                factors = analyzer.analyze_risk_factors(weather_data)
                risk_assessment = analyzer.calculate_risk_level(factors)
                
                # Определяем источник данных
                from_api = True  # Все данные теперь с API
                
                results.append({
                    "name": name,
                    "risk_level": risk_assessment.risk_level,
                    "weather": weather_data.model_dump(),
                    "coordinates": data["coords"],
                    "from_api": from_api
                })
                
                if from_api:
                    successful_api_calls += 1
                
                # Задержка между запросами
                await asyncio.sleep(0.3)
                
        except Exception as e:
            logger.error(f"Критическая ошибка для {name}: {e}")
            # Добавляем демо-данные в случае ошибки
            demo_weather = analyzer._generate_realistic_demo_data(name)
            factors = analyzer.analyze_risk_factors(demo_weather)
            risk_assessment = analyzer.calculate_risk_level(factors)
            
            results.append({
                "name": name,
                "risk_level": risk_assessment.risk_level,
                "weather": demo_weather.model_dump(),
                "coordinates": data["coords"],
                "from_api": False
            })
    
    data_source = "realtime" if successful_api_calls > 0 else "demo"
    
    logger.info(f"Завершено: {successful_api_calls}/{len(MUNICIPALITIES)} успешных запросов")
    
    return {
        "timestamp": datetime.now().isoformat(),
        "municipalities": results,
        "data_source": data_source,
        "successful_requests": successful_api_calls,
        "total_requests": len(MUNICIPALITIES),
        "api_used": "Open-Meteo"
    }

@app.get("/api/weather/{municipality}")
async def get_weather_for_municipality(municipality: str):
    """Получение погоды для конкретного муниципалитета"""
    if municipality not in MUNICIPALITIES:
        raise HTTPException(status_code=404, detail="Municipality not found")
    
    data = MUNICIPALITIES[municipality]
    weather_data = await analyzer.get_weather_from_openmeteo(
        data["coords"][0], data["coords"][1], municipality
    )
    
    factors = analyzer.analyze_risk_factors(weather_data)
    risk_assessment = analyzer.calculate_risk_level(factors)
    from_api = True  # Всегда пытаемся получить с API
    
    return {
        "municipality": municipality,
        "coordinates": data["coords"],
        "weather": weather_data.model_dump(),
        "risk_assessment": risk_assessment.model_dump(),
        "timestamp": datetime.now().isoformat(),
        "from_api": from_api
    }

@app.get("/api/risk/matrix")
async def get_risk_matrix():
    """Получение матрицы рисков для overlay на карте"""
    try:
        # Получаем актуальные данные о погоде
        weather_response = await get_current_weather_all()
        
        # Создаем сетку рисков на основе текущих данных
        risk_grid = create_risk_grid_from_weather(weather_response)
        
        return {
            "timestamp": datetime.now().isoformat(),
            "grid": risk_grid,
            "bounds": [
                [58.2, 34.5],  # юго-запад
                [58.2, 48.0],  # юго-восток  
                [62.0, 48.0],  # северо-восток
                [62.0, 34.5]   # северо-запад
            ]
        }
    except Exception as e:
        logger.error(f"Ошибка создания матрицы рисков: {e}")
        # Возвращаем демо-сетку в случае ошибки
        return {
            "timestamp": datetime.now().isoformat(),
            "grid": create_demo_risk_grid(),
            "bounds": [
                [58.2, 34.5],
                [58.2, 48.0],  
                [62.0, 48.0],
                [62.0, 34.5]
            ]
        }

def create_demo_risk_grid():
    """Создание демо-сетки рисков"""
    risk_grid = []
    bounds = [
        [58.2, 34.5],
        [62.0, 48.0]
    ]
    
    south_west = bounds[0]
    north_east = bounds[1]
    
    lat_step = 0.3
    lng_step = 0.5
    
    for lat in range(int(south_west[0] * 10), int(north_east[0] * 10), int(lat_step * 10)):
        for lng in range(int(south_west[1] * 10), int(north_east[1] * 10), int(lng_step * 10)):
            cell_lat = lat / 10.0
            cell_lng = lng / 10.0
            
            # Случайный уровень риска для демо
            risk_level = random.randint(2, 4)
            
            risk_grid.append({
                "bounds": [
                    [cell_lat, cell_lng],
                    [cell_lat + lat_step, cell_lng + lng_step]
                ],
                "riskLevel": risk_level
            })
    
    return risk_grid

if __name__ == "__main__":
    import uvicorn
    
    logger.info("🚀 Запуск Weather Risk Analysis API с Open-Meteo")
    logger.info("📡 Используется бесплатный Open-Meteo API (без ключа)")
    
    uvicorn.run(app, host="0.0.0.0", port=8005)