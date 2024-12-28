import typing
import math
import os
import time
from datetime import datetime
from tqdm import tqdm  # type: ignore
import s2sphere  # type: ignore
import staticmaps  # type: ignore
import polyline  # type: ignore
import PIL.ImageDraw
from cairosvg import svg2png  # type: ignore
from typing import Tuple, Optional, List, Any
from sqlalchemy import create_engine  # type: ignore
from sqlalchemy.orm import declarative_base, sessionmaker  # type: ignore
from sqlalchemy import Column, Integer, String, Float  # type: ignore
import duckdb
import ffmpeg  # type: ignore
from pathlib import Path

Base = declarative_base()


class Activity(Base):  # type: ignore
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


def create_video_from_images(image_dir, output_file):
    # this shit function is written by cursor(model Claude)
    output_dir = os.path.dirname(output_file)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)
    head_file = Path(image_dir) / Path("github_2024.svg")
    head_is_exists = head_file.exists()
    # to png_file
    if head_is_exists:
        with head_file.open("rb") as f:
            head_path = Path(image_dir) / f"head.png"
            svg2png(
                f.read(),
                write_to=head_path.open("wb"),
                output_height=600,
                output_width=600,
            )
            # delete the svg file

    png_files = [f for f in os.listdir(image_dir) if f.lower().endswith(".png")]
    # migic number 40 yihong0618 did welcome to change it
    fps = len(png_files) / 60 if len(png_files) > 60 else 60

    png_files_with_time = [
        (f, os.path.getmtime(os.path.join(image_dir, f)))
        for f in png_files
        if f != "head.png"
    ]
    sorted_files = [f[0] for f in sorted(png_files_with_time, key=lambda x: x[1])]

    if not sorted_files:
        raise ValueError(f"no {image_dir} png files")

    list_file = "temp_file_list.txt"
    with open(list_file, "w", encoding="utf-8") as f:
        # Add head.png first if it exists
        if head_is_exists:
            f.write(f"file '{os.path.join(image_dir, 'head.png')}'\n")
            f.write(f"duration 1\n")  # Show head image for 3 seconds

        for png_file in sorted_files:
            file_path = os.path.join(image_dir, png_file)
            f.write(f"file '{file_path}'\n")
            f.write(f"duration {1/fps}\n")

    try:
        # Create input streams for both video and audio
        video_stream = ffmpeg.input(list_file, f="concat", safe=0)
        music_file = Path(image_dir) / Path("input.mp3")
        audio_stream = ffmpeg.input(music_file)

        # Combine video and audio streams
        stream = ffmpeg.output(
            video_stream,
            audio_stream,
            output_file,
            vcodec="libx264",
            pix_fmt="yuv420p",
            acodec="aac",
            r=fps,
            t=str(len(sorted_files) / fps + 1),
        ).overwrite_output()

        # Execute conversion
        stream.run(capture_stdout=True, capture_stderr=True)
        print(f"Well done output: {output_file}")

    except ffmpeg.Error as e:
        print(f"stdout: {e.stdout.decode('utf-8')}")
        print(f"stderr: {e.stderr.decode('utf-8')}")

    finally:
        # Clean up temp file
        if os.path.exists(list_file):
            os.remove(list_file)


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
    return f"{minutes} mins"


class RouteShow:
    def __init__(
        self,
        database: Optional[str] = None,
        is_all: bool = False,
        to_png: bool = False,
        use_duckdb: bool = False,
        year: int = datetime.now().year,
        repo_name: str = "yihong0618/run",
    ) -> None:
        if not database:
            database = "data/data.db"
        self.engine = create_engine(f"sqlite:///{database}")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.session = self.Session()
        self.is_all = is_all
        self.to_png = to_png
        self.use_duckdb = use_duckdb
        self.year = year
        self.repo_name = repo_name
        self.activities: List[Any] = []

    def _get_activities_from_duckdb(self) -> List[Activity]:
        activities = duckdb.sql(
            f"SELECT * FROM read_parquet('https://github.com/{self.repo_name}/raw/refs/heads/master/run_page/data.parquet') where start_date_local[:4]={self.year}"
        ).fetchall()
        return activities

    def _get_activities(self) -> List[Activity]:
        if self.is_all:
            return self.session.query(Activity).all()
        return (
            self.session.query(Activity)
            .filter(Activity.start_date_local[:4] == self.year)
            .order_by(Activity.run_id.desc())
            .all()
        )

    def generate_year_video(
        self, out_dir: str = "output", from_dir: str = "output"
    ) -> None:
        create_video_from_images(from_dir, f"{out_dir}/{self.year}.mp4")

    def generate_routes(self, out_dir: str = "output") -> None:
        if self.use_duckdb:
            self.activities = self._get_activities_from_duckdb()
            # convert to Activity object
            # (10476643980, '傍晚跑步', 2424.2, datetime.datetime(1970, 1, 1, 0, 16, 19), datetime.datetime(1970, 1, 1, 0, 17, 37), 'Run', '2024-01-01 11:27:53+00:00', '2024-01-01 19:27:53', '广贤路, 凌水街道, 栾金村, 甘井子区, 大连市, 辽宁省, 116085, 中国', 'iielF_dtdVCI\\l@JWMOS@Sf@Op@CX?TGX?Z@TPNP@REJSGiAIm@FUZe@KSQIOLIVAVWj@BVEXCr@LLb@FLQFYSm@@YFs@RS?WQKQFIVMn@Wl@CZBr@NJf@LHUBU?[EW?s@HYNSA[UIOHIRAVSl@MnAAXLRTDR?LOHs@CW@[BW?YHW@WQMSEKTMp@KTONSEKUAYJSPMHU@]JSJq@RANPZ`@RHxBrA`Ax@`@ZRF`@^HPv@`@`@XTJPLJVPFj@FRA~@FRBd@Cd@BRCHULM~ACRBz@?PGRCR@LSBWDy@AiB@u@GqAEWAY@s@Cu@JkABq@AWDo@IYBYOQu@[y@OSIg@ImAs@_@[g@S', None, 2.476)
            self.activities = [
                Activity(
                    run_id=row[0],
                    distance=row[2],
                    moving_time=row[3],
                    start_date_local=row[7],
                    summary_polyline=row[-3],
                    average_speed=row[-1],
                )
                for row in self.activities
            ]
        else:
            self.activities = self._get_activities()
        for row in tqdm(self.activities):
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
                out_dir_path = Path(out_dir)
                if (
                    not out_dir_path.exists()
                ):  # create the output directory if not exists
                    out_dir_path.mkdir(parents=True)
                svg_file_path = out_dir_path / f"{filename}.svg"
                with svg_file_path.open("w", encoding="utf-8") as f:
                    svg_image.write(f, pretty=True)
                if self.to_png:
                    with svg_file_path.open("rb") as f:
                        png_file_path = out_dir_path / f"{filename}.png"
                        svg2png(f.read(), write_to=png_file_path.open("wb"))
                        # delete the svg file
                        svg_file_path.unlink()
                # spider rule
                time.sleep(0.3)
            except Exception as e:
                print(f"something is wrong with run {row.run_id}, just continue {e}")
                continue
