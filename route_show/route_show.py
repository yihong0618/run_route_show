import typing
import math
import os
import time
from tqdm import tqdm  # type: ignore
import s2sphere  # type: ignore
import staticmaps  # type: ignore
import polyline  # type: ignore
import PIL.ImageDraw
from cairosvg import svg2png
from typing import Tuple, Optional, List, Any
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import Column, Integer, String, Float

Base = declarative_base()


class Activity(Base):
    __tablename__ = "activities"

    run_id = Column(Integer, primary_key=True)
    distance = Column(Float, nullable=False)
    moving_time = Column(String, nullable=False)
    start_date_local = Column(String, nullable=False)
    summary_polyline = Column(String, nullable=False)
    average_speed = Column(Float, nullable=False)


def textsize(
    self: PIL.ImageDraw.ImageDraw, *args: Any, **kwargs: Any
) -> Tuple[int, int]:
    x, y, w, h = self.textbbox((0, 0), *args, **kwargs)
    return w, h  # type: ignore


# monkeypatch fix for Context zoom


def _determine_zoom(
    self,
    width: int,
    height: int,
    b: typing.Optional[s2sphere.LatLngRect],
    c: s2sphere.LatLng,
) -> typing.Optional[int]:
    if b is None:
        b = s2sphere.LatLngRect(c, c)
    else:
        b = b.union(s2sphere.LatLngRect(c, c))
    assert b
    if b.is_point():
        return self._clamp_zoom(15)

    pixel_margin = self.extra_pixel_bounds()

    w = (width - pixel_margin[0] - pixel_margin[2]) / self._tile_provider.tile_size()
    h = (height - pixel_margin[1] - pixel_margin[3]) / self._tile_provider.tile_size()
    # margins are bigger than target image size => ignore them
    if w <= 0 or h <= 0:
        w = width / self._tile_provider.tile_size()
        h = height / self._tile_provider.tile_size()

    min_y = (
        1.0
        - math.log(math.tan(b.lat_lo().radians) + (1.0 / math.cos(b.lat_lo().radians)))
    ) / (2 * math.pi)
    max_y = (
        1.0
        - math.log(math.tan(b.lat_hi().radians) + (1.0 / math.cos(b.lat_hi().radians)))
    ) / (2 * math.pi)
    dx = (b.lng_hi().degrees - b.lng_lo().degrees) / 360.0
    if dx < 0:
        dx += math.ceil(math.fabs(dx))
    if dx > 1:
        dx -= math.floor(dx)
    dy = math.fabs(max_y - min_y)

    for zoom in range(1, self._tile_provider.max_zoom()):
        tiles = 2**zoom
        if (dx * tiles > w) or (dy * tiles > h):
            return self._clamp_zoom(zoom - 1)
    return self._clamp_zoom(18)


staticmaps.Context._determine_zoom = _determine_zoom  # type: ignore


# Monkeypatch fix for https://github.com/flopp/py-staticmaps/issues/39
PIL.ImageDraw.ImageDraw.textsize = textsize  # type: ignore


def format_pace(d: float) -> str:
    if not d:  # Check for NaN
        return "0"
    pace: float = (1000.0 / 60.0) * (1.0 / d)
    minutes: int = int(pace)
    seconds: int = int((pace - minutes) * 60.0)
    return f"{minutes}'{str(seconds).zfill(2)}"


def convert_moving_time_to_sec(moving_time: str) -> int:
    if not moving_time:
        return 0
    # Handle both "2 days, 12:34:56" and "12:34:56" formats
    time_parts = moving_time.split()
    time_str = time_parts[-1].split(".")[0] if len(time_parts) > 1 else moving_time
    hours, minutes, seconds = map(int, time_str.split(":"))
    total_seconds: int = (hours * 60 + minutes) * 60 + seconds
    return total_seconds


def format_run_time(moving_time: str) -> str:
    total_seconds: int = convert_moving_time_to_sec(moving_time)
    seconds: int = total_seconds % 60
    minutes: int = total_seconds // 60
    if minutes == 0:
        return f"{seconds}s"
    return f"{minutes}mins"


class RouteShow:
    def __init__(
        self, database: Optional[str] = None, is_all: bool = False, to_png: bool = False
    ) -> None:
        if not database:
            database = "data/data.db"
        self.engine = create_engine(f"sqlite:///{database}")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.session = self.Session()
        self.is_all = is_all
        self.to_png = to_png

    def _get_activities(self) -> List[Activity]:
        if self.is_all:
            return self.session.query(Activity).all()
        return (
            self.session.query(Activity)
            .order_by(Activity.run_id.desc())
            .limit(30)
            .all()
        )

    def generate_routes(self) -> None:
        activities: List[Activity] = self._get_activities()
        for row in tqdm(activities):
            try:
                context = staticmaps.Context()
                lines = polyline.decode(row.summary_polyline)
                line = [staticmaps.create_latlng(p[0], p[1]) for p in lines]
                context.add_object(staticmaps.Line(line, width=3))
                svg_image = context.render_svg(600, 600)
                if not row.start_date_local or not row.distance or not row.moving_time:
                    continue
                date_str = row.start_date_local[:16]
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
                distance = round(row.distance / 1000, 1)
                duration = format_run_time(str(row.moving_time))
                pace = format_pace(float(row.average_speed or 0))
                if self.to_png:
                    texts = [
                        (f"{duration}", 100),
                        (f"{distance} km", 300),
                        (f"{pace}", 500),
                    ]
                else:
                    texts = [
                        (f"⏱ {duration}", 100),
                        (f"{distance} km", 300),
                        (f"⌚ {pace}", 500),
                    ]
                for txt, x in texts:
                    svg_image.add(
                        svg_image.text(
                            txt,
                            insert=(x, 560),
                            fill="black",
                            font_size="30px",
                            font_weight="bold",
                            text_anchor="middle",
                        )
                    )
                # filenme like 20241011_5km_30mins
                filename = f"{row.start_date_local[:10].replace('-', '')}_{distance}km_{duration}"
                with open(f"{filename}.svg", "w", encoding="utf-8") as f:
                    svg_image.write(f, pretty=True)
                if self.to_png:
                    with open(f"{filename}.svg", "rb") as f:
                        svg2png(f.read(), write_to=open(f"{filename}.png", "wb"))
                        # delete the svg file
                        os.remove(f"{filename}.svg")
                # spider rule
                time.sleep(0.3)
            except Exception as e:
                print(f"something is wrong with run {row.run_id}, just continue {e}")
                continue
