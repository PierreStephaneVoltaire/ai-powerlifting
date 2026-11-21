import base64
from io import BytesIO
from types import SimpleNamespace

from openpyxl import load_workbook

from services.export.export_program_history import core


def test_selected_analysis_exports_render_actual_tables(monkeypatch):
    program = {
        "meta": {"program_name": "Demo", "current_block_id": "demo", "program_start": "2026-11-05", "height_cm": 181,
                 "blocks": [{"id": "demo", "status": "active", "start_date": "2026-11-05", "week_start_day": "Thursday"}]},
        "sessions": [{"block": "current", "block_id": "demo", "week_number": 1, "date": "2026-11-06", "completed": True,
                      "body_weight_kg": 84.123456789, "exercises": [
                          {"name": name, "kg": kg, "sets": 1, "reps": 3, "rpe": 9}
                          for name, kg in (("Squat", 180), ("Bench Press", 90), ("Deadlift", 198))
                      ]}],
        "diet_notes": [{"date": "2026-11-06", "avg_protein_g": 170, "avg_sleep_hours": 7.5, "consistent": True}],
    }
    weekly = {
        "week": 1, "window_start": "2026-11-05", "window_end": "2026-11-11", "sessions_analyzed": 1,
        "fatigue_index": 0.32, "readiness_score": {"score": 74, "zone": "yellow"},
        "compliance": {"planned": 1, "completed": 1, "pct": 100, "set_pct": 90},
        "lifts": {"squat": {"progression_rate_kg_per_week": 2.5}},
        "per_lift": {"squat": {"sets": 3, "accessories": [{"name": "Leg press", "sets": 2, "transfer": 0.5}]}},
        "exercise_stats": {"Squat": {"total_sets": 1, "total_volume": 540, "max_kg": 180}},
        "muscle_volume": {"muscles": {"quadriceps": {"weekly_sets": 8, "status": "productive"}}},
        "monotony_strain": {"weekly": [{"week_start": "2026-11-05", "monotony": 1.5, "strain": 42}]},
        "acwr": {"composite": 1.1, "dimensions": {"axial": {"value": 1.2}}},
        "fatigue_dimensions": {"weekly": {"2026-11-05": {"axial": 18}}},
        "inol": {"lifts": {"squat": {"adjusted": 1.25, "raw": 1.0}}},
        "ri_distribution": {"overall": {"heavy": {"count": 2, "pct": 50}}},
        "specificity_ratio": {"narrow": 0.61, "broad": 0.74},
        "volume_landmarks": {"squat": {"mev": 4, "mrv": 12, "confidence": "medium"}},
        "banister": {"series": [{"date": "2026-11-06", "ctl": 5, "atl": 7, "tsb": -2}]},
        "peaking_timeline": {"status_label": "On track", "series": [{"date": "2026-11-13", "projected_tsb": 6.1}]},
        "decoupling": {"series": [{"week_start": "2026-11-05", "decoupling": 0.42}]},
        "taper_quality": {"score": 80, "label": "good"},
        "projections": [{"comp_name": "Demo meet", "total": 530, "confidence": 0.72}],
        "alerts": [{"severity": "caution", "source": "acwr", "message": "Track axial load", "raw_detail": "Axial ratio 1.2"}],
    }

    async def read_program(store, args):
        return program

    monkeypatch.setattr(core, "_get_store", lambda args: SimpleNamespace(pk=args["pk"]))
    monkeypatch.setattr(core, "_read_program", read_program)
    monkeypatch.setattr(core, "_build_analysis_bundle", lambda *args, **kwargs: {
        "weekly": weekly, "weight_log": [{"date": "2026-11-05", "kg": 85.123456789}, {"date": "2026-11-06", "kg": 86}],
        "correlation": {"summary": "Cached exercise correlation"},
        "program_evaluation": {"summary": "Cached program evaluation"},
    })
    selection = {"pk": "test-athlete", "week_start": 1, "week_end": 1, "window_start": "2026-11-05", "window_end": "2026-11-11"}

    def download(format_name):
        return base64.b64decode(core.export_program_history({**selection, "format": format_name})["content_base64"])

    markdown = download("markdown").decode()
    workbook = load_workbook(BytesIO(download("xlsx")), read_only=True)
    for table in ("Readiness", "Accessory Workload", "Muscle Volume", "Foster Monotony and Strain", "EWMA ACWR",
                  "Fatigue Dimensions", "Stimulus-Adjusted INOL", "Relative Intensity", "Specificity", "Volume Landmarks",
                  "Banister Fitness and Fatigue", "Peaking Timeline", "Fatigue Decoupling", "Taper Quality", "Meet Projections",
                  "Analysis Alerts", "Weekly Nutrition and Sleep", "Athlete Measurements"):
        assert f"### {table}\n" in markdown
        assert table in workbook.sheetnames
    assert "| 2026-11-06 | 84.12 | -1.0 |" in markdown
    assert "84.123456789" not in markdown and "85.123456789" not in markdown
    assert "Cached exercise correlation" in markdown and "Cached program evaluation" in markdown
    assert "| W1 | 200.0 | 100.0 | 220.0 | 520.0 | 84.12 |" in markdown
    assert "| Classic |" in markdown
    assert list(workbook["Weekly Nutrition and Sleep"].values)[1][:3] == ("2026-11-05", None, 170)
    assert any(row[:6] == (1, 200, 100, 220, 520, 84.12) and row[8] == "Classic" for row in workbook["Trends"].values)
