# Make spmid a package and expose key modules
from .types import *           # noqa: F401,F403
from .spmid_analyzer import *  # noqa: F401,F403
from .spmid_reader import *    # noqa: F401,F403
from .spmid_plot import *      # noqa: F401,F403

# Export new component classes
from .data_filter import DataFilter
from .time_aligner import TimeAligner
from .note_matcher import NoteMatcher
from .error_detector import ErrorDetector
from .dtw_aligner import DTWAligner

