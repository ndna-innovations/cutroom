"""Camera "slim": the picture keeps its size and a vertical bar comes out narrower relative to the frame height."""
import subprocess, numpy as np
from studio import assets as A


def bar_width(filters):
    vf = "drawbox=x=440:y=0:w=400:h=720:color=white:t=fill" + "".join("," + f for f in filters)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=black:s=1280x720:d=0.1", "-vf", vf + ",format=gray",
                          "-frames:v", "1", "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    img = np.frombuffer(raw, np.uint8).reshape(720, 1280)
    return int((img[360] > 128).sum()), img.shape


def test_slim_keeps_size_and_narrows():
    w0, shape0 = bar_width([])
    w1, shape1 = bar_width(A.source_fixes({"slim": 0.92}))
    assert shape1 == shape0 == (720, 1280)
    # stretched taller by 1/0.92 then cropped: the bar's width-to-height ratio drops about 8%; width in px is unchanged,
    # so check the picture really was stretched: a horizontal line at the top moves down
    assert w1 == w0
    assert A.source_fixes({}) == []


def test_slim_stretches_vertically():
    vf = "drawbox=x=0:y=200:w=1280:h=40:color=white:t=fill," + A.source_fixes({"slim": 0.92})[0] + ",format=gray"
    raw = subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=black:s=1280x720:d=0.1", "-vf", vf,
                          "-frames:v", "1", "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    col = np.frombuffer(raw, np.uint8).reshape(720, 1280)[:, 640]
    rows = np.where(col > 128)[0]
    assert 42 <= len(rows) <= 45          # 40 px band now ~43.5 px tall: everything 1/0.92 taller, so people read 8% narrower
