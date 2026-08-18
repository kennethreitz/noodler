import math

import pytest

from noodler.motion import (
    CRITICAL_DAMPING_CONSTANT,
    Glide,
    KnobDrag,
    MAX_TIMESTEP,
    MeterBallistics,
    PointerTracker,
    Spring,
    advance_spring,
    clamp_timestep,
    drag_gain,
    glide,
    pixel_spring,
    smoothstep,
    unit_spring,
)


def _run(spring: Spring, seconds: float, frame_rate: float) -> Spring:
    """Advance a spring over exactly ``seconds`` at one display refresh rate.

    The final frame is shortened rather than rounded, so refresh rates that do
    not divide the duration still compare over identical wall-clock time.
    """
    remaining = seconds
    step = 1.0 / frame_rate
    while remaining > 0.0:
        spring.advance(min(step, remaining))
        remaining -= step
    return spring


def test_the_damping_constant_really_is_the_half_life_root() -> None:
    u = CRITICAL_DAMPING_CONSTANT
    assert (1.0 + u) * math.exp(-u) == pytest.approx(0.5, abs=1e-12)


def test_a_spring_covers_half_its_distance_in_one_half_life() -> None:
    spring = Spring(value=0.0, target=100.0, half_life=0.1, settle_distance=0.0)
    _run(spring, seconds=0.1, frame_rate=1_000.0)
    assert spring.value == pytest.approx(50.0, abs=0.05)


def test_settling_does_not_depend_on_the_display_refresh_rate() -> None:
    """The instrument must feel identical on 60 Hz and 120 Hz panels.

    This is the property a per-frame easing fraction cannot have: the same
    ``value += (target - value) * 0.24`` settles twice as fast at 120 Hz.
    """
    settled = [
        _run(
            Spring(value=0.0, target=420.0, half_life=0.11, settle_distance=0.0),
            seconds=0.25,
            frame_rate=rate,
        ).value
        for rate in (30.0, 60.0, 120.0, 144.0, 240.0)
    ]
    for value in settled:
        assert value == pytest.approx(settled[0], rel=0.005)


def test_settling_survives_a_jittery_frame_clock() -> None:
    """Real frame times are uneven; motion must not be."""
    steady = _run(
        Spring(value=0.0, target=1.0, half_life=0.09, settle_distance=0.0),
        seconds=0.3,
        frame_rate=240.0,
    )
    jittery = Spring(value=0.0, target=1.0, half_life=0.09, settle_distance=0.0)
    elapsed = 0.0
    step = 1.0 / 240.0
    index = 0
    while elapsed < 0.3:
        # A repeating uneven cadence, averaging the same 240 Hz.
        dt = min(step * (0.25 + 1.5 * (index % 3)), 0.3 - elapsed)
        if dt <= 0.0:
            break
        jittery.advance(dt)
        elapsed += dt
        index += 1
    assert jittery.value == pytest.approx(steady.value, rel=0.01)


def test_a_critically_damped_spring_never_overshoots_from_rest() -> None:
    spring = Spring(value=0.0, target=1.0, half_life=0.08, settle_distance=0.0)
    previous = spring.value
    for _ in range(600):
        current = spring.advance(1.0 / 120.0)
        assert current >= previous - 1e-12, "motion reversed"
        assert current <= 1.0 + 1e-9, "overshot the target"
        previous = current


def test_a_frame_hitch_cannot_launch_a_module_across_the_rack() -> None:
    spring = Spring(value=0.0, target=50.0, half_life=0.1)
    spring.advance(4.0)
    assert 0.0 <= spring.value <= 50.0
    assert math.isfinite(spring.velocity)


def test_a_spring_settles_exactly_rather_than_asymptotically() -> None:
    spring = Spring(value=0.0, target=17.0, half_life=0.05)
    _run(spring, seconds=1.0, frame_rate=120.0)
    assert spring.settled
    assert spring.value == 17.0
    assert spring.velocity == 0.0


def test_a_retarget_keeps_the_velocity_it_already_had() -> None:
    spring = Spring(value=0.0, target=100.0, half_life=0.1, settle_distance=0.0)
    _run(spring, seconds=0.05, frame_rate=120.0)
    moving = spring.velocity
    assert moving > 0.0
    spring.retarget(200.0)
    assert spring.velocity == moving


def test_snap_cancels_motion_in_progress() -> None:
    spring = Spring(value=0.0, target=100.0, half_life=0.1)
    spring.advance(1.0 / 60.0)
    assert spring.snap() == 100.0
    assert spring.velocity == 0.0
    assert spring.snap(3.0) == 3.0
    assert spring.target == 3.0


def test_a_zero_half_life_arrives_immediately() -> None:
    assert advance_spring(0.0, 5.0, 9.0, 1.0 / 60.0, 0.0) == (9.0, 0.0)


@pytest.mark.parametrize("dt", [0.0, -1.0, float("nan"), float("inf")])
def test_an_unusable_timestep_freezes_motion_instead_of_breaking_it(dt: float) -> None:
    assert clamp_timestep(dt) == 0.0
    spring = Spring(value=2.0, target=8.0, half_life=0.1)
    assert spring.advance(dt) == 2.0


def test_a_long_frame_is_clamped_not_believed() -> None:
    assert clamp_timestep(1.0) == MAX_TIMESTEP
    assert clamp_timestep(0.008) == pytest.approx(0.008)


