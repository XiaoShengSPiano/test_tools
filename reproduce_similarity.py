
import sys
import os
import numpy as np
import pandas as pd
from typing import Optional, Tuple, Dict, Any, List

# Ensure we can import backend modules
sys.path.append(os.getcwd())

from backend.force_curve_analyzer import ForceCurveAnalyzer
from utils.logger import Logger

# Mock Note class to simulate the structure expected by ForceCurveAnalyzer
class MockNote:
    def __init__(self, key_on_ms: List[float], values: List[float], note_id: int):
        self.id = note_id
        # In the real code, key_on_ms is likely an array of times for the curve
        self.key_on_ms = np.array(key_on_ms)
        # Mocking the after_touch which has a .values attribute
        # We need an instance that has .values
        class MockSeries:
            def __init__(self, val):
                self.values = np.array(val)
                self.index = np.arange(len(val)) # Add index just in case
        
        self.after_touch = MockSeries(values)
        
        # Add basic attributes that might be checked
        self.velocity = 60
        self.hammers_val = np.array([])


def create_sine_wave(length=100, shift=0.0, scale=1.0, noise=0.0):
    x = np.linspace(0, 4*np.pi, length)
    y = np.sin(x + shift) * scale + noise
    # Normalize to 0-1 range roughly for force curve simulation (force is positive)
    y = y + 1.2 # Make all positive
    return x * 10, y # Time in ms, values

def main():
    logger = Logger.get_logger()
    logger.info("Starting reproduction script for similarity comparison")

    # Create two similar curves
    times1, values1 = create_sine_wave(length=100, shift=0.0)
    times2, values2 = create_sine_wave(length=100, shift=0.5, scale=0.9) # Slightly shifted and scaled

    note1 = MockNote(times1, values1, 1)
    note2 = MockNote(times2, values2, 2)

    print("\n--- Testing Existing ForceCurveAnalyzer ---")
    try:
        analyzer = ForceCurveAnalyzer()
    
        result = analyzer.compare_curves(note1, note2, record_note=note1, replay_note=note2)
        if result:
            print(f"Similarity Score: {result.get('overall_similarity', 'N/A')}")
            print(f"DTW Distance: {result.get('dtw_distance', 'N/A')}")
            if 'alignment_comparison' in result:
                print("Alignment comparison figure generated (mock success)")
        else:
            print("Comparison failed (returned None)")
    except Exception as e:
        print(f"Error executing compare_curves: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
