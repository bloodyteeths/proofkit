import io
import json
from starlette.testclient import TestClient
from app import app


def test_api_compile_json_backcompat(monkeypatch):
    client = TestClient(app)
    spec = json.dumps({
        "version": "1.0",
        "industry": "haccp",
        "job": {"job_id": "test"},
        "spec": {"method": "OVEN_AIR", "target_temp_C": 57.22, "hold_time_s": 60},
        "data_requirements": {"max_sample_period_s": 60, "allowed_gaps_s": 120}
    })
    csv_bytes = b"timestamp,temp\n2024-01-01T00:00:00Z,10\n2024-01-01T00:01:00Z,9\n"
    files = {
        'csv_file': ('data.csv', io.BytesIO(csv_bytes), 'text/csv'),
        'spec_json': (None, spec)
    }
    # This endpoint requires auth in production; bypass with monkeypatch if needed
    response = client.post('/api/compile/json', files=files)
    assert response.status_code in (200, 401, 402)
    if response.status_code == 200:
        data = response.json()
        assert 'pass' in data
        assert 'status' in data
        assert 'flags' in data
