
"""
    FOR CIRCUITPYTHON ONLY

    Copyright 2021 Paulus H.J. Schulinck (@paulsk on discord, CircuitPython, deepdiver member)
    Github: @PaulsPt
    Permission is hereby granted, free of charge, to any person obtaining a copy
    of this software and associated documentation files (the "Software"),
    to deal in the Software without restriction, including without limitation the rights to use,
    copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software,
    and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

    The above copyright notice and this permission notice shall be included in all copies
    or substantial portions of the Software.

    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
    INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE
    AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
    DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
    ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

    End of license text

    (Using firmware: Adafruit CircuitPython 7.0.0-alpha.3-15-gbc014cecb on 2021-06-04; Raspberry Pi Pico with rp2040)

    This is the main python script for the project 'msfs2020_gps_rx',
    using a Raspberry Pi Pico dev board, mounted on a Seeed Grove Shield for Pi Pico
    Attached to it via I2C: a 20x4 character Hitachi 44780 LCD with piggy-back I2C expander.
    See the README.md and documentation folder for details about this project.

    Update 2021-10-10
    This version is modified to use it on an Adafruit (Unexpected Maker) FeatherS2 (= ESP32S2) board
    and a SparkFun SerLCD 20x4 RGB Qwwic display connected via a SparkFun logic level converter (5V / 3V3).
    (Using firmware: Adafruit CircuitPython 6.3.0 on 2021-06-01; FeatherS2 with ESP32S2)
    This version also has functions to read data details of:
    a) the operating system the board is running on. See function get_os_info();
    b) the (not so unique!) cpu id. See function get_cpu_id().
    Both functions are called by the function my_board().

    Update 2022-07-04/05
    Changed platform to: an Unexpected Maker FeatherS2 (with Adafruit CircuitPython v.8.0.0-alpha.1).
    I2C via QT/Stemma connector to a 3.3 logic SparkFun SerLCD 16x4.
    I made some changes in function get_cpu_id() because it caused an UnicodeError. I made a lot of changes in the
    split_types() function. For this I could delete the function bfr_fnd(). I made also changes to the ck_uart()
    function. In ck_uart() I added checks to see if the GPS messages of tyep $GPRMC and $GPGGA have there ID's and
    in the tail of the message is a '*' character.
    For UART I changed the use of board.UART() for busio.UART because the busio version gives me more settings flexibility:
    baudrate, timeout, receiver_buffer_size. I experienced a great decrease of failed/rejected msg receptions. Before these
    latest modifications, the message wait times were average 10.5 seconds with extremes of 13.6 seconds. Now, the average
    wait time for a messages is between 0.4 and 0.99 seconds, incidently extremes of 4.98 seconds. On 20 messages,
    these extremes happened 2 times. Comaring the average message wait time between the old and the new algorythm,
    gives an efficiency gain of a factor 20 (maximum) and a factor 10 (minimum).
    I added functionality to perform some reception time diagnostics. This functionality is controlled via the global flag 'use_diagnosics'.
    There is also a flag 'use_dotstar' which controls the use of the built-in RGB LED.
    This script has a 'gps_msgs' class which is used to store and retrieve the received gps msg data.
    The gps data comes from the FSUIPC7 add-on software for MSFS2020, via the Options menu, GPS Out..., set to the MS Windows 10/11 COM port
    of the USB-to-RS232 interface board and in FSUIPC7 GPS Out set for a baudrate of 4800 bps.

    Update 2022-07-25.
    Added an Adafruit MCP2221a Microchip.com USB-I2C/UART Combo. Serial Number: 0003175453
    VID 0x04D8, PID 0x00DD. Power source: bus-powered
    GP0 = 2 (LED_URX)
    GP1 = 3 (LED_UTX) (connected to external blue LED)
    GP2 = 1 (USBCFG)
    GP3 = 1 (LED_I2C)

    Update 2022-07-27 test with an Adafruit CP2101N.
    Worked OK after Windows driver "Silicon Labs CP210x USB to UART bridge (COM25) was present.
"""

import board
import busio
import digitalio
import microcontroller
import sys, os
from time import sleep, monotonic_ns
import adafruit_dotstar as dotstar
import feathers2
# +--------------------------+
# | Imports for LCD control  |
# +--------------------------+
from sparkfun_serlcd import Sparkfun_SerLCD_I2C

# -----------------------+
# General debug flag     |
my_debug = False      #  |
# -----------------------+
# Other global flags     |
ctrl_c_flag = False   #  |
# -----------------------+
my_os = None  # will hold a list containing O.S. info
my_machine = None
#               like fw version, machine name.
#               Data collected through function: get_os_info()
my_cpu_id = None # collected through function get_cpu_id()

# +--------------------------------------+
# | Msg rx diagnostics                   |
# +--------------------------------------+
use_diagnosics = False
if use_diagnosics:
    diagnostics_iterations = 20 # Perform rx msg diagnostics for n times
    diagn_dict = {} # used for msg receive time diagnostics
else:
    diagn_dict = None # needs always to be defined. Used in 'globals' cmd in loop() and ck_uart()
    # See loop()
# +--------------------------------------+
# | Definition for the I2C character LCD |
# +--------------------------------------+
if board.board_id == 'unexpectedmaker_feathers2':
    i2c = board.STEMMA_I2C()
else:
    i2c = board.I2C()

# It happens when that SerLCD gets locked-up
# e.g. caused by touching with a finger the
# RX pin (4th pin fm left).
# This pin is very sensitive!
# A locked-up situation is often shown as that
# all the 8x5 segments of the LCD are 'filled with inverse pixels.
# see: https://github.com/KR0SIV/SerLCD_Reset for a reset tool.
# But this is not what I want.
# I want to be able to reset the LCD from within this script.
while True:
    try:
        lcd = Sparkfun_SerLCD_I2C(i2c)
        break
    except ValueError:
        print("The LCD is locked-up. Please connect RS with GND for a second or so.")
        sleep(10)  # wait a bit

