import math
import time
from config import ONE_EURO_MIN_CUTOFF, ONE_EURO_BETA, ONE_EURO_DERIVATIVE_CUTOFF

class OneEuroFilter:
    def __init__(self, t0, x0, dx0=0.0, min_cutoff=ONE_EURO_MIN_CUTOFF, beta=ONE_EURO_BETA, d_cutoff=ONE_EURO_DERIVATIVE_CUTOFF):
        """
        Initialize the One Euro Filter.
        """
        self.min_cutoff = float(min_cutoff)
        self.beta = float(beta)
        self.d_cutoff = float(d_cutoff)
        self.x_prev = float(x0)
        self.dx_prev = float(dx0)
        self.t_prev = float(t0)

    def smoothing_factor(self, t_e, cutoff):
        r = 2 * math.pi * cutoff * t_e
        return r / (r + 1)

    def exponential_smoothing(self, a, x, x_prev):
        return a * x + (1 - a) * x_prev

    def filter(self, t, x):
        """
        Compute the filtered signal.
        """
        t_e = t - self.t_prev

        if t_e <= 0.0:
            return self.x_prev

        # The filtered derivative of the signal.
        a_d = self.smoothing_factor(t_e, self.d_cutoff)
        dx = (x - self.x_prev) / t_e
        dx_hat = self.exponential_smoothing(a_d, dx, self.dx_prev)

        # The filtered signal.
        cutoff = self.min_cutoff + self.beta * abs(dx_hat)
        a = self.smoothing_factor(t_e, cutoff)
        x_hat = self.exponential_smoothing(a, x, self.x_prev)

        self.x_prev = x_hat
        self.dx_prev = dx_hat
        self.t_prev = t

        return x_hat

class Stabilizer:
    def __init__(self):
        self.filter_x = None
        self.filter_y = None
    
    def update(self, measurement):
        """
        measurement: (x, y)
        """
        if measurement is None:
            return None
        
        t = time.time()
        x, y = measurement
        
        if self.filter_x is None:
            self.filter_x = OneEuroFilter(t, x)
            self.filter_y = OneEuroFilter(t, y)
            return (x, y)
        
        start = time.time() # To ensure we don't pass duplicate timestamps if called super fast?
        # Actually OneEuro expects monotonic time.
        
        smoothed_x = self.filter_x.filter(t, x)
        smoothed_y = self.filter_y.filter(t, y)
        
        return (smoothed_x, smoothed_y)
