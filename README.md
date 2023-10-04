# pv-dashboard

Custom made logging with dashboard for photovoltaic systems

* logging via RS485
* database: sqlite3
* dashboard: streamlit

![dashboard day](doc/screenshot_0.png)
![dashboard month](doc/screenshot_1.png)

## specs
### PV system
* panels: 132x Schüco MPE 185 MS 06 (185W)
* inverter: 4x Schüco SGI 4500 plus, 1x Schüco 3500 T plus 02
* commissioning date: 2011

### hardware
* Banana Pi BPI-M1 with armbian
* RS485 to USB converter: YYH-256 (MAX485, CH340)

## Getting started
1. clone repo\
`git clone https://github.com/yannikmotzet/pv-dashboard.git`

2. install Python dependencies\
`pip install -r requirements.txt`

3. create and start services
* logger: 

    `sudo vim /etc/systemd/system/pv-logger.service`

    ```
    [Unit]
    Description=PV logger daemon

    [Service]
    WorkingDirectory=/home/pi/pv-dashboard/
    User=pi
    ExecStart=/usr/bin/python3 logging/logger_daemon.py
    Type=simple

    [Install]
    WantedBy=multi-user.target
    ```

    `sudo systemctl enable pv-logger.service`

* dashboard:\
    `sudo vim /etc/systemd/system/pv-dashboard.service`

    ```
    [Unit]
    Description=PV Dashboard (Streamlit)

    [Service]
    WorkingDirectory=/home/pi/pv-dashboard/
    User=pi
    ExecStart=python3 -m streamlit run dashboard/main.py --browser.gatherUsageStats False
    Type=simple

    [Install]
    WantedBy=multi-user.target
    ```

    `sudo systemctl enable pv-dashboard.service`

## knowledge pool
* [TechCrawler - dd-wrt Logger per RS-485 an Kaco Wechselrichter](https://web.archive.org/web/20180423200510/http://techcrawler.riedme.de/2011/09/25/dd-wrt-logger-per-rs-485-an-kaco-wechselrichter/)
* [photovoltaikforum - RS485 Protokoll KACO Powador Wechselrichter](https://web.archive.org/web/20151217143954/http://www.photovoltaikforum.com/datenlogger-f5/rs485-protokoll-kaco-powador-wechselrichter-t24143-s80.html#p562493)
* [plieningerweb/kacors485](https://github.com/plieningerweb/kacors485)