sleep(1)


# while not i2c.try_lock():

# 0x72 found (= SparkFun serLCD ?)
"""
try:
    while True:
        print(
            "I2C addresses found:",
            [hex(device_address) for device_address in i2c.scan()],
        )
        sleep(2)

finally:  # unlock the i2c bus when ctrl-c'ing out of the loop
    i2c.unlock()
"""
# +-----------------------------------------------+
# | SparkFun LCD special command codes            |
# +-----------------------------------------------+
HIGH = 1
LOW = 0

# +-----------------------------------------------+
# | Hardware definitions for builtin BLUE LED     |
# +-----------------------------------------------+
#led_interval = 1000
led_state = HIGH  # idem. When HIGH the LED is OFF

# Make sure the 2nd LDO is turned on
feathers2.enable_LDO2(True)
# +-----------------------------------------------+
# | Hardware definitions for builtin NeoPixel LED |
# +-----------------------------------------------+
use_dotstar = False
if use_dotstar:
    # Create a DotStar instance
    dots = dotstar.DotStar(board.APA102_SCK, board.APA102_MOSI, 1, brightness=0.5, auto_write=True)

biLdIsOn = False # Flag for the built-in blue led

# Buffers
rx_buffer_len = 152  # was: 151
rx_buffer = bytearray(rx_buffer_len * b'\x00')

# +-----------------------------------------------+
# | Create an instance of the UART object class   |
# +-----------------------------------------------+
uart = busio.UART(board.TX, board.RX, baudrate=4800, timeout=0, receiver_buffer_size=rx_buffer_len)  # board.RX, board.TX)
#uart = board.UART()

if sys.version_info > (3,):
    long = int

nRMC = None
nGGA = None

_id = 0
_lat = 1
_latdir = 2
_lon = 3
_londir = 4
_gs = 5
_crs = 6
_alt = 7

class gps_msgs:
    def __init__(self):
        self.gps = ["",  "",  "",  "",  "", "", "", ""]

    def write(self, s):
        tp = isinstance(s,list)
        if tp == True:
            self.gps[_id] = s[_id] # ID
            self.gps[_lat] = s[_lat] # Lat
            self.gps[_latdir] = s[_latdir] # LadID N/S
            self.gps[_lon] = s[_lon] # Lon
            self.gps[_londir] = s[_londir] # LonID E/W
            self.gps[_gs] = s[_gs] # GS
            self.gps[_crs] = s[_crs] # CRS
            self.gps[_alt] = s[_alt] # Alt

    def read(self, n):
        tp = isinstance(n, type(None))
        if tp == True:
            n = 0
        if n >= 0 and n <= 7:
            return self.gps[n]
        else:
            return self.gps

    def clean(self):
            self.gps[0] = ""
            self.gps[1] = ""
            self.gps[2] = ""
            self.gps[3] = ""
            self.gps[4] = ""
            self.gps[5] = ""
            self.gps[6] = ""
            self.gps[7] = ""

encoding = 'utf-8'
lcd_maxrows = 4
lcd_rowlen = 20
lp_cnt = 0
max_lp_cnt = 99
startup = -1
loop_time = 0
t_elapsed = 0
msg_nr = 0

# next four defs copied from:
# I:\pico\paul_projects\pico\circuitpython\msfs2020_gps_rx_picolipo\2021-09-03_16h49_ver
ac_none = 0
ac_stopped = 1
ac_taxying = 2
ac_flying = 4

am_last_stat = ac_none
am_stat = ac_stopped # am_stat = airplane movement status
am_stat_dict = {0:"stopped", 2:"taxying", 4: "flying"}
lac_Stopped = True
lac_IsTaxying = False
lacStopMsgShown = False
lacTaxyMsgShown = False
acStopInitMonot = 0
acStopInterval = 6000 # mSec

# Classes
my_msgs = gps_msgs()

# +--------------------------------------+
# | Definitions for all LEDs             |
# +--------------------------------------+
led_colors_dict = {
    'green' : 0,
    'red' : 1,
    'blue' : 2,
    'white' : 3,
    'off' : 4 }

lcd_bl_colors = ["black", "red", "orange", "yellow", "green", "blue", "indigo", "violet", "grey", "white"]

brill = 50

colorN = [(0,  0,     0),     # black is off
  (brill,       0,     0),     # bright red
  (0xFF8C00,    0,     0),     # orange
  (brill,       brill, 0),     # bright yellow
  (0,           brill, 0),     # bright green
  (0,           0,     brill), # bright blue
  (0x4B0082,    0,     0),     # indigo
  (0xA020F0,    0,     0),     # violet
  (0x808080,    0,     0),     # grey
  (brill,       brill, brill)] # white

# Create a colour wheel index int
color_index = 0
lcd_color_index = 0
lcd_clr_chg_cnt = 0

"""
   get_os_info() -> Bool
        @brief
        Get and extract the name and version of the CircuitPython firmware installed,
        e.g. 'release='6.3.0' and 'version='6.3.0 on 2021-06-01'.
        Get also the name of the 'machine', e.g.: FeatherS2 with ESP32S2'
    Parameters: None
    Return: Bool

"""
def get_os_info():
    global my_os, my_debug, my_machine
    my_fw_itms = ("sysname", "nodename", "release", "version", "machine")
    n = os.uname()
    if n:
        my_os = n
        le = len(my_os)
        my_machine = my_os[le-1]
        print("get_os_info(): my_machine=", my_machine)
        if my_debug:
            for i in range(le):  # sysname, nodename, release, version and machine
            # e.g.: (sysname='esp32s2', nodename='esp32s2', release='6.3.0',
            # version='6.3.0 on 2021-06-01', machine='FeatherS2 with ESP32S2')
                print("{}: \'{}\'.".format(my_fw_itms[i], my_os[i]), end='\n')
        return True
    else:
        print("get_os_info(): n: {}, type(n): {}".format(n, type(n)), end='\n')
        return False

