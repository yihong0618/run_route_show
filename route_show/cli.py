import argparse
from route_show.route_show import RouteShow


def main():
    parser = argparse.ArgumentParser(description="Generate routes from Strava data")
    parser.add_argument("--database", default=None, help="Path to SQLite database")
    parser.add_argument("--all", action="store_true", help="Show all activities")
    parser.add_argument("--to_png", action="store_true", help="Save routes as PNG")
    args = parser.parse_args()
    route_show = RouteShow(args.database, args.all, args.to_png)
    route_show.generate_routes()
