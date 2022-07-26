# UM_FeatherS2_MSFS2020_GPSout_GPRMC_and_GPGGA
 RX fliter and dispay MSFS2020 GPS data on 4x20 serLCD


Display flown track to Sparkfun serLCD and use ground speed to control displayed data

Software:
See 'Example'

Used hardware:

a) a Personal computer running Microsoft Windows 11 or a Microsoft XBox seriex X (not tested) on which are installed and running: 
    - Microsoft Flight simulator 2020 (MSFS2020) (```https://www.flightsimulator.com/```);
    - FSUIPC7 from Pete & Jowhn Dowson (```http://www.fsuipc.com/```)

b) Unexpected Maker FeatherS2: ```https://unexpectedmaker.com/shop``` or: ```https://www.adafruit.com/product/4769```;

c) Sparkfun serLCD 4x20: ```https://www.sparkfun.com/products/16398```;

d) Adafruit MCP2221A breakout - General Purpose USB to GPIO ADC I2C - Stemma QT / Qwiic (Product ID 4471 ```https://www.adafruit.com/product/4471```)
   or: other type of USB to RS232 serial converter (FTDI), e.g.: model YP-05. Attention: use a model that is able to provide logic 3V3 level signals.

e) Adafruit ISO154x, Bidirectional I2C Isolator STEMMA QT/Qwii ( Product nr 4903, ```https://www.adafruit.com/product/4903```)

Flow of the GPS data:  PC MSFS2020 w FSUIPC7 > COMx > MCP2221 TX/RX > FeatherS2 RX/TX.
I2C connection #1: MCP2221 QT > QT ISO154x QT > QT FeatherS2
I2C connection #2: MCP2221 5V > QT serLCD red wire
                   MCP2221  GND > QT serLCD black wire
                   ISO154x SDA (blue wire) on FeatherS2 side of ISO154x > QT serLCD
                   ISO154x SCL (yellow wire) on FeatherS2 side of IS154x > QT serLCD

This project uses circuitpython.

Goals of this project:

To receive, filter and use certain elements of GPRMC GPS datagram data sent by an add-on called ```FSUIPC7``` to the ```Microsoft Flight Simulator 2020 (FS2020)```.
From the filtered GPRMC GPS type of datagram this project only uses the ```Track made good true``` and the ```groundspeed```. The track flown by the aircraft is displayed on the 4x20 serLCD, only when the groundspeed value exceeds a certain minimum value set in the micropython script. If the groundspeed is zero the aircraft is assumed to be halted or be parked. In that case the script will display ```Airplane stopped or parked```. When the groundspeed is > 0.2 and < 30 kts, the script will display ```Airplane is taxying```.  As soon as the groundspeed exceeds 30 kts the track flown value will be displayed onto the 4x20 serLCD.

+------------------------------------+
| USB-UART-to-FeatherS2 TX/RX pins:  |
+-----------------+------------------+
|  USB-to-serial  |  FeatherS2       |
|  converter      |  pin:            |
|  pin:           |                  |
+-----------------+------------------+
|- ```TX```pin    | to ```RX```pin   |
|- ```RX```pin    | to ```TX``` pin  |
+-----------------+------------------+

NOTE: The baudrate is set to 4800 baud (inside the FSUIPC7 > GPSout > 1 (or > 2). There, also select the correct COM-port for MS Windows 11)

Data Indicator LED:
Many USB-to-Serial converters have a LED that signals the presence of data. The YP-5 listed under d) above has such a LED.

I used the Mu-editor app to save, edit and test the script file: ```code.py```.


Disclamer:
This project has been tested and working on a pc running MS Windows 11 Pro.

Other sources:
To read more about the GPS GPRMC datagram specification see: ```https://docs.novatel.com/OEM7/Content/Logs/GPRMC.htm```.

License: MIT (see LICENSE file)