def test_smoothstep_is_flat_at_both_edges() -> None:
    assert smoothstep(0.0, 1.0, -1.0) == 0.0
    assert smoothstep(0.0, 1.0, 2.0) == 1.0
    assert smoothstep(0.0, 1.0, 0.5) == pytest.approx(0.5)
    assert smoothstep(1.0, 1.0, 1.0) == 1.0


def test_a_flick_loses_half_its_speed_every_half_life() -> None:
    # Integrated over real frames: a single 0.32 s step is the implausible
    # frame that clamp_timestep exists to refuse.
    velocity = 1_000.0
    elapsed = 0.0
    while elapsed < 0.32:
        velocity = glide(velocity, 1.0 / 240.0, 0.32)
        elapsed += 1.0 / 240.0
    assert velocity == pytest.approx(500.0, rel=0.01)

    assert glide(1_000.0, 0.0, 0.32) == 1_000.0
    assert glide(1_000.0, 0.32, 0.0) == 0.0
    assert glide(1_000.0, 1.0, 0.32) == pytest.approx(
        glide(1_000.0, MAX_TIMESTEP, 0.32)
    ), "a long frame must be clamped, not believed"


def test_a_released_pan_travels_further_at_any_frame_rate() -> None:
    distances = []
    for rate in (60.0, 240.0):
        momentum = Glide(half_life=0.3, minimum_speed=1.0)
        momentum.release(1_200.0)
        travelled = 0.0
        for _ in range(round(2.0 * rate)):
            travelled += momentum.advance(1.0 / rate)
        distances.append(travelled)
    assert distances[0] == pytest.approx(distances[1], rel=0.02)


def test_a_glide_below_its_minimum_speed_stops_dead() -> None:
    momentum = Glide(velocity=1.0, minimum_speed=8.0)
    assert not momentum.moving
    assert momentum.advance(1.0 / 60.0) == 0.0
    assert momentum.velocity == 0.0


def test_pointer_speed_is_smoothed_toward_the_real_rate() -> None:
    tracker = PointerTracker(half_life=0.05)
    for _ in range(200):
        tracker.sample(10.0, 1.0 / 100.0)
    assert tracker.speed == pytest.approx(1_000.0, rel=0.01)
    assert tracker.sample(0.0, 0.0) == tracker.speed


def test_a_slow_drag_resolves_finer_than_a_fast_one() -> None:
    crawling = drag_gain(0.0)
    sweeping = drag_gain(5_000.0)
    assert crawling < drag_gain(700.0) < sweeping
    assert drag_gain(0.0, fine=True) < crawling


def test_a_knob_needs_nominal_travel_for_its_full_range() -> None:
    knob = KnobDrag(travel_pixels=180.0)
    knob.begin(0.0)
    # One steady sweep upward, fast enough to be treated as a coarse gesture.
    for _ in range(60):
        knob.advance(-30.0, 1.0 / 60.0)
    assert knob.position == 1.0

    knob.begin(0.5)
    for _ in range(10):
        knob.advance(1.0, 1.0 / 60.0, fine=True)
    assert knob.position < 0.5
    assert knob.position == pytest.approx(0.5, abs=0.01)


def test_a_knob_cannot_be_dragged_past_its_own_range() -> None:
    knob = KnobDrag(minimum=-1.0, maximum=1.0)
    knob.begin(5.0)
    assert knob.position == 1.0
    for _ in range(200):
        knob.advance(50.0, 1.0 / 60.0)
    assert knob.position == -1.0


def test_the_meter_rises_instantly_and_falls_on_a_known_slope() -> None:
    meter = MeterBallistics(release_half_life=0.25)
    assert meter.advance(0.8, 1.0 / 60.0) == 0.8

    elapsed = 0.0
    while elapsed < 0.25:
        meter.advance(0.0, 1.0 / 240.0)
        elapsed += 1.0 / 240.0
    assert meter.level == pytest.approx(0.4, rel=0.02)


def test_the_meter_holds_a_transient_above_the_falling_bar() -> None:
    meter = MeterBallistics(peak_hold_seconds=1.0)
    meter.advance(0.9, 1.0 / 60.0)
    for _ in range(30):
        meter.advance(0.1, 1.0 / 60.0)
    assert meter.peak == 0.9
    assert meter.level < 0.9

    for _ in range(240):
        meter.advance(0.1, 1.0 / 60.0)
    assert meter.peak < 0.9
    assert meter.peak >= meter.level

    meter.reset()
    assert (meter.level, meter.peak) == (0.0, 0.0)


def test_the_meter_ignores_a_broken_sample() -> None:
    meter = MeterBallistics()
    meter.advance(0.5, 1.0 / 60.0)
    assert meter.advance(float("nan"), 1.0 / 60.0) <= 0.5
    assert meter.advance(-3.0, 1.0 / 60.0) >= 0.0


def test_a_pixel_spring_settles_below_a_visible_distance() -> None:
    spring = pixel_spring(0.0)
    spring.retarget(400.0)
    elapsed = 0.0
    while not spring.settled and elapsed < 5.0:
        spring.advance(1.0 / 120.0)
        elapsed += 1.0 / 120.0
    assert spring.value == 400.0
    assert elapsed < 0.5, "a rack move should land in well under half a second"


def test_a_unit_spring_does_not_swallow_the_zoom_range() -> None:
    """A pixel-scale settle threshold would make any zoom change instant."""
    spring = unit_spring(1.0)
    spring.retarget(1.65)
    spring.advance(1.0 / 120.0)
    assert not spring.settled
    assert 1.0 < spring.value < 1.65
