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
        self.state = {i: {'actual': 25.0, 'setpoint': 25.0, 'output': 0.0} for i in range(1, 9)}
        self.client = AsyncClientMock()
        self._detect_pymodbus_version()
        self.actual_temp_address = 360
        self.setpoint_address = 2160
        self.output_address = 1904
        self.modbus_offset = 5000
        self._registers: dict[int, int] = {}
        self._update_registers_from_state()

    @property
    def base_addresses(self):
        """Return address constants."""
        return {
            'actual': self.actual_temp_address,
            'setpoint': self.setpoint_address,
            'output': self.output_address,
        }

    def _perturb(self):
        for temps in self.state.values():
            if temps['actual'] < temps['setpoint']:
                temps['actual'] += 1
                temps['output'] = min(temps['setpoint'] - temps['actual'], 100)
            elif temps['actual'] > temps['setpoint']:
                temps['actual'] -= 1
                temps['output'] = 0
        self._update_registers_from_state()

    def _update_registers_from_state(self):
        for zone, temps in self.state.items():
            zone_offset = self.modbus_offset * (zone - 1)
            for param, base_addr in self.base_addresses.items():
                val = temps[param]
                hi, lo = struct.unpack('>HH', struct.pack('>f', val))
                reg = base_addr + zone_offset
                self._registers[reg] = hi
                self._registers[reg + 1] = lo

    def _update_state_from_registers(self):
        for zone in self.state:
            zone_offset = self.modbus_offset * (zone - 1)
            for param, base_addr in self.base_addresses.items():
                reg = base_addr + zone_offset
                hi = self._registers.get(reg, 0)
                lo = self._registers.get(reg + 1, 0)
                packed = struct.pack('>HH', hi, lo)
                val = struct.unpack('>f', packed)[0]
                self.state[zone][param] = val

    async def _request(self, method, address, count, **kwargs):
        if method == 'read_holding_registers':
            regs = [self._registers.get(address + i, 0) for i in range(count)]
            if pymodbus38plus:
                return ReadHoldingRegistersResponse(registers=regs)  # type: ignore
            return ReadHoldingRegistersResponse(regs)

        if method == 'write_registers':
            for i, val in enumerate(count):
                self._registers[address + i] = val
            self._update_state_from_registers()
            self._perturb()
            return WriteMultipleRegistersResponse(address, count)

        raise NotImplementedError(f'Unrecognised method: {method}')
