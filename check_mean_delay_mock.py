
import sys
import os
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Mock classes to simulate the structure
class NoteMatcher:
    def __init__(self):
        self._mean_error_cached = None
        self.matched_pairs = [(1, 1, "note1", "note2")] # Mock matched pairs
    
    def get_mean_error(self):
        return 123.45 # Mock value (0.1ms unit)

class SPMIDAnalyzer:
    def __init__(self):
        self.note_matcher = NoteMatcher()
    
    def get_mean_error(self):
        if self.note_matcher:
            return self.note_matcher.get_mean_error()
        return 0.0

class PianoAnalysisBackend:
    def __init__(self):
        self.analyzer = SPMIDAnalyzer()
        self.multi_algorithm_mode = True
    
    def test_logic(self):
        mean_delay = 0.0
        if self.analyzer:
            mean_error_0_1ms = self.analyzer.get_mean_error()
            print(f"DEBUG: mean_error_0_1ms = {mean_error_0_1ms}")
            if mean_error_0_1ms is not None:
                mean_delay = mean_error_0_1ms / 10.0
        
        print(f"Calculated mean_delay: {mean_delay}ms")

if __name__ == "__main__":
    backend = PianoAnalysisBackend()
    backend.test_logic()

