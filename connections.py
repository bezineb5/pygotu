import logging
import serial
import usb.core
import usb.util

log = logging.getLogger(__name__)

CONNECTION_TYPE_USB = "USB"
CONNECTION_TYPE_SERIAL = "SERIAL"

VENDOR_ID = 0x0df7
PRODUCT_ID = 0x0900
INTERFACE = 0
ENDPOINT = 0x81
TIMEOUT = 2000


class USBSerial(object):
    __slots__ = ['receive_buffer', 'dev', 'endpoint']

    def __init__(self):
        self.receive_buffer = bytearray()

        dev = usb.core.find(idVendor=VENDOR_ID, idProduct=PRODUCT_ID)
        dev.default_timeout = TIMEOUT
        dev.set_configuration()
        # get an endpoint instance
        cfg = dev.get_active_configuration()
        intf = cfg[(0,0)]

        ep = usb.util.find_descriptor(
            intf,
            # match the first IN endpoint
            custom_match = \
            lambda e: \
                usb.util.endpoint_direction(e.bEndpointAddress) == \
                usb.util.ENDPOINT_IN)

        assert ep is not None


        self.dev = dev
        self.endpoint = ep

    def write(self, data):
        # Using control write, 8 bytes per transfer
        result = self.dev.ctrl_transfer(0x21, 0x09, 0x0200, 0x0000, data[:8])
        assert result == 8
        self.read(3)
        result = self.dev.ctrl_transfer(0x21, 0x09, 0x0200, 0x0000, data[8:])
        assert result == 8
        
    
    def read(self, size=1):
        self._fill_receive_buffer(size)
        data = self.receive_buffer[:size]
        self.receive_buffer = self.receive_buffer[size:]

        return data

    def _fill_receive_buffer(self, size):
        while(len(self.receive_buffer) < size):
            raw_data = self.endpoint.read(0x10)
            data = raw_data.tobytes()
            self.receive_buffer.extend(data)


    def flush(self):
        self.receive_buffer.clear()
        try:
            self.endpoint.read(0x10)
        except:
            pass
    
    def close(self):
        pass


def get_connection(connection_type: str=CONNECTION_TYPE_USB, port_name: str=None):
    if connection_type == CONNECTION_TYPE_USB:
        return USBSerial()
    elif port_name and connection_type == CONNECTION_TYPE_SERIAL:
        return serial.Serial(port_name, 9600)
    
    raise Exception("Unable to find connection type %s on port %s", connection_type, port_name)