"""
   get_cpu_id() -> Bool
        @brief
        Gets the unique id of the cpu
    Parameters: None
    Return: Bool

"""
def get_cpu_id():
    global my_cpu_id, my_debug
    TAG = "get_cpu_id(): "
    lRetval = True  # assume positive result
    n1 = None
    n2 = None
    try:
        n1 = microcontroller.cpu.uid
        n2 = n1[:-2]
        if my_debug:
            print(TAG+"cpu uid: {}".format(n2), end='\n')
            print(TAG+"list(n2)=", list(n2))
    except AttributeError as e:
        # This happenen when trying this with a CircuitPython v8.0.0-alpha.1 on a Unexpected Maker FeatherS2
        print("get_cpu_id(): while trying to get \"microcontroller.cpu.uid\" occurred error:", e)
        return False
    if my_debug:
        print(TAG+"received cpu uid: {}".format(n1), end='\n')

    my_cpu_id_str = s = ""
    res = 0
    mult = 0
    le_uid2 = len(n2)
    # See: https://github.com/adafruit/circuitpython/issues/462,
    # especially the post by user 'Sommersoft' on 2018-01-13.
    if le_uid2 > 0:
        # added by @PaulskPt on 2022-07-04
        cpu_uid_lst = list(n2) # e.g.:  [199, 253, 26, 1, 163, 224]
        p = 0
        s = ""
        if my_debug:
            print(TAG+"cpu uid contains {} digits.".format(le_uid2), end='\n')
        i = le_uid2
        for c in cpu_uid_lst:
            if i == 4: mult = 10000
            elif i == 3: mult = 1000
            elif i == 2: mult = 10
            elif i == 1: mult = 1
            elif i == 0: mult = 0
            n2 = ord(chr(c))
            if my_debug:
                print(TAG+"the value of digit {} is: {:3d}.   ".format(i, n2), end='')
            res += n2 * mult
            if my_debug:
                print(TAG+"ord(0x{:02x}): {:3d}, i: {}, mult: {:5d}, result of calculation: {}".format(n2, n2, i, mult, res), end='\n')
            i -= 1
            s += chr(n2)+" "

        if my_debug:
            print("", end='\n')
            print(TAG+"final res = {} ".format(res), end='\n')
        s_res = str(res)
        if my_debug:
            print(TAG+"get_cpu_id(): unique cpu id: \'{}\'".format(s_res), end='\n')
        my_cpu_id = s_res

        if isinstance(n2, str):
            le = len(n2)
            p = 0
            s = ""
            if le > 0:
                if my_debug:
                    print(TAG+"cpu uid contains {} digits.".format(le), end='\n')
                i = le
                for c in n:
                    if i == 4: mult = 10000
                    elif i == 3: mult = 1000
                    elif i == 2: mult = 10
                    elif i == 1: mult = 1
                    elif i == 0: mult = 0
                    n2 = ord(c)
                    if my_debug:
                        print(TAG+"the value of digit {} is: {:2d}.   ".format(i, n2), end='')
                    res += n2 * mult
                    if my_debug:
                        print(TAG+"ord(0x{:02x}): {:2d}, i: {}, mult: {:5d}, result of calculation: {}".format(n2, n2, i, mult, res), end='\n')
                    i -= 1
                    s += chr(n2)+" "
                if my_debug:
                    print("", end='\n')
                    print(TAG+"final res = {} ".format(res), end='\n')
                s_res = str(res)
                if my_debug:
                    print(TAG+"get_cpu_id(): unique cpu id: \'{}\'".format(s_res), end='\n')
                my_cpu_id = s_res
            else:
                lRetval = False
        else:
            lRetVal = False
    else:
        lRetval = False
    return lRetval

"""
   my_board() -> None
        @brief
        Function prints global variables my_os and my_cpu_id
        if global my_debug is True and if either of these variables contain values
        Called by setup()
    Parameters: None
    Return: None
"""
def my_board():
    global my_os, my_cpu_id
    #if my_debug:
    #if my_os:
    print("OS: {}.".format(my_os), end='\n')
    #if my_cpu_id:
    print("CPU ID: {}.".format(my_cpu_id), end='\n')

"""
   lcd_deflt_clr() -> None
        @brief
        Sets LCD default background color
    Parameters: None
    Return: None

"""
def lcd_dflt_clr():
    global colorN
    lcd.set_backlight(colorN[2][0])  # set backlight to orange

"""
   chg_lcd_bg_clr() -> None
        @brief
        Sets LCD background to color upon value of global lcd_color_index
    Parameters: None
    Return: None

"""
def chg_lcd_bg_clr():
    global colorN, lcd_bl_colors, lcd_color_index
    lcd.clear()
    lcd.write(lcd_bl_colors[lcd_color_index])
    if colorN[lcd_color_index][0] > 255:
        lcd.set_backlight(colorN[lcd_color_index][0])
    else:
        lcd.set_backlight_rgb(colorN[lcd_color_index][0], colorN[lcd_color_index][1], colorN[lcd_color_index][2])
    lcd_color_index += 1
    if lcd_color_index >= len(colorN):
        lcd_color_index = 0

"""
    lcd_chr_test(void) -> None
        @brief
        This function sends a block of characters to the lcd
        to test what graphic representation the lcd will show.
        The low-end and high-end of the range of character values
        has to be manually put in line 355 or accept what is there as default
        THIS FUNCTION IS CALLED FROM setup() BUT NOT USED IN THIS MOMENT (2021-10-11)

        Parameters: None

        Return: None
"""
def lcd_chr_test():
    col = row = 0
    spc = chr(0x20)
    lcd.clear()
    for _ in range(0x20,0xfe):   # start with ascii <spc>
        if _ < 0x80 or _ > 0x9f:
            c1 = chr(_)
            lcd.set_cursor(col, row)
            lcd._put_char(_)
            #lcd.write(spc)
            print("hex value: {}, graphic: {} ".format(hex(_), c1), end='\n')
            col += 1
            if col >= 18:
                col = 0
                row += 1
                if row > 3:
                    row = 0
                    sleep(5)
                    lcd.clear()
    sleep(5)

