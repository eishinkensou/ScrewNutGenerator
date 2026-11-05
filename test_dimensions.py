# -*- coding: utf-8 -*-
"""Plain-Python tests for the Fusion-independent part of ScrewNutGenerator.
Run:  python test_dimensions.py
"""
import importlib.util
import math
import os
import unittest

_here = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location('sng', os.path.join(_here, 'ScrewNutGenerator.py'))
sng = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sng)

CHECK_SIZES = ['M3', 'M8', 'M20']


class TableTests(unittest.TestCase):
    def test_required_sizes_x_heads_complete(self):
        for size in CHECK_SIZES:
            self.assertIn(size, sng.PITCH)
            self.assertIn(size, sng.NUT)
            for k in sng.NUT_REQUIRED_KEYS:
                self.assertGreater(sng.NUT[size][k], 0, (size, 'nut', k))
            for head in sng.HEAD_TYPES:
                self.assertIn(size, sng.HEAD[head], (size, head))
                h = sng.HEAD[head][size]
                for k in sng.HEAD_REQUIRED_KEYS[head]:
                    self.assertIn(k, h, (size, head, k))
                    self.assertGreater(h[k], 0, (size, head, k))
                self.assertIn('std', h, (size, head))

    def test_all_sizes_all_heads_complete(self):
        for size in sng.SIZES:
            for head in sng.HEAD_TYPES:
                h = sng.HEAD[head][size]
                for k in sng.HEAD_REQUIRED_KEYS[head]:
                    self.assertGreater(h.get(k, 0), 0, (size, head, k))

    def test_geometry_sanity(self):
        for size in sng.SIZES:
            d = sng.nominal_diameter(size)
            for head in sng.HEAD_TYPES:
                h = sng.HEAD[head][size]
                if head == 'Hex':
                    self.assertGreater(h['s'], d, (size, head))
                    continue
                self.assertGreater(h['dk'], d, (size, head))
                self.assertLess(h['t'], h['k'], (size, head))
                # socket (across corners) must fit inside head and leave a wall
                self.assertLess(h['ss'] * 2 / math.sqrt(3), h['dk'], (size, head))
                if head == 'CSK':  # 90 deg: k = (dk - d) / 2
                    self.assertAlmostEqual(h['k'], (h['dk'] - d) / 2, places=2, msg=size)
            self.assertGreater(sng.NUT[size]['s'], d, size)
            self.assertLess(sng.internal_minor_diameter(size), d)

    def test_known_values(self):
        self.assertEqual(sng.PITCH['M8'], 1.25)
        self.assertEqual(sng.HEAD['Allen']['M8'], {'dk': 13.0, 'k': 8.0, 'ss': 6.0, 't': 4.0, 'std': True})
        self.assertEqual(sng.NUT['M20'], {'s': 30.0, 'm': 18.0})
        self.assertAlmostEqual(sng.internal_minor_diameter('M8'), 6.647, places=3)


