#!/usr/bin/env python
#
# Copyright (c) 2019, Pycom Limited.
#
# This software is licensed under the GNU GPL version 3 or any
# later version, with permitted additional terms. For more information
# see the Pycom Licence v1.0 document supplied with this file, or
# available at https://www.pycom.io/opensource/licensing
#

# system packages
try:
    from adafruit_ticks import ticks_ms, ticks_diff
except ModuleNotFoundError:
    from pcticks import ticks_ms, ticks_diff
import struct
import time

# custom packages
from . import const as Const
from . import functions
from .common import Request
from .common import ModbusException


class Serial(object):

    def __init__(self, serial):
        
        self._uart = serial.uart
        self._ctrlPin = serial.ctrl_pin

        baudrate = serial.baudrate
        databits = serial.bytesize
        stopbits = serial.stopbits
    

        if baudrate <= 19200:
            self._t35chars = (3500 * (databits + stopbits + 2)) // baudrate
        else:
            self._t35chars = 1.75


    def _calculate_crc16(self, data):
        crc = 0xFFFF

        for char in data:
            crc = (crc >> 8) ^ Const.CRC16_TABLE[((crc) ^ char) & 0xFF]

        return struct.pack("<H", crc)

    def _bytes_to_bool(self, byte_list):
        bool_list = []

        for index, byte in enumerate(byte_list):
            bool_list.extend([bool(byte & (1 << n)) for n in range(8)])

        return bool_list

    def _to_short(self, byte_array, signed=True):
        response_quantity = int(len(byte_array) / 2)

        fmt = ">" + (("h" if signed else "H") * response_quantity)

        return struct.unpack(fmt, byte_array)

    def _exit_read(self, response):
        if response[1] >= Const.ERROR_BIAS:
            if len(response) < Const.ERROR_RESP_LEN:
                return False
        elif Const.READ_COILS <= response[1] <= Const.READ_INPUT_REGISTER:
            expected_len = (
                Const.RESPONSE_HDR_LENGTH + 1 + response[2] + Const.CRC_LENGTH
            )
            if len(response) < expected_len:
                return False
        elif len(response) < Const.FIXED_RESP_LEN:
            return False

        return True

    def _uart_read(self):
        response = bytearray()

        for x in range(1, 40):
            if self._uart.in_waiting:
                response.extend(self._uart.read(self._uart.in_waiting))

                # variable length function codes may require multiple reads
                if self._exit_read(response):
                    break
            time.sleep(0.05)

        return response

    def _uart_read_frame(self, timeout=None):
        received_bytes = bytearray()

        # set timeout to at least twice the time between two frames in case the
        # timeout was set to zero or None
        if timeout == 0 or timeout is None:
            timeout = 2 * self._t35chars  # in milliseconds

        start_ms = ticks_ms()

        # stay inside this while loop at least for the timeout time
        while ticks_diff(ticks_ms(), start_ms) <= timeout:
            # check amount of available characters
            if self._uart.in_waiting:
                # remember this time in milliseconds
                last_byte_ts = ticks_ms()

                # do not stop reading and appending the result to the buffer
                # until the time between two frames elapsed
                while ticks_diff(ticks_ms(), last_byte_ts) <= self._t35chars:
                    r = self._uart.read(self._uart.in_waiting)
                    # if something has been read after the first iteration of
                    # this inner while loop (during self._t35chars time)
                    if r not in [None, b""]:
                        # append the new read stuff to the buffer
                        received_bytes.extend(r)

                        # update the timestamp of the last byte being read
                        last_byte_ts = ticks_ms()

            # if something has been read before the overall timeout is reached
            if len(received_bytes) > 0:
                return received_bytes

        # return the result in case the overall timeout has been reached
        return received_bytes

    def _send(self, modbus_pdu, slave_addr):
        serial_pdu = bytearray()
        serial_pdu.append(slave_addr)
        serial_pdu.extend(modbus_pdu)

        crc = self._calculate_crc16(serial_pdu)
        serial_pdu.extend(crc)

        if self._ctrlPin:
            self._ctrlPin.value = 1

        self._uart.write(serial_pdu)

        if self._ctrlPin:
            time.sleep(self._t35chars / 1e6)
            self._ctrlPin.value = 0

    def _send_receive(self, modbus_pdu, slave_addr, count):
        # flush the Rx FIFO
        if self._uart.in_waiting:
            self._uart.read(self._uart.in_waiting)

        self._send(modbus_pdu, slave_addr)

        return self._validate_resp_hdr(
            self._uart_read(), slave_addr, modbus_pdu[0], count
        )

    def _validate_resp_hdr(self, response, slave_addr, function_code, count):
        if len(response) == 0:
            raise OSError("no data received from slave")

        resp_crc = response[-Const.CRC_LENGTH :]
        expected_crc = self._calculate_crc16(
            response[0 : len(response) - Const.CRC_LENGTH]
        )

        if (resp_crc[0] is not expected_crc[0]) or (resp_crc[1] is not expected_crc[1]):
            raise OSError("invalid response CRC")

        if response[0] != slave_addr:
            raise ValueError("wrong slave address")

        if response[1] == (function_code + Const.ERROR_BIAS):
            raise ValueError("slave returned exception code: {:d}".format(response[2]))

        hdr_length = (
            (Const.RESPONSE_HDR_LENGTH + 1) if count else Const.RESPONSE_HDR_LENGTH
        )

        return response[hdr_length : len(response) - Const.CRC_LENGTH]

    def read_coils(self, slave_addr, starting_addr, coil_qty):
        modbus_pdu = functions.read_coils(starting_addr, coil_qty)

        resp_data = self._send_receive(modbus_pdu, slave_addr, True)
        status_pdu = self._bytes_to_bool(resp_data)

        return status_pdu

    def read_discrete_inputs(self, slave_addr, starting_addr, input_qty):
        modbus_pdu = functions.read_discrete_inputs(starting_addr, input_qty)

        resp_data = self._send_receive(modbus_pdu, slave_addr, True)
        status_pdu = self._bytes_to_bool(resp_data)

        return status_pdu

    def read_holding_registers(
        self, slave_addr, starting_addr, register_qty, signed=True
    ):
        modbus_pdu = functions.read_holding_registers(starting_addr, register_qty)

        resp_data = self._send_receive(modbus_pdu, slave_addr, True)
        register_value = self._to_short(resp_data, signed)

        return register_value

    def read_input_registers(
        self, slave_addr, starting_addr, register_qty, signed=True
    ):
        modbus_pdu = functions.read_input_registers(starting_addr, register_qty)

        resp_data = self._send_receive(modbus_pdu, slave_addr, True)
        register_value = self._to_short(resp_data, signed)

        return register_value

    def write_single_coil(self, slave_addr, output_address, output_value):
        modbus_pdu = functions.write_single_coil(output_address, output_value)

        resp_data = self._send_receive(modbus_pdu, slave_addr, False)
        operation_status = functions.validate_resp_data(
            resp_data,
            Const.WRITE_SINGLE_COIL,
            output_address,
            value=output_value,
            signed=False,
        )

        return operation_status

    def write_single_register(
        self, slave_addr, register_address, register_value, signed=True
    ):
        modbus_pdu = functions.write_single_register(
            register_address, register_value, signed
        )

        resp_data = self._send_receive(modbus_pdu, slave_addr, False)
        operation_status = functions.validate_resp_data(
            resp_data,
            Const.WRITE_SINGLE_REGISTER,
            register_address,
            value=register_value,
            signed=signed,
        )

        return operation_status

    def write_multiple_coils(self, slave_addr, starting_address, output_values):
        modbus_pdu = functions.write_multiple_coils(starting_address, output_values)

        resp_data = self._send_receive(modbus_pdu, slave_addr, False)
        operation_status = functions.validate_resp_data(
            resp_data,
            Const.WRITE_MULTIPLE_COILS,
            starting_address,
            quantity=len(output_values),
        )

        return operation_status

    def write_multiple_registers(
        self, slave_addr, starting_address, register_values, signed=True
    ):
        modbus_pdu = functions.write_multiple_registers(
            starting_address, register_values, signed
        )

        resp_data = self._send_receive(modbus_pdu, slave_addr, False)
        operation_status = functions.validate_resp_data(
            resp_data,
            Const.WRITE_MULTIPLE_REGISTERS,
            starting_address,
            quantity=len(register_values),
        )

        return operation_status

    def send_response(
        self,
        slave_addr,
        function_code,
        request_register_addr,
        request_register_qty,
        request_data,
        values=None,
        signed=True,
    ):
        modbus_pdu = functions.response(
            function_code,
            request_register_addr,
            request_register_qty,
            request_data,
            values,
            signed,
        )
        self._send(modbus_pdu, slave_addr)

    def send_exception_response(self, slave_addr, function_code, exception_code):
        modbus_pdu = functions.exception_response(function_code, exception_code)
        self._send(modbus_pdu, slave_addr)

    def get_request(self, unit_addr_list, timeout=None):
        req = self._uart_read_frame(timeout)

        if len(req) < 8:
            return None

        if req[0] not in unit_addr_list:
            return None

        req_crc = req[-Const.CRC_LENGTH :]
        req_no_crc = req[: -Const.CRC_LENGTH]
        expected_crc = self._calculate_crc16(req_no_crc)

        if (req_crc[0] != expected_crc[0]) or (req_crc[1] != expected_crc[1]):
            return None

        try:
            request = Request(self, req_no_crc)
        except ModbusException as e:
            self.send_exception_response(req[0], e.function_code, e.exception_code)
            return None

        return request
