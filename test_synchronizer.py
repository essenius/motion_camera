import unittest
import time as Time
from synchronizer import Synchronizer

class TestSynchronizer(unittest.TestCase):
    def test_synchronizer_initialization(self):
        DELTA = 0.002
        Synchronizer.set_rate(100)
        interval = Synchronizer.sampling_interval
        self.assertEqual(interval, 0.01)  # 100 Hz = 10 ms interval
        test_start_time = Time.time()
        start_time = Synchronizer.wait_for_next_sampling(None)
        self.assertAlmostEqual(start_time, test_start_time, delta=DELTA)
        # normal run, should give multiplier 1
        end_time1 = Synchronizer.wait_for_next_sampling(start_time)
        self.assertEqual(end_time1, start_time + interval)
        self.assertGreaterEqual(end_time1, start_time + interval)
        self.assertLess(end_time1, start_time + interval + DELTA)
        # force overrun, should give multiplier 1 and not wait
        end_time2 = Synchronizer.wait_for_next_sampling(start_time)
        self.assertLess(end_time2, start_time + interval + DELTA)

        # force overrun of over one sample, should give multiplier 2 and wait
        Time.sleep(0.01)
        end_time3 = Synchronizer.wait_for_next_sampling(start_time)
        test_end_time = Time.time()
        self.assertGreaterEqual(end_time3, start_time + 2 * interval)
        self.assertLess(end_time3, start_time + 2 * interval + DELTA)
        self.assertAlmostEqual(end_time3, test_end_time, delta=DELTA)
