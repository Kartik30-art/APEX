import json

from apex import train_forex


def test_download_only_collects_history_without_training(monkeypatch, tmp_path, capsys):
    rows = [{"timestamp": "2024-01-01T00:00:00+00:00"}]
    monkeypatch.setattr(
        train_forex, "fetch_yahoo_history",
        lambda symbol, period, interval: rows,
    )

    def fake_save_history(bars, output_path, **kwargs):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("csv-placeholder")
        return {"row_count": len(bars), "interval": kwargs["interval"]}

    monkeypatch.setattr(train_forex, "save_history", fake_save_history)
    monkeypatch.setattr(
        train_forex, "train_model",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("training must be skipped")),
    )

    result = train_forex.main([
        "--symbol", "EURUSD=X",
        "--period", "10y",
        "--interval", "1d",
        "--data-dir", str(tmp_path / "data"),
        "--model-dir", str(tmp_path / "models"),
        "--download-only",
    ])
    output = json.loads(capsys.readouterr().out)
    assert result == 0
    assert output["dataset"]["row_count"] == 1
    assert (tmp_path / "data" / "EURUSD_X_1d.csv").exists()
    assert not (tmp_path / "models" / "EURUSD_X_1d.json").exists()
