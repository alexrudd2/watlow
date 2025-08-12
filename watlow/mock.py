"""Mock Watlow interface. Use for debugging systems."""

import struct
from unittest.mock import MagicMock

from watlow.driver import Gateway as realGateway

try:
    from pymodbus.pdu.register_message import (  # type: ignore
        ReadHoldingRegistersResponse,
        WriteMultipleRegistersResponse,
    )
    pymodbus38plus = True
except ImportError:
    pymodbus38plus = False
    try:  # pymodbus 3.7.x
        from pymodbus.pdu.register_read_message import ReadHoldingRegistersResponse  # type: ignore
        from pymodbus.pdu.register_write_message import (  # type: ignore
            WriteMultipleRegistersResponse,
        )
    except ImportError:
        from pymodbus.register_read_message import ReadHoldingRegistersResponse  # type: ignore
        from pymodbus.register_write_message import WriteMultipleRegistersResponse  # type: ignore

class AsyncClientMock(MagicMock):
    """Magic mock that works with async methods."""

    async def __call__(self, *args, **kwargs):
        """Convert regular mocks into into an async coroutine."""
        return super().__call__(*args, **kwargs)

    def close(self):
        """Close the connection."""
        ...


class Gateway(realGateway):
    """Mock interface to the Watlow Gateway used to communicate with ovens."""

    def __init__(self, *args, max_temp=220, **kwargs):
        self.setpoint_range = (10, max_temp)
        self.client = AsyncClientMock()
        self._detect_pymodbus_version()
        self.actual_temp_address = 360
        self.setpoint_address = 2160
        self.output_address = 1904
        self.modbus_offset = 5000
        self._registers: dict[int, int] = {}

        # Initialize _registers with default 25.0 for actual/setpoint, 0.0 output
        for zone in range(1, 9):
            zone_offset = self.modbus_offset * (zone - 1)
            for addr, val in [
                (self.actual_temp_address + zone_offset, 25.0),
                (self.setpoint_address + zone_offset, 25.0),
                (self.output_address + zone_offset, 0.0),
            ]:
                hi, lo = struct.unpack('>HH', struct.pack('>f', val))
                self._registers[addr] = hi
                self._registers[addr + 1] = lo

    def _read_float(self, addr: int) -> float:
        hi = self._registers.get(addr, 0)
        lo = self._registers.get(addr + 1, 0)
        packed = struct.pack('>HH', hi, lo)
        return struct.unpack('>f', packed)[0]

    def _write_float(self, addr: int, val: float):
        hi, lo = struct.unpack('>HH', struct.pack('>f', val))
        self._registers[addr] = hi
        self._registers[addr + 1] = lo

    def _perturb(self):
        for zone in range(1, 9):
            zone_offset = self.modbus_offset * (zone - 1)
            actual_addr = self.actual_temp_address + zone_offset
            setpoint_addr = self.setpoint_address + zone_offset
            output_addr = self.output_address + zone_offset

            actual = self._read_float(actual_addr)
            setpoint = self._read_float(setpoint_addr)
            output = self._read_float(output_addr)

            if actual < setpoint:
                actual += 1
                output = min(setpoint - actual, 100)
            elif actual > setpoint:
                actual -= 1
                output = 0

            self._write_float(actual_addr, actual)
            self._write_float(setpoint_addr, setpoint)
            self._write_float(output_addr, output)

    async def _request(self, method, address, count, **kwargs):
        if method == 'read_holding_registers':
            regs = [self._registers.get(address + i, 0) for i in range(count)]
            if pymodbus38plus:
                return ReadHoldingRegistersResponse(registers=regs)
            return ReadHoldingRegistersResponse(regs)  # type: ignore

        if method == 'write_registers':
            for i, val in enumerate(count):
                self._registers[address + i] = val
            self._perturb()
            return WriteMultipleRegistersResponse(address, count)

        raise NotImplementedError(f'Unrecognised method: {method}')
