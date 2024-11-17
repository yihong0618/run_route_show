import staticmaps
import s2sphere as s2
import math
import sqlite3
import polyline
import PIL.ImageDraw
from typing import Tuple, Union, List


def textsize(self: PIL.ImageDraw.ImageDraw, *args, **kwargs):
    x, y, w, h = self.textbbox((0, 0), *args, **kwargs)
    return w, h


# Monkeypatch fix for https://github.com/flopp/py-staticmaps/issues/39
PIL.ImageDraw.ImageDraw.textsize = textsize


class XY:
    """Represent x,y coords with properly overloaded operations."""

    def __init__(self, x: float = 0, y: float = 0) -> None:
        self.x = x
        self.y = y

    def __mul__(self, factor: Union[float, "XY"]) -> "XY":
        if isinstance(factor, XY):
            return XY(self.x * factor.x, self.y * factor.y)
        return XY(self.x * factor, self.y * factor)

    def __rmul__(self, factor: Union[float, "XY"]) -> "XY":
        if isinstance(factor, XY):
            return XY(self.x * factor.x, self.y * factor.y)
        return XY(self.x * factor, self.y * factor)

    def __add__(self, other: "XY") -> "XY":
        return XY(self.x + other.x, self.y + other.y)

    def __sub__(self, other: "XY") -> "XY":
        return XY(self.x - other.x, self.y - other.y)

    def __repr__(self):
        return f"XY: {self.x}/{self.y}"

    def tuple(self) -> Tuple[float, float]:
        return self.x, self.y


# mercator projection
def latlng2xy(latlng: s2.LatLng) -> XY:
    return XY(lng2x(latlng.lng().degrees), lat2y(latlng.lat().degrees))


def lng2x(lng_deg: float) -> float:
    return lng_deg / 180 + 1


def lat2y(lat_deg: float) -> float:
    return 0.5 - math.log(math.tan(math.pi / 4 * (1 + lat_deg / 90))) / math.pi

def bbox(polylines: List[List[s2.LatLng]]) -> s2.LatLngRect:
    """Compute the smallest rectangle that contains the entire track (border box)."""
    bbox = s2.LatLngRect()
    for line in polylines:
        for latlng in line:
            bbox = bbox.union(s2.LatLngRect.from_point(latlng.normalized()))
    return bbox


def project(
    bbox: s2.LatLngRect, size: XY, offset: XY, latlnglines: List[List[s2.LatLng]]
) -> List[List[Tuple[float, float]]]:
    min_x = lng2x(bbox.lng_lo().degrees)
    d_x = lng2x(bbox.lng_hi().degrees) - min_x
    while d_x >= 2:
        d_x -= 2
    while d_x < 0:
        d_x += 2
    min_y = lat2y(bbox.lat_lo().degrees)
    max_y = lat2y(bbox.lat_hi().degrees)
    d_y = abs(max_y - min_y)
    # the distance maybe zero
    if d_x == 0 or d_y == 0:
        return []
    scale = size.x / d_x if size.x / size.y <= d_x / d_y else size.y / d_y
    offset = offset + 0.5 * (size - scale * XY(d_x, -d_y)) - scale * XY(min_x, min_y)
    lines = []
    # If len > $zoom_threshold, choose 1 point out of every $step to reduce size of the SVG file
    zoom_threshold = 400
    for latlngline in latlnglines:
        line = []
        step = int(len(latlngline) / zoom_threshold) + 1
        for i in range(0, len(latlngline), step):
            latlng = latlngline[i]
            if bbox.contains(latlng):
                line.append((offset + scale * latlng2xy(latlng)).tuple())
            else:
                if len(line) > 0:
                    lines.append(line)
                    line = []
        if len(line) > 0:
            lines.append(line)
    return lines


def format_pace(d: float) -> str:
    if not d:  # Check for NaN
        return "0"
    pace = (1000.0 / 60.0) * (1.0 / d)
    minutes = int(pace)
    seconds = int((pace - minutes) * 60.0)
    return f"{minutes}'{str(seconds).zfill(2)}"


def convert_moving_time_to_sec(moving_time: str) -> int:
    if not moving_time:
        return 0
    # moving_time: '2 days, 12:34:56' or '12:34:56'
    time = moving_time.split()[1].split(".")[0]
    hours, minutes, seconds = map(int, time.split(":"))
    total_seconds = (hours * 60 + minutes) * 60 + seconds
    return total_seconds


def format_run_time(moving_time: str) -> str:
    total_seconds = convert_moving_time_to_sec(moving_time)
    seconds = total_seconds % 60
    minutes = total_seconds // 60
    if minutes == 0:
        return f"{seconds}s"
    return f"{minutes}min"


SQL = "SELECT * FROM activities ORDER BY run_id DESC LIMIT 3;"
with sqlite3.connect("data.db") as conn:
    cursor = conn.cursor()
    # Fetch all table names
    cursor.execute(SQL)
    rows = cursor.fetchall()
    lines = []
    index = 1
    for row in rows:
        context = staticmaps.Context()
        lines = polyline.decode(row[-3])
        line = [staticmaps.create_latlng(p[0], p[1]) for p in lines]
        context.add_object(staticmaps.Line(line))
        svg_image = context.render_svg(600, 600)
        date_str = row[6]
        # 2024-11-14 12:34:56+00:00 -> 2024-11-14 12:34
        date_str = date_str[:16]
        svg_image.add(
            svg_image.text(
                date_str,
                insert=(100, 50),
                fill="black",
                font_size="20px",
                font_weight="bold",
                text_anchor="middle",
            )
        )
        distance = round(row[2] / 1000, 1)
        duration = format_run_time(row[3])
        pace = format_pace(row[-1])
        texts = [(f"⏱ {duration}", 100), (f"{distance} 公里", 300), (f"⌚ {pace}", 500)]
        for text, x in texts:
            svg_image.add(
                svg_image.text(
                    text,
                    insert=(x, 575),
                    fill="black",
                    font_size="25px",
                    font_weight="bold",
                    text_anchor="middle",
                )
            )

        with open(f"test_{index}.svg", "w", encoding="utf-8") as f:
            svg_image.write(f, pretty=True)
        index += 1
