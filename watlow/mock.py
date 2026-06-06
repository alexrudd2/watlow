"""Mock Watlow interface. Use for debugging systems."""

import struct
from unittest.mock import MagicMock

from watlow.driver import Gateway as realGateway

try:
    from pymodbus.pdu.register_message import ReadHoldingRegistersResponse  # type: ignore
    pymodbus38plus = True
except ImportError:
    pymodbus38plus = False
    try:  # pymodbus 3.7.x
        from pymodbus.pdu.register_read_message import ReadHoldingRegistersResponse  # type: ignore
    except ImportError:
        from pymodbus.register_read_message import ReadHoldingRegistersResponse  # type: ignore

class AsyncClientMock(MagicMock):
    """Magic mock that works with async methods."""

    async def __call__(self, *args, **kwargs):
        """Convert regular mocks into into an async coroutine."""
        return super().__call__(*args, **kwargs)

    async def close(self):
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

        # Initialize each zone with 25.0 for actual/setpoint, 0.0 output
        self._registers: dict[int, float] = {}
        for zone in range(1, 9):
            zone_offset = self.modbus_offset * (zone - 1)
            self._registers[self.actual_temp_address + zone_offset] = 25.0
            self._registers[self.setpoint_address + zone_offset] = 25.0
            self._registers[self.output_address + zone_offset] = 0.0

    def _perturb(self):
        for zone in range(1, 9):
            zone_offset = self.modbus_offset * (zone - 1)
            actual_addr = self.actual_temp_address + zone_offset
            setpoint_addr = self.setpoint_address + zone_offset
            output_addr = self.output_address + zone_offset

            actual = self._registers[actual_addr]
            setpoint = self._registers[setpoint_addr]
            output = self._registers[output_addr]

            if actual < setpoint:
                actual += 1
                output = min(setpoint - actual, 100)
            elif actual > setpoint:
                actual -= 1
                output = 0

            self._registers[actual_addr] = actual
            self._registers[output_addr] = output

    async def _request(self, method, address, count, **kwargs):
        if method == 'read_holding_registers':
            val = self._registers.get(address, 0.0)
            hi, lo = struct.unpack('>HH', struct.pack('>f', val))
            if pymodbus38plus:
                return ReadHoldingRegistersResponse(registers=[hi, lo])  # type: ignore
            return ReadHoldingRegistersResponse([hi, lo])  # type: ignore

        if method == 'write_registers':
            hi, lo = count[0], count[1]
            self._registers[address] = struct.unpack('>f', struct.pack('>HH', hi, lo))[0]
            self._perturb()
            return

        raise NotImplementedError(f'Unrecognised method: {method}')
