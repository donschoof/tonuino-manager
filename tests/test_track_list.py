import pytest

pytest.importorskip("PyQt6")

from gui.track_list import reorder_with_selection


def order(tracks, selected, delta):
    new_order, rows = reorder_with_selection(tracks, {id(t) for t in selected}, delta)
    return new_order, rows


def test_move_single_track_up_and_down():
    ta, tb, tc = [object() for _ in range(3)]
    new, rows = order([ta, tb, tc], [tb], -1)
    assert new == [tb, ta, tc] and rows == [0]
    new, rows = order([ta, tb, tc], [tb], 1)
    assert new == [ta, tc, tb] and rows == [2]


def test_move_at_edge_changes_nothing():
    ta, tb = object(), object()
    assert order([ta, tb], [ta], -1)[0] == [ta, tb]
    assert order([ta, tb], [tb], 1)[0] == [ta, tb]


def test_scattered_selection_is_gathered_to_a_block():
    t = [object() for _ in range(5)]
    new, rows = order(t, [t[1], t[3]], -1)
    assert new == [t[1], t[3], t[0], t[2], t[4]] and rows == [0, 1]
