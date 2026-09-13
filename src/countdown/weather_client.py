import datetime as dt

from pyowm import OWM
from pyowm.weatherapi30.weather import Weather

from countdown.config_manager import WeatherConfig
from display.weather_panel import WeatherPanel

class WeatherClient:
    def __init__(self, config: WeatherConfig):
        self.owm = OWM(config.api_key)
        self.mgr = self.owm.weather_manager()
        self.location = config.location
        self.weather: Weather | None = None
        self.rec_time: int | None = None


    def get_weather(self) -> WeatherPanel:
        return WeatherPanel(Weather(1789276877, None,
                                    None, 1,
                                    {}, {},
                                    {}, 1,
                                    {}, {"temp": 286.42},
                                    None, None,
                                    212, "",
                                    1, 1,
                                    1, 1,
                                    None))


        if self.weather and self.rec_time:
            last_poll = dt.datetime.fromtimestamp(self.rec_time)
            if dt.datetime.now() - dt.timedelta(minutes=30) < last_poll:
                return WeatherPanel(self.weather)
        observation = self.mgr.weather_at_place(self.location)
        self.weather = observation.weather
        self.rec_time = observation.rec_time
        return WeatherPanel(self.weather)