"""
    lcd_clean_fm(fm_row, to_row) -> None
        @brief
        This function clears the lcd from row number indicated by parameter fm_row,
        until and including row number indicated by parameter to_row.

        Parameters: int fm_row, int to_row

        Return: None
"""
def lcd_clean_fm(fm_row, to_row = (lcd_maxrows-1)):
    global lcd_maxrows
    if fm_row >=0 and fm_row <= 3:
        if isinstance(to_row, type(None)):
            to_row = lcd_maxrows -1
        while True:
            lcd.set_cursor(0, fm_row)
            lcd.write(" "*20)
            fm_row +=1
            if fm_row > lcd_maxrows-1:
                break

"""
    setup(void) -> None
        @brief
        This function is called by main().
        It sets starting parameters for the lcd:
        - no system messages (to the lcd);
        - no cursor;
        - (if cursor) do not blink the cursor.
        It also resets the uart input buffer

        Parameters: None

        Return: None
"""
def setup():
    global lcd, uart, degreesChar

    # lcd.backlight();
    lcd.system_messages(False)
    # 150 for system with CP2101N (5Volt)
    #  50 for system with CP2221a
    lcd.set_contrast(150)  # Set to 50 for 5 Volt. Set lcd contrast to default value (was: 120). Value 50 worked fine with UM FeatherS2
    lcd_dflt_clr()  # set default lcd backlight color to orange
    lcd.cursor(0)  # do not show cursor (use 2 for show cursor)
    lcd.blink(0)   # do not blink cursor
    lcd.clear()
    lcd.set_cursor(0, 0)   # ATTENTION: the SerLCD module set_cursor(col,row)

    if use_dotstar and led_state == LOW: # Switch off the RGB LED
        led_toggle()
        #dotstar_led_off()

    #lcd_chr_test()  # print all the characters in the lcd rom

    if uart:
        uart.reset_input_buffer()  # Clear the rx buffer

    sleep(1)  # <--------------- DELAY ---------------

    get_os_info()  # Collect O.S. info. Put in global variable my_os and (partly) in my_machine

    get_cpu_id()   # Collect cpu id info. Put in global variable my_cpu_id


"""
    loop(void) -> boolean
        @brief
        This functions is the backbone of this script. It is called by main().
        It makes calls to various important functions in this script.
        It also will stop execution if the user pressed the Ctrl-C key combo (keyboard interrupt).

        Parameters: None

        Return: boolean
"""
def loop():
    global startup, am_stat, lp_cnt, biLdIsOn, lcd, msg_nr, ctrl_c_flag, diagn_dict

    TAG = "loop(): "
    lRetval = True  # assume positive
    chrs_rcvd = 0
    ac_stopped_cnt = 0
    ac_flying_cnt = 0
    lstop = False
    lSplitOK = False
    lcd_cleared = False
    lcd.clear()
    lcd.set_cursor(0, 0)
    lcd.write("MSFS 2020      ")
    lcd.set_cursor(0, 1)
    lcd.write("GPRMC/GPGGA data RX")
    lcd.set_cursor(0, 2)
    lcd.write("Platform ")
    lcd.set_cursor(0, 3)
    if my_machine:
        print(TAG+"my_machine= \"{}\"".format(my_machine))
        n1 = my_machine.find("ESP32S")
        n2 = my_machine.find("with")
        if n1 > 0 and n2 >=0:
            s = my_machine[:n2]+my_machine[n2:n2+1]+" "+my_machine[n2+5:]
        else:
            s = my_machine[:19]  # Not more than 20 characters
        lcd.write(s)
        #print(TAG+"my_machine (cut)= \"{}\"".format(s))
    else:
        lcd.write(sys.platform)
    sleep(5)
    lcd_clean_fm(2) # clean lcd rows 2 and 3
    print()
    print("MSFS2020 GPS GPRMC data reception decoder sketch by Paulsk (mailto: ct7agr@live.com.pt). ")
    print("\nNumber of loops in this run: {}".format(max_lp_cnt))
    chrs_rcvd = 0
    print("........................", end="\n")
    lcd.set_cursor(0, 3)
    lcd.write("About to receive...")
    while True:
        try:
            lp_cnt += 1
            # lcd.clear()
            print("\nStart of loop {}".format(lp_cnt), end="\n")

            if use_dotstar and led_state == LOW: # Switch off the dotstar RGB LED
                led_toggle()

            if startup == -1:
                uart.reset_input_buffer()

            wait_cnt = 0
            chrs_rcvd = ck_uart()
            print(TAG+"characters rcvd: ", chrs_rcvd)
            if chrs_rcvd > 0:
                lSplitOK = split_types()
                print(TAG+"split_types() result = {}".format(lSplitOK))
                ac_status()
                if am_stat == ac_stopped:
                    ac_stopped_cnt += 1
                    print(TAG+"ac_stopped_cnt=", ac_stopped_cnt)
                    if ac_stopped_cnt >= 5:
                        #if not lacStopMsgShown and not lacTaxyMsgShown:
                        lcd.set_cursor(0, 3)
                        lcd.write("About to receive...")
                elif am_stat == ac_flying:
                    ac_flying_cnt += 1
                    if ac_flying_cnt >= 5:
                        ac_stopped_cnt = 0 # reset when we sure are flying and no incidently gs = 0
                    if ac_flying_cnt > 1000:
                        ac_flying_cnt = 0  # reset
                if lSplitOK:
                    #ac_status()
                    if am_stat == ac_flying: # are we flying?
                        msg_nr += 1
                        print(TAG+"handling msg nr: {:02d}".format(msg_nr))
                        if use_diagnosics:
                            if msg_nr in diagn_dict:
                                diagn_dict[msg_nr][1] = 1 if lResult else 0
                            else:
                                print(TAG+"msg_nr {} not found in diagn_dict".format(msg_nr))
                        lcd_pr_msgs()
                        chrs_rcvd = 0
                        #sleep(0.1)
                        if msg_nr >= max_lp_cnt:
                            pass
                    if lstop == True:
                        if biLdIsOn:
                            #led.value = 0
                            feathers2.led_set(0)
                            biLdIsOn = False
                    else:
                        if startup == -1:
                            print("Waiting for serial com line to become available...")
                            startup = 0
                    print("End of loop {:2d}".format(lp_cnt), end="\n")
                    print("........................", end="\n")
                    if msg_nr >= max_lp_cnt:
                        msg_nr = 0
                        lp_cnt = 0
            else:
                pass
            if lstop == True:
                break
            if use_diagnosics:
                # Prepare and print to REPL a rx msgs diagnostics report
                if len(diagn_dict) >= diagnostics_iterations:
                    avg_time = 0
                    avg_split = 0
                    v = s = 0
                    le = len(diagn_dict)
                    for k, v in sorted(diagn_dict.items()):
                        if isinstance(diagn_dict[k], dict):
                            le2 = len(diagn_dict[k])
                            if le2 == 1:
                                v = diagn_dict[k][0]
                            if le2 == 2:
                                v = diagn_dict[k][0]
                                s = diagn_dict[k][1] # split result
                                avg_split += s
                        if isinstance(diagn_dict[k], float):
                            v = diagn_dict[k]
                        avg_time += v
                        print("msg nr: {:2d}, wait time for msg: {:7.4f}. Split result: {}".format(k, v, s))
                    print("Average wait time for msg: {:>5.2f}. Average split result: {:>5.2f}".format(avg_time/le, float(avg_split/le)))
                    diagn_dict = {} # cleanup the diagnostics dict
            #lcd_cleared = False
        except KeyboardInterrupt:
            ctrl_c_flag = True
            print("\'Ctrl-C\' pressed. Going to quit...")
            lcd.clear()
            lcd.set_cursor(1,2)
            lcd.write("\'Ctrl-C\' pressed.")
            lcd.set_cursor(1,2)
            lcd.write("Going to quit...")
            sleep(5)
            lRetval = False
            break

    #sleep(0.5)
    return lRetval

