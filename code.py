from umodbus import modbus, bridge
import usb_cdc
import board
import digitalio
import time
import microcontroller


class SerObj:
    def __init__(self, serial, ctrl_pin=None):
        self.uart = serial
        self.ctrl_pin = ctrl_pin
        self.baudrate = getattr(serial, "baudrate", 115200)
        self.bytesize = getattr(serial, "bytesize", 8)
        self.stopbits = getattr(serial, "stopbits", 1)


periph_addr = 11

usb = SerObj(usb_cdc.data)
repl = usb_cdc.console
mod = modbus.ModbusRTU(periph_addr, serial=usb)

bri = bridge.Bridge(mod, repl=repl)


class Neo:
    def __init__(self):
        import neopixel_write

        self._nw = neopixel_write.neopixel_write
        self.neo = digitalio.DigitalInOut(board.NEOPIXEL)
        self.neo.switch_to_output()
        pwr = digitalio.DigitalInOut(board.NEOPIXEL_POWER)
        pwr.switch_to_output()
        pwr.value = True
        self._value = False

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, val):
        self._value = val
        color = b"\xFF\x00\x00" if val else b"\x00\x00\x00"
        self._nw(self.neo, color)


try:
    led = digitalio.DigitalInOut(board.LED)
    led.switch_to_output()
except AttributeError:
    led = Neo()


class Test:
    def __init__(self):
        self.value = 100.0


test = Test()

coils = [(led, "value", "LED")]
iregs = [
    (microcontroller.cpu, "temperature", "f", "TEMP"),
    (time, "time", "Q", "TIME"),
]
hregs = [(test, "value", "f", "TEST")]

bri.add_coils(coils)
bri.add_iregs(iregs)
bri.add_hregs(hregs)


while True:
    bri.update()
    time.sleep(0.01)
