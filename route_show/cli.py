import argparse
import shutil
from datetime import datetime
from route_show.route_show import RouteShow


def main():
    parser = argparse.ArgumentParser(description="Generate routes from Strava data")
    parser.add_argument("--database", default=None, help="Path to SQLite database")
    parser.add_argument("--all", action="store_true", help="Show all activities")
    parser.add_argument("--to_png", action="store_true", help="Save routes as PNG")
    parser.add_argument(
        "--use_duckdb", action="store_true", help="Use DuckDB instead of SQLite"
    )
    parser.add_argument("--year", default=datetime.now().year, help="generate the year")
    parser.add_argument("--video", action="store_true", help="generate the video")
    parser.add_argument("--repo_name", default="yihong0618/run", help="repo name")

    args = parser.parse_args()
    # if video is true, then we need to generate the video
    if args.video:
        # check if ffmpeg is installed
        if not shutil.which("ffmpeg"):
            print("ffmpeg is not installed, please install it first")
            return
    route_show = RouteShow(
        args.database,
        args.all,
        args.to_png,
        use_duckdb=args.use_duckdb,
        year=args.year,
        repo_name=args.repo_name,
    )
    if args.video:
        route_show.generate_year_video()
    else:
        route_show.generate_routes()
