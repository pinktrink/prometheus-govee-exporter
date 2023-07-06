# Prometheus Govee Exporter

This is a simple tool for exporting temperature, humidity, and battery levels
from compatible [Govee](https://us.govee.com/) sensors to
[Prometheus](https://prometheus.io/) or compatible services.

It can be run standalone or in Docker.


## Compatible Devices

* [GVH5072](https://www.amazon.com/Bluetooth-Temperature-Thermometer-Hygrometer-Calibration/dp/B07DWMJKP5)
* [GVH5075](https://www.amazon.com/Govee-Thermometer-Hygrometer-Temperature-Notification/dp/B08QDF3ZJ7)

In the future, more devices might be supported.


# Manual Installation

This has only been tested on Linux environments. Make sure you have Bluetooth
support already working.

To install manually, run:

```
$ pip install prometheus-govee-exporter
```

Then simply run:

```
$ prometheus-govee-exporter
```

If all goes well, this will begin scanning for compatible Govee devices, reporting their status.

You can also scan for specific devices:

```
$ prometheus-govee-exporter GVH5072_ABC GVH5075_DEF
```

And assign labels:

```
$ prometheus-govee-exporter GVH5072_ABCD=Office "GVH5075_DEFG=Living Room"
```

There are additional command line flags for changing the polling interval, log level, and export HTTP port.


# Docker Installation

This is available on Docker as `chipx86/prometheus-govee-exporter`. You'll need
to run this in privileged mode and mount `/var/run/dbus/:/var/run/dbus/`.

Here's a sample `docker-compose.yaml` configuration linking the exporter,
Prometheus, and Grafana together:

```yaml
version: '3.7'

services:
  govee-exporter:
    image: chipx86/prometheus-govee-exporter
    privileged: true
    environment:
      - DEVICES="GVH5075_A123=Living Room" GVH5075_B456=Office GVH5072_C987=Bedroom GVH5075_D654=Outside

    volumes:
      - '/var/run/dbus/:/var/run/dbus/'

    ports:
      - 9889:9889

  prometheus:
    image: prom/prometheus:v2.36.2
    restart: always
    hostname: 'prometheus'
    volumes:
      - './config:/etc/prometheus'

    depends_on:
      - govee-exporter

    ports:
      - 9090:9090

  grafana:
    image: grafana/grafana-enterprise
    restart: always
    hostname: 'grafana'
    depends_on:
      - prometheus

    ports:
      - 3000:3000
```

The following environment variables can be set:

* `DEVICES`: A space-separated list of devices to modify, optionally assigned to a
  label. Make sure to quote the assignment if specifying labels with spaces.

* `PORT`: The HTTP port to export. This defaults to 9889.

* `LOG_LEVEL`: The logging level. This supports `DEBUG` (showing lots of Bluetooth communication data), `INFO` (Temperature/humidity/battery levels, as they come in), `WARNING` (general warnings), or `ERROR` (error information), or `CRITICAL` (probably will never see this).


# Configuring Prometheus

To add this to Prometheus, specify the following in your `prometheus.yml`
(`config/prometheus.yml`, in the above `docker-compose` setup):

```
scrape_configs:
  - job_name: my_govee
    static_configs:
      - targets:
          - 'your-hostname:9889'
```

The following gauge data will be exported for each device/label:

* `govee_temp_c_deg`: The temperature in Celsius
* `govee_temp_f_deg`: The temperature in Fahrenheit
* `govee_humidity_pct`: The humidity level as a percentage
* `govee_battery_pct`: The battery level as a percentage

You can query based off the following parameters:

* `device`: The Govee device ID (e.g., `GVH5072_ABCD`)
* `label`: The assigned label
* `instance`: The server hosting the exporter
* `job`: The configured job name in `prometheus.yml`


# Neat, what else do you do?

I work on the open source, extensible
[Review Board](https://www.reviewboard.org) code and document review system over at
[Beanbag](https://www.beanbaginc.com).

You can also find me here:

* [Blog](https://blog.chipx86.com)
* [Mastodon](https://mastodon.online/@chipx86)
* [Twitter](https://twitter.com/@chipx86)
* [GitHub](https://github.com/chipx86)
