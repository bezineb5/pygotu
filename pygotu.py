import datetime
import logging
import time
from functools import lru_cache
from struct import pack, unpack

log = logging.getLogger(__name__)

MODE_GPS_DONGLE = 0
MODE_GPS_TRACKER = 1
MODE_CONFIGURE = 3

# Model details contain 3 fields:
# - The name of the device
# - The number of blocks to erase during a purge
# - Wether an unknown purge command 0x1d should be sent during purge
MODELS = {
    0x13: ("GT-100", 0x080, False),
    0x14: ("GT-200", 0x200, False),
    0x15: ("GT-120", 0x100, False),
    0x17: ("GT-200e/GT-600", 0x700, True),
}

def hexdumps(s: bytes) -> None:
    return s.hex()


def bitcount(n: int) -> int:
    count = 0
    while n > 0:
        if (n & 1 == 1):
            count += 1
        n >>= 1

    return count


@lru_cache(maxsize=4)
def get_year(year_offset: int) -> int:
    current_year = datetime.date.today().year
    quotient = (current_year - 2000) // 16
    year = 2000 + 16 * quotient + year_offset

    if year > current_year:
        year -= 16

    return year


class GT200Dev:
    __slots__ = ['dev', 'model_info']

    def __init__(self, device):
        self.dev = device
        self.dev.flush()
        self.model_info = MODELS[0x13]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        self.dev.close()

    def write_cmd(self, cmd1, cmd2):
        self.dev.flush()
        assert len(cmd1) == 8
        assert len(cmd2) == 8
        cs = 0
        for ch in cmd1 + cmd2[:7]:
            cs += ch
        cs = ((cs ^ 0xff) + 0x01) & 0xff
        cmd2 = cmd2[:7] + bytes([cs])
        log.debug("Send1&2: %s", hexdumps(cmd1 + cmd2))
        self.dev.write(cmd1 + cmd2)

    def read(self, sz) -> bytes:
        result = self.dev.read(sz)
        log.debug("Read: %s", hexdumps(result))
        return result

    def read_resp(self, fmt=None):
        recv = self.read(3)
        if recv[0] != 0x93:
            raise Exception("Unable to identify device")
        _, sz = unpack(">ch", recv)
        if sz < 0:
            log.debug("Read Error: %s", sz)
            return None
        log.debug("Reading %s bytes...", sz)

        resp = self.read(sz)
        if fmt:
            return unpack(">" + fmt, resp)
        else:
            return resp

    def nmea_switch(self, mode: int) -> None:
        mch = [b"\x00", b"\x01", b"\x02", b"\x03"][mode]
        self.write_cmd(
            b"\x93\x01\x01" + mch + b"\x00\x00\x00\x00",
            b"\x00\x00\x00\x00\x00\x00\x00\x00"
        )
        self.read(1)

    def identify(self):
        self.write_cmd(
            b"\x93\x0a\x00\x00\x00\x00\x00\x00",
            b"\x00\x00\x00\x00\x00\x00\x00\x00"
        )
        serial, v_maj, v_min, model, v_lib = self.read_resp(fmt="IbbHH")
        log.debug("Serial: %s", serial)
        log.debug("Ver: %s.%s", v_maj, v_min)
        log.debug("Model %s:", model)
        log.debug("USBlib: %s", v_lib)

    def model(self):
        self.write_cmd(
            b"\x93\x05\x04\x00\x03\x01\x9f\x00",
            b"\x00\x00\x00\x00\x00\x00\x00\x00"
        )
        checkcode, model_code = self.read_resp(fmt="Hb")
        if checkcode != 0xC220:
            log.error("Unexpected result from model query: %s", checkcode)
            return

        current_model = MODELS.get(model_code)
        if not current_model:
            raise Exception("Unknown model: {}".format(model_code))
        self.model_info = current_model
        log.info("Found device: %s", current_model[0])

    def count(self) -> int:
        self.write_cmd(
            b"\x93\x0b\x03\x00\x1d\x00\x00\x00",
            b"\x00\x00\x00\x00\x00\x00\x00\x00"
        )
        n1, n2 = self.read_resp(fmt="Hb")
        num = n1*256 + n2
        log.debug("Num DP: %s (%s %s)", num, n1, n2)
        return num

    def flash_read(self, pos: int=0, size: int=0x1000) -> bytes:
        chpos = pack(">I", pos)
        chsz = pack(">H", size)
        self.write_cmd(
            b"\x93\x05\x07" + chsz + b"\x04\x03" + chpos[1:2],
            chpos[2:4] + b"\x00\x00\x00\x00\x00\x00"
        )
        buf = self.read_resp()
        return buf

    def purge_all_120(self):
        purge_flag = False
        n_blocks = self.model_info[1]
        should_send_unk_1d_command = self.model_info[2]

        for i in range(n_blocks, 0, -1):
            log.debug("I=%s", i)
            if purge_flag:
                while self.unk_write2(0x01) != b"\x00":
                    log.debug("Waiting...")
                    pass
            else:
                if self.flash_read(pos=(i * 0x1000), size=0x10) != (b"\xff" * 0x10):
                    purge_flag = True
                else:
                    continue
            self.unk_write1(0)
            self.flash_write_purge(i * 0x1000)
        if purge_flag:
            if should_send_unk_1d_command:
                self.unk_purge1(0x1d)
            self.unk_purge1(0x1e)
            self.unk_purge1(0x1f)
            while self.unk_write2(0x01) != b"\x00":
                log.debug("Waiting...")

        if should_send_unk_1d_command:
            self.unk_purge1(0x1d)
        self.unk_purge1(0x1e)
        self.unk_purge1(0x1f)

    def purge_all_gt900(self):
        purge_flag = False
        n_blocks = 0x700

        for i in range(n_blocks-1, 0, -1):
            log.debug("I=%s", i)
            if not purge_flag:
                log.debug("NP")
                if self.flash_read(pos=(i * 0x1000), size=0x10) != (b"\xff" * 0x10):
                    log.debug("pf = true")
                    purge_flag = True
                else:
                    log.debug("cont.")
                    continue
            log.debug("Writing")
            self.unk_write1(0x00)
            self.flash_write_purge(i * 0x1000)
            log.debug("UNKW2")
            while self.unk_write2(0x01) != b"\x00":
                log.debug("Waiting...")
            log.info("Purged.")

    def flash_write_purge(self, pos) -> bytes:
        chpos = pack(">I", pos)
        w = 0x20
        self.write_cmd(
            b"\x93\x06\x07\x00\x00\x04" + bytes([w, chpos[1]]),
            chpos[2:4] + b"\x00\x00\x00\x00\x00\x00"
        )
        buf = self.read_resp()
        return buf

    def unk_write1(self, p1: int) -> bytes:
        self.write_cmd(
            b"\x93\x06\x04\x00" + bytes([p1]) + b"\x01\x06\x00",
            b"\x00\x00\x00\x00\x00\x00\x00\x00"
        )
        buf = self.read_resp()
        return buf

    def unk_write2(self, p1: int) -> bytes:
        p1ch = pack('>H', p1)
        self.write_cmd(
            b"\x93\x05\x04" + p1ch + b"\x01\x05\x00",
            b"\x00\x00\x00\x00\x00\x00\x00\x00"
        )
        buf = self.read_resp()
        return buf

    def unk_purge1(self, p1: int) -> bytes:
        self.write_cmd(
            b"\x93\x0C\x00" + bytes([p1]) + b"\x00\x00\x00\x00",
            b"\x00\x00\x00\x00\x00\x00\x00\x00"
        )
        buf = self.read_resp()
        return buf

    def unk_purge2(self, p1: int) -> bytes:
        self.write_cmd(
            "\x93\x08\x02" + bytes([p1]) + "\x00\x00\x00\x00",
            "\x00\x00\x00\x00\x00\x00\x00\x00"
        )
        buf = self.read_resp()
        return buf

    def all_records(self):
        rpos = 0
        buf = ""
        num_rec_read = 0
        num_rec_all = self.count()

        RECSIZE = 0x20
        while True:
            rpos += 1
            buf = self.flash_read(rpos * 0x1000)
            for i in range(len(buf) // RECSIZE):
                record = GTRecord(num_rec_read, buf[i*RECSIZE:(i+1)*RECSIZE])
                if record.valid:
                    yield record
                num_rec_read += 1
                if num_rec_read >= num_rec_all:
                    log.debug("End by count: %s", num_rec_all)
                    return
            log.debug("End RECLOOP")

    def all_tracks(self):
        idx = 0
        curlist = []
        for rec in self.all_records():
            if rec.kind == 'WP':
                curlist.append(rec)
            if rec.kind == 'LOG' and rec.msg == 'RESET COUNTER':
                if curlist:
                    yield GTTrack(idx, curlist)
                    idx += 1
                    curlist = []
        if curlist:
            yield GTTrack(idx, curlist)


class GTTrack:
    __slots__ = ['idx', 'records']

    def __init__(self, idx, reclist):
        self.idx = idx
        self.records = list(reclist)

    @property
    def first_point(self):
        return self.records[0]

    @property
    def last_point(self):
        return self.records[len(self.records) - 1]

    @property
    def first_time(self):
        return self.first_point.localtime

    @property
    def last_time(self):
        return self.last_point.localtime

    @property
    def num_points(self):
        return len(self.records)

    def __str__(self):
        return "{0.idx}: {0.first_time:%Y/%m/%d %H:%M:%S} - {0.last_time:%Y/%m/%d %H:%M:%S} points:[{0.num_points}]".format(self)


class GTRecord:
    __slots__ = ['valid', 'idx', 's', 'plr', 'flag', 'datetime', 'msg', 'kind', 'lat', 'lon',
                 'elevation', 'speed', 'course', 'sat', 'desc', 'ehpe', 'unk1', 'flagopts']

    def __init__(self, idx, s):
        self.valid = True
        self.idx = idx
        self.s = s
        flag, ym, dhm, ms = unpack(">BBHH", self.s[0x00:0x06])
        self.plr = unpack(">H", self.s[0x1e:0x20])
        self.flag = flag

        year = get_year(ym >> 4)
        month = (ym & 0x0F) % 13
        day = dhm >> 11
        if day <= 0:
            day = 1
        hour = ((dhm >> 6) & 0b00011111) % 24
        minutes = (dhm & 0b00111111) % 60
        sec = int(ms / 1000) % 60
        ms = ms % 1000

        try:
            self.datetime = datetime.datetime(
                year, month, day, hour, minutes, sec, ms)
        except ValueError:
            self.datetime = None
            self.valid = False
            log.warning("InvalidDate: %s", (year, month,
                                            day, hour, minutes, sec, ms))

        self.msg = None

        if flag & 0x20 != 0:
            # Invalid point
            self.valid = False
            log.warning("Invalid flag found, %s", flag)

        if flag == 0xF1:
            self.parse_device_log()
        elif flag == 0xF5:
            self.parse_heartbeat()
        else:
            self.parse_waypoint()

    @property
    def is_waypoint(self):
        return self.kind == "WP"

    @property
    def localtime(self):
        return self.datetime - datetime.timedelta(seconds=time.timezone)

    def parse_waypoint(self):
        self.kind = "WP"
        (ae, r_sat_map, r_lat, r_lon, r_ele_gps, r_speed,
         r_course, f2) = unpack(">HiiiiHHH", self.s[0x06:0x1e])

        self.unk1 = (ae >> 12)
        self.ehpe = (ae & 0b0000111111111111) * 1e-2 * 0x10  # in m

        self.lon = r_lon / 10000000.0
        self.lat = r_lat / 10000000.0
        self.elevation = r_ele_gps / 100.0  # in m
        self.speed = (r_speed / 100.0) / 1000.0 * 3600.0  # km/h
        self.course = r_course / 100.0  # degree
        self.sat = bitcount(r_sat_map)  # f2 & 0b00001111 # num of sat

        self.flagopts = set()

        FLAGNAMES = ["U0", "U1", "WP", "U3", "NDI", "TSTOP", "TSTART", "U7"]
        for bit in range(8):
            if self.flag & (1 << bit):
                self.flagopts.add(FLAGNAMES[bit])

        #self.fopts = ",".join(self.flagopts)

        if self.lat == 0 and self.lon == 0:
            self.valid = False

        self.desc = "WP LATLON:({0.lat}, {0.lon}) ele:{0.elevation} speed:{0.speed} uf={0.unk1:b} ehpe={0.ehpe} {0.flagopts}".format(
            self)

    def parse_heartbeat(self):
        raise NotImplementedError()

    def parse_device_log(self):
        self.kind = "LOG"
        self.msg = self.s[0x06:0x1e].replace('\x00', '').strip()
        self.desc = "LOG {0.msg}".format(self)

    def parse_unknown(self):
        self.kind = "UNK"
        self.desc = "UNK {0.flag}".format(self)

    def __str__(self):
        return "{0.datetime:%Y/%m/%d %H:%M:%S} {0.desc}".format(self)


def test():
    import connections
    dev = GT200Dev(connections.get_connection())

    dev.identify()
    n = dev.count()

    # for track in dev.all_tracks():
    #    print track

    for rec in dev.all_records():
        print("- ", rec.idx, "/", n, ":", rec)

    dev.close()


def main():
    test()


if __name__ == '__main__':
    main()
