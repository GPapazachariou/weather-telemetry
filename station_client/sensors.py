"""
Sensor driver abstraction for weather station clients.

To connect real hardware, implement SensorDriver and pass the instance to the client.
Example hardware drivers to add:
  - BME280Driver  (temperature/humidity/pressure via I2C, e.g. Adafruit CircuitPython)
  - DHT22Driver   (temperature/humidity via GPIO, e.g. Raspberry Pi)
  - SerialDriver  (readings forwarded over USB serial from Arduino/ESP32)
"""

import hashlib
import math
import random
from abc import ABC, abstractmethod


class SensorDriver(ABC):
    """Abstract base class for weather sensor drivers."""

    @abstractmethod
    def read(self) -> dict:
        """
        Read sensor values.

        Returns a dict with keys: temperature (°C), humidity (%), windspeed (m/s).
        Raise RuntimeError if the sensor cannot be read.
        """
        ...


class SimulatedSensorDriver(SensorDriver):
    """
    Simulated sensor driver for testing without hardware.
    Produces deterministic mean values per station with Gaussian noise.
    """

    def __init__(self, station_id: str):
        self.station_id = station_id

    def read(self) -> dict:
        return {
            "temperature": self._value_for("temperature", lo=-40.0, hi=85.0, noise=0.6),
            "humidity": self._value_for("humidity", lo=0.0, hi=100.0, noise=2.5),
            "windspeed": self._value_for("windspeed", lo=0.0, hi=100.0, noise=1.2),
        }

    def _value_for(self, metric: str, lo: float, hi: float, noise: float) -> float:
        mean = self._stable_mean(metric, lo, hi)
        value = mean + random.gauss(0, noise)
        value = max(lo, min(hi, value))
        return round(value, 2)

    def _stable_mean(self, metric: str, lo: float, hi: float) -> float:
        digest = int(hashlib.sha256(f"{self.station_id}:{metric}".encode()).hexdigest()[:8], 16)
        base = digest % 50
        return lo + (base / 49.0) * (hi - lo)


# ---------------------------------------------------------------------------
# Hardware driver stubs — uncomment and install the required library when
# connecting real sensors to a Raspberry Pi or compatible SBC.
# ---------------------------------------------------------------------------

# class BME280Driver(SensorDriver):
#     """Temperature / humidity / pressure via I2C (Bosch BME280).
#
#     Install: pip install adafruit-circuitpython-bme280
#     Wiring:  SDA → GPIO2, SCL → GPIO3, VCC → 3.3V, GND → GND
#     """
#     def __init__(self, i2c_address: int = 0x76):
#         import board
#         import busio
#         import adafruit_bme280.basic as adafruit_bme280
#         i2c = busio.I2C(board.SCL, board.SDA)
#         self._sensor = adafruit_bme280.Adafruit_BME280_I2C(i2c, address=i2c_address)
#
#     def read(self) -> dict:
#         return {
#             "temperature": round(self._sensor.temperature, 2),
#             "humidity": round(self._sensor.humidity, 2),
#             "windspeed": 0.0,  # BME280 has no anemometer; add separately
#         }


# class DHT22Driver(SensorDriver):
#     """Temperature / humidity via GPIO (DHT22 / AM2302).
#
#     Install: pip install adafruit-circuitpython-dht
#     Wiring:  DATA → any GPIO pin, VCC → 3.3V–5V, GND → GND
#     """
#     def __init__(self, gpio_pin: int = 4):
#         import board
#         import adafruit_dht
#         pin = getattr(board, f"D{gpio_pin}")
#         self._sensor = adafruit_dht.DHT22(pin)
#
#     def read(self) -> dict:
#         return {
#             "temperature": round(self._sensor.temperature, 2),
#             "humidity": round(self._sensor.humidity, 2),
#             "windspeed": 0.0,  # DHT22 has no anemometer; add separately
#         }
