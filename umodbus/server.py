import struct
import time
from . import const as Const


class Server:

    FORMAT_INTS = ["c", "b", "B", "h", "H", "i", "I", "l", "L", "q", "Q"]
    FORMAT_FLOATS = ["f", "d"]
    FORMAT_LIST = FORMAT_INTS + FORMAT_FLOATS

    MOD_FUNCS = {
        "COILS": "_coil",
        "ISTS": "_ist",
        "IREGS": "_ireg",
        "HREGS": "_hreg",
    }

    def __init__(self,  serial):
        self.serial = serial
        self.clients = []
    
    def add_client(self, address):
        pass

    def update(self):
        self.update_inputs()
        self.modbus.process()
        if self.repl:
            self.repl_comm()
            while self._message_queue:
                self.handle_message(self._message_queue.pop(0))
        self.update_outputs()

    def repl_comm(self):
        if not self.repl.in_waiting:
            return
        input = self.repl.read(self.repl.in_waiting)
        self.repl.write(input)
        if b"\r" in input:
            self.repl.write(b"\n")
        self._repl_buff += input.decode()
        if "\r" in self._repl_buff:
            buff_split = self._repl_buff.split("\r")
            self._message_queue.extend(buff_split[:-1])
            self._repl_buff = buff_split[-1:][0]

    def handle_message(self, message):
        mess_list = message.strip().split(",")
        try:
            crc = mess_list[2]
        except IndexError:
            crc = None
        try:
            value = mess_list[1]
        except IndexError:
            value = None
        cmd = mess_list[0].upper()
        if cmd not in self.cmd_dict:
            return
        type, reg, format = self.cmd_dict[cmd]

        if value is None:
            mod_func = f"get{self.MOD_FUNCS[type]}"
            retval = getattr(self.modbus, mod_func)(reg)
            if format in self.FORMAT_LIST:
                retval = struct.pack("b" * struct.calcsize(format), *retval)
                retval = struct.unpack(format, retval)[0]
            retval = str(retval).encode("utf-8")
            retcrc = str(int.from_bytes(self._calculate_crc16(retval), "big")).encode(
                "utf-8"
            )
            retmess = retval + b"," + retcrc + b"\r\n"
            self.repl.write(retmess)
            return
        if type in ["ISTS", "IREGS"]:
            return
        if type == "COILS":
            value = bool(int(value))
        mod_func = f"set{self.MOD_FUNCS[type]}"
        value = self._stored_val(format, value)
        getattr(self.modbus, mod_func)(reg, value)
        self.modbus._set_changed_register(type, reg, value)
        return

    def _calculate_crc16(self, data):
        crc = 0xFFFF

        for char in data:
            crc = (crc >> 8) ^ Const.CRC16_TABLE[((crc) ^ char) & 0xFF]

        return struct.pack("<H", crc)

    def update_inputs(self):
        new_time = time.monotonic()
        if new_time - self._start > self.delay:
            self._start = new_time
            for reg, val in self.iregs.items():
                obj, attr, format = val[0]
                new_val = getattr(obj, attr)
                try:
                    new_val = getattr(obj, attr)()
                except TypeError:
                    pass
                if new_val != val[1]:
                    val[1] = new_val
                    self.modbus.set_ireg(reg, self._stored_val(format, new_val))

    def update_outputs(self):
        updated_regs = []
        for reg, val in self.modbus.changed_coils.items():
            if reg in self.coils:
                obj, attr, format = self.coils[reg]
                setattr(obj, attr, val["val"])
                updated_regs.append(reg)
        [self.modbus._changed_registers["COILS"].pop(reg) for reg in updated_regs]

    def add_reg(self, type, *args, reg=None):
        try:
            object, attr, format, command = args
        except ValueError:
            object, attr, command = args
            format = None

        reg_dict = getattr(self, type.lower())
        if reg is None:
            reg = getattr(self, f"{type}_REG")
            while reg in reg_dict:
                reg += 1
        else:
            if reg in reg_dict:
                print(f"{type} register {reg} collision.")
                return False

        self.cmd_dict[command] = (type, reg, format)
        val = getattr(object, attr)
        try:
            val = val()
        except TypeError:
            pass
        if type in ["ISTS", "IREGS"]:
            reg_dict[reg] = [(object, attr, format), val]
        else:
            reg_dict[reg] = (object, attr, format)
        add_func = getattr(self.modbus, f"add_{type[:-1].lower()}")
        add_func(reg, self._stored_val(format, val))
        return reg

    def add_ists(self, ist_list):
        return [self.add_reg("ISTS", *ist) for ist in ist_list]

    def add_coils(self, coil_list):
        return [self.add_reg("COILS", *coil) for coil in coil_list]

    def add_iregs(self, input_list):
        return [self.add_reg("IREGS", *input) for input in input_list]

    def add_hregs(self, hreg_list):
        return [self.add_reg("HREGS", *hreg) for hreg in hreg_list]

    def _stored_val(self, format, val):
        if format in self.FORMAT_FLOATS:
            val = float(val)
        if format in self.FORMAT_INTS:
            val = int(val)
        if format in self.FORMAT_LIST:
            stored_format = "b" * struct.calcsize(format)
            p_val = struct.pack(format, val)
            return list(struct.unpack(stored_format, p_val))
        else:
            return val

