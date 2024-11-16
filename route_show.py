import staticmaps
import sqlite3
import polyline
import PIL.ImageDraw


def textsize(self: PIL.ImageDraw.ImageDraw, *args, **kwargs):
    x, y, w, h = self.textbbox((0, 0), *args, **kwargs)
    return w, h


# Monkeypatch fix for https://github.com/flopp/py-staticmaps/issues/39
PIL.ImageDraw.ImageDraw.textsize = textsize


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
