"""The decisions, one scenario at a time, in both modes (DESIGN.md sections 6 and 11)."""
from __future__ import annotations

from datetime import timedelta

from callfirst import rules
from callfirst.household import Delivery, ExpectedVisit, Trusted, iso
from callfirst.rules import Alert, Chime

from .conftest import T0, door, offline, person, ring, seconds


def play(h, *events):
    actions = []
    for e in events:
        actions += rules.on_event(h, e, e.at)
    return actions


def alerts(actions, reason=None):
    return [a for a in actions if isinstance(a, Alert) and (reason is None or a.reason == reason)]


def chimes(actions):
    return [a.slot for a in actions if isinstance(a, Chime)]


# --------------------------------------------------------------------------- the courier


def test_courier_rings_door_opens_reminder_then_strong_alert(home):
    actions = play(home, person(T0), ring(T0 + seconds(3)), door(T0 + seconds(40)))
    assert chimes(actions) == [rules.REMINDER]
    [alert] = alerts(actions)
    assert (alert.reason, alert.confidence) == ("answered", "strong")
    assert alert.recipients == ("sarah@example.com",)
    assert alert.snapshot_at == iso(T0)


def test_reminder_plays_on_the_ring_not_before(home):
    assert chimes(play(home, person(T0))) == []
    assert chimes(play(home, ring(T0 + seconds(5)))) == [rules.REMINDER]


def test_one_reminder_and_one_alert_per_visit(home):
    actions = play(home, ring(T0), ring(T0 + seconds(10)), door(T0 + seconds(20)),
                   person(T0 + seconds(30)), door(T0 + seconds(50)))
    assert chimes(actions) == [rules.REMINDER]
    assert len(alerts(actions)) == 1


def test_bell_only_long_stay_is_a_weak_alert_that_says_what_it_cannot_see(bell_only):
    events = [ring(T0)] + [person(T0 + seconds(s)) for s in (20, 40, 65)]
    [alert] = alerts(play(bell_only, *events))
    assert alert.confidence == "weak"
    assert "cannot see whether the door was opened" in alert.detail
    assert "opened for" not in alert.detail


def test_bell_only_short_stay_is_reminder_only(bell_only):
    actions = play(bell_only, ring(T0), person(T0 + seconds(20)), person(T0 + seconds(45)))
    assert chimes(actions) == [rules.REMINDER]
    assert alerts(actions) == []


def test_bell_only_never_counts_dwell_without_a_ring(bell_only):
    # Someone lingering by the door without ringing is not someone let in.
    actions = play(bell_only, *[person(T0 + seconds(s)) for s in (0, 30, 60, 85)])
    assert alerts(actions) == []


# --------------------------------------------------------------------------- expected people


def test_carer_in_their_window_changes_nothing(home):
    home.visits.append(ExpectedVisit("carer", [1], "14:00", "16:00"))   # Tuesdays
    actions = play(home, ring(T0), door(T0 + seconds(20)))
    assert chimes(actions) == [] and alerts(actions) == []


def test_carer_window_is_local_time_not_utc(home):
    home.visits.append(ExpectedVisit("carer", [1], "19:00", "20:00"))  # 19:00 UTC is 15:00 NY
    assert alerts(play(home, ring(T0), door(T0 + seconds(20))))


def test_declared_delivery_in_its_window_changes_nothing(home):
    home.deliveries.append(Delivery("UPS", "1Z999AA10123456784",
                                    iso(T0 - timedelta(hours=1)), iso(T0 + timedelta(hours=2))))
    actions = play(home, ring(T0), door(T0 + seconds(20)))
    assert chimes(actions) == [] and alerts(actions) == []


def test_declared_delivery_outside_its_window_is_unexpected(home):
    home.deliveries.append(Delivery("UPS", "1Z999AA10123456784",
                                    iso(T0 + timedelta(hours=3)), iso(T0 + timedelta(hours=5))))
    assert alerts(play(home, ring(T0), door(T0 + seconds(20))))


# --------------------------------------------------------------------------- not answering


def test_parcel_drop_door_never_opened_is_reminder_only(home):
    actions = play(home, person(T0), ring(T0 + seconds(2)), person(T0 + seconds(15)))
    rules.tick(home, T0 + seconds(200))
    assert chimes(actions) == [rules.REMINDER] and alerts(actions) == []
    assert home.visit is None


def test_fetching_the_parcel_after_the_driver_left_is_not_answering(home):
    play(home, ring(T0), person(T0 + seconds(10)))
    assert alerts(play(home, door(T0 + seconds(10 + 5 * 60)))) == []


def test_resident_going_out_is_not_answering_anyone(home):
    assert alerts(play(home, door(T0))) == []


