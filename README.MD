# JuicePass Proxy

This tool will publish JuiceBox data by using a Man in the Middle UDP proxy to MQTT that is auto-discoverable by HomeAssistant. The `Enel X Way` app will continue to function.

It can also publish the IP of the proxy to the JuiceBox directly to avoid using custom local DNS servers using the `update_udpc` and `juicebox_host` command line parameters.

Builds upon work by lovely folks in this issue: https://github.com/home-assistant/core/issues/86588

_Hopefully we won't need this if EnelX fixes their API!_

#### It is required that both your JuiceBox and the machine you are running `juicepassproxy` on have internal, static IPs on your intranet.

## Docker Compose Installation

### Features
*  If `JUICEBOX_HOST` is defined, it will run a telnet script to get the EnelX Server and Port as well as the JuiceBox ID.

*  If `ENELX_IP` is not defined, it will use the CloudFlare DNS (1.1.1.1) to get the IP address of the EnelX Server and avoid a DNS lookup loop.

*  If `LOCAL_IP` is not defined, it will lookup the Local IP address of the Docker.

* If `UPDATE_UDPC` is true, JuicePass Proxy will continually update the JuiceBox via telnet to send its data to JuicePass Proxy. Use this if you are not able to change your DNS to route the JuiceBox traffic to JuicePass Proxy.

### Instructions

