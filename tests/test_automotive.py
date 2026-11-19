"""In-vehicle multi-chip placement: declared chip specs, never real automotive silicon."""
import pytest

from spatial.automotive import Chip, PlacementError, Task, makespan_s, place, total_energy_j


def test_single_task_single_chip():
    chips = (Chip("mcu", flops_per_s=1e9, power_w=5.0),)
    out = place((Task("camera_isp", flops=1e9),), chips)
    assert len(out) == 1 and out[0].chip == "mcu" and out[0].start_s == 0.0
    assert out[0].finish_s == pytest.approx(1.0)


def test_cheaper_faster_chip_wins_when_both_eligible():
    mcu = Chip("mcu", flops_per_s=1e9, power_w=5.0)
    soc = Chip("soc", flops_per_s=1e10, power_w=20.0)
    out = place((Task("detect", flops=1e10),), (mcu, soc))
    assert out[0].chip == "soc"           # finishes in 1s on soc vs 10s on mcu


def test_npu_only_task_goes_to_npu_chip_even_if_slower():
    mcu = Chip("mcu", flops_per_s=1e10, power_w=5.0, supports_npu=False)
    npu = Chip("npu", flops_per_s=1e9, power_w=15.0, supports_npu=True)
    out = place((Task("segment", flops=1e9, needs_npu=True),), (mcu, npu))
    assert out[0].chip == "npu"


def test_no_eligible_chip_raises():
    mcu = Chip("mcu", flops_per_s=1e9, power_w=5.0, supports_npu=False)
    with pytest.raises(PlacementError, match="needs_npu"):
        place((Task("segment", flops=1e9, needs_npu=True),), (mcu,))


def test_dependency_order_respected_across_two_chips():
    mcu = Chip("mcu", flops_per_s=1e9, power_w=5.0)
    soc = Chip("soc", flops_per_s=1e9, power_w=5.0)
    tasks = (
        Task("camera_isp", flops=1e9),
        Task("sensor_fusion", flops=1e9, after=("camera_isp",)),
        Task("path_planning", flops=1e9, after=("sensor_fusion",)),
    )
    out = place(tasks, (mcu, soc))
    by_name = {p.task: p for p in out}
    assert by_name["camera_isp"].finish_s <= by_name["sensor_fusion"].start_s
    assert by_name["sensor_fusion"].finish_s <= by_name["path_planning"].start_s
    assert makespan_s(out) == pytest.approx(3.0)


def test_unknown_dependency_raises():
    with pytest.raises(PlacementError, match="unknown task"):
        place((Task("a", flops=1.0, after=("missing",)),), (Chip("c", 1.0, 1.0),))


def test_dependency_cycle_raises():
    tasks = (Task("a", flops=1.0, after=("b",)), Task("b", flops=1.0, after=("a",)))
    with pytest.raises(PlacementError, match="cycle"):
        place(tasks, (Chip("c", 1.0, 1.0),))


def test_duplicate_task_name_raises():
    with pytest.raises(PlacementError, match="duplicate"):
        place((Task("a", flops=1.0), Task("a", flops=2.0)), (Chip("c", 1.0, 1.0),))


def test_empty_chip_catalogue_raises():
    with pytest.raises(PlacementError, match="empty"):
        place((Task("a", flops=1.0),), ())


def test_total_energy_is_power_times_busy_time_summed_per_chip():
    mcu = Chip("mcu", flops_per_s=1e9, power_w=10.0)
    out = place((Task("a", flops=1e9), Task("b", flops=2e9, after=("a",))), (mcu,))
    assert total_energy_j(out, (mcu,)) == pytest.approx(10.0 * 3.0)   # 3s busy at 10W


def test_cli_automotive_runs_a_sample_catalogue(tmp_path, capsys):
    import json
    from spatial.cli import main
    cat = {
        "chips": [
            {"name": "mcu", "flops_per_s": 4e9, "power_w": 5.0},
            {"name": "npu", "flops_per_s": 2e9, "power_w": 15.0, "supports_npu": True},
        ],
        "tasks": [
            {"name": "camera_isp", "flops": 1e9},
            {"name": "segment", "flops": 2e9, "needs_npu": True, "after": ["camera_isp"]},
        ],
    }
    f = tmp_path / "vehicle.json"
    f.write_text(json.dumps(cat))
    assert main(["automotive", "--file", str(f)]) == 0
    out = capsys.readouterr().out
    assert "camera_isp -> mcu" in out and "segment -> npu" in out and "makespan" in out


def test_cli_automotive_reports_placement_error_cleanly(tmp_path, capsys):
    import json
    from spatial.cli import main
    cat = {"chips": [{"name": "mcu", "flops_per_s": 1e9, "power_w": 5.0}],
           "tasks": [{"name": "segment", "flops": 1e9, "needs_npu": True}]}
    f = tmp_path / "vehicle.json"
    f.write_text(json.dumps(cat))
    assert main(["automotive", "--file", str(f)]) == 1
    assert "PlacementError" in capsys.readouterr().err
