class MedianCalculatorFactoryImpl:
    def __init__(self, strategy_provider=None):
        self._strategy_provider = strategy_provider or (lambda: None)
    def create(self):
        return _MedianCalculator(self._strategy_provider())

class _MedianCalculator:
    def __init__(self, strategy):
        self.strategy = strategy
    def calculate(self, values):
        ordered = sorted(values)
        mid = len(ordered) // 2
        return ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2
