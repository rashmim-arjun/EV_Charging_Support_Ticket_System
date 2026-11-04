"""Optional frozen bin calibration fitted on a separate synthetic development seed."""
import json
from pathlib import Path

CALIBRATION_PATH = Path(__file__).resolve().parents[1] / 'config' / 'calibration.json'


def calibration_metadata():
    if CALIBRATION_PATH.exists():
        return json.loads(CALIBRATION_PATH.read_text(encoding='utf-8'))
    return None


def calibrated_confidence(strength, asserted=True):
    if not asserted:
        return None
    model = calibration_metadata()
    if not model:
        return None
    for row in model['bins']:
        if strength <= row['upper']:
            return row['probability']
    return model['bins'][-1]['probability']
