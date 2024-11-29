import pytest
from route_show.route_show import (
    Activity,
    format_pace,
    convert_moving_time_to_sec,
    format_run_time,
    Base,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.close()


@pytest.fixture
def sample_activity(db_session):
    activity = Activity(
        run_id=1,
        distance=5000.0,
        moving_time="00:30:00",
        start_date="2024-01-01 10:00:00+00:00",  # Fixed date for testing
        summary_polyline="abc123",
        average_speed=2.77,
    )
    db_session.add(activity)
    db_session.commit()
    return activity


def test_format_pace():
    assert format_pace(2.77) == "6'01"  # ~6:00 min/km
    assert format_pace(0) == "0"
    assert format_pace(5.54) == "3'00"  # ~3:00 min/km


def test_convert_moving_time_to_sec():
    assert convert_moving_time_to_sec("00:30:00") == 1800
    assert convert_moving_time_to_sec("2 days, 12:34:56") == 45296
    assert convert_moving_time_to_sec("") == 0


def test_format_run_time():
    assert format_run_time("00:00:45") == "45s"
    assert format_run_time("00:30:00") == "30mins"
    assert format_run_time("") == "0s"


def test_activity_model(sample_activity, db_session):
    activity = db_session.query(Activity).first()
    assert activity.run_id == 1
    assert activity.distance == 5000.0
    assert activity.moving_time == "00:30:00"
    assert activity.start_date.startswith("2024-01-01")
    assert activity.summary_polyline == "abc123"
    assert activity.average_speed == 2.77