"""
    ck_uart(void) -> int (nr_bytes)
        @brief
        This functions reads the incoming data via the uart.
        The received data is put into rx_buffer.
        If data received this function will return the number of bytes received.
        The function will loop if the value(s) of the received data is zero.
        Parameters: None

        Return: int
"""
def ck_uart():
    global rx_buffer, msg_nr, loop_time, diagn_dict, nRMC, nGGA, my_debug
    TAG = 'ck_uart(): '
    nr_bytes = i = 0
    tot_nr_bytes = 0
    delay_ms = 0.2
    rx_buffer_s = b = ""
    n1 = n2 = n3 = n4 = 0
    if use_diagnosics:
        rx_wait_start = monotonic_ns()
    while True:
        #nr_bytes = uart.readinto(rx_buffer)
        rx_buffer = uart.read(rx_buffer_len)
        if rx_buffer is None:
            sleep(0.2)
            continue
        nr_bytes = len(rx_buffer)
        if my_debug:
            print(TAG+"nr of bytes= ", nr_bytes)
            print(TAG+"type(rx_buffer)=", type(rx_buffer))
            print(TAG+"rcvd data: {}".format(rx_buffer),end="\n")
        #for i in range(5):
        #    sleep(delay_ms)
        loop_time = monotonic_ns()
        if nr_bytes is None:
            if my_debug:
                print(TAG+"nr_bytes is None")
            sleep(delay_ms)
            continue
        if not nr_bytes:
            if my_debug:
                print(TAG+"nr_bytes=", nr_bytes)
            sleep(delay_ms)
            continue
        if nr_bytes > 1:
            tot_nr_bytes += nr_bytes
            print(TAG+"tot_nr_bytes=", tot_nr_bytes)
            rx_buffer_s += rx_buffer.decode(encoding) # if receiving a 2nd part: add it.
            print(TAG+"rx_buffer_s=", rx_buffer_s)
            # Check for '*' in tail. If present, the message is very probably complete.
            tail = rx_buffer_s[-15:]
            print(TAG+"tail=", tail)
            n0 = tail.find('*') # find '*' in tail 10 characters. If not found, loop
            if my_debug:
                print(TAG+"* found in tail of msg at: ", n0)
            if n0 < 0: # no '*' in tail
                sleep(delay_ms)
                continue
            if n1 == 0:
                n1 = rx_buffer_s.find('$GPRMC')
                if n1 < 0:
                    sleep(delay_ms)
                    continue
                else:
                    nRMC = n1
                    print(TAG+"$GPRMC msg received")
            if n2 == 0:
                n2 = rx_buffer_s.find('$GPGGA')
                if n2 < 0:
                    sleep(delay_ms)
                    continue
                else:
                    nGGA = n2
                    print(TAG+"$GPGGA msg received")
                n3 = int(tot_nr_bytes*0.75) # get 3/4 of length of characters received
                if my_debug:
                    print(TAG+"n0 = {}, n1 = {}, n2= {}, n3 ={}".format(n0, n1, n2, n3))
                if n1 > n3: # check if $GPRMC occurs at more than 3/4 of the characters received
                    sleep(delay_ms)
                    continue
                else:
                    # print(TAG+"returning with {} nr of bytes".format(nr_bytes))
                    if use_diagnosics:
                        rx_wait_stop = monotonic_ns()
                        rx_wait_duration = float((rx_wait_stop - rx_wait_start) / 1000000000) # convert nSec to mSec
                        diagn_dict[msg_nr+1] = {0: rx_wait_duration, 1: -1} # add a key/value pair for diagnostics
                        print(TAG+"it took {:6.2f} seconds for a complete msg ($GPRMC & $GPGGA) to be received".format(rx_wait_duration))
                    rx_buffer = rx_buffer_s.encode(encoding)
                    if my_debug:
                        print(TAG+"rx_bufffer returned=", rx_buffer)
                    return tot_nr_bytes
        elif nr_bytes == 1:
            if rx_buffer[0] == b'\x00':
                sleep(delay_ms)
                i += 1
                if i % 1000 == 0:
                    print("Waiting for uart line to become ready")
        else:
            empty_buffer()
            sleep(delay_ms)
            continue
    #return tot_nr_bytes

