"""Tests for the close-circle visual layout (no Tk window needed)."""
import math
import unittest
from app import seat_layout


class LayoutTests(unittest.TestCase):
    def test_host_at_bottom_and_ellipse_is_compact(self):
        cx,cy,rx,ry,r,spots=seat_layout(8,700,490)
        self.assertAlmostEqual(spots[0][0],cx)
        self.assertAlmostEqual(spots[0][1],cy+ry)
        self.assertAlmostEqual(rx/ry,1.16)
        self.assertEqual(len(spots),9)

    def test_left_one_appears_left_and_right_one_appears_right(self):
        cx,cy,rx,ry,r,spots=seat_layout(8,700,490)
        self.assertLess(spots[1][0],cx)
        self.assertGreater(spots[8][0],cx)
        self.assertAlmostEqual(spots[1][0]+spots[8][0],2*cx)
        self.assertAlmostEqual(spots[1][1],spots[8][1])

    def test_positions_fit_canvas_for_configurable_people(self):
        for people in (3,8,12,16):
            for w,h in ((580,430),(700,490),(960,700)):
                cx,cy,rx,ry,r,spots=seat_layout(people,w,h)
                self.assertEqual(len(spots),people+1)
                self.assertTrue(all(r<=x<=w-r and r<=y<=h-r
                                    for x,y in spots.values()))


if __name__=='__main__':
    unittest.main()
