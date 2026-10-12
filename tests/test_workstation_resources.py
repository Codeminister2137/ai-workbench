"""Windows snapshot contracts: unavailable is distinct from idle; no inference."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows CIM snapshot")
SCRIPT = Path(__file__).resolve().parents[1] / "scripts/workstation-resources.ps1"


def snapshot(memory_free="4", cpu="25", engines="40,30,20"):
    command = f"""
. '{SCRIPT.as_posix()}'
$values = @({engines})
$rows = @(
    [pscustomobject]@{{Name='pid_1_luid_0_phys_0_eng_0_engtype_3D';
                      UtilizationPercentage=$values[0]}},
    [pscustomobject]@{{Name='pid_2_luid_0_phys_0_eng_0_engtype_3D';
                      UtilizationPercentage=$values[1]}},
    [pscustomobject]@{{Name='pid_3_luid_0_phys_0_eng_1_engtype_Copy';
                      UtilizationPercentage=$values[2]}}
)
ConvertTo-ResourceSnapshot @{{
    cpu=@{{available=$true;rows=@([pscustomobject]@{{Name='_Total';PercentProcessorTime={cpu}}})}}
    memory=@{{available=$true;rows=@([pscustomobject]@{{TotalVisibleMemorySize=8;FreePhysicalMemory={memory_free}}})}}
    gpu_memory=@{{available=$false;rows=@()}}
    gpu_engines=@{{available=$true;rows=$rows}}
}} | ConvertTo-Json -Depth 4 -Compress
"""
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True,
        text=True,
        timeout=20,
        check=True,
    )
    return json.loads(result.stdout)


@pytest.mark.parametrize("engines", ("0,$null,0", "0,101,0", "0,[double]::NaN,0"))
def test_invalid_engine_does_not_turn_partial_idle_counters_into_available_gpu(engines):
    result = snapshot(engines=engines)
    assert result["gpu_busiest_engine_percent_estimate"] is None
    assert "gpu_engines" in result["unavailable"]


def test_snapshot_units_engine_aggregation_and_private_instance_omission():
    result = snapshot()
    assert result["memory_total_bytes"] == 8192
    assert result["memory_available_bytes"] == 4096
    assert result["cpu_busy_percent"] == 25
    assert result["gpu_busiest_engine_percent_estimate"] == 70
    assert result["gpu_dedicated_available_bytes"] is None
    assert result["gpu_dedicated_used_bytes"] is None
    assert "gpu_memory" in result["unavailable"]
    assert "pid_" not in json.dumps(result)


@pytest.mark.parametrize("free,cpu", [("$null", "$null"), ("9", "101"), ("-1", "-1")])
def test_invalid_or_missing_data_is_not_reported_as_available(free, cpu):
    result = snapshot(memory_free=free, cpu=cpu)
    assert result["memory_available_bytes"] is None
    assert result["cpu_busy_percent"] is None
    assert {"memory", "cpu_busy"} <= set(result["unavailable"])


def test_actual_idle_zero_remains_distinct_from_unknown():
    result = snapshot(memory_free="0", cpu="0", engines="0,0,0")
    assert result["memory_available_bytes"] == 0
    assert result["cpu_busy_percent"] == 0
    assert result["gpu_busiest_engine_percent_estimate"] == 0
    assert "cpu_busy" not in result["unavailable"]


def test_gpu_engines_same_engine_clamped_to_100():
    result = snapshot(engines="60,60,0")
    assert result["gpu_busiest_engine_percent_estimate"] == 100


def test_gpu_engine_invalid_negative_does_not_avail_when_others_valid():
    result = snapshot(engines="0,-1,0")
    assert result["gpu_busiest_engine_percent_estimate"] is None
    assert "gpu_engines" in result["unavailable"]


def test_gpu_engine_invalid_infinite_does_not_avail_when_others_valid():
    result = snapshot(engines="0,[double]::PositiveInfinity,0")
    assert result["gpu_busiest_engine_percent_estimate"] is None
    assert "gpu_engines" in result["unavailable"]