def test_a_late_door_event_from_before_the_visitor_came_is_not_an_answer(home):
    # The resident came home at T0; the doorbell rang a minute later; the
    # door's webhook was delivered last.
    actions = play(home, ring(T0 + seconds(60)), door(T0))
    assert alerts(actions) == []


def test_door_webhook_arriving_before_the_ring_still_counts(home):
    # Webhooks are not ordered: the door opened 20 s after the ring, but its
    # delivery arrived first.
    actions = play(home, door(T0 + seconds(20)), ring(T0))
    assert alerts(actions, "answered")


# --------------------------------------------------------------------------- heightened watch


def test_courier_returning_two_days_later_alerts_before_the_door_opens(home):
    play(home, ring(T0), door(T0 + seconds(30)))
    rules.tick(home, T0 + timedelta(minutes=10))
    later = T0 + timedelta(days=2)
    actions = play(home, person(later), ring(later + seconds(3)))
    assert [a.reason for a in alerts(actions)] == ["heightened"]
    assert chimes(actions) == [rules.HEIGHTENED_REMINDER]


def test_heightened_visit_that_is_then_answered_is_told_twice(home):
    play(home, ring(T0), door(T0 + seconds(30)))
    later = T0 + timedelta(days=2)
    actions = play(home, ring(later), door(later + seconds(20)))
    assert [a.reason for a in alerts(actions)] == ["heightened", "answered"]


def test_heightened_watch_ends_after_seven_days(home):
    play(home, ring(T0), door(T0 + seconds(30)))
    later = T0 + timedelta(days=8)
    actions = play(home, ring(later))
    assert alerts(actions) == [] and chimes(actions) == [rules.REMINDER]


def test_no_heightened_watch_without_an_alert(home):
    play(home, ring(T0))
    rules.tick(home, T0 + timedelta(minutes=10))
    assert alerts(play(home, ring(T0 + timedelta(days=1)))) == []


# --------------------------------------------------------------------------- the door going blind


def test_doorbell_offline_during_an_unexpected_visit_is_said(home):
    actions = play(home, ring(T0), offline(T0 + seconds(20)))
    [alert] = alerts(actions)
    assert alert.reason == "blind" and alert.confidence is None


def test_doorbell_offline_with_nobody_there_is_not_an_alert(home):
    assert alerts(play(home, offline(T0))) == []
    assert home.doorbell_online is False


# --------------------------------------------------------------------------- the protection itself


def test_pause_tells_the_family_and_silences_the_door(home):
    [told] = rules.pause(home, T0 + timedelta(hours=3), T0)
    assert told.reason == "change" and told.recipients == ("sarah@example.com",)
    actions = play(home, ring(T0 + seconds(60)), door(T0 + seconds(80)))
    assert chimes(actions) == [] and alerts(actions) == []


def test_a_pause_cannot_outlast_a_day(home):
    rules.pause(home, T0 + timedelta(days=30), T0)
    assert not home.paused(T0 + timedelta(hours=25))
    assert chimes(play(home, ring(T0 + timedelta(hours=25)))) == [rules.REMINDER]


def test_adding_a_visit_for_today_tells_the_family(home):
    [told] = rules.add_visit(home, ExpectedVisit("repairman", [1], "16:00", "17:00"), T0)
    assert told.reason == "change" and "repairman" in told.detail


def test_adding_a_visit_for_next_week_is_not_an_alarm(home):
    [note] = rules.add_visit(home, ExpectedVisit("carer", [4], "10:00", "11:00"), T0)
    assert not isinstance(note, Alert)


def test_declaring_a_delivery_for_this_afternoon_tells_the_family(home):
    d = Delivery("UPS", "1Z999AA10123456784", iso(T0 + timedelta(hours=1)),
                 iso(T0 + timedelta(hours=3)))
    [told] = rules.add_delivery(home, d, T0)
    assert told.reason == "change"


def test_removing_someone_tells_them_too(home):
    home.trusted.append(Trusted("Tom", "tom@example.com"))
    [told] = rules.remove_trusted(home, "tom@example.com", T0)
    assert set(told.recipients) == {"sarah@example.com", "tom@example.com"}
    assert [t.email for t in home.trusted] == ["sarah@example.com"]


def test_switching_off_tells_the_family_and_the_door_goes_quiet(home):
    [told] = rules.switch_off(home, T0)
    assert told.recipients == ("sarah@example.com",)
    assert play(home, ring(T0 + seconds(5)))[0].text == "protection is off"


def test_nothing_happens_until_the_resident_switches_it_on(home):
    home.enabled = False
    actions = play(home, ring(T0), door(T0 + seconds(20)))
    assert chimes(actions) == [] and alerts(actions) == []