"""
   find_all(c) -> dict
   dict consists of an integer as key
   and an integer as value

"""
def find_all(c):
    #global rx_buffer
    f_dict = {}
    if c is None:
        return 0
    if type(c) is int:
        c2 = chr(c)
    elif type(c) is str:
        c2 = c
    rx_buffer_s = rx_buffer.decode()
    if my_debug:
        print("find_all(): rx_buffer=", rx_buffer)
    le = len(rx_buffer_s)
    if le > 0:
        ret = rx_buffer_s.count(c2)
        o_cnt = 0
        for i in range(le):
            if rx_buffer_s[i] == c2:
                f_dict[o_cnt] = i
                o_cnt += 1
    return f_dict

"""
    split_types(void) -> boolean
        @brief
        This functions searches the rx_buffer various times to find certain patterns
        that are tipical for the GPRMC and GPGGA GPS datagrams.
        If found, the data will be saved in the my_msgs class
        Parameters: None

        Return: boolean

"""
def split_types():
    global rx_buffer, my_msgs, nRMC, nGGA
    TAG = "split_types(): "
    lResult = True
    sRMC = sGGA = None
    rmc_s = gga_s = ""
    nr_RMC_items = nr_GGA_items = 0
    le_b4 = le_aft = 0
    nRMC_end = nGGA_end = 0
    lGPRMC_go = lGPGGA_go = False
    msg_lst = []
    rmc_lst = []
    gga_lst = []
    rmc_msg_lst = []
    gga_msg_lst = []
    le_dict = 0

    if my_debug:
        print(TAG+"entry...contents rx_buffer=", rx_buffer)
    t_rx_buffer = rx_buffer.decode()
    le_t_rx = len(t_rx_buffer)

    f_dict = find_all(10)
    if f_dict:
        le_dict = len(f_dict)
        if my_debug:
            print(TAG+"f_dict= {}, length dict = {}".format(f_dict, le_dict))

    if le_dict < 2:
        print(TAG+"exiting... f_dict length < 2")
        return False

    if nRMC is None: # in ck_uart() already has been done a find for $GPRMC and if found set nRMC
        nRMC = t_rx_buffer.find('$GPRMC')
    if nGGA is None: # idem for $GPGGA and nGGA
        nGGA = t_rx_buffer.find('$GPGGA')

    if le_dict >= 1 and (nRMC < 0 or nRMC > f_dict[le_dict-1]):
        print(TAG+"exiting.. nRMC = {}, f_dict[le_dict-1] = {}".format(nRMC, f_dict[le_dict-1]))
        return False  # $GPRMC not in first or not in first two msgs

    if nRMC >= 0:
        rmc_s = t_rx_buffer[nRMC:nRMC+6]
    if nGGA >= 0:
        gga_s = t_rx_buffer[nGGA:nGGA+6]

    if my_debug:
        print(TAG+"nRMC=", nRMC)
        print(TAG+"nGGA=", nGGA)

    if nRMC >= 0 and nGGA >= 0:
        if nRMC < nGGA:
            if nRMC >= 0:
                if le_dict == 1 or le_dict == 2:
                    sRMC_end = f_dict[0]+1
                    sRMC = t_rx_buffer[nRMC:f_dict[0]+1] # copy $GPRMC...\r\n'
                    if my_debug:
                        print(TAG+"sRMC = t_rx_buffer[{}:{}]".format(nRMC, sRMC_end))
                if le_dict == 3:
                    sRMC = t_rx_buffer[nRMC:f_dict[1]+1] # idem
            if nGGA > 0:
                if le_dict == 2:
                    if nGGA > f_dict[1]:
                        nGGA_end = le_t_rx
                    else:
                        nGGA_end = f_dict[1]+1
                    sGGA = t_rx_buffer[nGGA:nGGA_end] # copy $GPGGA...\r\n'
                    if my_debug:
                        print(TAG+"sGGA = t_rx_buffer[{}:{}]".format(nGGA, nGGA_end))
                if le_dict == 3:
                    sGGA = t_rx_buffer[nGGA:f_dict[2]+1] # idem
        elif nGGA < nRMC:
            if nGGA >= 0:
                if le_dict == 1 or le_dict == 2:
                    nGGA_end = f_dict[0]+1
                    sGGA = t_rx_buffer[nGGA:nGGA_end] # copy $GPGGA...\r\n'
                    if my_debug:
                        print(TAG+"sGGA = t_rx_buffer[{}:{}]".format(nGGA, nGGA_end))
                if le_dict == 3:
                    sGGA = t_rx_buffer[nGGA:f_dict[1]+1] # idem
            if nRMC > 0:
                if le_dict == 2:
                    if nRMC > f_dict[1]:
                        nRMC_end = le_t_rx
                    else:
                        nRMC_end = f_dict[1]+1
                    sRMC = t_rx_buffer[nRMC:nRMC_end] # copy $GPRMC...\r\n'
                    if my_debug:
                        print(TAG+"sRMC = t_rx_buffer[{}:{}]".format(nRMC, nRMC_end))
                if le_dict == 3:
                    sRMC = t_rx_buffer[nRMC:f_dict[2]+1] # idem

    if my_debug:
        print(TAG+"nRMC= ", nRMC)
        print(TAG+"rmc_s=", rmc_s)
        print(TAG+"sRMC=", sRMC)

        print(TAG+"nGGA= ", nGGA)
        print(TAG+"gga_s=", gga_s)
        print(TAG+"sGGA=", sGGA)

    lIsStr = isinstance(sRMC,str)
    if lIsStr:
        rmc_msg_lst = sRMC.split(",")
        nr_RMC_items = len(rmc_msg_lst)
        if nr_RMC_items == 12:
            lGPRMC_go = True

    lIsStr = isinstance(sGGA,str)
    if lIsStr:
        nGGA_ID = sGGA.find("$")
        if nGGA_ID > 0:
            pass
        else:
            gga_msg_lst = sGGA.split(",")
            nr_GGA_items = len(gga_msg_lst)
            if nr_GGA_items == 15:
                t_alt = float(gga_msg_lst[9])
                p = isinstance(t_alt,float)
                if p == True:
                    #                                  alt
                    t_alt = round(int(float(gga_msg_lst[9])) * 3.2808)
                else:
                    t_alt = 0
                lGPGGA_go = True

        if lGPRMC_go == True:
            #                      id             lat             latdir          lon           londir            gs        track true
            rmc_lst = [rmc_msg_lst[0], rmc_msg_lst[3], rmc_msg_lst[4], rmc_msg_lst[5], rmc_msg_lst[6], rmc_msg_lst[7], rmc_msg_lst[8]]
            if lGPGGA_go == True:
                rmc_lst.append(str(t_alt))
            else:
                rmc_lst.append("0")
            my_msgs.write(rmc_lst)
            if not my_debug:
                print(TAG+"rmc_lst + t_alt=", rmc_lst)
        if my_debug:
            print(TAG+"cross-check: my_msgs class data contents: {}".format(my_msgs.read(9)), end="\n")

    empty_buffer() # not emptying the buffer here causes an error in lcd_pr_msgs() !!!
    if lGPRMC_go == False and lGPGGA_go == False:
        lResult = False

    return lResult