1. Pick One Option:

    A. Configure your DNS server running on your network (like Pi-hole or your router) to route all UDP traffic from your JuiceBox to the machine running this proxy. Instructions for how to do this will vary by router. See [Getting EnelX Server IPs](#getting-enelx-server-ips) for instructions on what EnelX Server you need to override.

    B. Set these Docker Environment Variables in your Docker Compose file:</br>

      ```
      UPDATE_UDPC=true
      JUICEBOX_HOST=<IP address of your JuiceBox>
      JPP_HOST=<IP address of the machine that the JuicePass Proxy Docker Container is running on>
      ```

    C. Use your router to redirect traffic from JuiceBox to JuicePass Proxy

      *  Check the port that your JuiceBox is using to communicate. See [Getting EnelX Server IPs](#getting-enelx-server-ips)

      *  Create a redirect rule on your router redirect UDP traffic coming from JuiceBox to the IP:PORT where you are running JuicePass Proxy

      *  Create a masquerade rule on router to masquerade the traffic that goes to JuicePass Proxy IP:PORT (hairpin nat)

      *  Depending of your forward rules, you may need to create an extra rule to allow that forwarding traffic

      *  Sample MikroTik rules for reference (10.1.12.230 = JuiceBox, 10.1.0.22 = JuicePass Proxy)</br>

      ```
      add action=dst-nat chain=dstnat comment=juicebox dst-port=8042 protocol=udp src-address=10.1.12.230 to-addresses=10.1.0.22 to-ports=8042
      #
      add action=masquerade chain=srcnat comment=juicebox dst-address=10.1.0.22 dst-port=8042 protocol=udp src-address=10.1.12.230
      ```

1. Add the `juicepassproxy` container to your Docker Compose file.

    A.  Set `ports:` to the port listed in the UDCP line, likely `8047` _(see [Getting EnelX Server IPs](#getting-enelx-server-ips))_.

    B. Define the applicable environment variables _(see [Docker Environment Variables](#docker-environment-variables))_.

    C. Specify the location for the config and optionally the logs folder

1. Start the Docker container.

### Example Docker Compose

```yaml
networks:
  default:
    driver: bridge
    ipam:
      config:
        - subnet: 172.16.100.0/24

services:
  juicepassproxy:
    image: ghcr.io/snicker/juicepassproxy:latest
    hostname: juicepassproxy
    container_name: juicepassproxy
    restart: unless-stopped
    logging:
      driver: json-file
    ports:
      - 8047:8047/udp
    environment:
      - JUICEBOX_HOST=10.100.50.30
      - UPDATE_UDPC=true
      - JPP_HOST=10.100.200.50
      - MQTT_HOST=10.100.200.5
      - MQTT_USER=mosquitto
      - MQTT_PASS=***
    volumes:
      - /etc/localtime:/etc/localtime:ro
      - ./config:/config
      - ./log:/log #Optional
```

### Docker Environment Variables

Variable | Required | Description & Default |
-- | -- | --
**JUICEBOX_HOST** | **Recommended**</br></br>**Required if Update UDPC is True.** | If defined, will attempt to get the EnelX Server Name, IP, and Port using telnet.
**UPDATE_UDPC** | No | Default: false. If true, will continually update the JuiceBox via telnet to point to JuicePass Proxy.
**TELNET_TIMEOUT** | No | Default: 30. Timeout in seconds for telnet operations.
**JPP_HOST**  | **Required if Update UDPC is True** |  This is the IP or Hostname of the machine where JuicePass Proxy is running (**not** the IP of the Docker Container)
**MQTT_HOST** | No | 127.0.0.1
**MQTT_PORT** | No | 1883
**MQTT_USER** | No |
**MQTT_PASS** | No |
**MQTT_DISCOVERY_PREFIX** | No | homeassistant

<details>
<summary><h3>Less Common Docker Environment Variables</h3></summary>

Variable | Required | Description & Default |
-- | -- | --
**DEVICE_NAME** | No | JuiceBox
**DEBUG** | No | false
**EXPERIMENTAL**  | No  | Default: false. Enables additional entities in Home Assistant that are in in development or can be used toward developing the ability to send commands to a JuiceBox
**IGNORE_ENELX**  | No  | Default: false. If true, will not send commands received from EnelX to the JuiceBox nor send outgoing information from the JuiceBox to EnelX
**TELNET_TIMEOUT**  | No  | Default: 30. Timeout in seconds for telnet operations.
**JUICEBOX_ID**  | No | If not defined, will attempt to get the JuiceBox ID using telnet.
**LOCAL_IP**<br><br>_Deprecated Variable: SRC_ | No | If not defined, will attempt to get the Local Docker IP. Can optionally define port (ex. 127.0.0.1:8047). If unsuccessful, will default to 127.0.0.1.
**LOCAL_PORT** | No | Local port for JuicePass Proxy to listen on. If not defined, will use the EnelX Port.
**ENELX_IP**<br><br>_Deprecated Variable: DST_ | No | If not defined, will attempt to get the IP of the EnelX Server. If unsuccessful, will default to 54.161.185.130. Can optionally define port (ex. 54.161.185.130:8047). If defined, only use the IP address of the EnelX Server and not the fully qualified domain name to avoid DNS lookup loops.
</details>

<details>
<summary><h2>Manual Installation</h2></summary>

1. Clone this repository
2. Use Python 3.10+ (I recommend setting up a virtual environment)
3. Install requirements `pip install -r requirements.txt`
4. Launch by executing `python3 juicepassproxy.py --juicebox_host <IP of the JuiceBox> --mqtt_host <mqtt_host>` (params documented below)
5. Nothing happens!
6. Configure your DNS server running on your network (like Pi-hole or your router) to route all DNS requests from EnelX to the machine running this proxy. For me this was `juicenet-udp-prod3-usa.enelx.com`. See below for instructions to determine that.
7. Alternatively to #6, you can enable `--update_udpc` on the command line and set `--juicebox_host` and the application will force publish the IP in the `--local_ip` argument to the JuiceBox and avoid the need to set DNS rules on your router or DNS server. **NOTE: if you need to publish a different IP than the one in the `--local_ip` argument, you can make use of the `--jpp_host` arg.**

### CLI Options

```
options:
  -h, --help            show this help message and exit
  --juicebox_host HOST  Host or IP address of the JuiceBox. Required for
                        --update_udpc or if --enelx_ip not defined.
  --update_udpc         Update UDPC on the JuiceBox. Requires --juicebox_host
  --jpp_host, --juicepass_proxy_host HOST
                        EXTERNAL host or IP address of the machine running
                        JuicePass Proxy. Optional: only necessary when using
                        --update_udpc and it will be inferred from the address
                        in --local_ip if omitted.
  -H, --mqtt_host HOST  MQTT Hostname to connect to (default: 127.0.0.1)
  -p, --mqtt_port PORT  MQTT Port (default: 1883)
  -u, --mqtt_user USER  MQTT Username
  -P, --mqtt_password PASSWORD
                        MQTT Password
  -D, --mqtt_discovery_prefix PREFIX
                        Home Assistant MQTT topic prefix (default:
                        homeassistant)
  --config_loc LOC      The location to store the config file (default:
                        ~/.juicepassproxy)
  --log_loc LOC         The location to store the log files (default: ~)
  --name DEVICE_NAME    Home Assistant Device Name (default: JuiceBox)
  --debug               Show Debug level logging. (default: Info)
  --experimental        Enables additional entities in Home Assistant that are
                        in in development or can be used toward developing the
                        ability to send commands to a JuiceBox.
  --ignore_enelx        If set, will not send commands received from EnelX to
                        the JuiceBox nor send outgoing information from the
                        JuiceBox to EnelX
  --telnet_timeout SECONDS
                        Timeout in seconds for Telnet operations (default: 30)
  --juicebox_id ID      JuiceBox ID. If not defined, will obtain it
                        automatically.
  --local_ip IP         Local IP (and optional port). If not defined, will
                        obtain it automatically. (Ex. 127.0.0.1:8047)
                        [Deprecated: -s --src]
  --local_port PORT     Local Port for JPP to listen on.
  --enelx_ip IP         Destination IP (and optional port) of EnelX Server. If
                        not defined, --juicebox_host required and then will
                        obtain it automatically. (Ex. 54.161.185.130:8047)
                        [Deprecated: -d --dst]
```

_For `--enelx_ip`, only use the IP address of the EnelX Server and **not** the fully qualified domain name (FQDN) to avoid DNS lookup loops._

</details>

#### Deprecated Environment Variables and Command Line options will continue to work for now but will be removed at some point in the future.

## Getting EnelX Server IPs

To get the destination IP:Port of the EnelX server, telnet into your JuiceBox device:
`$ telnet 192.168.x.x 2000`
and type the `list` command:

```
list
! # Type  Info
# 0 FILE  webapp/index.html-1.4.0.24 (1995, 0)
# 1 UDPC  juicenet-udp-prod3-usa.enelx.com:8047 (26674)
```

The address is in the `UDPC` line. Run, `ping`, `nslookup`, or similar command to determine the IP.

As of November, 2023: `juicenet-udp-prod3-usa.enelx.com` = `54.161.185.130`.
