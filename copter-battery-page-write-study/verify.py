"""Check the release call path, REAL32 comparison and the original navigation capture offline."""
import gzip
import runpy
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
SENSORS = REPO / "gui-original-copter-sensors"
WIRE = runpy.run_path(str(SENSORS / "verify.py"))
RUN = WIRE["RUN"]

def ordered(text, phrases):
    end = 0
    for phrase in phrases:
        try:
            end = text.index(phrase, end) + len(phrase)
        except ValueError as error:
            raise ValueError("Missing or out of order: " + phrase) from error

def section(text, name):
    return next(block for block in text.split("\n\n") if name in block.splitlines()[0])

def check():
    il = (HERE / "release-il.txt").read_text(encoding="utf-8")
    ordered(section(il, "::Activate()"), ["ldc.i4.0","::startup","::CMB_batmontype_SelectedIndexChanged",
                                         "::CMB_batmonsensortype_SelectedIndexChanged","::Start()"])
    ordered(section(il, "::CMB_batmonsensortype_SelectedIndexChanged("),
            ["::TXT_ampspervolt_Validated","::TXT_divider_Validated"])
    ordered(section(il, "::TXT_divider_Validated("),
            ["::startup","::get_Enabled","VOLT_DIVIDER","BATT_VOLT_MULT","System.Single::Parse","conv.r8","::setParam"])
    ordered(section(il, "::InitializeComponent()"), ["::TXT_divider_Validated","::add_Validated"])
    tick = section(il, "::timer1_Tick")
    assert "setParam" not in tick and "TXT_divider_Validated" not in tick and "::set_Text" in tick
    assert "publicValue=10.100000000000001 text=10.1 promotedParsed=10.100000381469727 equalDouble=False outgoingWire=9A-99-21-41" in il
    assert "publicValue=17 text=17 promotedParsed=17 equalDouble=True" in il
    guard = section(il, "<setParamAsync>d__177::MoveNext()")
    ordered(guard, ["::get_Value()", "System.Double", "::value", "bne.un", "::force"])
    storage = next(b for b in il.split("\n\n") if "ldc.i4 245" in b)
    ordered(storage, ["::lastparamset","ldc.r8 10","::AddSeconds","::lastparamset","ldc.i4 245"])
    log = (RUN / "release.log").read_text(encoding="utf-8",errors="replace")
    ordered(log, ["ConfigBatteryMonitoring Battery Monitor","BATT_MONITOR not modified as same",
                  "BATT_AMP_PERVLT not modified as same", "VOLT_DIVIDER=10.1000003814697",
                  "setParam 'BATT_VOLT_MULT'", "gotback BATT_VOLT_MULT", "doCommand cmd PREFLIGHT_STORAGE",
                  "ConfigBatteryMonitoring2 Battery Monitor 2"])
    packets = WIRE["packets"](gzip.decompress(next(RUN.glob("*.tlog.gz")).read_bytes()))
    received, sent, commit = [], [], []
    hbs = []
    for micros, sysid, compid, msg, payload in packets:
        if (sysid, compid) == (1,1):
            if msg == 22 and payload[8:24].rstrip(b"\0") == b"BATT_VOLT_MULT":
                received.append((micros,payload[:4]))
            if msg == 0:
                hbs.append(payload[6] & 128)
        elif sysid == 255:
            if msg == 23:
                assert payload[6:22].rstrip(b"\0") == b"BATT_VOLT_MULT"
                assert payload[4:6] == bytes([1,1])
                sent.append((micros,payload[:4]))
            if msg == 76 and int.from_bytes(payload[28:30],"little") == 245:
                assert payload[:4] == bytes.fromhex("0000803f")
                commit.append(micros)
    assert len(received) == 2 and len(sent) == len(commit) == 1 and len(hbs) == 518 and not any(hbs)
    assert received[0][1] == sent[0][1] == received[1][1] == bytes.fromhex("9a992141")
    assert received[0][0] < sent[0][0] < received[1][0] < commit[0]
    assert commit[0] - received[1][0] == 10172525
    print("Release activation, numeric guard, identical wire bytes and delayed storage verified.")

if __name__ == "__main__":
    check()
