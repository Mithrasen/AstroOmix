import pytest

from src.data.timepoints import MISSION_DURATION_DAYS, sort_timepoints, to_mission_day


def test_preflight_labels_are_negative():
    assert to_mission_day("L-92") == -92
    assert to_mission_day("L-44") == -44
    assert to_mission_day("L-3") == -3


def test_launch_is_day_zero():
    assert to_mission_day("L-0") == 0


def test_return_labels_are_offset_by_mission_duration():
    """R+1 is one day after splashdown, not one day after launch. Collapsing
    that would erase the 3-day flight from the timeline."""
    assert to_mission_day("R+1") == MISSION_DURATION_DAYS + 1 == 4
    assert to_mission_day("R+194") == MISSION_DURATION_DAYS + 194 == 197


def test_preflight_and_postflight_never_collide():
    days = [to_mission_day(t) for t in ["L-92", "L-44", "L-3", "R+1", "R+45", "R+82", "R+194"]]
    assert days == sorted(days)
    assert len(set(days)) == len(days)


def test_sort_is_chronological_not_lexicographic():
    labels = ["R+194", "L-3", "R+1", "L-92", "R+45"]
    assert sort_timepoints(labels) == ["L-92", "L-3", "R+1", "R+45", "R+194"]


def test_unknown_label_raises_rather_than_guessing():
    for bad in ["FD2", "", "L92", "X+1", "R+"]:
        with pytest.raises(ValueError):
            to_mission_day(bad)
