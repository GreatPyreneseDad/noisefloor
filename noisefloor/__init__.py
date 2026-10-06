"""noisefloor — measure an LLM judge's retest variance before trusting its deltas."""
from .stats import Comparison, Flips, Retest, compare, draws_needed, flips, retest
from .runner import measure, run_command, load_log, group_scores, group_labels

__version__ = "0.1.0"
__all__ = ["Comparison", "Flips", "Retest", "compare", "draws_needed", "flips", "retest",
           "measure", "run_command", "load_log", "group_scores", "group_labels"]
