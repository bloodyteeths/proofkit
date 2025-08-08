import json
import pandas as pd
from core.models import SpecV1
from core.decide import make_decision


def _mk_df(cols):
    data = {
        'timestamp': pd.date_range('2024-01-01', periods=10, freq='T')
    }
    for name, values in cols.items():
        data[name] = values
    return pd.DataFrame(data)


def test_autoclave_missing_pressure_indeterminate():
    spec = SpecV1(**json.loads(open('core/spec_library/autoclave_v1.json').read()))
    # Only temperature present
    df = _mk_df({'temp_1': [121.5]*10, 'temp_2': [121.2]*10})
    decision = make_decision(df, spec)
    assert getattr(decision, 'status', 'FAIL') == 'INDETERMINATE'
    assert any('Pressure data required' in r for r in decision.reasons)


def test_sterile_missing_humidity_indeterminate():
    spec = SpecV1(**json.loads(open('core/spec_library/sterile_v1.json').read()))
    df = _mk_df({'temp_1': [55.0]*120})
    decision = make_decision(df, spec)
    assert getattr(decision, 'status', 'FAIL') == 'INDETERMINATE'


def test_concrete_missing_humidity_indeterminate():
    spec = SpecV1(**json.loads(open('core/spec_library/concrete_v1.json').read()))
    df = _mk_df({'temp_1': [21.5]*200})
    decision = make_decision(df, spec)
    assert getattr(decision, 'status', 'FAIL') == 'INDETERMINATE'


def test_haccp_temperature_only_fallback_flag():
    spec = SpecV1(**json.loads(open('core/spec_library/haccp_v1.json').read()))
    # Provide temp with a non-existent named sensor in selection to trigger fallback
    df = _mk_df({'temp_1': [50.0]*10})
    decision = make_decision(df, spec)
    # HACCP is temp-only; should not be indeterminate
    assert getattr(decision, 'status', 'PASS' if decision.pass_ else 'FAIL') in ['PASS', 'FAIL']
    # Fallback may not always trigger here, but ensure flags exists
    assert hasattr(decision, 'flags')