class ValidationTests(unittest.TestCase):
    def test_defaults_ok(self):
        for size in ['M4', 'M8', 'M20']:
            for head in sng.HEAD_TYPES:
                e, _ = sng.validate('both', size, head, 25, 0.25, 0.0)
                self.assertEqual(e, [], (size, head, e))

    def test_check_matrix_runs(self):
        # M3/M8/M20 x 4 heads with a small clearance must all validate
        for size in CHECK_SIZES:
            for head in sng.HEAD_TYPES:
                e, _ = sng.validate('both', size, head, 25, 0.1, 0.0)
                self.assertEqual(e, [], (size, head, e))

    def test_estimated_size_warns(self):
        _, w = sng.validate('bolt', 'M20', 'Button', 30, 0.25, 0.0)
        self.assertTrue(any('推定' in x for x in w))

    def test_too_short(self):
        e, _ = sng.validate('bolt', 'M8', 'Allen', 2, 0.25, 0.0)
        self.assertTrue(e)
        e, _ = sng.validate('bolt', 'M8', 'CSK', 4, 0.25, 0.0)  # CSK k=4.96 > 4
        self.assertTrue(e)

    def test_clearance_range_and_depth(self):
        self.assertTrue(sng.validate('nut', 'M8', 'Allen', 25, 1.1, 0)[0])   # out of range
        self.assertTrue(sng.validate('nut', 'M8', 'Allen', 25, 0.7, 0)[0])   # >= H1 0.677
        self.assertTrue(sng.validate('nut', 'M8', 'Allen', 25, -0.1, 0)[0])
        self.assertTrue(sng.validate('nut', 'M2', 'Allen', 25, 0.25, 0)[0])  # >= H1
        e, w = sng.validate('nut', 'M3', 'Allen', 25, 0.25, 0)
        self.assertEqual(e, [])
        self.assertTrue(w)  # > 0.7 H1 (0.19)
        # nut-only: external clearance ignored for depth check
        self.assertEqual(sng.validate('nut', 'M3', 'Allen', 25, 0.1, 0.5)[0], [])

    def test_conversions(self):
        self.assertAlmostEqual(sng.face_offset_for_clearance(0.25), 0.125)
        self.assertAlmostEqual(sng.axial_shift_for_clearance(0.25), 0.25 * math.tan(math.radians(30)))

    def test_recommended_clearance_no_warning(self):
        for size in sng.SIZES:
            c = sng.RECOMMENDED_C_INT[size]
            e, w = sng.validate('both', size, 'Allen', 25, c, 0.0)
            self.assertEqual((e, w), ([], []), (size, c, e, w))

    def test_partial_thread(self):
        self.assertEqual(sng.validate('bolt', 'M8', 'Allen', 40, 0.15, 0, 20)[0], [])
        self.assertTrue(sng.is_partial_thread('M8', 'Allen', 40, 20))
        self.assertFalse(sng.is_partial_thread('M8', 'Allen', 40, 0))
        self.assertTrue(sng.validate('bolt', 'M8', 'Allen', 40, 0.15, 0, 2)[0])   # < 3P
        self.assertTrue(sng.validate('bolt', 'M8', 'Allen', 40, 0.15, 0, -1)[0])
        e, w = sng.validate('bolt', 'M8', 'Allen', 40, 0.15, 0, 45)  # >= shank -> full
        self.assertEqual(e, [])
        self.assertTrue(w)
        self.assertFalse(sng.is_partial_thread('M8', 'Allen', 40, 45))
        # CSK: shank below head = L - k
        self.assertFalse(sng.is_partial_thread('M8', 'CSK', 25, 21))

    def test_bed_relief(self):
        for size in sng.SIZES:
            r, h = sng.bed_relief_size(size)
            d = sng.nominal_diameter(size)
            self.assertGreaterEqual(r, d / 2.0 + 0.3 - 1e-9)
            self.assertLess(r, sng.NUT[size]['s'] / 2.0)  # inside the hexagon
            self.assertGreater(h, 0.2 - 1e-9)
            self.assertLess(h, 0.25 * sng.NUT[size]['m'])
        self.assertAlmostEqual(sng.bed_relief_size('M8')[0], 4.35)
        self.assertAlmostEqual(sng.bed_relief_size('M12')[0], 6.45)
        self.assertAlmostEqual(sng.bed_relief_size('M8')[1], 0.4)
        self.assertAlmostEqual(sng.bed_relief_size('M3')[1], 0.24)

    def test_chamfer_sizes(self):
        self.assertAlmostEqual(sng.bed_chamfer_size(5.5), 0.275)
        self.assertEqual(sng.bed_chamfer_size(3.0), 0.2)
        self.assertEqual(sng.bed_chamfer_size(30.0), 0.5)
        for size in sng.SIZES:
            for head in ('Allen', 'Button', 'CSK'):
                ss = sng.HEAD[head][size]['ss']
                self.assertLess(sng.socket_chamfer_size(ss), ss / 4)

    def test_settings_roundtrip(self):
        import tempfile
        path = os.path.join(tempfile.mkdtemp(), 's.json')
        self.assertEqual(sng.load_settings(path), sng.DEFAULT_SETTINGS)  # missing file
        st = {'target': 'nut', 'size': 'M3', 'head': 'CSK', 'length': 12.0,
              'thread_len': 0.0, 'c_int': 0.12, 'c_ext': 0.05, 'overhang': 0.1}
        sng.save_settings(path, st)
        self.assertEqual(sng.load_settings(path), st)
        with open(path, 'w') as f:
            f.write('{broken')
        self.assertEqual(sng.load_settings(path), sng.DEFAULT_SETTINGS)
        with open(path, 'w') as f:
            f.write('{"size": "M99", "head": "X", "length": "abc"}')
        self.assertEqual(sng.load_settings(path), sng.DEFAULT_SETTINGS)

    def test_overhang(self):
        # table complete and recommended values validate without error for every size
        for size in sng.SIZES:
            self.assertIn(size, sng.RECOMMENDED_OVERHANG)
            e, _ = sng.validate('both', size, 'Allen', 25, sng.RECOMMENDED_C_INT[size], 0.0,
                                0.0, sng.RECOMMENDED_OVERHANG[size])
            self.assertEqual(e, [], (size, e))
        self.assertTrue(sng.validate('nut', 'M8', 'Allen', 25, 0.2, 0, 0, -0.1)[0])  # negative
        self.assertTrue(sng.validate('nut', 'M8', 'Allen', 25, 0.2, 0, 0, 0.7)[0])   # out of range
        self.assertTrue(sng.validate('nut', 'M3', 'Allen', 25, 0.1, 0, 0, 0.3)[0])   # >= P/2 (M3 P=0.5)
        e, w = sng.validate('nut', 'M8', 'Allen', 25, 0.5, 0, 0, 0.45)  # 0.5 + 0.26 = 1.12 x H1 0.677 -> warning
        self.assertEqual(e, [])
        self.assertTrue(any('張り出し' in x for x in w))
        # combinations that fit in the print tests must pass silently
        for size, c, o in (('M3', 0.15, 0.0), ('M5', 0.2, 0.0), ('M8', 0.5, 0.3), ('M8', 0.55, 0.3), ('M10', 0.55, 0.3), ('M12', 0.5, 0.3)):
            self.assertEqual(sng.validate('both', size, 'Allen', 25, c, 0.0, 0.0, o), ([], []), size)
        self.assertAlmostEqual(sng.radial_equivalent_of_axial(0.1), 0.1 / math.tan(math.radians(30)))
        self.assertAlmostEqual(sng.face_offset_for_axial_shift(0.2), 0.2 * math.cos(math.radians(30)))

    def test_names(self):
        self.assertEqual(sng.component_names('M8', 'Allen', 25), ('M8x25_Allen', 'Nut_M8'))
        self.assertEqual(sng.component_names('M2.5', 'Hex', 12.5)[0], 'M2.5x12.5_Hex')


if __name__ == '__main__':
    # Print the M3/M8/M20 x 4 heads table for visual review
    print('%-5s %-7s %6s %6s %6s %6s  std  bolt(D x H @L=25)' % ('size', 'head', 's/dk', 'k', 'ss', 't'))
    for size in CHECK_SIZES:
        for head in sng.HEAD_TYPES:
            h = sng.HEAD[head][size]
            od, th = sng.bolt_expected_size(size, head, 25)
            print('%-5s %-7s %6.2f %6.2f %6s %6s  %-4s %.2f x %.2f' % (
                size, head, h.get('s', h.get('dk')), h['k'],
                h.get('ss', '-'), h.get('t', '-'), 'Y' if h['std'] else 'est', od, th))
        n = sng.NUT[size]
        print('%-5s %-7s %6.2f %6.2f   P=%.2f D1=%.3f H1=%.3f' % (
            size, 'Nut', n['s'], n['m'], sng.PITCH[size],
            sng.internal_minor_diameter(size), sng.thread_engagement_height(sng.PITCH[size])))
    print()
    unittest.main(verbosity=2)
