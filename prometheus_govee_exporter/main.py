"""Continuously export data from Govee temperature sensors for Prometheus.

See https://github.com/chipx86/prometheus-govee-exporter for documentation and
details.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime
from typing import Dict, Tuple

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from prometheus_client import start_http_server, Gauge, Enum


# The default interval at which sensors should be polled.
DEFAULT_POLL_INTERVAL_SECS = 30

# The default port for serving content to be consumed by Prometheus.
DEFAULT_EXPORTER_PORT = 9889


def parse_gvh5072_5075_data(
    data: Dict[int, bytes],
) -> Tuple[float, float, int]:
    """Parse data from a Govee GVH5072/5075 temperature/humidity sensors.

    The following data is parsed from manufacturer key 0xEC88.

    Data is in the form of::

        00000000  00000000  00000000  00000000  00000000  00000000
        ^------^  ^^-------------------------^  ^------^  ^------^
        |         ||                             |         |
        |         ||                             |         |- Unknown (padding?)
        |         ||                             |
        |         ||                             |- Battery remaining %
        |         ||
        |         ||- Temp and humidity (big endian)
        |         |
        |         |- Sign bit
        |
        ^- Unknown (padding?)

    For more information, see: https://github.com/Thrilleratplay/GoveeWatcher

    Args:
        data (dict):
            Bleak's parsed manufacturer data.

    Returns:
        tuple:
        A 3-tuple in the form of:

        0 (float):
            The temperature in Celsius.

        1 (float):
            The humidity as a percentage betweem 0 and 100.

        2 (int):
            The battery level as a percentage between 0 and 100.
    """
    temp_data = data[0xec88]
    temp_vals = int.from_bytes(temp_data[1:4], 'big')

    # Determine if the temperature is a negative value, and chop off the sign so
    # we don't end up with crazy temperature data like 839 C.
    is_negative = temp_vals & 0x800000
    temp_vals = temp_vals & 0x7FFFFF

    # Extract the temperature and humidity.
    temp = float(temp_vals / 10_000)
    humidity = float((temp_vals % 1_000) / 10)

    if is_negative:
        temp = -temp

    # Extract the battery percentage remaining.
    battery_vals = temp_data[4]

    return temp, humidity, battery_vals


GOVEE_PARSERS = {
    'GVH5072': parse_gvh5072_5075_data,
    'GVH5075': parse_gvh5072_5075_data,
}


class GoveeExporter:
    """An exporter for Govee temperature/humidity sensor devices.

    This watches for Bluetooth advertisements from compatible Govee devices
    (currently H5072/H5075 devices) and emits data over HTTP for Prometheus
    to consume.

    The data emitted include:

    * ``govee_temp_c_deg``: Temperature (Celsius)
    * ``govee_temp_f_deg``: Temperature (Fahrenheight)
    * ``govee_humidity_pct``: Humidity (as a percentage between 0-100)
    * ``govee_battery_pct``: Battery remaining (as a percentage between 0-100)

    Each of these are output with ``{device="<devicename"}``.
    """

    def __init__(
        self,
        poll_interval_secs: int,
        devices: Dict[str, str],
    ) -> None:
        """Initialize the exporter.

        This will set up all of the Prometheus Gauges for emitting temperature,
        humidity, and battery data.

        Args:
            poll_interval_secs (int):
                The interval between Bluetooth polls in seconds.

            devices (dict):
                A mapping of scannable device IDs to labels. If empty, all devices
                will be scannable.
        """
        self.poll_interval_secs = poll_interval_secs
        self.devices = devices

        self.temp_c_gauge = Gauge('govee_temp_c_deg',
                                  'Govee Temperature (Celsius)',
                                  ['device', 'label'])
        self.temp_f_gauge = Gauge('govee_temp_f_deg',
                                  'Govee Temperature (Fahrenheit)',
                                  ['device', 'label'])
        self.humidity_gauge = Gauge('govee_humidity_pct',
                                    'Govee Humidity %',
                                    ['device', 'label'])
        self.battery_gauge = Gauge('govee_battery_pct',
                                   'Govee Battery Remaining %',
                                   ['device', 'label'])

    async def run_scan_loop(self) -> None:
        """Continuously scan for devices and advertisements.

        This will scan using the configured polling interval. New advertisements
        will be handled by :py:meth:`on_advertisement`.
        """
        scanner = BleakScanner(
            lambda *args, **kwargs: self.on_advertisement(*args, **kwargs))

        if self.devices:
            device_list: List[str] = []

            for device, label in sorted(self.devices.items(),
                                        key=lambda pair: pair[0]):
                if device == label:
                    device_list.append(device)
                else:
                    device_list.append(f'{device}={label}')

            logging.info('Scanning for devices (%s)...', ';'.join(device_list))
        else:
            logging.info('Scanning for all devices...')

        while True:
            await scanner.start()
            await asyncio.sleep(self.poll_interval_secs)
            await scanner.stop()

    def update_temp(
        self,
        device: str,
        label: str,
        temp_c: float,
        temp_f: float,
    ) -> None:
        """Update temperature for a device.

        Args:
            device (str):
                The unique name of the device.

            label (str):
                The label to use for the device.

            temp_c (float):
                The temperature in Celsius.

            temp_f (float):
                The temperature in Fahrenheight.
        """
        self.temp_c_gauge.labels(device=device,
                                 label=label).set(temp_c)
        self.temp_f_gauge.labels(device=device,
                                 label=label).set(temp_f)

    def update_humidity(
        self,
        device: str,
        label: str,
        humidity: float,
    ) -> None:
        """Update humidity for a device.

        Args:
            device (str):
                The unique name of the device.

            label (str):
                The label to use for the device.

            humidity (float):
                The humidity as a percentage between 0-100.
        """
        self.humidity_gauge.labels(device=device,
                                   label=label).set(humidity)

    def update_battery(
        self,
        device: str,
        label: str,
        battery: int,
    ) -> None:
        """Update battery remaining for a device.

        Args:
            device (str):
                The unique name of the device.

            label (str):
                The label to use for the device.

            battery (int):
                The battery remaining as a percentage between 0-100.
        """
        self.battery_gauge.labels(device=device,
                                  label=label).set(battery)

    def on_advertisement(
        self,
        device: BLEDevice,
        advertisement_data: AdvertisementData,
    ) -> None:
        """Handle an advertisemenet from a device.

        This will handle handle only devices starting with ``GVH``, which identify
        a Govee device. If it's a match, the device's manufacturer data will be
        parsed out and data will be emitted to the HTTP port for Prometheus.

        Args:
            device (bleak.backends.device.BLEDevice):
                The device emitting the advertisement.

            advertisement_data (bleak.backends.scanner.AdvertisementData):
                The parsed advertisement data.
        """
        device_name = device.name

        if not device_name.startswith('GVH'):
            return

        device_label = self.devices.get(device_name)

        if not device_label and self.devices:
            # This isn't a device we're scanning for.
            logging.info('Ignoring device "%s". It\'s not on our scan list.',
                         device_name)
            return

        parser = GOVEE_PARSERS.get(device_name.split('_')[0])

        if not parser:
            return

        temp_c, humidity, battery = parser(advertisement_data.manufacturer_data)

        if 0:
            last_temp_c = self.last_temps_c.get(device_name)

            if (last_temp_c is not None and
                abs(temp_c - last_temp_c) > self.TEMP_C_ERROR_THRESHOLD):
                # This may be a data error. Ignore this.
                #
                # It's possible that this is data corruption, or something just
                # unknown about the data being sent. I personally get it only from
                # a device sitting in the fridge, which doesn't have great reception.
                #
                # In my case, when this happens, the resulting temperature is 839 C
                # (sometimes 840 C), while the previous is around 2-3 C. This is
                # pretty consistent.
                #
                # I don't want to assume anything about the data being corrupted, or
                # what numbers are expectd when this happens. So we'll just detect a
                # large-enough temperature difference.
                return

        # Convert from Celsius to Fahrenheight.
        temp_f = round(32 + 9 * temp_c / 5, 2)

        device_label = self.devices.get(device_name, device_name)

        self.update_temp(device_name, device_label, temp_c, temp_f)
        self.update_humidity(device_name, device_label, humidity)
        self.update_battery(device_name, device_label, battery)

        logging.info('%s: %s (%s): Temp = %sC (%sF), Humidity = %s%%, '
                     'Battery = %s%%',
                     datetime.now(),
                     device.name,
                     device_label,
                     temp_c,
                     temp_f,
                     humidity,
                     battery)


async def run() -> None:
    """Main handler for the exporter.

    This will parse arguments and then set up the HTTP server and Bluetooth
    scanner.
    """
    parser = argparse.ArgumentParser(
        description='Provide Govee sensor data to Prometheus.')
    parser.add_argument(
        '-p',
        '--port',
        type=int,
        default=DEFAULT_EXPORTER_PORT,
        help=(
            'The HTTP port to serve for Prometheus. The default is %s.'
            % DEFAULT_EXPORTER_PORT
        ))
    parser.add_argument(
        '-i',
        '--poll-interval',
        type=int,
        default=DEFAULT_POLL_INTERVAL_SECS,
        help=(
            'The default poll interval in seconds. The default is %s.'
            % DEFAULT_POLL_INTERVAL_SECS
        ))
    parser.add_argument(
        'devices',
        nargs='*',
        metavar='DEVICE[=LABEL]',
        help=(
            'Devices to scan for. You can optionally assign a label to each, which '
            'can help provide better information in Prometheus or tools like '
            'Grafana. For example: "GVH5075_ABCD=Living Room" GVH5075_EFGH=Office.'
            'If no devices are provided, all available devices will be returned.'
        ))
    parser.add_argument(
        '--log-level',
        dest='log_level',
        default='WARNING',
        choices=(
            'DEBUG',
            'INFO',
            'WARNING',
            'ERROR',
            'CRITICAL',
        ),
        help=(
            'The log level to use. Choose "INFO" to show scanning information. '
            'The default is WARNING.'
        ))
    parser.add_argument(
        '--log-filename',
        dest='log_filename',
        help=(
            'A file to use for all logging. If not provided, loggging will go to '
            'standard out.'
        ))

    options = parser.parse_args()

    devices = {}

    if options.devices:
        for pair in options.devices:
            try:
                device, label = pair.split('=', 2)
            except ValueError:
                device = pair
                label = device

            devices[device] = label

    # Set up logging.
    logging.basicConfig(filename=options.log_filename,
                        level=getattr(logging, options.log_level))

    # Start serving over the port.
    start_http_server(options.port)

    # Set up the exporter and scan for devices.
    exporter = GoveeExporter(poll_interval_secs=options.poll_interval,
                             devices=devices)
    await exporter.run_scan_loop()


def main():
    asyncio.run(run())


if __name__ == '__main__':
    main()