"""
    led_BI_toggle(void) -> void
        @brief
        This functions toggles the builtin blue LED
        THIS FUNCTION IS USED FOR THE MOMENT (2021-10-11)

        Parameters: None

        Return: None
"""
def led_BI_toggle():
    global led, biLdIsOn

    if biLdIsOn:
        #led.value = 0
        feathers2.led_set(0)
        biLdIsOn = False
    else:
        #led.value = 1
        feathers2.led_set(1)
        biLdIsOn = True

"""
    led_toggle(void) -> void
        @brief
        This functions toggles the builtin neopixel LED and the external 3-color LED
        THIS FUNCTION IS NOT BEING USED FOR THE MOMENT (2021-10-11)

        Parameters: None

        Return: None
"""
def led_toggle():
    global led_state, HIGH, LOW, color_c_arr, color_index
    # uses global variable led_state
    led_chrs_rcvd = 0 # Before this was a global defined variable.
    brightness = 0.1
    if led_state == HIGH:
        led_state = LOW  # a=!a
    elif led_state == LOW:
        led_state = HIGH  # a=!a

    if led_state == LOW:
        # Get the R,G,B values of the next colour
        color_index = 0 # black ?
        r,g,b = feathers2.dotstar_color_wheel( color_index )
        # Set the colour on the dotstar
        dots[0] = ( r, g, b, brightness)  # was 0.5
        #pixels[0] = color_c_arr[led_colors_dict['off']]  # Set the color of the builtin LED to black
        #pixels.show()
        #blink_led3(led_colors_dict['off'])  # Switch the external 3-color LED off
    else:
        # Get the R,G,B values of the next colour
        r,g,b = feathers2.dotstar_color_wheel( color_index )
        # Set the colour on the dotstar
        dots[0] = ( r, g, b, brightness)  # was 0.5
        # Increase the wheel index
        color_index += 2
        # If the index == 255, loop it
        if color_index == 255:
            color_index = 0
        # Invert the internal LED state every half colour cycle
        feathers2.led_blink()
        # Sleep for 15ms so the colour cycle isn't too fast
        sleep(0.015)
        #pixels[0] = color_c_arr[led_colors_dict['green']]  # Set the color of the builtin LED to GREEN
        #pixels.show()
        #blink_led3(led_colors_dict['green']) # Switch the external 3-color LED GREEN


""" dotstar_led_off(void) -> void
    Switches the built-in dotstar led off
"""
def dotstar_led_off():
    global led_state, color_index
    brightness = 0.1
    color_index = 0 # black ?
    r,g,b = feathers2.dotstar_color_wheel( color_index )
    # Set the colour on the dotstar
    dotstar[0] = ( r, g, b, brightness)  # was 0.5
    led_state = HIGH

def ck_gs():
    t_gs = my_msgs.read(_gs)
    if t_gs is not None:
        if my_debug:
            print("groundspeed={}".format(t_gs))
        return float(t_gs)
    return 0.0

"""
    ac_status(void) -> boolean
        @brief
        This function chcks if the aircraft is moving or not. When not moving it will write
        a message to REPL and to the LCD

        Parameters: None

        Return: boolean
"""
# Function copied from: I:\pico\paul_projects\pico\circuitpython\msfs2020_gps_rx_picolipo\2021-09-03_16h49_ver
def ac_status():
    global lacStopMsgShown, lacTaxyMsgShown, acStopInitMonot, acStopInterval, am_stat, am_stat_dict, am_last_stat
    TAG = "ac_status(): "
    s = "Airplane is stopped or parked"
    t = "Airplane is taxying"
    f = "Airplane is flying"
    #gs = 5
    t_elapsed = 0
    lelapsed = False
    t_gs = my_msgs.read(_gs)
    le = len(t_gs)
    if my_debug:
        print(TAG,"value of gs = {}, len(gs) = {}".format(t_gs, le), end='\n')
    if le == 0: # check for t_gs == "". This happened sometimes!
        v_gs = 0
    else:
        v_gs = round(int(float(t_gs)))
    if v_gs <= 0.2:
        am_stat = ac_stopped
        lacTaxyMsgShown = False
    elif v_gs < 30:
        am_stat = ac_taxying
        lacStopMsgShown = False
    else:
        am_stat = ac_flying
        #lacStopMsgShown = False
        #lacTaxyMsgShown = False
        acStopInitMonot = 0
    am_last_stat = am_stat
    if my_debug:
        print(TAG,"value of v_gs = {}".format(v_gs), end='\n')
        print(TAG,"am_stat =", am_stat_dict[am_stat], end='\n')

    if am_stat == ac_stopped:
        currMonot = monotonic_ns()
        if acStopInitMonot == 0:
            acStopInitMonot = currMonot

        t_elapsed = (((currMonot - acStopInitMonot) + 500000)// 1000000)
        if my_debug:
            print(TAG,"t_elapsed:{}. acStopInterval: {}".format(t_elapsed, acStopInterval), end='\n')

        if t_elapsed >= acStopInterval:
            lelapsed = True

        if my_debug:
            print(TAG,"lelapsed:{}. lacStopMsgShown: {}".format(lelapsed, lacStopMsgShown), end='\n')
        if lelapsed:
            if lacStopMsgShown == False:
                lcd.clear()  # It takes about ten seconds before this message is shown after aircraft is stopped
                lcd.set_cursor(0,1)
                lcd.write(s)
                lacStopMsgShown = True
            print(s, end = '\n') # Alway print to REPL (it does almost immediately)
    if am_stat == ac_taxying:
        if not lacTaxyMsgShown:
            lcd.clear()  # It takes about ten seconds before this message is shown after aircraft is stopped
            lcd.set_cursor(0,1)
            lcd.write(t)
            lacTaxyMsgShown = True

def empty_buffer():
    global rx_buffer, rx_buffer_len
    rx_buffer = bytearray(rx_buffer_len * b'\x00')


def lcd_pr_msgs():
    global startup, loop_time, t_elapsed, msg_nr, my_msgs, lcd_maxrows, lacStopMsgShown, lacTaxyMsgShown, lac_Stopped
    TAG = "lcd_pr_msgs(): "
    dp = 0
    msg_itm = 0
    lcd_vpos = 0
    s = s0 = ""

    lat   =  1
    latID =  2
    lon   =  3
    lonID =  4
    gs    =  5
    crs   =  6
    alt   =  7

    degs = chr(0xdf)
    if startup == -1 or lacStopMsgShown or lacTaxyMsgShown:
        lacStopMsgShown = False
        lacTaxyMsgShown = False
        lcd.clear()
    lcd.set_cursor(18, 0)
    lcd.write("{:0>2d}".format(msg_nr))
    lcd_vpos = 0
    itms_lst = [lat, lon, gs, crs]
    led_BI_toggle()
    for msg_itm in itms_lst:
        if msg_itm == lat:
            lat_v = my_msgs.read(lat)
            dp = lat_v.find(".")
            if dp >= 0:
                if dp == 4:
                    s0 = "{: >2s}{}{:0>2s}\'{:0>2s}.{:0>2s}\"".format(lat_v[:2], degs, lat_v[2:4], lat_v[5:7],lat_v[7:])
                elif dp == 3:
                    s0 = "{: >2s}{}{:0>2s}\'{:0>2s}.{:0>2s}\" ".format(lat_v[:1], degs, lat_v[1:3], lat_v[4:6],lat_v[6:])
            s = my_msgs.read(latID) + "    " + s0
        if msg_itm == lon:
            lon_v = my_msgs.read(lon)
            dp = lon_v.find(".")
            if dp >= 0:
                if dp == 5:
                    s0 = "{: >2s}{}{:0>2s}\'{:0>2s}.{:0>2s}\"".format(lon_v[:3], degs, lon_v[3:5], lon_v[6:8], lon_v[8:])
                elif dp == 4:
                    s0 = "{: >2s}{}{:0>2s}\'{:0>2s}.{:0>2s}\" ".format(lon_v[:2], degs, lon_v[2:4], lon_v[5:7], lon_v[7:])
            s = my_msgs.read(lonID) + "   " + s0
        if msg_itm == gs:
            #gs0 = my_msgs.read(gs)
            s = "GS  {: >3d} ALT {: >5d} FT".format(round(int(float(my_msgs.read(gs)))),
                round(int(float(my_msgs.read(alt)))))
        if msg_itm == crs:
            #crs0 = my_msgs.read(crs)
            s = "CRS {:0>3d} DEGS     ".format(round(int(float(my_msgs.read(crs)))))
        lcd.set_cursor(0, lcd_vpos)

        le = len(s)
        for _ in range(le):
            lcd._put_char(ord(s[_]))
        #lcd.write(s)
        lcd_vpos += 1
    t_elapsed = (((monotonic_ns() - loop_time) + 500000)// 1000000)
    print(TAG+"Duration rx -> lcd: {} mSecs".format(t_elapsed), end="\n")

    my_msgs.clean()

    lcd.set_cursor(19, 3)

    lcd_vpos += 1
    if lcd_vpos >= lcd_maxrows:
        lcd_vpos = 0

    led_BI_toggle()

def main():
    global my_debug, ctrl_c_flag
    lResult = True
    cnt = 0

    setup()
    my_board()

    while True:
        lcd.clear()
        sleep(2)
        lcd.set_cursor(0, 0)
        lcd.write("FSUIPC7 GPS RX ")
        lcd.set_cursor(0, 1)
        lcd.write("for MSFS2020   ")
        sleep(2)
        lcd.set_cursor(0, 1)
        lcd.write("via serial     ")
        sleep(2)
        lcd.clear()

        if cnt == 0:
            lResult = loop()
            cnt += 1
            if lResult == False:
                if ctrl_c_flag:  # Ctrl-c has been pressed
                    break
                if my_debug == True:
                    print("loop(): setup returned with: \"{}\" in line nr: {}".format(lResult))
            break

    cnt = 0
    while True:
        cnt += 1
        if cnt >= 100:
            cnt = 0
            led_BI_toggle()

if __name__ == '__main__':
    main()
